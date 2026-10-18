"""Transcript cleaning (S2-2): Nano fixes misheard words, removes fillers, fixes punctuation.

The model gets batches of {id, text} and returns {id, text} only. This code puts the
original start/end back, so ids and times can never change. Anything the model returns
that fails a check is replaced by the ORIGINAL text and counted in the clean report.

Files per job (the raw transcript.json is never touched):
    jobs/{id}/transcript_clean.json   list of Segment (same shape as transcript.json)
    jobs/{id}/clean_report.json       what was reverted and why, tokens, cost
    jobs/{id}/clean_batches/batch_NNNN.json   checkpoint of every batch the model answered; a rerun
                                              reuses these and only calls the missing batches
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import llm
import llm_config
from schemas import Segment
from storage import job_key, load_json, load_transcript, save_json

ROLE = "nano"
STAGE = "cleaning"

BATCH_MAX_SEGMENTS = 15
BATCH_MAX_CHARS = 1800
CONTEXT_SEGMENTS = 3  # read-only neighbours before/after a batch, never returned
DEFAULT_WORKERS = 4  # batches are independent, so they can run in parallel

# Evidence (Oct 17, one Nano call, 5 segments, 304 prompt tokens): 1342 completion tokens, of
# which about 1100 were thinking text (message.reasoning), about 170 the JSON answer; Nano does
# not report reasoning_tokens. That is roughly 260 completion tokens per segment, so a batch of
# 15 needs about 4000. Oct 17 re-run at 8000: 3 of 7 batches were cut off (thinking length
# varies), so 12000; at 12000 3 of 7 were still cut, so 20000. A truncated batch is still retried
# once with double.
MAX_TOKENS = 20000

MIN_RATIO = 0.3  # cleaned text shorter than this share of the original is suspicious
MAX_RATIO = 1.3  # ... longer than this (plus MAX_EXTRA_CHARS) is invented text
MAX_EXTRA_CHARS = 10
SHORT_ORIGINAL = 20  # below this many characters the "too short" check is skipped
# Cleaning may only remove fillers, fix punctuation/capitalization and swap a misheard word.
MAX_NEW_WORDS = 2  # words (case-insensitive) in the cleaned text that are not in the original
MAX_REMOVED_WORDS = 4  # more words than this removed from one segment -> revert (not just fillers)
NEW_SYMBOL_CHARS = "()[]{}=+-*/<>^_%$#@&|~\\"  # plus any digit; a char the original lacks -> revert

SYSTEM_PROMPT = """You clean speech-to-text transcript segments of a university lecture.
For every segment in "segments":
You may make only three kinds of edits:
1. Remove filler words (uh, um) and stutters or repeated words.
2. Fix punctuation and capitalization.
3. Replace a word the speech recognizer clearly misheard with the most plausible similar-sounding word, only when the surrounding text makes it clear. If you are not sure, keep the text as it is.
Do NOT add words, digits or symbols (such as ( ) = + -) that were not in the original text. Do NOT summarize, add facts, explain, translate, merge segments or split segments.
"context_before" and "context_after" are neighbouring segments for context only: do NOT return them.
Reply with ONLY a JSON list, one object per segment in "segments", in the same order:
[{"id": "<same id>", "text": "<cleaned text>"}]
No other text, no code fence."""


@dataclass(frozen=True)
class CleanResult:
    segments: list[Segment]
    report: dict


def make_batches(segments: list[Segment]) -> list[list[Segment]]:
    batches: list[list[Segment]] = []
    current: list[Segment] = []
    chars = 0
    for s in segments:
        if current and (len(current) >= BATCH_MAX_SEGMENTS or chars + len(s.text) > BATCH_MAX_CHARS):
            batches.append(current)
            current, chars = [], 0
        current.append(s)
        chars += len(s.text)
    if current:
        batches.append(current)
    return batches


def _parse_reply(content: str) -> list:
    start, end = content.find("["), content.rfind("]")
    if start == -1 or end <= start:
        raise ValueError("no JSON list found")
    try:
        parsed = json.loads(content[start : end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON ({e.msg})") from None
    if not all(isinstance(item, dict) for item in parsed):
        raise ValueError("list items must be objects")
    return parsed


def _check_reply(parsed: list, batch: list[Segment]) -> dict[str, str]:
    """id -> text. Raises ValueError when ids differ, are reordered, or text is not a string."""
    got = [item.get("id") for item in parsed]
    want = [s.id for s in batch]
    if got != want:
        missing = [i for i in want if i not in got]
        extra = [i for i in got if i not in want]
        raise ValueError(
            f"ids must match exactly and in order (missing {missing[:3]}, unexpected {extra[:3]})"
        )
    if not all(isinstance(item.get("text"), str) for item in parsed):
        raise ValueError("every item needs a string 'text'")
    return {item["id"]: item["text"] for item in parsed}


def _segment_problem(original: str, cleaned: str) -> str | None:
    if not cleaned.strip():
        return "empty_text"
    if len(cleaned) > MAX_RATIO * len(original) + MAX_EXTRA_CHARS:
        return "too_long"
    if len(original) >= SHORT_ORIGINAL and len(cleaned) < MIN_RATIO * len(original):
        return "too_short"
    original_chars = set(original)
    for ch in set(cleaned) - original_chars:
        if ch.isdigit() or ch in NEW_SYMBOL_CHARS:
            return "new_symbol"
    known = set(_words(original))
    if sum(1 for w in _words(cleaned) if w not in known) > MAX_NEW_WORDS:
        return "new_words"
    if len(_words(original)) - len(_words(cleaned)) > MAX_REMOVED_WORDS:
        return "removed_too_much"
    return None


def _words(text: str) -> list[str]:
    return re.findall(r"[\w']+", text.lower())


def _clean_batch(batch, before, after, job_id, client) -> dict:
    """Returns {"texts": {id: text} | None, "reason": str | None, usage numbers}."""
    payload = json.dumps(
        {
            "context_before": [{"id": s.id, "text": s.text} for s in before],
            "segments": [{"id": s.id, "text": s.text} for s in batch],
            "context_after": [{"id": s.id, "text": s.text} for s in after],
        },
        ensure_ascii=False,
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": payload},
    ]
    out = {"texts": None, "reason": None, "calls": 0, "prompt_tokens": 0,
           "completion_tokens": 0, "cost": 0.0, "cost_unknown": False}
    max_tokens = MAX_TOKENS

    for attempt in (1, 2):
        try:
            result = llm.call_model(
                ROLE, messages, job_id=job_id, stage=STAGE, max_tokens=max_tokens,
                client=client, temperature=0,
            )
        except llm.LLMError as error:
            out["calls"] += error.attempts
            out["cost_unknown"] = True  # failed attempts may or may not have been billed
            out["reason"] = "llm_error"
            return out
        out["calls"] += result.attempts
        out["prompt_tokens"] += result.prompt_tokens or 0
        out["completion_tokens"] += result.completion_tokens or 0
        if result.est_cost_usd is None:
            out["cost_unknown"] = True
        else:
            out["cost"] += result.est_cost_usd

        if result.truncated:
            reason, detail = "batch_truncated", "it was cut off (too long)"
            max_tokens *= 2
        else:
            try:
                out["texts"] = _check_reply(_parse_reply(result.text), batch)
                out["reason"] = None
                return out
            except ValueError as error:
                reason, detail = "batch_invalid", str(error)
        out["reason"] = reason
        if attempt == 1:
            messages = messages[:2] + [{
                "role": "user",
                "content": (
                    f"Your previous answer was rejected: {detail}. Reply again with ONLY the "
                    'JSON list for exactly the ids in "segments", in the same order.'
                ),
            }]
    return out


class _StorageCheckpoint:
    """One small JSON file per answered batch. A file is used only if its ids equal the batch's ids."""

    def __init__(self, job_id: str, storage=None):
        self.job_id, self.storage = job_id, storage

    def _key(self, n: int) -> str:
        return job_key(self.job_id, f"clean_batches/batch_{n:04d}.json")

    def get(self, n: int, ids: list[str]) -> dict | None:
        try:
            saved = load_json(self._key(n), self.storage)
        except (FileNotFoundError, ValueError):
            return None
        if saved.get("ids") != ids or not isinstance(saved.get("outcome", {}).get("texts"), dict):
            return None
        return saved["outcome"]

    def put(self, n: int, ids: list[str], outcome: dict) -> None:
        save_json(self._key(n), {"ids": ids, "outcome": outcome}, self.storage)


