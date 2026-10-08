"""Tests for sources.py: the model picks segment_id, code fills start/end."""
from schemas import LectureSource, Segment, StatementDraft, WebSource
from sources import check_source_consistency, fill_lecture_times

TRANSCRIPT = [
    Segment(id="seg_0002", start=30.0, end=42.0, text="..."),
    Segment(id="seg_0003", start=42.0, end=55.5, text="..."),
]


def test_lecture_source_gets_times_from_transcript():
    draft = StatementDraft(
        id="st_0001",
        section_id="sec_01",
        text="Gradient descent steps against the gradient.",
        sources=[{"type": "lecture", "segment_id": "seg_0003"}],
    )

    result = fill_lecture_times([draft], TRANSCRIPT)

    assert result.problems == []
    source = result.statements[0].sources[0]
    assert isinstance(source, LectureSource)
    assert (source.segment_id, source.start, source.end) == ("seg_0003", 42.0, 55.5)
    assert check_source_consistency(result.statements, TRANSCRIPT) == []


def test_model_written_times_are_ignored():
    # Even if the model invents start/end, the transcript times win.
    draft = StatementDraft(
        id="st_0002",
        section_id="sec_01",
        text="...",
        sources=[{"type": "lecture", "segment_id": "seg_0003", "start": 999, "end": 1000}],
    )

    source = fill_lecture_times([draft], TRANSCRIPT).statements[0].sources[0]

    assert (source.start, source.end) == (42.0, 55.5)


def test_unknown_segment_is_reported_not_filled():
    draft = StatementDraft(
        id="st_0003",
        section_id="sec_01",
        text="...",
        sources=[{"type": "lecture", "segment_id": "seg_0999"}],
    )

    result = fill_lecture_times([draft], TRANSCRIPT)

    assert result.statements == []
    assert result.rejected == [draft]
    assert len(result.problems) == 1
    assert result.problems[0].statement_id == "st_0003"
    assert result.problems[0].segment_id == "seg_0999"


def test_web_sources_pass_through_unchanged():
    draft = StatementDraft(
        id="st_0004",
        section_id="sec_01",
        text="...",
        sources=[{"type": "web", "url": "https://en.wikipedia.org/wiki/Gradient_descent", "title": "GD"}],
    )

    source = fill_lecture_times([draft], TRANSCRIPT).statements[0].sources[0]

    assert source == WebSource(url="https://en.wikipedia.org/wiki/Gradient_descent", title="GD")


def test_consistency_check_catches_times_outside_segment():
    bad = fill_lecture_times(
        [StatementDraft(id="st_0005", section_id="sec_01", text="...",
                        sources=[{"type": "lecture", "segment_id": "seg_0003"}])],
        TRANSCRIPT,
    ).statements
    bad[0].sources[0].end = 80.0  # simulate a later bug that corrupts the times

    problems = check_source_consistency(bad, TRANSCRIPT)

    assert problems == ["statement st_0005: time 42.0-80.0 outside seg_0003"]
