# AI-voice2text

Turn a lecture recording into trustworthy study materials.

Upload a lecture recording. The app transcribes it with **NVIDIA Parakeet**, uses
**NVIDIA Nemotron** models on **Nebius Token Factory** to clean it, split it by topic
and add supporting knowledge from the web, then produces study notes (.md), slides
(.pptx) and a timestamped transcript (.txt). A judge model checks that every
statement has a source (a lecture timestamp or a web link) and does not contradict
the lecture.

Built for the Nebius x NVIDIA Global AI Hackathon (track: Best Apps and Agents).

> Status: early setup (Epic 0). Sections marked _TBD_ are filled in as we build.

## Repo structure

```
frontend/   Next.js (JavaScript) + Tailwind CSS
backend/    Python + FastAPI
```

## Requirements

- Node.js 20.9+ (for Next.js 16)
- Python 3.12
- **ffmpeg** (system requirement, used to convert uploaded audio to 16 kHz mono WAV)
  - macOS: `brew install ffmpeg`
  - Ubuntu/Debian: `sudo apt install ffmpeg`
  - Windows: download from https://ffmpeg.org/download.html and add it to `PATH`
  - Check: `ffmpeg -version`
- A Nebius Token Factory API key

## Setup

### 1. Environment variables

```bash
cp .env.example .env
# then open .env and paste your own key after NEBIUS_API_KEY=
```

Never commit `.env` (it is in `.gitignore`).

### 2. Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Open http://127.0.0.1:8000 (API docs at http://127.0.0.1:8000/docs).

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000.

## How we use NVIDIA models and Nebius

| Step | Model / tool | Where it runs |
|---|---|---|
| Speech-to-text with timestamps | NVIDIA Parakeet TDT 0.6B v3 | _TBD (S0-3): not found on Token Factory (checked Oct 7, 2026); confirm with organizers_ |
| Clean transcript, split by topic | Nemotron Nano | Nebius Token Factory |
| Find gaps, write notes and slides | Nemotron Super | Nebius Token Factory |
| Judge every statement | Nemotron Ultra | Nebius Token Factory |

### Model IDs and limits

From the Token Factory catalog (`GET /v1/models?verbose=true`, checked Oct 7, 2026).
Prices are USD per 1M tokens.

| Role | Model ID | Context limit (tokens) | Input price | Output price |
|---|---|---|---|---|
| Nano | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | 262,144 | $0.06 | $0.24 |
| Super | `nvidia/nemotron-3-super-120b-a12b` | 262,144 | $0.30 | $0.90 |
| Ultra | `nvidia/Nemotron-3-Ultra-550b-a55b` | 1,048,576 | $1.00 | $3.00 |

Smoke test (`backend/smoke_test.py`, one short prompt, one call per model, Oct 7, 2026).
Timings are single-call samples (the first call also includes connection warmup),
not a speed comparison between models:

| Model | Response time | Prompt + completion tokens |
|---|---|---|
| Nano | 3,355 ms | 30 + 101 |
| Super | 1,378 ms | 30 + 65 (35 reasoning) |
| Ultra | 710 ms | 30 + 30 (16 reasoning) |

Notes:
- These models produce reasoning tokens before the answer; they count (and are billed) as completion tokens.
- Re-check IDs and prices with `python backend/list_models.py` (listing models uses no tokens).
- Parakeet: not found in the Token Factory model list or docs index (checked Oct 7, 2026); confirm with organizers.

## Other Nebius tools used

_TBD_

## Feedback on Token Factory, AI Cloud and NVIDIA models

_TBD_

## Credits

- NVIDIA Parakeet TDT 0.6B v3 (CC BY 4.0)

## License

MIT, see [LICENSE](LICENSE).
