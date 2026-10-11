# Project overview

Nebius x NVIDIA Global AI Hackathon (track: Best Apps and Agents).
Submit Oct 29, 2026 (hard deadline Oct 30 noon). Public repo, MIT license.

## What the app does

User uploads a lecture recording and gets trustworthy study materials:
notes (.md), slides (.pptx), timestamped transcript (.txt).
Core idea: **every statement has a source** (lecture timestamp or web link), and a
separate judge model (Ultra) checks it. No model grades its own work.

## Pipeline (one job)

```
upload audio (or .txt/.srt/.vtt fallback)
 -> audio prep: ffmpeg to 16 kHz mono WAV, ~2-min chunks        (S1-2)
 -> transcribe: Parakeet -> Segment[] with start/end           (S1-1)
 -> clean: Nano fixes misheard terms, keeps segment IDs         (S2-2)
 -> topic split: Nano -> Section[] (no gaps/overlaps)           (S2-3, S2-4)
 -> gap finder: Super lists terms needing explanation           (S3-1)
 -> web search (Tavily/Brave/Serper), cached, capped            (S3-2..4)
 -> write notes + slides: Super -> Statement[], Slide[]         (S4)
 -> judge: code checks first, then Ultra; fix once or drop      (S5)
 -> export .txt / .md / .pptx / .zip                            (S6)
```
Job stages shown in UI: transcribing -> cleaning -> enriching -> writing -> judging -> exporting -> done.
All steps after topic split run **per section** (context limits, focused output).

## Stack

- `frontend/`: Next.js 16, JavaScript (no TypeScript), Tailwind. Deployed on Vercel.
- `backend/`: Python 3.12, FastAPI, `openai` library (no agent framework), python-pptx. Deployed on Render (free, sleeps after 15 min).
- Storage: Supabase or S3 (not decided). Paths like `jobs/{id}/transcript.json`, `jobs/{id}/search.json`.
- Parakeet: runs separately (WSL2 + GPU, NeMo). Not in `backend/requirements.txt`.

## Key facts

| Item | Value |
|---|---|
| Token Factory base URL | `https://api.tokenfactory.nebius.com/v1/` (env `NEBIUS_API_KEY`) |
| Nano | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` (262k ctx) |
| Super | `nvidia/nemotron-3-super-120b-a12b` (262k ctx) |
| Ultra | `nvidia/Nemotron-3-Ultra-550b-a55b` (1M ctx) |
| Parakeet | `nvidia/parakeet-tdt-0.6b-v3`, CC-BY-4.0, NOT on Token Factory |
| Backend live | https://ai-voice2text.onrender.com (`/health`) |
| Frontend live | https://ai-voice2text.vercel.app |
| Env on Render | `FRONTEND_ORIGINS` (comma-separated, no trailing `/`) |
| Env on Vercel | `NEXT_PUBLIC_API_URL` (no trailing `/`, redeploy after change) |

Models output reasoning tokens (billed as completion tokens). Re-check IDs/prices:
`python backend/list_models.py` (free).

## Data contracts (`backend/schemas.py`, frozen after Oct 11 — announce changes)

- `Segment {id, start, end, text}`
- `Section {id, title, start, end, segment_ids}`
- `Statement {id, section_id, text, sources: [LectureSource | WebSource]}`
- `Slide {section_id, title, bullets: [Statement], example, speaker_notes}`
- `Job {id, status, stage, error, outputs: {txt, md, pptx}}`; `JobResponse` adds `statements`
- Samples: `backend/samples/*.json`, checked by `backend/validate_samples.py`.

**Decision D1** (`docs/DECISIONS.md`): the model outputs only `segment_id` for a lecture
source (`StatementDraft`); code fills start/end (`backend/sources.py`
`fill_lecture_times`). Unknown IDs are reported, never guessed.

## Backend files

| File | Purpose |
|---|---|
| `main.py` | FastAPI app, CORS, `GET /`, `GET /health`, includes mock jobs router |
| `mock_jobs.py` | S0-8 mock: `POST /jobs`, `GET /jobs/{id}` cycle stages on a timer |
| `schemas.py`, `sources.py` | Data contracts; lecture-time filling and checks |
| `check_env.py`, `list_models.py`, `smoke_test.py` | S0-1 / S0-2 scripts |
| `parakeet/transcribe_s03.py` | S0-3 chunked Parakeet test (WSL) |
| `tests/test_sources.py` | `python -m pytest tests -q` |

## Findings so far

- Parakeet (S0-3): 10 min audio in 5.6 s on RTX 4060; must chunk (~2 min) or GPU runs out of memory.
  Timestamps correct across chunks. Some term errors (e.g. "Hesians") -> Nano cleanup fixes them.
  Decision: use Parakeet; S1-3 fallback not required (still useful for the demo).
- **Open:** where Parakeet runs in production (no GPU on Render). Decide before Epic 9.
- **Open:** storage choice (Supabase vs S3); search provider.

## Status (update when a story finishes)

Epic 0: S0-1, S0-2, S0-3, S0-4, S0-5, S0-7, S0-8 have commits. **S0-6 (rules check) not done.**
Next: S0-6, then Epic 1 (due Oct 16).
