"""Topic split (S2-3): Nano groups the cleaned transcript into titled sections.

The model only chooses WHERE a new topic starts: [{"title", "first_segment_id"}]. This code
builds segment_ids, start and end from the transcript, so times are never written by the model
and sections can have no gap and no overlap. If the model's answer fails a check twice, the
lecture is cut into equal time parts ("Part N") and the report says so.

Files per job:
    jobs/{id}/sections.json        list of Section
    jobs/{id}/topics_report.json   fallback used or not, flagged sections, tokens, cost
"""
import json
from dataclasses import dataclass

import llm
import llm_config
from clean import _parse_reply, load_clean_transcript
from schemas import Section, Segment
from storage import job_key, load_json, save_json

ROLE = "nano"
STAGE = "topic_split"

# Nano thinks before it answers (see clean.py); one call sees the whole lecture, so be generous.
# A truncated answer is retried once with double.
MAX_TOKENS = 16000

FALLBACK_PART_SEC = 300.0  # equal time parts when the model's answer is unusable
MIN_SECTION_SEC = 60.0  # a shorter section is merged into its neighbour (see merge_short)
MAX_SECTION_SEC = 720.0  # a longer section is only flagged in the report, not changed

SYSTEM_PROMPT = """You split a university lecture transcript into topics.
"segments" is the whole lecture, in order, as [{"id", "text"}].
Choose where each new topic starts. Give each topic a short, specific title (3 to 8 words).
Rules:
- The first topic must start at the first segment.
- Topics are consecutive: a topic ends where the next one starts. Do not skip or repeat segments.
- The target is 3 to 8 minutes per topic. A short aside, a recap sentence or a change of example is NOT a new topic.
Reply with ONLY a JSON list, in lecture order:
[{"title": "<title>", "first_segment_id": "<id of the first segment of the topic>"}]
No other text, no code fence."""


@dataclass(frozen=True)
class TopicResult:
    sections: list[Section]
    report: dict


def _check_reply(parsed: list, segments: list[Segment]) -> list[tuple[str, int]]:
    """[(title, index of first segment)]. Raises ValueError with a hint the model can act on."""
    index = {s.id: i for i, s in enumerate(segments)}
    out = []
    for item in parsed:
        title, first = item.get("title"), item.get("first_segment_id")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("every topic needs a non-empty string 'title'")
        if first not in index:
            raise ValueError(f"first_segment_id {first!r} is not an id in segments")
        out.append((title.strip(), index[first]))
    if not out:
        raise ValueError("the list is empty")
    if out[0][1] != 0:
        raise ValueError(f"the first topic must start at {segments[0].id}")
    starts = [i for _, i in out]
    if any(b <= a for a, b in zip(starts, starts[1:])):
        raise ValueError("first_segment_id values must be in lecture order, without repeats")
    return out


def build_sections(segments: list[Segment], cuts: list[tuple[str, int]]) -> list[Section]:
    """A section ends where the next one starts (no gap, no overlap); the last ends with the lecture."""
    sections = []
    for n, (title, first) in enumerate(cuts):
        last_excl = cuts[n + 1][1] if n + 1 < len(cuts) else len(segments)
        chunk = segments[first:last_excl]
        end = segments[last_excl].start if last_excl < len(segments) else chunk[-1].end
        sections.append(Section(
            id=f"sec_{n + 1:02d}", title=title, start=chunk[0].start, end=end,
            segment_ids=[s.id for s in chunk],
        ))
    return sections


def _lengths(segments: list[Segment], cuts: list[tuple[str, int]]) -> list[float]:
    starts = [segments[i].start for _, i in cuts]
    ends = starts[1:] + [segments[-1].end]
    return [e - b for b, e in zip(starts, ends)]


