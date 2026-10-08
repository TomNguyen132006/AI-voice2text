"""Turn model drafts into final statements, and check sources against the transcript.

The model only chooses WHICH segment supports a statement (segment_id).
Code copies the real start/end from the transcript, so times can never be invented.
"""
from dataclasses import dataclass, field

from schemas import (
    LectureSource,
    LectureSourceDraft,
    Section,
    Segment,
    Statement,
    StatementDraft,
)


@dataclass
class SourceProblem:
    """A draft statement that could not be turned into a Statement."""

    statement_id: str
    segment_id: str
    reason: str


@dataclass
class FillResult:
    statements: list[Statement] = field(default_factory=list)  # filled, ready for the judge
    problems: list[SourceProblem] = field(default_factory=list)  # retry once or drop (S4-3 / S5-3)
    rejected: list[StatementDraft] = field(default_factory=list)  # the drafts that had problems


def fill_lecture_times(drafts: list[StatementDraft], segments: list[Segment]) -> FillResult:
    """Copy start/end from the transcript into every lecture source.

    A draft that points to a segment_id that does not exist is NOT guessed:
    it goes to result.problems / result.rejected and is left out of result.statements.
    """
    by_id = {seg.id: seg for seg in segments}
    result = FillResult()

    for draft in drafts:
        sources = []
        problems = []
        for src in draft.sources:
            if isinstance(src, LectureSourceDraft):
                seg = by_id.get(src.segment_id)
                if seg is None:
                    problems.append(SourceProblem(draft.id, src.segment_id, "unknown segment_id"))
                    continue
                sources.append(LectureSource(segment_id=seg.id, start=seg.start, end=seg.end))
            else:
                sources.append(src)  # web sources pass through unchanged

        if problems:
            result.problems.extend(problems)
            result.rejected.append(draft)
        else:
            result.statements.append(
                Statement(id=draft.id, section_id=draft.section_id, text=draft.text, sources=sources)
            )

    return result


def check_source_consistency(
    statements: list[Statement],
    segments: list[Segment],
    sections: list[Section] | None = None,
) -> list[str]:
    """Safety net: return a list of problems (empty list = all consistent).

    Checks that each statement's section exists (if sections are given), each lecture
    source points to a real segment, and its times lie inside that segment.
    """
    by_id = {seg.id: seg for seg in segments}
    section_ids = {sec.id for sec in sections} if sections is not None else None
    problems = []

    for st in statements:
        if section_ids is not None and st.section_id not in section_ids:
            problems.append(f"statement {st.id}: unknown section {st.section_id}")
        for src in st.sources:
            if src.type != "lecture":
                continue
            seg = by_id.get(src.segment_id)
            if seg is None:
                problems.append(f"statement {st.id}: unknown segment {src.segment_id}")
            elif not (seg.start <= src.start <= src.end <= seg.end):
                problems.append(f"statement {st.id}: time {src.start}-{src.end} outside {seg.id}")

    return problems
