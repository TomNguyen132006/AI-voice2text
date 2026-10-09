"""S0-3 T4: transcribe a 16 kHz mono WAV with Parakeet TDT 0.6B v3 (local GPU).

Writes a list of Segment dicts ({id, start, end, text}, see backend/schemas.py)
to a JSON file and prints run time and peak GPU memory.

Long audio does not fit in 8 GB VRAM in one pass (NeMo 3.0 masks the whole
input in the subsampling step: ~7.9 GB for 10 min). So we split the audio into
chunks of about --chunk-sec seconds, cutting at the quietest point near each
boundary, and add each chunk's offset back to its timestamps.

Run inside the WSL Parakeet venv (see README "Parakeet local test environment"):
    HF_HUB_OFFLINE=1 ~/parakeet-s03/.venv/bin/python transcribe_s03.py IN.wav OUT.json
"""

import argparse
import json
import os
import tempfile
import time

import numpy as np
import soundfile as sf
import torch

MODEL_NAME = "nvidia/parakeet-tdt-0.6b-v3"
SAMPLE_RATE = 16000


def find_cut_points(audio, chunk_sec, search_sec=5.0, frame_sec=0.1):
    """Return sample indices where to cut: the quietest 0.1 s frame within
    +-search_sec of every chunk_sec boundary."""
    frame = int(frame_sec * SAMPLE_RATE)
    cuts = [0]
    target = chunk_sec * SAMPLE_RATE
    while target < len(audio) - search_sec * SAMPLE_RATE:
        lo = int(target - search_sec * SAMPLE_RATE)
        hi = int(target + search_sec * SAMPLE_RATE)
        window = audio[lo:hi][: (hi - lo) // frame * frame].reshape(-1, frame)
        quietest = int(np.argmin((window ** 2).mean(axis=1)))
        cut = lo + quietest * frame + frame // 2
        cuts.append(cut)
        target = cut + chunk_sec * SAMPLE_RATE
    cuts.append(len(audio))
    return cuts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("wav")
    parser.add_argument("out_json")
    parser.add_argument("--chunk-sec", type=float, default=120.0)
    args = parser.parse_args()

    audio, sr = sf.read(args.wav, dtype="float32")
    if sr != SAMPLE_RATE or audio.ndim != 1:
        raise SystemExit(f"need 16 kHz mono WAV, got {sr} Hz, shape {audio.shape}")
    cuts = find_cut_points(audio, args.chunk_sec)

    import nemo.collections.asr as nemo_asr  # slow import, keep it after input checks

    t0 = time.perf_counter()
    model = nemo_asr.models.ASRModel.from_pretrained(MODEL_NAME)
    model = model.to("cuda").eval()
    load_s = time.perf_counter() - t0

    torch.cuda.reset_peak_memory_stats()
    t1 = time.perf_counter()
    raw = []  # (start_sec, end_sec, text) in whole-file time
    with tempfile.TemporaryDirectory() as tmp, torch.inference_mode():
        for n, (a, b) in enumerate(zip(cuts, cuts[1:])):
            path = os.path.join(tmp, f"chunk_{n:03d}.wav")
            sf.write(path, audio[a:b], SAMPLE_RATE)
            hyp = model.transcribe([path], timestamps=True, batch_size=1, verbose=False)[0]
            offset = a / SAMPLE_RATE
            for s in hyp.timestamp["segment"]:
                raw.append((offset + float(s["start"]), offset + float(s["end"]), s["segment"].strip()))
    torch.cuda.synchronize()
    run_s = time.perf_counter() - t1

    segments = [
        {"id": f"seg_{i:04d}", "start": round(start, 2), "end": round(end, 2), "text": text}
        for i, (start, end, text) in enumerate(raw, start=1)
        if text
    ]
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=1)

    gib = 1024 ** 3
    print(f"audio length:        {len(audio) / SAMPLE_RATE:.1f} s")
    print(f"chunks:              {len(cuts) - 1} (cuts at {[round(c / SAMPLE_RATE, 1) for c in cuts]})")
    print(f"segments:            {len(segments)}")
    print(f"model load:          {load_s:.1f} s")
    print(f"transcribe run time: {run_s:.1f} s")
    print(f"peak GPU allocated:  {torch.cuda.max_memory_allocated() / gib:.2f} GiB")
    print(f"peak GPU reserved:   {torch.cuda.max_memory_reserved() / gib:.2f} GiB")


if __name__ == "__main__":
    main()
