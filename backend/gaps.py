"""Gap finder (S3-1): Super lists, per section, the terms a beginner would need explained more.

Per section the model sees only the section title and that section's cleaned segments, and
answers [{"section_id", "term", "reason"}]. This code checks every item: the section_id must be
the one asked, every word of the term must occur in that section's text, duplicates and items
over the maximum are dropped. A term found in several sections is kept only in the section where
it is said most often. Dropped items are listed in the report, never silently lost.
Gap items stay plain dicts (no schemas.py change). The "reason" is a plain-text note for the search
and the writer; it is NOT a Statement and the judge does not check it.

Usage (from backend/):  python -m gaps <job_id>

Files per job:
    jobs/{id}/gaps.json          list of {section_id, term, reason}
    jobs/{id}/gaps_report.json   dropped items with reasons, flagged sections, calls, tokens, cost
"""
import json
import re
from dataclasses import dataclass

import llm
import llm_config
from clean import _parse_reply, load_clean_transcript
from schemas import Section, Segment
from sections import for_each_section
from storage import job_key, save_json
from topics import load_sections

ROLE = "super"
STAGE = "gap_finder"

GAPS_MAX_PER_SECTION = 5
# Super's thinking counts as output tokens. A truncated answer is retried once with double.
MAX_TOKENS = 16000

SYSTEM_PROMPT = """You help a beginner study a university lecture. The user message is JSON: one section of the lecture,
with its "section_id", its "title" and its "segments" as [{"id", "start", "text"}].
Find the terms or examples in THIS section that a beginner would need explained more.
Rules:
- Choose a term only if the lecturer uses it without explaining it, or explains it only briefly. Skip basic words the lecture already defines.
- "term" is short and written as it is said in the section. Use only words that appear in the section's text; do not invent terms.
- "reason" is one plain-text sentence on why a beginner needs this explained. No LaTeX, no math markup, no dollar signs or backslashes.
- Give at most %d items, the most important first. An empty list is allowed if nothing needs more explanation.
- "section_id" must be the section_id from the user message.
Reply with ONLY a JSON list:
[{"section_id": "<same section_id>", "term": "<term>", "reason": "<one sentence>"}]
No other text, no code fence."""


@dataclass(frozen=True)
class SectionGaps:
    section_id: str
    items: list[dict]
    info: dict  # report entry: dropped items, flagged reason, per-attempt call facts, usage
    counts: tuple[int, ...] = ()  # how often each item's term occurs in the section text (same order as items)


@dataclass(frozen=True)
class GapsResult:
    items: list[dict]
    report: dict


def _words(text: str) -> list[str]:
    return re.findall(r"[\w']+", text.lower())


def _fold(word: str) -> str:
    """Fold a trailing plural 's' ("gradients" -> "gradient"); keeps "class", "analysis", "bus"."""
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def normalize_term(term: str) -> str:
    """Lowercase, trimmed, words joined by one space, plural 's' of every word folded."""
    return " ".join(_fold(w) for w in _words(term))


def _count(term: str, segments: list[Segment]) -> int:
    """How many times the (normalized) term occurs in the segments' text, plural forms included."""
    want = normalize_term(term).split()
    have = [_fold(w) for w in _words(" ".join(s.text for s in segments))]
    return sum(have[i : i + len(want)] == want for i in range(len(have) - len(want) + 1)) if want else 0


_MARKUP = re.compile(r"[$\\{}^_]")


def clean_reason(text: str) -> str:
    """Plain text on one line: LaTeX/markup characters removed ("$x^*$" -> "x*")."""
    return " ".join(_MARKUP.sub("", text).split())


def _user_message(section: Section, segments: list[Segment]) -> str:
    return json.dumps(
        {
            "section_id": section.id,
            "title": section.title,
            "segments": [{"id": s.id, "start": round(s.start, 1), "text": s.text} for s in segments],
        },
        ensure_ascii=False,
    )


