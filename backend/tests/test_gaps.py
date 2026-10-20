"""Tests for gaps.py (S3-1). Fake client only: no network, no keys."""
import json

import httpx2 as httpx  # openai 3.x ships httpx2, not httpx
import openai
import pytest

import gaps
import llm
from schemas import Section, Segment
from storage import LocalStorage, job_key, load_json, save_json
from tests.test_clean import FakeClient, make_response, payload_of

TEXTS = [
    "The Hessian matrix holds second derivatives.",
    "Condition number is lambda max over lambda min.",
    "Steepest descent follows the gradient.",
    "Other section talks about eigenvalues only.",
]
SEGS = [Segment(id=f"seg_{i:04d}", start=i * 10.0, end=i * 10.0 + 9.5, text=t) for i, t in enumerate(TEXTS)]
SECS = [
    Section(id="sec_01", title="Hessian Basics", start=0.0, end=20.0, segment_ids=["seg_0000", "seg_0001"]),
    Section(id="sec_02", title="Descent", start=20.0, end=39.5, segment_ids=["seg_0002", "seg_0003"]),
]


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "_sleep", lambda s: None)
    monkeypatch.setenv("LLM_LOG_PATH", str(tmp_path / "calls.jsonl"))


def item(term, section_id="sec_01", reason="A beginner needs this."):
    return {"section_id": section_id, "term": term, "reason": reason}


def one(responder, section=SECS[0]):
    segs = [s for s in SEGS if s.id in section.segment_ids]
    client = FakeClient(responder)
    return gaps.gaps_for_section(section, segs, job_id="job_g1", client=client), client


def reply(*items):
    return json.dumps(list(items))


def test_valid_answer():
    r, client = one(lambda k, n: reply(item("Hessian matrix"), item("condition number")))
    assert [i["term"] for i in r.items] == ["Hessian matrix", "condition number"]
    assert r.info["flagged"] is None and r.info["dropped"] == [] and len(client.calls) == 1
    assert client.calls[0]["model"] == "nvidia/nemotron-3-super-120b-a12b"
    assert client.calls[0]["max_tokens"] == gaps.MAX_TOKENS


def test_invalid_json_then_valid():
    r, client = one(lambda k, n: "not json" if n == 1 else reply(item("Hessian")))
    assert [i["term"] for i in r.items] == ["Hessian"]
    assert len(client.calls) == 2 and r.info["flagged"] is None
    assert "rejected" in client.calls[1]["messages"][-1]["content"]


def test_invalid_twice_gives_empty_and_flag():
    r, client = one(lambda k, n: "still not json")
    assert r.items == [] and r.info["flagged"] == "invalid_reply" and len(client.calls) == 2
    assert gaps.build_result("job_g1", [r]).report["flagged"] == [{"section_id": "sec_01", "reason": "invalid_reply"}]


def test_truncated_retry_doubles_max_tokens():
    def responder(k, n):
        return make_response("", finish="length") if n == 1 else reply(item("Hessian"))

    r, client = one(responder)
    assert [c["max_tokens"] for c in client.calls] == [gaps.MAX_TOKENS, gaps.MAX_TOKENS * 2]
    assert len(r.items) == 1 and r.info["flagged"] is None


def test_term_not_in_section_is_dropped():
    # "eigenvalues" is in sec_02's text, "Jacobian" nowhere, "Hessian inverse": "inverse" is missing
    r, _ = one(lambda k, n: reply(item("eigenvalues"), item("Jacobian"), item("Hessian inverse"), item("Hessian")))
    assert [i["term"] for i in r.items] == ["Hessian"]
    reasons = {d["term"]: d["reason"] for d in r.info["dropped"]}
    assert reasons["Jacobian"].startswith("term_not_in_section") and "inverse" in reasons["Hessian inverse"]
    assert set(reasons) == {"eigenvalues", "Jacobian", "Hessian inverse"}


def test_term_match_is_case_insensitive():
    r, _ = one(lambda k, n: reply(item("HESSIAN Matrix")))
    assert len(r.items) == 1


