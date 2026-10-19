# AI-voice2text

Turn a lecture recording into trustworthy study materials.

Upload a lecture recording. The app transcribes it with **NVIDIA Parakeet**, uses
**NVIDIA Nemotron** models on **Nebius Token Factory** to clean it, split it by topic
and add supporting knowledge from the web, then produces study notes (.md), slides
(.pptx) and a timestamped transcript (.txt). A judge model checks that every
statement has a source (a lecture timestamp or a web link) and does not contradict
the lecture.

Built for the Nebius x NVIDIA Global AI Hackathon (track: Best Apps and Agents).

> Status: Epic 2 done (Oct 19). Transcription (S1), model layer `llm.py` (S2-1), cleaning `clean.py` (S2-2),
> topic split `topics.py` (S2-3), long transcripts (S2-4), golden test `backend/golden/` (S2-5) and the
> end-to-end entry point `python backend/run_epic2.py <transcript.json>` (clean + topic split, prints the
> sections and the cost of the job). Next: Epic 3. Sections marked _TBD_ are filled in as we build.

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
| Backend | Render, Free instance, US region. Live: https://ai-voice2text.onrender.com ([/health](https://ai-voice2text.onrender.com/health)) | Root Directory `backend`; build `pip install -r requirements.txt`; start `uvicorn main:app --host 0.0.0.0 --port $PORT`; health check `/health`; env `PYTHON_VERSION=3.12.6`, `FRONTEND_ORIGINS` |
| Frontend | Vercel (Hobby). Live: https://ai-voice2text.vercel.app | Root Directory `frontend`; env `NEXT_PUBLIC_API_URL` = backend URL |

Set `NEXT_PUBLIC_API_URL` and `FRONTEND_ORIGINS` **without a trailing `/`** (`.../` + `/health` = `//health` = 404).
Where each variable lives (both set, no trailing `/`):

| Variable | Set on | Value |
|---|---|---|
| `FRONTEND_ORIGINS` | **Render** (backend) only | `https://ai-voice2text.vercel.app,http://localhost:3000` (comma-separated) |
| `NEXT_PUBLIC_API_URL` | **Vercel** (frontend) only | `https://ai-voice2text.onrender.com` |

