"""One door for "ask the model for JSON and check it" (S4-3): call_validated.

    result = call_validated("super", messages, parse_fn, job_id=..., stage=..., max_tokens=...)

It calls llm.call_model, strips a code fence, and runs parse_fn(text). parse_fn builds the objects
the stage needs (schemas.py objects or a stage-local draft) and raises ValidationProblem when the
answer is not usable. On a problem there is ONE retry: the same messages plus a short user message
"Your last answer was invalid: <problems>. Return only the corrected JSON." (the bad answer itself is
not sent back, so the retry stays cheap and no raw data is repeated). A cut-off answer
(finish_reason "length") is retried once with doubled max_tokens. So there are at most 2 tries.

call_validated NEVER raises to the pipeline: after the second failure, or when call_model gives up
(LLMError), it returns ValidatedResult(ok=False, error_kind, error_message, ...). The result sums
the cost and the attempts of every try. A cost of None from the API makes cost_is_lower_bound True.

Problem messages hold at most 3 problems, each with a field path and a clipped text, never raw
data; known API keys are scrubbed from them.
"""
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable

import pydantic

import llm
from clean import _parse_reply

MAX_TRIES = 2  # first call + ONE retry
MAX_PROBLEMS = 3
MAX_PROBLEM_CHARS = 120
_KEY_ENVS = ("NEBIUS_API_KEY", "TAVILY_API_KEY")
_KEY_SHAPE = re.compile(r"\b(?:tvly|sk|nvapi|v1)[-.][A-Za-z0-9_.-]{12,}")
_FENCE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*\n?(.*?)\n?\s*```\s*$", re.DOTALL)


def _scrub(text: str) -> str:
    for name in _KEY_ENVS:
        value = os.getenv(name)
        if value and len(value) >= 8:
            text = text.replace(value, "[hidden]")
    return _KEY_SHAPE.sub("[hidden]", text)


def _clip(text: str) -> str:
    text = " ".join(_scrub(str(text)).split())
    return text if len(text) <= MAX_PROBLEM_CHARS else text[: MAX_PROBLEM_CHARS - 3] + "..."


class ValidationProblem(Exception):
    """The model's answer is not usable. Holds at most 3 short problems (with field paths)."""

    def __init__(self, problems: "str | list[str]"):
        items = [problems] if isinstance(problems, str) else list(problems)
        clipped = [_clip(p) for p in items[:MAX_PROBLEMS]]
        if len(items) > MAX_PROBLEMS:
            clipped.append(f"(+{len(items) - MAX_PROBLEMS} more)")
        self.problems = clipped
        super().__init__("; ".join(clipped) or "invalid answer")

    @classmethod
    def from_pydantic(cls, error: pydantic.ValidationError, prefix: str = "") -> "ValidationProblem":
        """Only the field path and pydantic's message; never the input value."""
        return cls([
            f"{prefix}{'.'.join(str(p) for p in e['loc']) or '(root)'}: {e['msg']}"
            for e in error.errors()
        ])


def strip_fences(text: str) -> str:
    """Remove one surrounding ``` or ```json code fence, if there is one."""
    match = _FENCE.match(text)
    return match.group(1) if match else text.strip()


def parse_json_list(text: str) -> list[dict]:
    """The JSON list of objects inside text (same extraction as clean.py); raises ValidationProblem."""
    try:
        return _parse_reply(text)
    except ValueError as error:
        raise ValidationProblem(str(error)) from None


def parse_json_object(text: str) -> dict:
    """The JSON object inside text (from the first { to the last }); raises ValidationProblem."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValidationProblem("no JSON object found")
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError as error:
        raise ValidationProblem(f"invalid JSON ({error.msg})") from None
    if not isinstance(parsed, dict):
        raise ValidationProblem("the answer must be a JSON object")
    return parsed


@dataclass
class ValidatedResult:
    ok: bool
    value: Any = None  # what parse_fn returned (None when ok is False)
    error_kind: str | None = None  # "invalid" | "truncated" | "empty" | "api_error"
    error_message: str | None = None  # short; no raw data
    attempts: int = 0  # tries made by call_validated (1 or 2)
    calls: int = 0  # real HTTP calls, including call_model's own retries
    prompt_tokens: int = 0
    completion_tokens: int = 0
    est_cost_usd: float = 0.0
    cost_is_lower_bound: bool = False
    latency_ms: int = 0
    steps: list[dict] = field(default_factory=list)  # one entry per try: facts only, no text


def retry_message(problem: str) -> dict:
    return {
        "role": "user",
        "content": f"Your last answer was invalid: {problem}; return only the corrected JSON.",
    }


def call_validated(
    role: str,
    messages: list[dict],
    parse_fn: Callable[[str], Any],
    *,
    job_id: str,
    stage: str,
    max_tokens: int,
    client=None,
    **extra,
) -> ValidatedResult:
    out = ValidatedResult(ok=False)
    current = list(messages)
    tokens = max_tokens
    for attempt in range(1, MAX_TRIES + 1):
        out.attempts = attempt
        step = {"attempt": attempt, "max_tokens": tokens}
        out.steps.append(step)
        try:
            result = llm.call_model(
                role, current, job_id=job_id, stage=stage, max_tokens=tokens, client=client, **extra,
            )
        except llm.LLMError as error:
            out.calls += error.attempts
            out.cost_is_lower_bound = True  # a failed attempt may or may not have been billed
            out.error_kind, out.error_message = "api_error", _clip(error)
            step["problem"] = out.error_message
            return out
        out.calls += result.attempts
        out.prompt_tokens += result.prompt_tokens or 0
        out.completion_tokens += result.completion_tokens or 0
        out.latency_ms += result.latency_ms
        if result.est_cost_usd is None:
            out.cost_is_lower_bound = True
        else:
            out.est_cost_usd += result.est_cost_usd
        step.update(
            finish_reason=result.finish_reason, prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens, reasoning_tokens=result.reasoning_tokens,
            latency_ms=result.latency_ms, text_chars=len(result.text),
        )

        if result.truncated:
            out.error_kind, out.error_message = "truncated", "the answer was cut off (too long)"
            tokens *= 2
            retry = current  # same question, more room
        elif not result.text.strip():
            out.error_kind, out.error_message = "empty", "the answer was empty"
            retry = current + [retry_message(out.error_message)]
        else:
            try:
                out.value = parse_fn(strip_fences(result.text))
            except ValidationProblem as problem:
                out.error_kind, out.error_message = "invalid", str(problem)
            except pydantic.ValidationError as error:
                out.error_kind, out.error_message = "invalid", str(ValidationProblem.from_pydantic(error))
            except Exception as error:  # a parser must not crash the pipeline
                out.error_kind, out.error_message = "invalid", _clip(f"{type(error).__name__} while reading the answer")
            else:
                out.ok, out.error_kind, out.error_message = True, None, None
                return out
            retry = current + [retry_message(out.error_message)]
        step["problem"] = out.error_message
        current = retry
    out.value = None
    return out