def test_too_many_are_cut_to_the_maximum_keeping_the_first():
    words = ["hessian", "matrix", "second", "derivatives", "condition", "number", "lambda"]
    r, _ = one(lambda k, n: reply(*[item(w) for w in words]))
    assert [i["term"] for i in r.items] == words[: gaps.GAPS_MAX_PER_SECTION]
    over = [d for d in r.info["dropped"] if d["reason"] == "over_max"]
    assert [d["term"] for d in over] == words[gaps.GAPS_MAX_PER_SECTION:]


def test_duplicate_terms_case_insensitive():
    r, _ = one(lambda k, n: reply(item("Hessian"), item("hessian"), item(" HESSIAN ")))
    assert len(r.items) == 1
    assert [d["reason"] for d in r.info["dropped"]] == ["duplicate", "duplicate"]


def test_wrong_section_id_is_dropped():
    r, _ = one(lambda k, n: reply(item("Hessian", "sec_02"), item("condition number")))
    assert [i["term"] for i in r.items] == ["condition number"]
    assert r.info["dropped"][0]["reason"].startswith("wrong_section_id")


def test_missing_reason_is_dropped():
    r, _ = one(lambda k, n: reply({"section_id": "sec_01", "term": "Hessian"}, item("lambda")))
    assert [i["term"] for i in r.items] == ["lambda"]
    assert r.info["dropped"][0]["reason"] == "missing_term_or_reason"


def test_empty_list_is_fine_and_not_flagged():
    r, client = one(lambda k, n: "[]")
    assert r.items == [] and r.info["flagged"] is None and len(client.calls) == 1


def test_reply_with_text_around_the_list_is_parsed():
    r, _ = one(lambda k, n: "Here you go:\n" + reply(item("Hessian")))
    assert len(r.items) == 1


def test_llm_error_gives_empty_and_flag():
    def responder(k, n):
        request = httpx.Request("POST", "http://x")  # 400 is not retried
        raise openai.BadRequestError("bad", response=httpx.Response(400, request=request), body=None)

    r, _ = one(responder)
    assert r.items == [] and r.info["flagged"] == "llm_error"


def test_each_call_sees_only_its_own_section():
    seen = {}

    def responder(k, n):
        p = payload_of(k)
        seen[p["section_id"]] = p
        return "[]"

    result = gaps.find_gaps(SEGS, SECS, job_id="job_g1", client=FakeClient(responder))
    assert result.items == []
    assert [s["id"] for s in seen["sec_01"]["segments"]] == ["seg_0000", "seg_0001"]
    assert [s["id"] for s in seen["sec_02"]["segments"]] == ["seg_0002", "seg_0003"]
    assert seen["sec_01"]["title"] == "Hessian Basics"
    assert "eigenvalues" not in json.dumps(seen["sec_01"])
    assert "Hessian" not in json.dumps(seen["sec_02"])


def test_gaps_job_saves_files_and_report_numbers(tmp_path):
    storage = LocalStorage(tmp_path / "st")
    save_json(job_key("job_g2", "transcript_clean.json"), [s.model_dump() for s in SEGS], storage)
    save_json(job_key("job_g2", "sections.json"), [s.model_dump() for s in SECS], storage)

    def responder(k, n):
        sid = payload_of(k)["section_id"]
        return reply(item("Hessian", sid), item("nonsense", sid)) if sid == "sec_01" else "[]"

    result = gaps.gaps_job("job_g2", storage, FakeClient(responder))
    saved = load_json(job_key("job_g2", "gaps.json"), storage)
    report = load_json(job_key("job_g2", "gaps_report.json"), storage)
    assert saved == result.items and [g["term"] for g in saved] == ["Hessian"]
    assert report["calls"] == 2 and report["gap_count"] == 1
    assert report["prompt_tokens"] == 200 and report["completion_tokens"] == 400
    assert report["est_cost_usd"] > 0 and report["dropped"][0]["section_id"] == "sec_01"


def test_no_sections_makes_no_call():
    result = gaps.find_gaps(SEGS, [], job_id="job_g1", client=FakeClient(lambda k, n: 1 / 0))
    assert result.items == [] and result.report["calls"] == 0
