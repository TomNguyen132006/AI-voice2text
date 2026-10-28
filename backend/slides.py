"""Slide writer (S4-2): one slide per section, built FROM the validated statements of that section.

Super sees the section title and that section's statements as [{id, text}] (no sources, no urls) and
chooses only: a short slide title and optionally ONE statement id as the example. The model never writes a
claim and does not pick the bullets. Code builds the schemas.Slide:
- bullets      = copies of ALL statements of the section except the example (text and sources unchanged), in
                 lecture order (by the first lecture time of each statement; web-only statements last, in notes order)
- example      = the text of the chosen example statement. That statement is not a bullet, so nothing is printed
                 twice. Slide.example is a plain string without sources, so code writes the sources of the example
                 into the speaker notes ("Source of the example: ..."); the statement itself, with its sources,
                 stays in notes.json. (A section with only one statement keeps it as a bullet, with no example.)
- speaker_notes = built by code only: the statements that are not shown (their texts), the source line of the
                 example, and the lecture time range of the section for re-listening. The model writes no free text.
- title        = the model's short label (a name for the topic, not a claim); a title that is empty or
                 too long is replaced by the section title.
Limits (slides_config.py) are enforced by code: an unknown example id (not in this section) is dropped;
more than SLIDE_MAX_BULLETS bullets are cut (the later ones in lecture order); a statement of more than SLIDE_MAX_WORDS_PER_BULLET words is
not shown as a bullet (it is not shortened, because that would be rewriting it). Cut and long statements
move to the speaker notes, so nothing is lost. A slide without bullets is flagged and left out; a section
whose call fails is flagged and the others go on.

Usage (from backend/):  python -m slides <job_id>

Files per job:
    jobs/{id}/slides.json          list of Slide (schemas.py)
    jobs/{id}/slides_report.json   dropped items with reasons, flagged sections, calls, tokens, cost
"""
import json
from dataclasses import dataclass
from typing import Optional

import pydantic

import llm
import llm_config
import slides_config
from schemas import Section, Slide, Statement
from storage import job_key, load_json, save_json
from topics import load_sections
from validate import ValidationProblem, call_validated, parse_json_object

ROLE = "super"
STAGE = "slide_writer"

SYSTEM_PROMPT = """You turn the notes of ONE lecture section into ONE slide for a beginner. The user message is JSON:
"section_id", "title" and "statements" as [{"id", "text"}] (the notes of this section, already checked).
You do not write any content yourself, and you do not choose the bullets: every statement except the example is shown as a bullet automatically. You choose two things:
- "title": a short name for the topic of the slide (a label, not a sentence that claims something).
- "example": the id of ONE statement that works best as the worked example of the slide (a concrete case, number or instance), or null if none does. It is shown in a separate example box instead of as a bullet. Use only an id from the user message.
Reply with ONLY a JSON object:
{"title": "<short topic name>", "example": "st_0002"}
No other text, no code fence."""


class _SlideDraft(pydantic.BaseModel):
    """What the model returns. Local to this stage: schemas.py stays unchanged."""

    title: str
    example: Optional[str] = None


@dataclass(frozen=True)
class SectionSlide:
    section_id: str
    slide: Optional[Slide]  # None when the section has no usable slide (see info["flagged"])
    info: dict  # report entry for this section


@dataclass(frozen=True)
class SlidesResult:
    slides: list[Slide]
    report: dict


def _parse(text: str) -> _SlideDraft:
    try:
        return _SlideDraft(**parse_json_object(text))
    except pydantic.ValidationError as error:
        raise ValidationProblem.from_pydantic(error) from None


def _words(text: str) -> int:
    return len(text.split())


