"""Tests for sections.py (S2-4 T4)."""
import pytest

import topics
from schemas import Segment
from sections import for_each_section, segments_of


def segs(n):
    return [Segment(id=f"seg_{i:04d}", start=i * 10.0, end=i * 10.0 + 9.5, text=f"t{i}") for i in range(n)]


def sections_for(s, starts):
    return topics.build_sections(s, [(f"T{i}", i) for i in starts])


def test_each_segment_is_seen_exactly_once_and_only_inside_its_section():
    s = segs(20)
    secs = sections_for(s, [0, 5, 9, 15])
    seen = []

    def fn(section, part):
        low, high = section.start, section.end
        for seg in part:
            assert seg.id in section.segment_ids
            assert low <= seg.start < high or seg is part[-1]  # last segment may end the lecture
            seen.append(seg.id)
        return (section.id, len(part))

    results = for_each_section(s, secs, fn)
    assert results == [("sec_01", 5), ("sec_02", 4), ("sec_03", 6), ("sec_04", 5)]
    assert seen == [x.id for x in s]


def test_stub_that_raises_on_a_foreign_segment_never_does():
    s = segs(12)
    secs = sections_for(s, [0, 4, 8])
    ranges = {sec.id: set(sec.segment_ids) for sec in secs}

    def fn(section, part):
        stray = [x.id for x in part if x.id not in ranges[section.id]]
        if stray:
            raise AssertionError(f"{section.id} got {stray}")
        return len(part)

    assert for_each_section(s, secs, fn) == [4, 4, 4]


def test_unknown_segment_id_raises():
    s = segs(4)
    secs = sections_for(s, [0])
    with pytest.raises(ValueError):
        segments_of(secs[0], s[:2])


def test_no_sections_no_calls():
    assert for_each_section(segs(3), [], lambda *_: 1 / 0) == []
