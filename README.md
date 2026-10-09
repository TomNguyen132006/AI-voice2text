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

## Deployment (S0-5)

| Part | Host | Settings |
|---|---|---|
| Backend | Render, Free instance, US region | Root Directory `backend`; build `pip install -r requirements.txt`; start `uvicorn main:app --host 0.0.0.0 --port $PORT`; health check `/health`; env `PYTHON_VERSION=3.12.6`, `FRONTEND_ORIGINS` |
| Frontend | Vercel | Root Directory `frontend`; env `NEXT_PUBLIC_API_URL` = backend URL |

`backend/requirements.txt` is the deploy list: no torch / NeMo (Parakeet runs separately, see below).

**The free Render backend sleeps after 15 minutes without requests**; the first request
after that takes extra time to wake it. Open `<backend URL>/health` and wait for
`{"status":"ok"}` **before recording the demo video and before submission**.

## How we use NVIDIA models and Nebius

| Step | Model / tool | Where it runs |
|---|---|---|
| Speech-to-text with timestamps | NVIDIA Parakeet TDT 0.6B v3 | Tested locally (WSL2 + RTX 4060), see [S0-3 result](#parakeet-test-result-s0-3). Not on Token Factory. Production host: _open question_ |
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
- Parakeet: not found in the Token Factory model list or docs index (checked Oct 7, 2026).

## Parakeet local test environment (S0-3)

Tested Oct 8, 2026 on Windows 11 + WSL2 (Ubuntu 26.04), NVIDIA RTX 4060 Laptop (8 GB VRAM).
Parakeet runs in its own Python 3.12 venv inside WSL (NeMo officially supports Linux).

| Component | Version |
|---|---|
| Python | 3.12.15 (installed with uv 0.12.23) |
| torch | 2.14.1+cu130 (CUDA 13.0, cuDNN 9.24) |
| nemo-toolkit[asr] | 3.0.0 |
| transformers | 5.19.0 (pinned `>=4.45`, see note) |
| tokenizers / huggingface-hub | 0.23.2 / 1.33.0 |
| ffmpeg (system) | 8.0.1 |

Full pinned list (155 packages): `backend/parakeet/requirements-s03.lock`.
Disk use: about 6.4 GB for the venv, plus 2.5 GB for the model file.

Reproduce (inside WSL/Ubuntu):

```bash
sudo apt install -y ffmpeg
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12
mkdir -p ~/parakeet-s03 && cd ~/parakeet-s03
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r <repo>/backend/parakeet/requirements-s03.lock
```

Note: without `transformers>=4.45` the resolver picked transformers 4.12.2, whose
tokenizers 0.10.3 has no Python 3.12 wheel and needs a Rust compiler (install fails).

## Parakeet test result (S0-3)

Oct 8, 2026. Script: `backend/parakeet/transcribe_s03.py`.

**Where it runs:** locally in WSL2, NVIDIA RTX 4060 Laptop (8 GB VRAM), NeMo 3.0.0.
Token Factory does not host Parakeet (checked in S0-3 T2).

**Sample:** 10 minutes (599.9 s) of MIT 18.065 Lecture 22 (see Credits), 16 kHz mono WAV.
One speaker, clear audio.

**Speed and memory:**

| Measure | Result |
|---|---|
| Transcribe 10 min of audio | 5.6 s |
| Model load | 19 s |
| GPU peak | 5.61 GiB reserved (4.71 GiB allocated) |

A single 10-minute pass ran out of GPU memory: NeMo 3.0 masks the whole input in the
subsampling step (about 7.9 GB for 10 min). So audio must be **chunked**: about 2 minutes
per chunk, cut at the quietest point, then add each chunk's start offset to its
timestamps. This feeds S1-2.

**Accuracy spot-check** (listened by a person):

| Check | Result |
|---|---|
| Timestamps A, B, C | 3/3 correct, including C right after a chunk boundary (offset is correct) |
| "lambda max over lambda min" | Correct |
| "Hessian" | Recognised, but misspelled "Hesians" once (written correctly elsewhere) |
| Formula x1² + b·x2² | Parakeet wrote "x1 squared **was** bx2 squared". The audio is ambiguous (sounds like "was"), but the math needs "plus". Ambiguous-audio error: the cleaning step (Nano) must fix it from context |

Timestamps are segment-level (a segment can be 10-15 s long). Word timestamps are
available from the same model if needed later.

**Decision:** OK, use Parakeet. The errors look fixable by the cleaning step.
The S1-3 fallback (transcript upload) is not needed.

**Known gaps:**
- Only one 10-minute sample, one speaker, clear audio. Noisy audio and accents are not tested.
- The cleaning step must not "fix" things by logic without a source. Keep the lecture
  timestamp so a person can re-listen.
- **Not solved:** where Parakeet runs in production. The deployed server will not have
  a laptop GPU. Needs a decision before the Epic 9 deploy (Nebius AI Cloud GPU or another option).

## How sources work

Every statement in the notes and slides must have a source: a lecture moment or a web page.

- The model never writes start/end times. For a lecture source it only picks a
  `segment_id` (`LectureSourceDraft` / `StatementDraft` in `backend/schemas.py`).
- Code fills start/end from the transcript (`fill_lecture_times` in `backend/sources.py`).
  An unknown `segment_id` is reported, never guessed, so the pipeline can retry once or drop it.
- `check_source_consistency` re-checks the result (segment exists, times inside the segment).

Why we chose this: see [docs/DECISIONS.md](docs/DECISIONS.md) (D1).

Run the tests:

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest tests -q
```

## Other Nebius tools used

_TBD_

## Feedback on Token Factory, AI Cloud and NVIDIA models

_TBD_

## Credits

- Parakeet TDT 0.6B v3 is licensed CC-BY-4.0; credit NVIDIA.
  Model: [nvidia/parakeet-tdt-0.6b-v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) by NVIDIA.
- Test lecture (S0-3 and demo): Gilbert Strang. *18.065 Matrix Methods in Data Analysis,
  Signal Processing, and Machine Learning, Lecture 22: Gradient Descent: Downhill to a
  Minimum.* Spring 2018. Massachusetts Institute of Technology: MIT OpenCourseWare,
  [ocw.mit.edu](https://ocw.mit.edu/courses/18-065-matrix-methods-in-data-analysis-signal-processing-and-machine-learning-spring-2018/resources/lecture-22-gradient-descent-downhill-to-a-minimum/).
  License: [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
  The audio/video is not stored in this repo. Our demo video using this lecture is
  non-commercial: no ads, no monetization.

## License

MIT, see [LICENSE](LICENSE).
