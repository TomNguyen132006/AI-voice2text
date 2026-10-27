"""Tests for stats.py (S8-2). No network."""
import json

import stats
from storage import LocalStorage, job_key, save_json


def row(job, stage, role="super", status="ok", prompt=100, completion=50, ms=1000, cost=0.001):
    return {"job_id": job, "stage": stage, "role": role, "model_id": f"m-{role}", "status": status, "latency_ms": ms,
            "prompt_tokens": prompt, "completion_tokens": completion, "reasoning_tokens": 10, "est_cost_usd": cost}


def write_log(tmp_path, rows):
    path = tmp_path / "calls.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n", encoding="utf-8")
    return path


def test_call_stats_sums_per_stage_and_role_for_one_job(tmp_path):
    path = write_log(tmp_path, [
        row("job_a", "notes_writer"), row("job_a", "notes_writer", ms=2000),
        row("job_a", "judge", role="ultra", cost=0.01),
        row("job_a", "judge", role="ultra", status="timeout", prompt=None, completion=None, cost=None),
        row("job_b", "notes_writer"),
    ])
    r = stats.call_stats("job_a", path)
    assert list(r["by_stage"]) == ["notes_writer", "judge"]  # pipeline order, other jobs left out
    n = r["by_stage"]["notes_writer"]
    assert (n["calls"], n["prompt_tokens"], n["completion_tokens"], n["latency_ms"]) == (2, 200, 100, 3000)
    j = r["by_stage"]["judge"]
    assert j["calls"] == 2 and j["failed_calls"] == 1 and j["cost_is_lower_bound"] and j["est_cost_usd"] == 0.01
    assert r["by_role"]["ultra"]["model_id"] == "m-ultra"
    assert r["total"]["calls"] == 4 and r["total"]["unknown_cost_calls"] == 1 and r["damaged_lines"] == 1


def test_call_stats_without_a_log(tmp_path):
    r = stats.call_stats("job_a", tmp_path / "missing.jsonl")
    assert r["by_stage"] == {} and r["total"]["calls"] == 0 and not r["total"]["cost_is_lower_bound"]


def test_judge_stats_shapes_the_report():
    report = {"statement_count": 5, "counts": {"pass": 3, "unsupported": 1, "no_source": 1, "unjudged": 0},
              "rejected_by_code": 1, "sent_to_judge": 4,
              "rejections": [{"statement_id": f"st_{i}", "verdict": "unsupported", "reason": "x", "by": "ultra", "extra": 1} for i in range(25)],
              "fix": {"attempted": 1, "fixed": 1}, "final": {"kept": 4}}
    j = stats.judge_stats(report)
    assert j["rejected_by_verdict"] == {"unsupported": 1, "no_source": 1} and j["passed_first_time"] == 3
    assert len(j["rejections"]) == stats.MAX_REJECTIONS_SHOWN and j["more_rejections"] == 5
    assert "extra" not in j["rejections"][0] and j["fixed"] == 1
    assert stats.judge_stats({}) == {}


def test_job_stats(tmp_path, monkeypatch):
    storage = LocalStorage(tmp_path / "data")
    assert stats.job_stats("job_s", storage) == {"available": False}
    monkeypatch.setenv("LLM_LOG_PATH", str(write_log(tmp_path, [row("job_s", "judge", role="ultra")])))
    save_json(job_key("job_s", "pipeline_report.json"), {"total_seconds": 9.5, "seconds_per_stage": {"judging": 4.0}, "warnings": ["w"]}, storage)
    save_json(job_key("job_s", "judge_report.json"), {"statement_count": 1, "counts": {"pass": 1}}, storage)
    r = stats.job_stats("job_s", storage)  # no call_stats.json yet: computed from the log
    assert r["available"] and r["total_seconds"] == 9.5 and r["warnings"] == ["w"]
    assert r["calls"]["total"]["calls"] == 1 and r["judge"]["passed_first_time"] == 1 and r["search"] == {}
    save_json(job_key("job_s", "call_stats.json"), {"total": {"calls": 99}}, storage)  # the saved copy wins
    assert stats.job_stats("job_s", storage)["calls"]["total"]["calls"] == 99
