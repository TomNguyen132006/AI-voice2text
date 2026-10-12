"""Tests for transcribe.py with a fake engine (no GPU, no NeMo needed)."""
import shutil
import subprocess

import pytest

import transcribe
from schemas import Segment
from transcribe import TranscribeError, get_engine, merge_chunks


def test_merge_adds_chunk_offsets_and_numbers_ids():
    results = [
        (0.0, [(0.0, 5.0, "First."), (5.0, 9.5, "Second.")]),
        (118.3, [(0.4, 6.0, "Third, after the cut.")]),
    ]

    segments = merge_chunks(results)

    assert segments == [
        Segment(id="seg_0001", start=0.0, end=5.0, text="First."),
        Segment(id="seg_0002", start=5.0, end=9.5, text="Second."),
        Segment(id="seg_0003", start=118.7, end=124.3, text="Third, after the cut."),
    ]


def test_merge_drops_empty_text_without_gaps_in_ids():
    results = [(0.0, [(0.0, 1.0, "  "), (1.0, 2.0, " Hello ")]), (60.0, [(0.0, 1.0, "")])]

    segments = merge_chunks(results)

    assert [(s.id, s.text) for s in segments] == [("seg_0001", "Hello")]


def test_unknown_engine_is_rejected(monkeypatch):
    monkeypatch.setenv("TRANSCRIBE_ENGINE", "magic")
    with pytest.raises(TranscribeError, match="unknown TRANSCRIBE_ENGINE"):
        get_engine()


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_transcribe_end_to_end_with_fake_engine(tmp_path):
    # 25 s of audio cut into ~10 s chunks -> 3 chunks. The fake engine returns one
    # segment per chunk covering the whole chunk, so the segments must tile 0..25 s.
    mp3 = tmp_path / "lecture.mp3"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=300:duration=25", str(mp3)],
        check=True,
    )
    engine = transcribe.FakeEngine()

    segments = transcribe.transcribe(mp3, engine=engine, chunk_sec=10)

    assert engine.calls == 3
    assert [s.id for s in segments] == ["seg_0001", "seg_0002", "seg_0003"]
    assert segments[0].start == 0.0
    for prev, nxt in zip(segments, segments[1:]):
        assert nxt.start == pytest.approx(prev.end, abs=0.01)  # offsets line up across cuts
    assert segments[-1].end == pytest.approx(25.0, abs=0.1)