def _clock(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600:d}:{total % 3600 // 60:02d}:{total % 60:02d}" if total >= 3600 else f"{total // 60:02d}:{total % 60:02d}"


def source_line(statement: Statement) -> str:
    """Where a statement comes from, built from its sources: lecture times and segment ids, web titles and urls."""
    parts = []
    lecture = [s for s in statement.sources if s.type == "lecture"]
    if lecture:
        times = ", ".join(f"{_clock(s.start)}-{_clock(s.end)}" for s in lecture)
        parts.append(f"lecture {times} ({', '.join(s.segment_id for s in lecture)})")
    parts += [f"web: {s.title} <{s.url}>" if s.title else f"web: <{s.url}>" for s in statement.sources if s.type == "web"]
    return "Source of the example: " + "; ".join(parts) + "."


def speaker_notes(section: Section, rest: list[Statement], example: Statement | None = None) -> str:
    """Only text copied from statements, plus the source of the example and the lecture time range.
    No sentence written by a model. Slide.example is a plain string without sources, so the sources of the
    example statement are written here, by code."""
    lines = [st.text for st in rest]
    if example is not None:
        lines.append(source_line(example))
    lines.append(f"Lecture time of this section: {_clock(section.start)} - {_clock(section.end)} (to listen again).")
    return "\n".join(lines)


def lecture_order(statements: list[Statement]) -> list[Statement]:
    """By the first lecture time of each statement; statements with no lecture source (web only) go last, in notes order."""
    def first_time(st: Statement) -> float:
        times = [s.start for s in st.sources if s.type == "lecture"]
        return min(times) if times else float("inf")
    return sorted(statements, key=first_time)  # sorted() is stable: equal times keep the notes order


def slide_for_section(
    section: Section, statements: list[Statement], *, job_id: str, client=None,
    max_bullets: int | None = None, max_words: int | None = None,
) -> SectionSlide:
    """One question to Super (plus one retry from call_validated). Never raises."""
    max_bullets = max_bullets or slides_config.max_bullets()
    max_words = max_words or slides_config.max_words_per_bullet()
    info = {
        "section_id": section.id, "title": section.title, "statements_in": len(statements), "bullets": 0,
        "example_statement_id": None, "slide_title": None, "flagged": None, "error_message": None, "dropped": [],
        "calls": 0, "tries": 0, "prompt_tokens": 0, "completion_tokens": 0, "est_cost_usd": 0.0,
        "cost_is_lower_bound": False, "latency_ms": 0, "steps": [],
    }
    if not statements:  # nothing to put on a slide: no model call
        info["flagged"] = "no_statements"
        return SectionSlide(section.id, None, info)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps({
            "section_id": section.id, "title": section.title,
            "statements": [{"id": st.id, "text": st.text} for st in statements],
        }, ensure_ascii=False)},
    ]
    result = call_validated(
        ROLE, messages, _parse, job_id=job_id, stage=STAGE, max_tokens=slides_config.SLIDE_MAX_TOKENS,
        client=client, temperature=0,
    )
    info.update(
        calls=result.calls, tries=result.attempts, prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens, est_cost_usd=result.est_cost_usd,
        cost_is_lower_bound=result.cost_is_lower_bound, latency_ms=result.latency_ms, steps=result.steps,
    )
    if not result.ok:
        info["flagged"], info["error_message"] = result.error_kind, result.error_message
        return SectionSlide(section.id, None, info)

    draft: _SlideDraft = result.value
    by_id = {st.id: st for st in statements}
    example_statement = None
    if draft.example is not None:
        if draft.example not in by_id:
            info["dropped"].append({"id": draft.example, "reason": "unknown_statement_id"})
        elif len(statements) == 1:  # a lone statement stays a bullet
            info["dropped"].append({"id": draft.example, "reason": "example_is_the_only_bullet (kept as bullet)"})
        else:
            example_statement = by_id[draft.example]
            info["example_statement_id"] = example_statement.id
    example = example_statement.text if example_statement else None

    chosen: list[Statement] = []
    for st in lecture_order(statements):
        if example_statement is not None and st.id == example_statement.id:
            continue
        if _words(st.text) > max_words:
            info["dropped"].append({"id": st.id, "reason": "too_long_for_a_bullet (moved to speaker notes)"})
        else:
            chosen.append(st)
    for st in chosen[max_bullets:]:
        info["dropped"].append({"id": st.id, "reason": "over_max_bullets (moved to speaker notes)"})
    bullets = chosen[:max_bullets]
    if not bullets:
        info["flagged"] = "no_bullets"
        return SectionSlide(section.id, None, info)

    title = " ".join(draft.title.split())
    if not title or _words(title) > slides_config.SLIDE_MAX_TITLE_WORDS:
        info["dropped"].append({"id": None, "reason": "title_empty_or_too_long (section title used)"})
        title = section.title
    used_ids = {st.id for st in bullets} | ({example_statement.id} if example_statement else set())
    slide = Slide(
        section_id=section.id, title=title,
        bullets=[st.model_copy(deep=True) for st in bullets], example=example,
        speaker_notes=speaker_notes(section, [st for st in statements if st.id not in used_ids], example_statement),
    )
    info["bullets"], info["slide_title"] = len(bullets), title
    return SectionSlide(section.id, slide, info)