Putting a variable on the wrong host does nothing (the backend never reads Vercel's env).
After changing `NEXT_PUBLIC_API_URL` on Vercel, redeploy the frontend (`NEXT_PUBLIC_` values are baked in at build time).

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

## Transcription (S1-1, S1-2)

`backend/transcribe.py` turns a recording into `Segment`s (`{id, start, end, text}`, times in
seconds from the start of the recording).

1. `audio_prep.py` decodes mp3, m4a, wav or mp4 with ffmpeg to 16 kHz mono and cuts it into
   ~120 s chunks at the quietest point near each boundary (S0-3: one long pass runs out of GPU memory).
2. The engine transcribes each chunk; `merge_chunks` adds each chunk's start offset, so
   timestamps stay correct across cuts.

Engine (`TRANSCRIBE_ENGINE` in `.env`): `local` = Parakeet on an NVIDIA GPU (needs the NeMo env
above), `fake` = no GPU, placeholder text with real chunk times (for testing the flow). These are the only valid values
(`parakeet` is not accepted).

```bash
cd backend
python audio_prep.py lecture.mp3 chunks_out --chunk-sec 60     # only decode + cut, list chunks
python transcribe.py lecture.mp3 out.json --engine fake         # any machine
python transcribe.py lecture.mp3 out.json                       # machine with Parakeet
```

### Transcript upload fallback (S1-3)

If Parakeet is not available, users can upload a transcript instead. `backend/transcript_import.py`
turns it into the same `Segment`s:

- `.srt` / `.vtt`: one segment per cue, with the cue's times.
- `.txt` with `[mm:ss]` or `[hh:mm:ss]` at the start of lines (our own `.txt` export format): one
  segment per stamped line.
- `.txt` without stamps: groups of 1–3 sentences with **estimated** times (~150 words per minute),
  so 📍 citations point near, not exactly at, the moment in the recording.

```bash
python transcript_import.py lecture.srt out.json
```

## Job storage (S1-4)

`backend/storage.py` is where every step saves and loads a job's files, under `jobs/{id}/`. The raw
transcript is saved once per job as `jobs/{id}/transcript.json` (`save_transcript` /
`load_transcript`), so cleanup and the judge can always compare against the original.

Backend (`STORAGE_BACKEND` in `.env`):

- `local` (default): files in `backend/.data/` (git-ignored). Dev only, because the deployed server
  loses local files on restart.
- `s3`: an S3-compatible bucket, planned to be Nebius Object Storage. Set `S3_ENDPOINT_URL`,
  `S3_REGION`, `S3_BUCKET`, `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`. Needed before the
  backend deploy (Epic 9).

## Known limitations of cleaning (S2-2)

`backend/clean.py` (Nano) removes fillers, fixes punctuation and replaces clearly misheard words.
Code guards revert a segment to the original text when the model adds digits/symbols, adds more than
2 new words, removes more than 4 words, or returns a text that is empty, much too long or too short
(see `jobs/{id}/clean_report.json`). Even so:

- The model can still **guess a wrong word** (seg_0019 "So I'm I just have" became "So I'm just have";
  seg_0097 "sur graph" became "surface"; seg_0062 "What's what direction" became "What's the direction";
  in the first run seg_0069 "order" was changed to "point", which was a model error: checked by ear,
  "order" is correct, and the second run correctly left it unchanged).
- It can **drop a small phrase** that changes the meaning (seg_0010 lost "when one over b is a";
  seg_0042 lost "I take"; seg_0043 lost "of that"; seg_0093 lost the question "what about").
- It can **leave an ASR error** untouched. Example: seg_0021. Checked by ear, the speaker said
  "x star is zero zero of course", but the transcript says "x star, zero", so the ASR dropped words.
  Cleaning leaves it unchanged on purpose (the `new_symbol` guard reverts "(0,0)"), because words that
  are missing from the text cannot be verified from the text alone. (seg_0018 "minima" is also correct
  as spoken, so leaving it unchanged was right.)
- The judge compares statements with the SAVED transcript (original and cleaned text), so it **cannot
  catch ASR errors**: if Parakeet heard a wrong word, the judge sees the same wrong word. The
  **timestamp** on every statement is what lets a person re-listen and check.

Segment ids are from the 10-minute test clip (Oct 17); they change if the audio is re-transcribed.

## Known limitations of topic split (S2-3)

`backend/topics.py` (Nano) lets the model choose only where a new topic starts; the code builds ids and
times and merges sections shorter than 60 s into a neighbour.

- **Titles can be vague for long sections.** Example: a 412 s section covering gradient, level sets and
  Hessian was titled "Gradient Direction Connection".
- **Boundaries vary between runs.** The boundary at 186.9 s (checked by ear: a real topic change) was
  found again with different prompts; the later boundaries were not stable (two runs with the same prompt
  gave cuts 4 to 7 segments apart).
- **Do not put a numeric duration target in the prompt** ("3 to 6 minutes"): the model then cuts the lecture
  into equal parts (cuts at 34% and 66%) instead of at topic changes, even in the middle of an example.
- **Time hints raise the reasoning tokens**: about 7.6k output tokens for a 10-minute clip (about 2.5k
  without hints), so `MAX_TOKENS` is 32000.

## Long lectures (S2-4)

- **Cleaning** (`clean.py`) works in batches of up to 15 segments and saves every answered batch to
  `jobs/{id}/clean_batches/`; a rerun only calls the missing batches.
- **Topic split** (`topics.py`) asks the whole lecture in one call when it is up to 22.5 minutes
  (`WINDOW_SEC * 1.5`). Longer lectures are cut into overlapping windows (`WINDOW_SEC` 900 s,
  `OVERLAP_SEC` 120 s). In the overlap the earlier window supplies boundaries before the middle (the
  "seam") and the later window those after it; boundaries fewer than 3 segments apart count as one.
  A window whose answer is invalid becomes "Part N" for that window only and is flagged in
  `topics_report.json`.
- `sections.for_each_section(segments, sections, fn)` runs a later step once per section.
- Measured on the 52-minute test lecture (Oct 17): cleaning 36 batches, 667 s, about $0.087, 14 of 528
  segments reverted by the guards; topic split 4 windows, 81 s, about $0.005. The topic split gave only 4
  sections (the longest 1419 s), which is coarse: the prompt says "fewer sections is better".

## Golden test (S2-5)

`backend/golden/run_golden.py` cleans and splits a 264 s excerpt (36 segments, text only, see
`backend/golden/NOTICE` for the license) and prints the differences. About $0.004 per run.

- **Hard checks** (exit code 1): segment ids and times unchanged, sections cover every segment once with
  no gap or overlap.
- **Soft checks** (`backend/golden/checks.json`, reported only, never change the exit code):
  `must_fix` (seg_0026 "Hessians"), `must_not_change` (seg_0018 keeps "minima"; seg_0021 gets no digits
  or symbols), `known_unfixed` (seg_0005 "was" should be "plus": an ASR error the cleaner cannot fix),
  and a boundary near seg_0027 (within 3 segments).
- **Known baseline failure:** `must_not_change` seg_0018 FAILS in every run ("minima" becomes "minimum").
  Recorded on purpose, the prompt was not changed for it.
- **Noise baseline (3 live runs, Oct 19):** the same input gave 11, 12 and 13 changed segments; 29 of 36
  segments had identical cleaned text in all 3 runs (best pair 32 of 36, worst pair 30 of 36); the
  guards reverted seg_0031 in 2 of 3 runs. The sections were 2, 3 and 3; the cut at seg_0027 was found
  in 3 of 3 runs (the cut at seg_0015 in 2 of 3). So **a change counts as real only if it is larger
  than this**: roughly 2 to 6 of 36 cleaned segments, or one extra cut, can differ between two runs
  of the same code.

## Latency and timeouts (Epic 2, from the call log)

- Nano, 114 attempts: p50 26 s, p90 58 s, max 116 s. Successful calls only: p50 23 s, p90 49 s, max 99 s.
  The 15 truncated calls ran 104 to 116 s (20000 tokens, about 170 tokens/s). Super and Ultra: one tiny call each
  (1.3 s and 1.0 s), not enough data.
- 2 attempts timed out at `DEFAULT_TIMEOUT_SEC` = 120 s (job_full52, cleaning, Oct 18); the retry of one finished in 9 s. The 300 s Nano timeout below is the fix.
- Applied Oct 19 (`llm_config.py`): Nano timeout **300 s**, because a call cut at 20000 tokens takes about 118 s
  and the doubled retry asks for 40000 tokens, about 235 s. Super and Ultra stay at 120 s until the judge is measured.

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
