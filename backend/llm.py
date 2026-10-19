"""One door to Nemotron on Token Factory (S2-1): call_model with retry and a call log.

Every pipeline stage calls call_model(role, messages, job_id=..., stage=..., max_tokens=...).
Model IDs, prices and timeouts come from llm_config.py. The key comes from NEBIUS_API_KEY.

Retries (up to llm_config.MAX_RETRIES, so up to 4 calls): timeout, connection error,
5xx and 429 (Retry-After honored, capped). Other 4xx fail at once. finish_reason "length"
is returned as truncated=True and is NOT retried (a retry would hit the same limit).

Call log: one JSON line per attempt in LLM_LOG_PATH (default backend/.data/logs/calls.jsonl).
It holds numbers and ids only: no API key, no prompt, no response text.
"""
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import openai
from openai import OpenAI

import llm_config

DEFAULT_LOG_PATH = Path(__file__).parent / ".data" / "logs" / "calls.jsonl"

_sleep = time.sleep  # tests replace this so they do not really wait


class LLMError(Exception):
    """The call failed for good (non-retryable error, or retries used up)."""

    def __init__(self, message, *, status_code=None, attempts=1):
        super().__init__(message)
        self.status_code = status_code  # HTTP status, or None for timeout/connection
        self.attempts = attempts


@dataclass(frozen=True)
class LLMResult:
    text: str  # "" when the model returned no content (e.g. all tokens spent on reasoning)
    finish_reason: str | None
    truncated: bool  # finish_reason == "length": the answer may be cut off or empty
    prompt_tokens: int | None
    completion_tokens: int | None  # INCLUDES reasoning tokens
    reasoning_tokens: int | None
    est_cost_usd: float | None
    latency_ms: int
    attempts: int
    role: str
    model_id: str


def estimate_cost(role: str, prompt_tokens: int, completion_tokens: int) -> float:
    """USD estimate. completion_tokens already includes reasoning tokens: do not add them again.

    Observed Oct 17 (Super, max_tokens=40): prompt 27, completion 40, reasoning 40,
    total 67 = 27 + 40, finish_reason "length", content None. Cost = 27 * 0.30/1M + 40 * 0.90/1M.
    """
    cfg = llm_config.get_role(role)
    return (
        prompt_tokens * cfg.price_in_per_1m + completion_tokens * cfg.price_out_per_1m
    ) / 1_000_000


def make_client() -> OpenAI:
    # max_retries=0: the openai library must not retry on its own, call_model owns the retries
    # (otherwise attempts would be hidden from the call log and the count would be wrong).
    return OpenAI(
        base_url=llm_config.BASE_URL,
        api_key=os.getenv(llm_config.API_KEY_ENV),
        max_retries=0,
    )


def log_path() -> Path:
    override = os.getenv("LLM_LOG_PATH")
    return Path(override) if override else DEFAULT_LOG_PATH


def _write_log(line: dict) -> None:
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
    except OSError:
        pass  # a broken log must never break a paying call


def _retry_wait(error: Exception, retry_number: int) -> float:
    """Seconds to wait before retry number 1, 2, 3."""
    response = getattr(error, "response", None)
    if response is not None:
        try:
            seconds = float(response.headers.get("retry-after", ""))
        except ValueError:  # missing, or an HTTP date (not supported): use backoff
            seconds = None
        if seconds is not None and seconds >= 0:
            return min(seconds, llm_config.RETRY_AFTER_CAP_SEC)
    return min(
        llm_config.RETRY_BACKOFF_BASE_SEC * 2 ** (retry_number - 1),
        llm_config.RETRY_AFTER_CAP_SEC,
    )


def _classify(error: Exception) -> tuple[str, bool, int | None]:
    """(log status, retryable?, http status) for an openai exception."""
    if isinstance(error, openai.APITimeoutError):  # check first: it is a subclass of the next
        return "timeout", True, None
    if isinstance(error, openai.APIConnectionError):
        return "connection_error", True, None
    if isinstance(error, openai.APIStatusError):
        code = error.status_code
        return f"http_{code}", code == 429 or code >= 500, code
    raise error  # not an API problem (a bug): do not hide it