def build_result(job_id: str, per_section: list[SectionSlide]) -> SlidesResult:
    infos = [s.info for s in per_section]
    report = {
        "job_id": job_id, "model_id": llm_config.get_role(ROLE).model_id,
        "max_bullets": slides_config.max_bullets(), "max_words_per_bullet": slides_config.max_words_per_bullet(),
        "section_count": len(per_section),
        "slides": [{"section_id": s.section_id, "example_statement_id": s.info["example_statement_id"]}
                   for s in per_section if s.slide is not None],
        "slide_count": sum(s.slide is not None for s in per_section),
        "flagged": [{"section_id": i["section_id"], "reason": i["flagged"], "message": i["error_message"]}
                    for i in infos if i["flagged"]],
        "dropped": [{"section_id": i["section_id"], **d} for i in infos for d in i["dropped"]],
        "calls": sum(i["calls"] for i in infos),
        "prompt_tokens": sum(i["prompt_tokens"] for i in infos),
        "completion_tokens": sum(i["completion_tokens"] for i in infos),
        "est_cost_usd": sum(i["est_cost_usd"] for i in infos),
        "cost_is_lower_bound": any(i["cost_is_lower_bound"] for i in infos),
        "sections": infos,
    }
    return SlidesResult([s.slide for s in per_section if s.slide is not None], report)


def load_inputs(job_id: str, storage=None, statements_file: str = "notes.json") -> dict:
    return {
        "sections": load_sections(job_id, storage),
        "statements": [Statement(**s) for s in load_json(job_key(job_id, statements_file), storage)],
    }


def write_section(section: Section, inputs: dict, *, job_id: str, client=None) -> SectionSlide:
    return slide_for_section(
        section, [st for st in inputs["statements"] if st.section_id == section.id], job_id=job_id, client=client,
    )


def write_slides(job_id: str, inputs: dict, client=None) -> SlidesResult:
    client = client or (llm.make_client() if inputs["statements"] else None)
    return build_result(job_id, [write_section(sec, inputs, job_id=job_id, client=client) for sec in inputs["sections"]])


def save_result(job_id: str, result: SlidesResult, storage=None) -> None:
    save_json(job_key(job_id, "slides.json"), [s.model_dump() for s in result.slides], storage)
    save_json(job_key(job_id, "slides_report.json"), result.report, storage)


def slides_job(job_id: str, storage=None, client=None, statements_file: str = "notes.json") -> SlidesResult:
    """statements_file: "notes.json", or "notes_final.json" to build slides only from statements the judge kept."""
    result = write_slides(job_id, load_inputs(job_id, storage, statements_file), client)
    save_result(job_id, result, storage)
    return result


def format_table(result: SlidesResult) -> str:
    r = result.report
    lines = [f"{'section':8} {'in':>3} {'bullets':>7} {'dropped':>7}  title"]
    for i in r["sections"]:
        lines.append(f"{i['section_id']:8} {i['statements_in']:>3} {i['bullets']:>7} {len(i['dropped']):>7}  "
                     + (f"FLAGGED {i['flagged']}" if i["flagged"] else (i["slide_title"] or "")))
    lines += ["", f"{r['slide_count']} slides, {len(r['dropped'])} dropped, {r['calls']} calls, "
                  f"{r['prompt_tokens']} + {r['completion_tokens']} tokens, "
                  f"cost ${r['est_cost_usd']:.5f}{' (lower bound)' if r['cost_is_lower_bound'] else ''}"]
    lines += [f"  dropped {d['section_id']} {d['id']}: {d['reason']}" for d in r["dropped"]]
    lines += [f"  FLAGGED {f['section_id']}: {f['reason']} ({f['message']})" for f in r["flagged"]]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        sys.exit("usage: python -m slides <job_id>   (run from backend/)")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(format_table(slides_job(sys.argv[1])))
