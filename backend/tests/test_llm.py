"""Tests for llm.py (S2-1 T3-T5). Fake client only: no network, no keys."""
import json
from types import SimpleNamespace

import httpx2 as httpx  # openai 3.x ships httpx2, not httpx
import openai
import pytest

import llm
import llm_config

REQUEST = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
MESSAGES = [{"role": "user", "content": "SECRET PROMPT TEXT"}]


def make_response(content="hello", finish="stop", prompt=27, completion=40, reasoning=10):
    details = SimpleNamespace(reasoning_tokens=reasoning)
    usage = SimpleNamespace(
        prompt_tokens=prompt, completion_tokens=completion, completion_tokens_details=details
    )
    choice = SimpleNamespace(
        message=SimpleNamespace(content=content), finish_reason=finish
    )
    return SimpleNamespace(choices=[choice], usage=usage)


def status_error(cls, code, headers=None):
    response = httpx.Response(code, headers=headers or {}, request=REQUEST)
    return cls(f"http {code}", response=response, body=None)


class FakeClient:
    """Plays a script: each item is an exception (raised) or a response (returned)."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """No real sleeping, and the call log goes to a temp file."""
    sleeps = []
    monkeypatch.setattr(llm, "_sleep", sleeps.append)
    log = tmp_path / "calls.jsonl"
    monkeypatch.setenv("LLM_LOG_PATH", str(log))
    return SimpleNamespace(sleeps=sleeps, log=log)


def run(client, role="super", **kwargs):
    return llm.call_model(
        role, MESSAGES, job_id="job_t1", stage="cleaning", max_tokens=100, client=client, **kwargs
    )


def log_lines(isolated):
    return [json.loads(line) for line in isolated.log.read_text(encoding="utf-8").splitlines()]


# ---------- cost formula ----------

def test_cost_matches_observed_super_call_and_reasoning_is_not_added_twice():
    # Observed call (Oct 17): prompt 27, completion 40, reasoning 40 -> total 67.
    cost = llm.estimate_cost("super", prompt_tokens=27, completion_tokens=40)
    assert cost == pytest.approx(27 * 0.30 / 1e6 + 40 * 0.90 / 1e6)
    assert cost == pytest.approx(4.41e-5)


# ---------- success path ----------

def test_success_returns_result_and_sends_config_values():
    client = FakeClient([make_response(content="hi")])
    result = run(client)

    assert result.text == "hi"
    assert result.finish_reason == "stop" and result.truncated is False
    assert result.prompt_tokens == 27 and result.completion_tokens == 40
    assert result.reasoning_tokens == 10
    assert result.attempts == 1
    assert result.model_id == llm_config.ROLES["super"].model_id
    sent = client.calls[0]
    assert sent["model"] == llm_config.ROLES["super"].model_id
    assert sent["max_tokens"] == 100
    assert sent["timeout"] == llm_config.timeout_for("super")


def test_none_content_becomes_empty_text():
    client = FakeClient([make_response(content=None, finish="length", completion=40, reasoning=40)])
    assert run(client).text == ""


def test_unknown_role_fails_before_any_call():
    client = FakeClient([])
    with pytest.raises(ValueError):
        run(client, role="mega")
    assert client.calls == []


# ---------- truncation ----------

def test_finish_reason_length_is_flagged_and_not_retried(isolated):
    client = FakeClient([make_response(content=None, finish="length")])
    result = run(client)

    assert result.truncated is True and result.finish_reason == "length"
    assert len(client.calls) == 1
    assert log_lines(isolated)[0]["status"] == "truncated"


# ---------- retries ----------

@pytest.mark.parametrize(
    "error",
    [
        openai.APITimeoutError(request=REQUEST),
        openai.APIConnectionError(request=REQUEST),
        status_error(openai.InternalServerError, 500),
        status_error(openai.InternalServerError, 503),
        status_error(openai.RateLimitError, 429),
    ],
    ids=["timeout", "connection", "500", "503", "429"],
)
def test_retryable_error_then_success(error):
    client = FakeClient([error, make_response()])
    result = run(client)

    assert result.attempts == 2 and len(client.calls) == 2


def test_gives_up_after_three_retries_with_four_calls(isolated):
    errors = [status_error(openai.InternalServerError, 502) for _ in range(4)]
    client = FakeClient(errors)

    with pytest.raises(llm.LLMError) as caught:
        run(client)

    assert len(client.calls) == 4
    assert caught.value.attempts == 4 and caught.value.status_code == 502
    assert len(isolated.sleeps) == 3


@pytest.mark.parametrize("code, cls", [
    (400, openai.BadRequestError),
    (401, openai.AuthenticationError),
    (404, openai.NotFoundError),
    (422, openai.UnprocessableEntityError),
])
def test_other_4xx_is_not_retried(code, cls):
    client = FakeClient([status_error(cls, code), make_response()])

    with pytest.raises(llm.LLMError) as caught:
        run(client)

    assert len(client.calls) == 1
    assert caught.value.status_code == code and caught.value.attempts == 1


def test_retry_after_header_is_honored(isolated):
    err = status_error(openai.RateLimitError, 429, {"retry-after": "7"})
    run(FakeClient([err, make_response()]))
    assert isolated.sleeps == [7.0]


def test_retry_after_is_capped(isolated):
    err = status_error(openai.RateLimitError, 429, {"retry-after": "9999"})
    run(FakeClient([err, make_response()]))
    assert isolated.sleeps == [llm_config.RETRY_AFTER_CAP_SEC]


def test_backoff_grows_without_retry_after(isolated):
    errors = [openai.APITimeoutError(request=REQUEST)] * 3
    run(FakeClient([*errors, make_response()]))
    base = llm_config.RETRY_BACKOFF_BASE_SEC
    assert isolated.sleeps == [base, base * 2, base * 4]


def test_unreadable_retry_after_falls_back_to_backoff(isolated):
    err = status_error(openai.RateLimitError, 429, {"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"})
    run(FakeClient([err, make_response()]))
    assert isolated.sleeps == [llm_config.RETRY_BACKOFF_BASE_SEC]


def test_client_is_built_with_no_hidden_retries(monkeypatch):
    seen = {}

    class Spy:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setenv("NEBIUS_API_KEY", "test-key-not-real")
    monkeypatch.setattr(llm, "OpenAI", Spy)
    llm.make_client()
    assert seen["max_retries"] == 0
    assert seen["base_url"] == llm_config.BASE_URL


# ---------- call log ----------

def test_log_has_one_line_per_attempt_including_failures(isolated):
    err = status_error(openai.InternalServerError, 500)
    run(FakeClient([err, make_response(prompt=27, completion=40, reasoning=40)]))

    first, second = log_lines(isolated)
    assert first["attempt"] == 1 and first["status"] == "http_500"
    assert first["prompt_tokens"] is None and first["est_cost_usd"] is None
    assert second["attempt"] == 2 and second["status"] == "ok"
    assert second["prompt_tokens"] == 27 and second["completion_tokens"] == 40
    assert second["reasoning_tokens"] == 40
    assert second["est_cost_usd"] == pytest.approx(4.41e-5)


def test_log_has_exactly_the_agreed_fields(isolated):
    run(FakeClient([make_response()]))
    (line,) = log_lines(isolated)

    assert set(line) == {
        "ts", "job_id", "stage", "role", "model_id", "attempt", "status", "latency_ms",
        "prompt_tokens", "completion_tokens", "reasoning_tokens", "est_cost_usd",
    }
    assert line["job_id"] == "job_t1" and line["stage"] == "cleaning" and line["role"] == "super"
    assert isinstance(line["latency_ms"], int)


def test_timeout_and_connection_statuses(isolated):
    run(FakeClient([
        openai.APITimeoutError(request=REQUEST),
        openai.APIConnectionError(request=REQUEST),
        make_response(),
    ]))
    assert [l["status"] for l in log_lines(isolated)] == ["timeout", "connection_error", "ok"]


def test_log_never_contains_key_prompt_or_response(isolated, monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "sk-super-secret-value")
    run(FakeClient([make_response(content="SECRET RESPONSE TEXT")]))
    raw = isolated.log.read_text(encoding="utf-8")

    assert "sk-super-secret-value" not in raw
    assert "SECRET PROMPT TEXT" not in raw
    assert "SECRET RESPONSE TEXT" not in raw


def test_log_path_defaults_inside_ignored_data_folder(monkeypatch):
    monkeypatch.delenv("LLM_LOG_PATH")
    path = llm.log_path()
    assert path.parts[-3:] == (".data", "logs", "calls.jsonl")
    assert path.parent.parent.parent.name == "backend"


def test_log_write_failure_does_not_break_the_call(monkeypatch, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setenv("LLM_LOG_PATH", str(blocker / "sub" / "calls.jsonl"))
    assert run(FakeClient([make_response()])).text == "hello"


# ---------- log summary ----------

def write_log(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_summary_counts_statuses_and_sums_known_costs(isolated):
    write_log(isolated.log, [
        {"status": "ok", "est_cost_usd": 0.001},
        {"status": "ok", "est_cost_usd": 0.002},
        {"status": "truncated", "est_cost_usd": 0.0005},
    ])
    summary = llm.summarize_log()

    assert summary["total_calls"] == 3
    assert summary["by_status"] == {"ok": 2, "truncated": 1}
    assert summary["total_est_cost_usd"] == pytest.approx(0.0035)
    assert summary["unknown_cost_attempts"] == 0
    assert summary["cost_is_lower_bound"] is False
    assert "lower bound" not in llm.format_summary(summary)


def test_summary_treats_null_cost_as_unknown_not_zero(isolated):
    write_log(isolated.log, [
        {"status": "ok", "est_cost_usd": 0.001},
        {"status": "http_500", "est_cost_usd": None},
        {"status": "timeout", "est_cost_usd": None},
    ])
    summary = llm.summarize_log()

    assert summary["total_est_cost_usd"] == pytest.approx(0.001)
    assert summary["unknown_cost_attempts"] == 2
    assert summary["cost_is_lower_bound"] is True
    text = llm.format_summary(summary)
    assert "lower bound" in text and "2 attempt(s) with unknown cost" in text


def test_summary_of_missing_log_is_empty(isolated):
    summary = llm.summarize_log()
    assert summary["total_calls"] == 0 and summary["total_est_cost_usd"] == 0.0


def test_summary_skips_damaged_lines(isolated):
    isolated.log.write_text('{"status": "ok", "est_cost_usd": 0.1}\nnot json\n', encoding="utf-8")
    summary = llm.summarize_log()
    assert summary["total_calls"] == 1 and summary["damaged_lines"] == 1