def call_model(
    role: str,
    messages: list[dict],
    *,
    job_id: str,
    stage: str,
    max_tokens: int,
    client=None,
    **extra,
) -> LLMResult:
    cfg = llm_config.get_role(role)  # unknown role fails here, before any call
    client = client or make_client()
    total_calls = llm_config.MAX_RETRIES + 1

    for attempt in range(1, total_calls + 1):
        started = time.perf_counter()
        base_line = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "job_id": job_id,
            "stage": stage,
            "role": role,
            "model_id": cfg.model_id,
            "attempt": attempt,
        }
        try:
            response = client.chat.completions.create(
                model=cfg.model_id,
                messages=messages,
                max_tokens=max_tokens,
                timeout=llm_config.timeout_for(role),
                **extra,
            )
        except Exception as error:
            latency_ms = round((time.perf_counter() - started) * 1000)
            status, retryable, code = _classify(error)
            _write_log({
                **base_line, "status": status, "latency_ms": latency_ms,
                "prompt_tokens": None, "completion_tokens": None,
                "reasoning_tokens": None, "est_cost_usd": None,
            })
            if not retryable or attempt == total_calls:
                raise LLMError(
                    f"{role} call failed after {attempt} attempt(s): {status}",
                    status_code=code, attempts=attempt,
                ) from error
            _sleep(_retry_wait(error, attempt))
            continue

        latency_ms = round((time.perf_counter() - started) * 1000)
        choice = response.choices[0]
        usage = response.usage
        prompt = getattr(usage, "prompt_tokens", None)
        completion = getattr(usage, "completion_tokens", None)
        details = getattr(usage, "completion_tokens_details", None)
        reasoning = getattr(details, "reasoning_tokens", None)
        cost = (
            estimate_cost(role, prompt, completion)
            if prompt is not None and completion is not None else None
        )
        truncated = choice.finish_reason == "length"
        _write_log({
            **base_line, "status": "truncated" if truncated else "ok",
            "latency_ms": latency_ms, "prompt_tokens": prompt,
            "completion_tokens": completion, "reasoning_tokens": reasoning,
            "est_cost_usd": cost,
        })
        return LLMResult(
            text=choice.message.content or "",
            finish_reason=choice.finish_reason,
            truncated=truncated,
            prompt_tokens=prompt,
            completion_tokens=completion,
            reasoning_tokens=reasoning,
            est_cost_usd=cost,
            latency_ms=latency_ms,
            attempts=attempt,
            role=role,
            model_id=cfg.model_id,
        )


def summarize_log(path: Path | None = None, job_id: str | None = None) -> dict:
    """Totals over a call log (only rows of one job if job_id is given).
    A null est_cost_usd is UNKNOWN, never counted as zero."""
    by_status: dict[str, int] = {}
    total_cost = 0.0
    unknown = damaged = calls = 0
    path = path or log_path()
    if path.is_file():
        for raw in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                damaged += 1
                continue
            if job_id is not None and row.get("job_id") != job_id:
                continue
            calls += 1
            by_status[row["status"]] = by_status.get(row["status"], 0) + 1
            if row.get("est_cost_usd") is None:
                unknown += 1
            else:
                total_cost += row["est_cost_usd"]
    return {
        "total_calls": calls,
        "by_status": by_status,
        "total_est_cost_usd": total_cost,
        "unknown_cost_attempts": unknown,
        "cost_is_lower_bound": unknown > 0,
        "damaged_lines": damaged,
    }


def format_summary(summary: dict) -> str:
    statuses = ", ".join(f"{k}={v}" for k, v in sorted(summary["by_status"].items())) or "none"
    lines = [
        f"calls: {summary['total_calls']} ({statuses})",
        f"estimated cost: ${summary['total_est_cost_usd']:.6f}",
    ]
    if summary["cost_is_lower_bound"]:
        lines[1] += (
            f"  (lower bound: {summary['unknown_cost_attempts']} attempt(s) with unknown cost)"
        )
    if summary["damaged_lines"]:
        lines.append(f"damaged log lines skipped: {summary['damaged_lines']}")
    return "\n".join(lines)