def _validate(parsed: list, section: Section, segments: list[Segment], max_items: int) -> tuple[list[dict], list[dict]]:
    """(kept, dropped). dropped = [{"term", "reason"}]; the first rule an item breaks is its reason."""
    known = {_fold(w) for w in _words(" ".join(s.text for s in segments))}  # same folding as normalize_term
    kept, dropped, seen = [], [], set()
    for item in parsed:
        term, why = item.get("term"), item.get("reason")
        shown = term if isinstance(term, str) else repr(term)
        if item.get("section_id") != section.id:
            dropped.append({"term": shown, "reason": f"wrong_section_id ({item.get('section_id')!r})"})
        elif not isinstance(term, str) or not isinstance(why, str) or not term.strip() or not why.strip():
            dropped.append({"term": shown, "reason": "missing_term_or_reason"})
        elif not _words(term) or any(w not in known for w in normalize_term(term).split()):
            missing = [w for w in _words(term) if _fold(w) not in known]
            dropped.append({"term": shown, "reason": f"term_not_in_section ({', '.join(missing) or 'no words'})"})
        elif normalize_term(term) in seen:
            dropped.append({"term": shown, "reason": "duplicate"})
        else:
            seen.add(normalize_term(term))
            kept.append({"section_id": section.id, "term": term.strip(), "reason": clean_reason(why)})
    for item in kept[max_items:]:
        dropped.append({"term": item["term"], "reason": "over_max"})
    return kept[:max_items], dropped


def gaps_for_section(
    section: Section, segments: list[Segment], *, job_id: str, client=None,
    max_items: int = GAPS_MAX_PER_SECTION,
) -> SectionGaps:
    """One question to Super (plus one retry when the answer is cut off or unusable)."""
    client = client or llm.make_client()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT % max_items},
        {"role": "user", "content": _user_message(section, segments)},
    ]
    info = {"section_id": section.id, "title": section.title, "segments": len(segments),
            "flagged": None, "dropped": [], "attempts": [], "calls": 0, "prompt_tokens": 0,
            "completion_tokens": 0, "est_cost_usd": 0.0, "cost_is_lower_bound": False}
    max_tokens = MAX_TOKENS
    for attempt in (1, 2):
        try:
            result = llm.call_model(
                ROLE, messages, job_id=job_id, stage=STAGE, max_tokens=max_tokens,
                client=client, temperature=0,
            )
        except llm.LLMError as error:
            info["calls"] += error.attempts
            info["cost_is_lower_bound"] = True  # failed attempts may or may not have been billed
            info["flagged"] = "llm_error"
            return SectionGaps(section.id, [], info)
        info["calls"] += result.attempts
        info["prompt_tokens"] += result.prompt_tokens or 0
        info["completion_tokens"] += result.completion_tokens or 0
        if result.est_cost_usd is None:
            info["cost_is_lower_bound"] = True
        else:
            info["est_cost_usd"] += result.est_cost_usd
        info["attempts"].append({
            "finish_reason": result.finish_reason, "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens, "reasoning_tokens": result.reasoning_tokens,
            "latency_ms": result.latency_ms, "max_tokens": max_tokens, "text_chars": len(result.text),
        })
        if result.truncated:
            reason, detail = "truncated", "it was cut off (too long)"
            max_tokens *= 2
        else:
            try:
                kept, dropped = _validate(_parse_reply(result.text), section, segments, max_items)
                info["dropped"], info["flagged"] = dropped, None  # a good retry clears the flag
                counts = tuple(_count(i["term"], segments) for i in kept)
                return SectionGaps(section.id, kept, info, counts)
            except ValueError as error:
                reason, detail = "invalid_reply", str(error)
        info["flagged"] = reason
        if attempt == 1:
            messages = messages[:2] + [{
                "role": "user",
                "content": f"Your previous answer was rejected: {detail}. Reply again with ONLY the JSON list.",
            }]
    return SectionGaps(section.id, [], info)


