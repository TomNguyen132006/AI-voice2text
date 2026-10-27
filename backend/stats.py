"""Per-job numbers for the stats panel and the Devpost write-up (S8-2): "measure, don't claim".

call_stats(job_id)  reads the model-call log (llm.py writes one JSONL row per HTTP attempt: job, stage, model, tokens, ms)
                    and sums it per stage and per model role. pipeline.py saves the result as jobs/{id}/call_stats.json when a
                    job ends, so the numbers survive a restart or a new server instance (the log file itself is local).
job_stats(job_id)   what GET /jobs/{id}/stats returns: those call numbers + seconds per stage (pipeline_report.json)
                    + the judge: verdicts of the first round, the rejection reasons, what the fix loop did (judge_report.json).
A cost of null in the log is UNKNOWN, never zero: the sums say "cost_is_lower_bound" when any attempt had no cost.
"""
import json

import llm
from storage import job_key, load_json

STAGE_ORDER = [
    "cleaning", "topic_split", "gap_finder", "notes_writer", "judge", "fixer", "slide_writer",
]
MAX_REJECTIONS_SHOWN = 20


def _empty() -> dict:
    return {"calls": 0, "failed_calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0,
            "latency_ms": 0, "est_cost_usd": 0.0, "unknown_cost_calls": 0}


def _add(total: dict, row: dict) -> None:
    total["calls"] += 1
    if row.get("status") not in ("ok", "truncated"):
        total["failed_calls"] += 1
    for key in ("prompt_tokens", "completion_tokens", "reasoning_tokens"):
        total[key] += row.get(key) or 0
    total["latency_ms"] += row.get("latency_ms") or 0
    if row.get("est_cost_usd") is None:
        total["unknown_cost_calls"] += 1
    else:
        total["est_cost_usd"] += row["est_cost_usd"]


def call_stats(job_id: str, path=None) -> dict:
    """Sums over the call log rows of one job: per stage, per role, and in total."""
    by_stage: dict[str, dict] = {}
    by_role: dict[str, dict] = {}
    total = _empty()
    damaged = 0
    path = path or llm.log_path()
    if path.is_file():
        for raw in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                damaged += 1
                continue
            if row.get("job_id") != job_id:
                continue
            for table, key in ((by_stage, row.get("stage") or "?"), (by_role, row.get("role") or "?")):
                _add(table.setdefault(key, {**_empty(), "model_id": row.get("model_id")}), row)
            _add(total, row)
    ordered = {s: by_stage[s] for s in STAGE_ORDER if s in by_stage}
    ordered.update({s: v for s, v in by_stage.items() if s not in ordered})
    for table in (ordered, by_role, {"total": total}):
        for item in table.values():
            item["cost_is_lower_bound"] = item["unknown_cost_calls"] > 0
    return {"by_stage": ordered, "by_role": by_role, "total": total, "damaged_lines": damaged}


def _optional(job_id: str, name: str, storage, default):
    try:
        return load_json(job_key(job_id, name), storage)
    except FileNotFoundError:
        return default


def judge_stats(report: dict) -> dict:
    """The judge part of judge_report.json, shaped for the panel."""
    if not report:
        return {}
    rejections = report.get("rejections", [])
    by_verdict = {k: v for k, v in report.get("counts", {}).items() if v and k != "pass"}
    fix = report.get("fix", {})
    return {
        "statements": report.get("statement_count"), "passed_first_time": report.get("counts", {}).get("pass"),
        "rejected_by_verdict": by_verdict, "rejected_by_code": report.get("rejected_by_code"),
        "sent_to_judge": report.get("sent_to_judge"),
        "rejections": [{k: r[k] for k in ("statement_id", "verdict", "reason", "by")} for r in rejections[:MAX_REJECTIONS_SHOWN]],
        "more_rejections": max(0, len(rejections) - MAX_REJECTIONS_SHOWN),
        "fix_attempted": fix.get("attempted"), "fixed": fix.get("fixed"),
        "final": report.get("final", {}),
        "flagged_sections": report.get("flagged", []),
    }


def job_stats(job_id: str, storage=None) -> dict:
    """Everything the stats panel shows. {"available": False} when the job has no reports (e.g. the sample job)."""
    pipeline_report = _optional(job_id, "pipeline_report.json", storage, {})
    if not pipeline_report:
        return {"available": False}
    calls = _optional(job_id, "call_stats.json", storage, None) or call_stats(job_id)
    return {
        "available": True,
        "total_seconds": pipeline_report.get("total_seconds"),
        "seconds_per_stage": pipeline_report.get("seconds_per_stage", {}),
        "warnings": pipeline_report.get("warnings", []),
        "calls": calls,
        "judge": judge_stats(_optional(job_id, "judge_report.json", storage, {})),
        "search": _optional(job_id, "search_report.json", storage, {}),
    }
