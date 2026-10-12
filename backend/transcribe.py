"""Transcription (S1-1): audio file -> list of Segment with start/end times.

Steps: audio_prep.prepare_audio() cuts the upload into ~2-min WAV chunks, an
engine transcribes each chunk, then merge_chunks() adds each chunk's offset so
every time is "seconds from the start of the recording".

The engine is pluggable (TRANSCRIBE_ENGINE in .env):
- "local": Parakeet with NeMo on this machine's NVIDIA GPU (see README, S0-3).
- "fake": dev only, no GPU; placeholder text with real chunk times.
- a remote GPU engine is added in Epic 9 (S9-1).
NeMo/torch are NOT in requirements.txt (deploy list), so they are imported only
inside the local engine.

Manual test:
    python transcribe.py lecture.mp3 out.json --engine fake    (any machine)
    python transcribe.py lecture.mp3 out.json                  (machine with the Parakeet env)
"""
import os
import tempfile
import time
import wave

from audio_prep import prepare_audio
from schemas import Segment

try:  # python-dotenv is not installed in the Parakeet venv; env vars still work there
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

DEFAULT_PARAKEET_MODEL = "nvidia/parakeet-tdt-0.6b-v3"


class TranscribeError(Exception):
    """Transcription could not run (bad config, engine failure)."""


class ParakeetLocalEngine:
    """Parakeet TDT on the local GPU. Loads the model once, on first use."""

    def __init__(self, model_name=None):
        self.model_name = model_name or os.getenv("PARAKEET_MODEL") or DEFAULT_PARAKEET_MODEL
        self._model = None

    def _load(self):
        try:
            import nemo.collections.asr as nemo_asr  # slow import, only when needed
            import torch
        except ImportError as e:
            raise TranscribeError(
                "NeMo is not installed here. Run Parakeet in its own env (README: Parakeet local test environment)"
            ) from e
        model = nemo_asr.models.ASRModel.from_pretrained(self.model_name)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model = model.to(device).eval()

    def transcribe_chunk(self, wav_path) -> list[tuple[float, float, str]]:
        """Return (start, end, text) per segment, times relative to the chunk."""
        if self._model is None:
            self._load()
        import torch

        with torch.inference_mode():
            hyp = self._model.transcribe([str(wav_path)], timestamps=True, batch_size=1, verbose=False)[0]
        return [(float(s["start"]), float(s["end"]), s["segment"]) for s in hyp.timestamp["segment"]]


class FakeEngine:
    """Dev only, no GPU: one placeholder segment per chunk, covering the whole chunk.
    Lets you test chunking/offsets and later pipeline steps without Parakeet."""

    def __init__(self):
        self.calls = 0

    def transcribe_chunk(self, wav_path) -> list[tuple[float, float, str]]:
        self.calls += 1
        with wave.open(str(wav_path)) as w:
            length = w.getnframes() / w.getframerate()
        return [(0.0, length, f"[fake transcript of chunk {self.calls}]")]


ENGINES = {"local": ParakeetLocalEngine, "fake": FakeEngine}


def get_engine():
    name = (os.getenv("TRANSCRIBE_ENGINE") or "local").strip().lower()
    if name not in ENGINES:
        raise TranscribeError(f"unknown TRANSCRIBE_ENGINE {name!r}, use one of {sorted(ENGINES)}")
    return ENGINES[name]()


def merge_chunks(results) -> list[Segment]:
    """Turn [(chunk_offset, [(start, end, text), ...]), ...] into Segments in
    whole-recording time, numbered seg_0001, seg_0002, ... Empty text is dropped."""
    raw = []
    for offset, segments in results:
        for start, end, text in segments:
            text = text.strip()
            if text:
                start, end = round(offset + start, 2), round(offset + end, 2)
                raw.append((start, max(start, end), text))
    raw.sort(key=lambda r: r[0])
    return [
        Segment(id=f"seg_{i:04d}", start=start, end=end, text=text)
        for i, (start, end, text) in enumerate(raw, start=1)
    ]


def transcribe(audio_path, engine=None, chunk_sec=120.0) -> list[Segment]:
    """Transcribe an audio/video file (mp3, m4a, wav, mp4) into Segments."""
    engine = engine or get_engine()
    with tempfile.TemporaryDirectory() as tmp:
        chunks = prepare_audio(audio_path, tmp, chunk_sec)
        results = [(c.offset, engine.transcribe_chunk(c.path)) for c in chunks]
    return merge_chunks(results)


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Transcribe a lecture into segments with timestamps.")
    parser.add_argument("audio")
    parser.add_argument("out_json")
    parser.add_argument("--chunk-sec", type=float, default=120.0)
    parser.add_argument("--engine", choices=sorted(ENGINES), help="overrides TRANSCRIBE_ENGINE")
    args = parser.parse_args()

    t0 = time.perf_counter()
    engine = ENGINES[args.engine]() if args.engine else get_engine()
    segments = transcribe(args.audio, engine=engine, chunk_sec=args.chunk_sec)
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump([s.model_dump() for s in segments], f, ensure_ascii=False, indent=1)

    print(f"segments:   {len(segments)}")
    if segments:
        print(f"last end:   {segments[-1].end:.1f} s")
    print(f"total time: {time.perf_counter() - t0:.1f} s (includes model load)")
