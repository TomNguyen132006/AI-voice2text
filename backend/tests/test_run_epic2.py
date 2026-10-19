"""Tests for run_epic2.py (end-to-end entry point). Fake client only: no network, no keys."""
import json

import pytest

import llm
import run_epic2
from storage import LocalStorage
from tests.test_clean import FakeClient, as_json, payload_of


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "_sleep", lambda s: None)
    monkeypatch.setenv("LLM_LOG_PATH", str(tmp_path / "calls.jsonl"))


def model(kwargs, n):
    user = payload_of(kwargs)
    if "duration_sec" in user:
        return json.dumps([{"title": "One", "first_segment_id": "seg_0000"}, {"title": "Two", "first_segment_id": "seg_0004"}])
    return as_json((s["id"], s["text"].replace("uh ", "")) for s in user["segments"])


def write_transcript(tmp_path, n=8):
    segs = [{"id": f"seg_{i:04d}", "start": i * 40.0, "end": i * 40.0 + 39.0, "text": f"uh word {i}"} for i in range(n)]
    path = tmp_path / "t.json"
    path.write_text(json.dumps(segs), encoding="utf-8")
    return str(path)


def test_run_cleans_splits_and_reports_cost_of_this_job_only(tmp_path):
    storage = LocalStorage(tmp_path / "store")
    other = {"job_id": "other_job", "status": "ok", "est_cost_usd": 5.0}
    llm.log_path().write_text(json.dumps(other) + "\n", encoding="utf-8")
    r = run_epic2.run(write_transcript(tmp_path), job_id="job_e2e_test", storage=storage, client=FakeClient(model))
    assert [s.title for s in r["sections"]] == ["One", "Two"]
    assert r["clean_report"]["changed_count"] == 8
    assert r["summary"]["total_calls"] == 2  # 1 clean batch + 1 topic call; "other_job" row not counted
    assert r["summary"]["total_est_cost_usd"] < 1.0
    text = run_epic2.format_result(r)
    assert "sec_01" in text and "One" in text and "cost of this job" in text


def test_summarize_log_filters_by_job_id(tmp_path):
    llm.log_path().write_text(
        json.dumps({"job_id": "a", "status": "ok", "est_cost_usd": 0.5}) + "\n"
        + json.dumps({"job_id": "b", "status": "ok", "est_cost_usd": 0.25}) + "\n", encoding="utf-8")
    assert llm.summarize_log(job_id="a")["total_est_cost_usd"] == pytest.approx(0.5)
    assert llm.summarize_log()["total_calls"] == 2


def test_main_needs_exactly_one_file(capsys):
    assert run_epic2.main([]) == 2
