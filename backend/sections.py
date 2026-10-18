"""Helpers for running a later stage (gaps, notes, judge) once per section (S2-4)."""
from schemas import Section, Segment


def segments_of(section: Section, segments: list[Segment]) -> list[Segment]:
    by_id = {s.id: s for s in segments}
    missing = [i for i in section.segment_ids if i not in by_id]
    if missing:
        raise ValueError(f"{section.id} lists unknown segment ids {missing[:3]}")
    return [by_id[i] for i in section.segment_ids]


def for_each_section(segments: list[Segment], sections: list[Section], fn) -> list:
    """Call fn(section, segments_of_that_section) once per section, in order; return the results in order.
    fn only ever sees the segments listed in section.segment_ids."""
    return [fn(section, segments_of(section, segments)) for section in sections]
