"""Tests for validate.py (S4-3). Fake client only: no network, no keys."""
import json

import httpx2 as httpx  # openai 3.x ships httpx2, not httpx
import openai
import pytest
import pydantic

import llm
from schemas import StatementDraft
from tests.test_clean import FakeClient, make_response
from validate import ValidationProblem, call_validated, parse_json_list, parse_json_object

REQUEST = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
MESSAGES = [{"role": "system", "content": "sys"}, {"role": "user", "content": "q"}]
GOOD = [{"id": "st_1", "section_id": "sec_01", "text": "t", "sources": [{"type": "lecture", "segment_id": "seg_0001"}]}]


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "_sleep", lambda s: None)
    monkeypatch.setenv("LLM_LOG_PATH", str(tmp_path / "calls.jsonl"))


def parse(text):
    """A typical parse_fn: JSON list -> StatementDraft objects."""
    try:
        return [StatementDraft(**item) for item in parse_json_list(text)]
    except pydantic.ValidationError as error:
        raise ValidationProblem.from_pydantic(error) from None


def run(responder, **kw):
    client = FakeClient(responder)
    result = call_validated("super", MESSAGES, parse, job_id="job_v1", stage="t", max_tokens=1000, client=client, **kw)
    return result, client


def test_valid_first_time():
    r, client = run(lambda k, n: json.dumps(GOOD))
    assert r.ok and r.attempts == 1 and len(client.calls) == 1
    assert isinstance(r.value[0], StatementDraft) and r.error_kind is None
    assert r.prompt_tokens == 100 and r.completion_tokens == 200 and r.est_cost_usd > 0


def test_code_fence_is_stripped():
    r, _ = run(lambda k, n: "```json\n" + json.dumps(GOOD) + "\n```")
    assert r.ok and r.value[0].id == "st_1"


def test_invalid_json_then_valid_sums_cost():
    r, client = run(lambda k, n: "not json at all" if n == 1 else json.dumps(GOOD))
    assert r.ok and r.attempts == 2 and len(client.calls) == 2
    assert r.prompt_tokens == 200 and r.completion_tokens == 400 and r.calls == 2
    assert "Your last answer was invalid" in client.calls[1]["messages"][-1]["content"]
    assert client.calls[1]["messages"][:2] == MESSAGES


@pytest.mark.parametrize("bad, expect", [
    ([{"id": "st_1", "section_id": "sec_01", "sources": []}], "text"),  # missing field
    ([{"id": 5, "section_id": "sec_01", "text": "t"}], "id"),  # wrong type
    ([{"id": "st_1", "section_id": "sec_01", "text": "t", "sources": [{"type": "video", "x": 1}]}], "sources"),
])
def test_schema_failure_then_valid(bad, expect):
    r, client = run(lambda k, n: json.dumps(bad) if n == 1 else json.dumps(GOOD))
    assert r.ok and r.attempts == 2
    assert expect in client.calls[1]["messages"][-1]["content"]  # the field path is in the retry message


def test_invalid_twice_returns_failed_result_and_does_not_raise():
    r, client = run(lambda k, n: "nope")
    assert not r.ok and r.value is None and r.error_kind == "invalid"
    assert r.attempts == 2 and len(client.calls) == 2 and r.prompt_tokens == 200
    assert r.error_message and len(r.steps) == 2


def test_truncated_then_valid_doubles_max_tokens():
    r, client = run(lambda k, n: make_response("[{", finish="length") if n == 1 else json.dumps(GOOD))
    assert r.ok and r.attempts == 2
    assert [c["max_tokens"] for c in client.calls] == [1000, 2000]
    assert client.calls[1]["messages"] == MESSAGES  # nothing appended for a cut-off answer


def test_truncated_twice_fails_with_kind():
    r, _ = run(lambda k, n: make_response("", finish="length"))
    assert not r.ok and r.error_kind == "truncated"


def test_empty_answer_is_retried_then_failed():
    r, client = run(lambda k, n: "   ")
    assert not r.ok and r.error_kind == "empty" and len(client.calls) == 2


def test_api_error_becomes_failed_result():
    def boom(k, n):
        raise openai.APIStatusError("bad", response=httpx.Response(400, request=REQUEST), body=None)

    r, client = run(boom)
    assert not r.ok and r.error_kind == "api_error" and r.cost_is_lower_bound
    assert len(client.calls) == 1 and r.calls == 1


def test_api_error_after_retries_keeps_attempts():
    def down(k, n):
        raise openai.APIStatusError("down", response=httpx.Response(503, request=REQUEST), body=None)

    r, client = run(down)
    assert not r.ok and r.error_kind == "api_error" and r.calls == len(client.calls) == 4


def test_retry_message_is_short_and_has_no_keys_or_raw_data(monkeypatch):
    secret = "tvly-SECRETSECRETSECRET1234"
    monkeypatch.setenv("TAVILY_API_KEY", secret)
    huge = "X" * 5000
    bad = [{"id": f"st_{i}", "section_id": "sec_01", "text": huge, "sources": [{"type": "web", "url": secret}], "extra": 1}
           for i in range(10)]
    bad.append({"id": "st_x", "text": secret + huge})  # missing section_id
    r, client = run(lambda k, n: json.dumps(bad) if n == 1 else json.dumps(GOOD))
    msg = client.calls[1]["messages"][-1]["content"]
    assert r.ok and len(msg) < 600
    assert secret not in msg and huge not in msg and "XXXXXXXX" not in msg


def test_at_most_three_problems_with_paths():
    problem = ValidationProblem([f"item.{i}.text: missing" for i in range(7)])
    assert len(problem.problems) == 4 and problem.problems[-1] == "(+4 more)"
    assert problem.problems[0] == "item.0.text: missing"
    long = ValidationProblem("y" * 1000)
    assert len(str(long)) <= 120


def test_parser_bug_does_not_crash_the_pipeline():
    client = FakeClient(lambda k, n: "[]")
    r = call_validated("super", MESSAGES, lambda text: 1 / 0, job_id="job_v1", stage="t", max_tokens=10, client=client)
    assert not r.ok and r.error_kind == "invalid" and "ZeroDivisionError" in r.error_message


def test_parse_json_object():
    assert parse_json_object('Here: {"a": [1]} done') == {"a": [1]}
    for bad in ("no braces", "{broken", "{}}{"):
        with pytest.raises(ValidationProblem):
            parse_json_object(bad)
