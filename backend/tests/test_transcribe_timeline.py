"""Offline check of the S1-1 chunk timeline: 300 s of synthetic audio, FakeEngine, no GPU.
Audio is built in pytest's tmp_path (outside the repo)."""
import shutil
import wave

import numpy as np
import pytest

import transcribe
from audio_prep import SAMPLE_RATE
from schemas import Segment


def _speech_like(seconds, gap_every=7.0, gap_sec=0.3):
    """Tone with a short silence every gap_every seconds (stands in for pauses between words)."""
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    audio = (np.sin(2 * np.pi * 300 * t) * 8000).astype(np.int16)
    audio[(t % gap_every) < gap_sec] = 0
    return audio


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_300s_timeline_ids_order_and_chunk_boundaries(tmp_path):
    wav_path = tmp_path / "synthetic_300s.wav"
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(_speech_like(300).tobytes())
    engine = transcribe.FakeEngine()

    segments = transcribe.transcribe(wav_path, engine=engine, chunk_sec=120)

    assert engine.calls >= 3  # 300 s at ~120 s per chunk
    # ids unique and sequential
    assert [s.id for s in segments] == [f"seg_{i:04d}" for i in range(1, len(segments) + 1)]
    # every item is a valid Segment (re-validate from plain dicts)
    for s in segments:
        Segment.model_validate(s.model_dump())
    # monotonic times
    assert segments[0].start == 0.0
    for s in segments:
        assert s.end >= s.start
    for prev, nxt in zip(segments, segments[1:]):
        assert nxt.start >= prev.start
        # no gap or overlap larger than 0.05 s at chunk boundaries
        assert abs(nxt.start - prev.end) <= 0.05
    # last end matches the real duration
    assert segments[-1].end == pytest.approx(300.0, abs=0.05)