def dedupe_across_sections(per_section: list[SectionGaps]) -> list[SectionGaps]:
    """A term (normalized) found in several sections stays only where it is said most often;
    a tie goes to the earliest section. The others are listed as duplicate_across_sections."""
    best: dict[str, tuple[int, int]] = {}  # term -> (count, index of the section that keeps it)
    for n, g in enumerate(per_section):
        for item, count in zip(g.items, g.counts):
            key = normalize_term(item["term"])
            if key not in best or count > best[key][0]:
                best[key] = (count, n)
    out = []
    for n, g in enumerate(per_section):
        items, counts, dropped = [], [], list(g.info["dropped"])
        for item, count in zip(g.items, g.counts):
            keeper = best[normalize_term(item["term"])][1]
            if keeper == n:
                items.append(item)
                counts.append(count)
            else:
                dropped.append({"term": item["term"],
                                "reason": f"duplicate_across_sections (kept in {per_section[keeper].section_id})"})
        out.append(SectionGaps(g.section_id, items, {**g.info, "dropped": dropped}, tuple(counts)))
    return out


def build_result(job_id: str, per_section: list[SectionGaps]) -> GapsResult:
    per_section = dedupe_across_sections(per_section)
    report = {
        "job_id": job_id, "model_id": llm_config.get_role(ROLE).model_id,
        "max_per_section": GAPS_MAX_PER_SECTION, "section_count": len(per_section),
        "gap_count": sum(len(g.items) for g in per_section),
        "flagged": [{"section_id": g.section_id, "reason": g.info["flagged"]}
                    for g in per_section if g.info["flagged"] and not g.items],
        "dropped": [{"section_id": g.section_id, **d} for g in per_section for d in g.info["dropped"]],
        "calls": sum(g.info["calls"] for g in per_section),
        "prompt_tokens": sum(g.info["prompt_tokens"] for g in per_section),
        "completion_tokens": sum(g.info["completion_tokens"] for g in per_section),
        "est_cost_usd": sum(g.info["est_cost_usd"] for g in per_section),
        "cost_is_lower_bound": any(g.info["cost_is_lower_bound"] for g in per_section),
        "sections": [g.info for g in per_section],
    }
    return GapsResult([item for g in per_section for item in g.items], report)


def find_gaps(segments: list[Segment], sections: list[Section], *, job_id: str, client=None) -> GapsResult:
    client = client or (llm.make_client() if sections else None)
    per_section = for_each_section(
        segments, sections,
        lambda section, segs: gaps_for_section(section, segs, job_id=job_id, client=client),
    )
    return build_result(job_id, per_section)


def save_result(job_id: str, result: GapsResult, storage=None) -> None:
    save_json(job_key(job_id, "gaps.json"), result.items, storage)
    save_json(job_key(job_id, "gaps_report.json"), result.report, storage)


def gaps_job(job_id: str, storage=None, client=None) -> GapsResult:
    """Load transcript_clean.json and sections.json, find gaps, save gaps.json and gaps_report.json."""
    result = find_gaps(
        load_clean_transcript(job_id, storage), load_sections(job_id, storage),
        job_id=job_id, client=client,
    )
    save_result(job_id, result, storage)
    return result


def format_table(result: GapsResult) -> str:
    lines = [f"{'section':8} {'term':24} reason"]
    lines += [f"{i['section_id']:8} {i['term'][:24]:24} {i['reason']}" for i in result.items]
    r = result.report
    lines += ["", f"{r['gap_count']} gaps, {len(r['dropped'])} dropped, {r['calls']} calls, "
                  f"{r['prompt_tokens']} + {r['completion_tokens']} tokens, "
                  f"cost ${r['est_cost_usd']:.5f}{' (lower bound)' if r['cost_is_lower_bound'] else ''}"]
    lines += [f"  dropped {d['section_id']} {d['term']!r}: {d['reason']}" for d in r["dropped"]]
    lines += [f"  FLAGGED {f['section_id']}: {f['reason']}" for f in r["flagged"]]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        sys.exit("usage: python -m gaps <job_id>   (run from backend/)")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(format_table(gaps_job(sys.argv[1])))
