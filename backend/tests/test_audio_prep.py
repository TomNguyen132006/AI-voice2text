"""Tests for audio_prep.py: cuts land in silence, offsets are right, ffmpeg decodes."""
import shutil
import subprocess
import wave

import numpy as np
import pytest

from audio_prep import (
    SAMPLE_RATE,
    AudioPrepError,
    find_cut_points,
    load_audio_16k,
    prepare_audio,
    write_chunks,
)


def tone(seconds):
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    return (np.sin(2 * np.pi * 440 * t) * 10000).astype(np.int16)


def silence(seconds):
    return np.zeros(int(seconds * SAMPLE_RATE), dtype=np.int16)


def test_cut_lands_in_silence_near_boundary():
    # Tone until 9 s, 0.5 s of silence at 9.0-9.5 s, tone again until 20 s.
    audio = np.concatenate([tone(9), silence(0.5), tone(10.5)])

    cuts = find_cut_points(audio, chunk_sec=10, search_sec=2)

    assert cuts[0] == 0 and cuts[-1] == len(audio)
    assert 9.0 <= cuts[1] / SAMPLE_RATE <= 9.5


def test_short_audio_is_one_chunk():
    audio = tone(3)
    assert find_cut_points(audio, chunk_sec=10) == [0, len(audio)]


def test_chunk_offsets_and_lengths(tmp_path):
    audio = np.concatenate([tone(9), silence(0.5), tone(10.5), silence(0.5), tone(9.5)])
    cuts = find_cut_points(audio, chunk_sec=10, search_sec=2)

    chunks = write_chunks(audio, cuts, tmp_path)

    assert [c.offset for c in chunks] == [c / SAMPLE_RATE for c in cuts[:-1]]
    total = 0
    for c in chunks:
        with wave.open(str(c.path)) as w:
            assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (SAMPLE_RATE, 1, 2)
            total += w.getnframes()
    assert total == len(audio)  # nothing lost or duplicated at the cuts


def test_unsupported_extension(tmp_path):
    with pytest.raises(AudioPrepError, match="unsupported"):
        load_audio_16k(tmp_path / "lecture.ogg")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_ffmpeg_decodes_mp3_to_16k_mono(tmp_path):
    # Make a 44.1 kHz stereo mp3 of 3 s, then check we get 3 s of 16 kHz mono back.
    mp3 = tmp_path / "clip.mp3"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
         "-ar", "44100", "-ac", "2", str(mp3)],
        check=True,
    )

    audio = load_audio_16k(mp3)

    assert audio.dtype == np.int16
    assert abs(len(audio) / SAMPLE_RATE - 3.0) < 0.1
    chunks = prepare_audio(mp3, tmp_path / "chunks", chunk_sec=120)
    assert len(chunks) == 1 and chunks[0].offset == 0.0