def merge_short(segments: list[Segment], cuts: list[tuple[str, int]]) -> tuple[list[tuple[str, int]], list[dict]]:
    """Merge sections shorter than MIN_SECTION_SEC, shortest first, into the previous one (the
    first section into the next). The merged section keeps the title of the longer of the two.
    Cutting at segment starts keeps the sections contiguous. Returns (cuts, merges for the report)."""
    cuts, merges = list(cuts), []
    while len(cuts) > 1:
        lengths = _lengths(segments, cuts)
        short = min(range(len(cuts)), key=lambda k: lengths[k])
        if lengths[short] >= MIN_SECTION_SEC:
            break
        other = short - 1 if short > 0 else 1
        keep_title = cuts[short][0] if lengths[short] > lengths[other] else cuts[other][0]
        merges.append({
            "merged_title": cuts[short][0], "seconds": round(lengths[short], 1),
            "into_title": cuts[other][0], "result_title": keep_title,
            "at": round(segments[cuts[short][1]].start, 1),
        })
        first = min(short, other)
        cuts[first] = (keep_title, cuts[first][1])
        del cuts[max(short, other)]
    return cuts, merges


def fallback_cuts(segments: list[Segment]) -> list[tuple[str, int]]:
    cuts, part_start = [], None
    for i, s in enumerate(segments):
        if part_start is None or s.start >= part_start + FALLBACK_PART_SEC:
            cuts.append((f"Part {len(cuts) + 1}", i))
            part_start = s.start
    return cuts


def _flagged(sections: list[Section]) -> list[dict]:
    out = []
    for sec in sections:
        length = sec.end - sec.start
        if length < MIN_SECTION_SEC:
            out.append({"id": sec.id, "reason": "too_short", "seconds": round(length, 1)})
        elif length > MAX_SECTION_SEC:
            out.append({"id": sec.id, "reason": "too_long", "seconds": round(length, 1)})
    return out


def split_topics(segments: list[Segment], *, job_id: str, client=None) -> TopicResult:
    report = {
        "job_id": job_id, "model_id": llm_config.get_role(ROLE).model_id,
        "total_segments": len(segments), "used_fallback": False, "fallback_reason": None,
        "calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
        "est_cost_usd": 0.0, "cost_is_lower_bound": False,
    }
    if not segments:
        report.update(section_count=0, merged_short=[], flagged=[])
        return TopicResult([], report)

    client = client or llm.make_client()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(
            {"segments": [{"id": s.id, "text": s.text} for s in segments]}, ensure_ascii=False)},
    ]
    max_tokens, cuts, reason = MAX_TOKENS, None, None
    for attempt in (1, 2):
        try:
            result = llm.call_model(
                ROLE, messages, job_id=job_id, stage=STAGE, max_tokens=max_tokens,
                client=client, temperature=0,
            )
        except llm.LLMError as error:
            report["calls"] += error.attempts
            report["cost_is_lower_bound"] = True  # failed attempts may or may not have been billed
            reason = "llm_error"
            break
        report["calls"] += result.attempts
        report["prompt_tokens"] += result.prompt_tokens or 0
        report["completion_tokens"] += result.completion_tokens or 0
        if result.est_cost_usd is None:
            report["cost_is_lower_bound"] = True
        else:
            report["est_cost_usd"] += result.est_cost_usd

        if result.truncated:
            reason, detail = "truncated", "it was cut off (too long)"
            max_tokens *= 2
        else:
            try:
                cuts = _check_reply(_parse_reply(result.text), segments)
                reason = None
                break
            except ValueError as error:
                reason, detail = "invalid_reply", str(error)
        if attempt == 1:
            messages = messages[:2] + [{
                "role": "user",
                "content": f"Your previous answer was rejected: {detail}. Reply again with ONLY the JSON list.",
            }]

    if cuts is None:
        cuts = fallback_cuts(segments)
        report.update(used_fallback=True, fallback_reason=reason)
    merges = []
    if not report["used_fallback"]:
        cuts, merges = merge_short(segments, cuts)
    sections = build_sections(segments, cuts)
    report.update(section_count=len(sections), merged_short=merges, flagged=_flagged(sections))
    return TopicResult(sections, report)


def split_job(job_id: str, storage=None, client=None) -> TopicResult:
    """Load jobs/{id}/transcript_clean.json, split it, save sections.json and topics_report.json."""
    result = split_topics(load_clean_transcript(job_id, storage), job_id=job_id, client=client)
    save_json(job_key(job_id, "sections.json"), [s.model_dump() for s in result.sections], storage)
    save_json(job_key(job_id, "topics_report.json"), result.report, storage)
    return result


def load_sections(job_id: str, storage=None) -> list[Section]:
    return [Section(**s) for s in load_json(job_key(job_id, "sections.json"), storage)]