def clean_transcript(
    segments: list[Segment], *, job_id: str, client=None, max_workers: int = DEFAULT_WORKERS,
    checkpoint=None,
) -> CleanResult:
    batches = make_batches(segments)
    client = client or (llm.make_client() if batches else None)
    resumed = 0
    position = 0
    jobs = []
    for batch in batches:
        before = segments[max(0, position - CONTEXT_SEGMENTS) : position]
        after = segments[position + len(batch) : position + len(batch) + CONTEXT_SEGMENTS]
        jobs.append((batch, before, after))
        position += len(batch)

    def work(numbered):
        nonlocal resumed
        n, (batch, before, after) = numbered
        ids = [s.id for s in batch]
        saved = checkpoint.get(n, ids) if checkpoint else None
        if saved is not None:
            resumed += 1
            return saved
        outcome = _clean_batch(batch, before, after, job_id, client)
        if checkpoint and outcome["texts"] is not None:  # failed batches are retried on a rerun
            checkpoint.put(n, ids, outcome)
        return outcome

    numbered_jobs = list(enumerate(jobs))

    if max_workers <= 1:
        outcomes = [work(j) for j in numbered_jobs]
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            outcomes = list(pool.map(work, numbered_jobs))

    cleaned: list[Segment] = []
    reverted: list[dict] = []
    for (batch, _, _), outcome in zip(jobs, outcomes):
        for original in batch:
            text, reason = original.text, outcome["reason"]
            if outcome["texts"] is not None:
                reason = _segment_problem(original.text, outcome["texts"][original.id])
                if reason is None:
                    text = outcome["texts"][original.id]
            if reason is not None:
                reverted.append({"id": original.id, "reason": reason})
            # id, start and end always come from the original, never from the model
            cleaned.append(Segment(id=original.id, start=original.start, end=original.end, text=text))

    by_reason: dict[str, int] = {}
    for r in reverted:
        by_reason[r["reason"]] = by_reason.get(r["reason"], 0) + 1
    changed = sum(1 for a, b in zip(segments, cleaned) if a.text != b.text)
    report = {
        "job_id": job_id,
        "model_id": llm_config.get_role(ROLE).model_id,
        "total_segments": len(segments),
        "batches": len(batches),
        "resumed_batches": resumed,
        "changed_count": changed,
        "unchanged_count": len(segments) - changed,
        "reverted_count": len(reverted),
        "reverted_by_reason": by_reason,
        "reverted": reverted,
        "calls": sum(o["calls"] for o in outcomes),
        "prompt_tokens": sum(o["prompt_tokens"] for o in outcomes),
        "completion_tokens": sum(o["completion_tokens"] for o in outcomes),
        "est_cost_usd": sum(o["cost"] for o in outcomes),
        "cost_is_lower_bound": any(o["cost_unknown"] for o in outcomes),
    }
    return CleanResult(cleaned, report)


def clean_job(job_id: str, storage=None, client=None, max_workers: int = DEFAULT_WORKERS) -> CleanResult:
    """Load jobs/{id}/transcript.json, clean it, save the two new files, return the result."""
    result = clean_transcript(
        load_transcript(job_id, storage), job_id=job_id, client=client, max_workers=max_workers,
        checkpoint=_StorageCheckpoint(job_id, storage),
    )
    save_json(job_key(job_id, "transcript_clean.json"), [s.model_dump() for s in result.segments], storage)
    save_json(job_key(job_id, "clean_report.json"), result.report, storage)
    return result


def load_clean_transcript(job_id: str, storage=None) -> list[Segment]:
    return [Segment(**s) for s in load_json(job_key(job_id, "transcript_clean.json"), storage)]
