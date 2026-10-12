"""Audio prep (S1-2): turn any upload into 16 kHz mono WAV chunks for Parakeet.

Parakeet needs 16 kHz mono audio, and long audio does not fit in GPU memory in one
pass (S0-3: ~7.9 GB for 10 min). So we:
1. decode the upload with ffmpeg (mp3, m4a, wav, or the audio of an mp4),
2. cut it into chunks of about chunk_sec seconds, at the quietest point near each
   boundary (so we never cut in the middle of a word),
3. remember each chunk's start offset, so transcribe.py can turn chunk times back
   into whole-recording times.
"""
import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
SUPPORTED_EXTS = {".mp3", ".m4a", ".wav", ".mp4"}


class AudioPrepError(Exception):
    """The upload could not be turned into 16 kHz mono audio."""


@dataclass
class Chunk:
    path: Path
    offset: float  # seconds from the start of the recording


def load_audio_16k(src) -> np.ndarray:
    """Decode any audio/video file to 16 kHz mono int16 samples with ffmpeg."""
    src = Path(src)
    if src.suffix.lower() not in SUPPORTED_EXTS:
        raise AudioPrepError(f"unsupported file type {src.suffix!r}, use one of {sorted(SUPPORTED_EXTS)}")
    if not src.is_file():
        raise AudioPrepError(f"file not found: {src}")
    if shutil.which("ffmpeg") is None:
        raise AudioPrepError("ffmpeg is not installed or not on PATH (see README: Requirements)")

    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-i", str(src),
           "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "-"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        msg = proc.stderr.decode("utf-8", errors="replace").strip()
        raise AudioPrepError(f"ffmpeg could not read {src.name}: {msg}")

    audio = np.frombuffer(proc.stdout, dtype=np.int16)
    if audio.size == 0:
        raise AudioPrepError(f"no audio found in {src.name}")
    return audio


def find_cut_points(audio, chunk_sec=120.0, search_sec=5.0, frame_sec=0.1) -> list[int]:
    """Return sample indices where to cut: the quietest frame_sec frame within
    +-search_sec of every chunk_sec boundary. First is 0, last is len(audio)."""
    frame = int(frame_sec * SAMPLE_RATE)
    cuts = [0]
    target = chunk_sec * SAMPLE_RATE
    while target < len(audio) - search_sec * SAMPLE_RATE:
        lo = int(target - search_sec * SAMPLE_RATE)
        hi = int(target + search_sec * SAMPLE_RATE)
        window = audio[lo:hi][: (hi - lo) // frame * frame].astype(np.float32).reshape(-1, frame)
        quietest = int(np.argmin((window ** 2).mean(axis=1)))
        cut = lo + quietest * frame + frame // 2
        cuts.append(cut)
        target = cut + chunk_sec * SAMPLE_RATE
    cuts.append(len(audio))
    return cuts


def write_chunks(audio, cuts, out_dir) -> list[Chunk]:
    """Write audio[cuts[i]:cuts[i+1]] as 16 kHz mono WAV files in out_dir."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    chunks = []
    for n, (a, b) in enumerate(zip(cuts, cuts[1:])):
        path = out_dir / f"chunk_{n:03d}.wav"
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)  # int16
            w.setframerate(SAMPLE_RATE)
            w.writeframes(np.ascontiguousarray(audio[a:b], dtype=np.int16).tobytes())
        chunks.append(Chunk(path=path, offset=a / SAMPLE_RATE))
    return chunks


def prepare_audio(src, out_dir, chunk_sec=120.0) -> list[Chunk]:
    """Decode src and split it into WAV chunks in out_dir, in time order."""
    audio = load_audio_16k(src)
    return write_chunks(audio, find_cut_points(audio, chunk_sec), out_dir)


if __name__ == "__main__":
    # Manual test: python audio_prep.py lecture.mp3 chunks_out [--chunk-sec 120]
    import argparse

    parser = argparse.ArgumentParser(description="Decode an upload and split it into 16 kHz mono WAV chunks.")
    parser.add_argument("src")
    parser.add_argument("out_dir")
    parser.add_argument("--chunk-sec", type=float, default=120.0)
    args = parser.parse_args()

    chunks = prepare_audio(args.src, args.out_dir, args.chunk_sec)
    for c in chunks:
        with wave.open(str(c.path)) as w:
            length = w.getnframes() / SAMPLE_RATE
        print(f"{c.path.name}  starts at {c.offset:8.2f} s  ({int(c.offset // 60):02d}:{c.offset % 60:05.2f})  length {length:6.2f} s")
    print(f"{len(chunks)} chunks written to {args.out_dir}")
