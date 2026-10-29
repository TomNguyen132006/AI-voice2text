# Lecturesque

Turn a lecture into notes and slides where every line cites a lecture timestamp or a web link, then gets checked against that source.

Turn a lecture recording into trustworthy study materials.

Upload a lecture recording. The app transcribes it with **NVIDIA Parakeet**, uses
**NVIDIA Nemotron** models on **Nebius Token Factory** to clean it, split it by topic
and add supporting knowledge from the web, then produces study notes (.md), slides
(.pptx) and a timestamped transcript (.txt). A judge model checks that every
statement has a source (a lecture timestamp or a web link) and does not contradict
the lecture.

Built for the Nebius x NVIDIA Global AI Hackathon (track: Best Apps and Agents).

## Status (checked Oct 27, 2026; Oct 28 additions are marked)

Labels: **PROVEN LIVE** = run with the real models, search API or server and the result was checked; **ONLY MOCKS** = tests with fake clients only;
**NOT TESTED** = not run at all; **BROKEN** = fails. "One job" = `job_013207f9ae93`, a 4.4-minute lecture excerpt uploaded as `.srt` through `POST /jobs` on a local
backend (250 s, $0.044, 19 model calls, 9 Tavily searches). A second real job, `job_4423c587753f` (CSC 335 "Data Models", 4.4 minutes, uploaded as `.srt`,
local backend, Oct 28), ran with the new slide rule and the new limits code: 415 s, $0.0588 ($0.0133 per minute of lecture), 20 statements, 10 Tavily searches.

| Epic | What | Status | Evidence and what is not covered |
|---|---|---|---|
| 0 Setup and contracts | repo, schemas, mock API, deploy skeleton | PROVEN LIVE | Render `/health` and the Vercel page answer 200. `schemas.py` got three optional fields later (`Job.updated_at`, `JobResponse.sections`, `JobResponse.summary`). |
| 1 Transcription | Parakeet, transcript upload | PROVEN LIVE (local GPU only) | Parakeet ran on a local RTX 4060 (Oct 8, see "Parakeet local test environment"); not re-run on Oct 27. `.srt` import checked on one job: 36 cues, times and text identical to the source. The 60-minute audio test (S1-2) is NOT TESTED. |
| 2 Model layer, cleaning, topic split | `llm.py`, `clean.py`, `topics.py` | PROVEN LIVE | Two real jobs. One Nano cleaning call was cut off at 20000 tokens and retried (118 s). |
| 3 Enrichment | gap finder, web search | PROVEN LIVE | 9 Tavily searches, 0 errors. The 429/5xx paths are ONLY MOCKS. |
| 4 Notes and slides | `notes.py`, `slides.py`, `check_sources.py` | PROVEN LIVE | Three real jobs. Slides (rule since Oct 28): the bullets are all statements of the section except the example, in lecture order, at most 7 and at most 700 characters of text; the rest goes to speaker notes, each with its sources. The model only chooses the title and the example id. It ran live once on this rule (`job_4423c587753f`: 2 slides, 5 bullets and an example each, `check_sources` all passed). |
| 5 Judge | `judge.py`, `fix.py` | PROVEN LIVE (one run) | Ultra judged 57 statements in three jobs (48 pass, 9 unsupported). One unsupported statement was rewritten once and passed; in the Oct 28 job all 5 unsupported statements were rewritten once, passed the second check and were kept (0 dropped). Code checks (`no_source`, `bad_source`, `unknown_url`) and the drop paths are ONLY MOCKS. The judge has no "weakly supported / speech recognition difference" level. |
| 6 Output files | `.txt`, `.md`, `.pptx`, `.zip` | PROVEN LIVE (`.txt`, `.md`, `.pptx` rendered in PowerPoint); NOT TESTED (`.pptx` in Google Slides) | Oct 28: the decks of three saved jobs and a stress deck were opened in PowerPoint and exported as slide images; text fit was checked by eye on those. Tests read the file back with python-pptx. |
| 7 Frontend and Job API | pipeline, `/jobs` API, Next.js page | PROVEN LIVE (pipeline and API, local); NOT TESTED (page in a browser, Job API on Render) | Every endpoint answered as expected on a local backend. `npm run build` and `eslint` pass. |
| 8 Logging and stats | call log, `/jobs/{id}/stats` | PROVEN LIVE (log, endpoint); NOT TESTED (stats panel in a browser) | Numbers come from `backend/.data/logs/calls.jsonl`. |
| 9 Deployment | Dockerfile, audio refusal, stale-job check, storage | PROVEN LIVE (audio refusal: `POST /jobs` answers 400 for audio without a GPU engine); NOT TESTED (Dockerfile never built, S3 storage); ONLY MOCKS (stale-job check) | Next.js is on 16.4.3 (0 npm advisories; 16.4.0 had 2 critical and 1 high). |

**Known limits**
- Audio works only on a local GPU machine (Parakeet needs NeMo and an NVIDIA GPU). The deployed backend has no GPU engine and accepts transcripts only (`.txt`, `.srt`, `.vtt`).
- The judge evidence is three jobs (57 statements), no repeat of the same job, and no comparison with a human check beyond reading 5 statements of the Oct 28 job against their segments and snippets (all 5 supported).
- **The judge accepts a few details beyond a snippet or segment.** Examples from reading statements (Oct 28): "a sequence of operations treated as a single unit" where the snippet only says that all operations complete or none do; "(family members covered by benefits)" added after "dependents" where neither the segment nor the snippet says it. The judge also let a vague rewrite through once ("there was a problem that was not easy to do"); the fixer prompt now allows dropping such a statement.
- **One-run evidence.** The numbers of the Oct 28 prompt changes come from one rerun of one lecture (`job_125c_rerun`, a copy of the 6.4-minute Introduction job); nothing was repeated and no human compared the results.
- **"Source-checked" means the cited lecture text or web snippet supports the statement; it does not check the speech recognition itself.** The deck tags and the results page use this word for a statement the judge accepted against its sources.
- **Speech recognition errors pass through the judge.** Parakeet can write a wrong word (for example "row or tuple" written as "raw or topel"; this reached a slide in the Oct 28 job). The judge compares each statement with the transcript, not with the audio, so it cannot see the error. The timestamp on every statement lets a person re-listen.
- Jobs and files are lost when the Render instance restarts or sleeps, unless S3 storage is configured (not tested).
- Render free tier cold start: about 33 s for the first request after sleep.
- `POST /jobs` has abuse limits (upload size, transcript length, concurrent jobs, jobs per day; see "Run locally with audio (GPU) vs deployed (transcript only)"), tested with unit tests only (ONLY MOCKS), not yet on Render. There is no login. The two job counters live in the memory of one server process.
- Token Factory lists 30 models (Oct 27) and none of them is a speech model, so a remote Parakeet engine through Token Factory is not available.

**What still has to be done for the app to work (keys, first run on the live URLs, audio, deploy, submission): see [docs/TODO_TO_RUN.md](docs/TODO_TO_RUN.md).**
Each section below says which run it describes. Sections marked _TBD_ are filled in as we build.

## Run locally with audio (GPU) vs deployed (transcript only)

| | Local machine with an NVIDIA GPU | Deployed server (Render free) |
|---|---|---|
| Accepts | audio/video (`.mp3 .m4a .wav .mp4 .webm .flac .ogg .aac .mov .mkv`) and transcripts (`.txt .srt .vtt`) | transcripts only |
| Needs | NeMo + Parakeet in the Python environment of the backend, `ffmpeg`, `TRANSCRIBE_ENGINE=local` | nothing extra |
| Audio upload | works if `nemo` can be imported by the backend | `POST /jobs` answers 400 "This server cannot transcribe audio..." |

On the development PC the backend runs in a Windows venv without NeMo, so it also refuses audio. Parakeet runs in a separate WSL2 environment: `backend/parakeet/transcribe_s03.py IN.wav OUT.json`
(16 kHz mono WAV in, a list of `{id, start, end, text}` out, chunks of about 120 s cut at quiet points). The repo has no script that writes `.srt`; the Oct 28 test lectures were converted
from that JSON by a throw-away script and uploaded as `.srt`. Measured on the RTX 4060: a 60 s clip took 2.2 s, a 4-7 minute lecture 3-4 s (plus 11-25 s to load the model).

**Abuse limits on `POST /jobs`** (all four are implemented in code; set them as environment variables; a developer can raise them in `.env`; restart the backend after a change):

| Variable | Default | What happens over the limit |
|---|---|---|
| `MAX_UPLOAD_MB` | 10 | HTTP 413 "The file is larger than N MB." The upload is read in 1 MB chunks and reading stops at the limit. The frontend shows the same number (`MAX_UPLOAD_MB` in `frontend/app/lib/api.js`, change both together). |
| `MAX_TRANSCRIPT_CHARS` | 15000 | HTTP 413 with the number of characters and the limit. Transcript uploads are counted after parsing, at `POST /jobs`. For audio the length is only known after transcription, so the job ends in `error` at the `transcribing` stage. |
| `MAX_CONCURRENT_JOBS` | 2 | HTTP 429 "Server busy, try again in a few minutes." Jobs running now, counted in this process. |
| `MAX_JOBS_PER_DAY` | 10 | HTTP 429 "The daily limit of N lectures for this server has been reached. Try again tomorrow." One counter per UTC day, in memory (a restart resets it). |

A slot is reserved before the upload is read and given back if the job never started (bad type, empty or too large file, transcript too long, storage error), so only queued jobs use up the day.
A job that was queued and fails later in the pipeline stays counted. `POST /jobs/sample` calls no model and no search, so it is not counted. For scale: the four test lectures (4.4 to 7 minutes) have 3,195 to 5,385 characters.
**Quality limits** (code defaults; each can be overridden by the environment variable of the same name, see `.env.example`):

| Variable | Default | What it limits |
|---|---|---|
| `GAPS_MAX_PER_SECTION` | 3 (was 5) | terms per section that are sent to web search |
| `NOTES_MAX_WEB_ONLY_PER_SECTION` | 2 | statements per section whose sources are all web results; extra ones are dropped by code (`web_only_cap` in `notes_report.json`), the ones whose term is used most in the section's lecture text stay |
| `SNIPPET_MAX_CHARS` | 1000 (notes writer was 600) | length of a web snippet in the prompt; the notes writer and the judge use the same value |
| `SLIDE_MAX_BULLETS` / `SLIDE_MAX_BULLET_CHARS` | 7 / 700 | bullets per slide / text on a slide |

A missing key is reported by name: `NEBIUS_API_KEY is not set ...` (models) or `TAVILY_API_KEY is not set` (web search, which only becomes a warning).

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

### Deploying the real pipeline (Epic 9)

What is done in the repo: `backend/Dockerfile` (python 3.12 + ffmpeg, starts on `$PORT`), `backend/.dockerignore`, the new variables in `.env.example`, an early "audio not supported here" answer, and a stale-job check. What needs your accounts is listed under "To do by hand".

**Backend environment** (set on the host, never in git): `NEBIUS_API_KEY`, `TAVILY_API_KEY`, `FRONTEND_ORIGINS`, and for storage that survives a restart `STORAGE_BACKEND=s3` with `S3_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`. Without them the backend still works with `STORAGE_BACKEND=local`, but jobs and files are lost when the instance restarts or sleeps.

**What the deployed backend can and cannot do.** It has no GPU and no NeMo, so **it cannot transcribe audio**: `POST /jobs` answers 400 for audio/video with "upload a transcript instead" (checked by `transcribe.audio_available()`), and takes `.txt`, `.srt` and `.vtt`. Audio works only on a machine with the Parakeet environment (`TRANSCRIBE_ENGINE=local`), or with `TRANSCRIBE_ENGINE=fake` for a dry run. A remote Parakeet engine is **not built**; if Token Factory or a Nebius GPU endpoint serves Parakeet, it is one more class in `transcribe.py` (`ENGINES`).
**Jobs are background tasks of the web process.** If the instance restarts or the free Render instance falls asleep mid-job, the job cannot continue: after `STALE_JOB_MINUTES` (45) without a save, `GET /jobs/{id}` reports it as an error ("upload the file again"). Polling from the open page keeps a free instance awake while a job runs.

**S9-3 secrets check (done Oct 27).** Scanned the whole git history (`git log --all -p`) for key shapes (`tvly-`, `nvapi-`, `sk-`, `AKIA`, JWTs, `NEBIUS_API_KEY=`/`TAVILY_API_KEY=`/`AWS_SECRET_ACCESS_KEY=` with a value, long `v1.` tokens) and for any committed `.env` file. Result: no `.env` was ever committed (only `.env.example` files, with empty values), and the only match is the fake string `tvly-SECRETSECRETSECRET1234` in `backend/tests/test_validate.py`, a test that checks keys are hidden. This was a pattern search, not a dedicated scanner (gitleaks/trufflehog); run one before submission if you want more certainty, and rotate the keys if they were ever pasted anywhere public.

**To do by hand (needs your accounts; not done):**
1. Create a Nebius Object Storage bucket and access keys, and set the `S3_*` / `AWS_*` variables on the backend host.
2. Set `NEBIUS_API_KEY`, `TAVILY_API_KEY` on the backend host. Check that `FRONTEND_ORIGINS` has the Vercel URL, and redeploy the frontend after changing `NEXT_PUBLIC_API_URL`.
3. Redeploy: the current Render service uses the plain Python runtime (no ffmpeg), which is fine for transcript uploads. For ffmpeg (or Nebius Serverless Endpoint) deploy `backend/Dockerfile`; **the Dockerfile has not been built** (no Docker on the dev machine).
4. Run one real job on the live URLs and look at the result in a browser. S0-6 (are third-party search APIs allowed, credit limits) is still unanswered in `context/epic.md`.

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

## Gap finder (S3-1)

`backend/gaps.py`: for each section, Super gets the title and only that section's cleaned segments and
returns `[{section_id, term, reason}]` (at most `GAPS_MAX_PER_SECTION` = 3 since Oct 28, before 5; plain dicts, no schema change).
Code checks every item: `section_id` must be the section asked, every word of `term` must occur in that
section's text, duplicates and items over the maximum are dropped. Invalid JSON or a cut-off answer is
retried once (cut-off with double `max_tokens`, start 16000), then the section gets an empty list and is
flagged. Files: `jobs/{id}/gaps.json` and `jobs/{id}/gaps_report.json` (dropped items with reasons, calls, tokens, cost).

After validation, a term (lowercase, trailing plural "s" folded: "gradients" = "gradient") found in several
sections is kept only in the section where it is said most often (tie: the earliest); the others are listed in
`gaps_report.json` as `duplicate_across_sections`. Any LaTeX or markup characters in a `reason` are stripped in code.
**The `reason` is a note for the search and the writer. It is not a `Statement` and the judge does not check it.**
Each gap may also carry an optional `query` (S3-1 T9): a web search query of 3-7 words written by Super for the subject of the whole
lecture (the prompt shows the titles of all sections as `lecture_titles`). It is additive: the required shape stays
`{section_id, term, reason}`. A missing, empty, non-text or over-80-character query is dropped (the term is used instead) and listed
in `gaps_report.json` under `queries_dropped`; quotes and LaTeX characters are stripped. It is a search hint, not a `Statement`, and is not judged.
Repeat a run (from `backend/`): `python -m gaps <job_id>` (sections one at a time, saves both files, prints the
table and the cost; about $0.004 for 3 sections).

First live run (before polish):: 3 calls, all `stop`, 15 gaps, 0 dropped,
4,789 + 2,164 tokens (reasoning 440 to 646 of each answer, inside `completion_tokens`), $0.0034.
Latency 6.8 s (14 segments), 8.0 s (12), 15.9 s (75) against the 120 s Super timeout: not too tight for these
sizes. The model has not been tried on a 20+ minute section yet.
Limits seen then: terms repeated across sections, some terms were generic ("gradients", "minimum point"),
and the reasons added general knowledge that is not in the lecture.
Polish run (Oct 20, prompt asks for terms used without or with only a brief explanation, plus the cross-section
dedupe): 9 gaps, 5 dropped, $0.0038. One run is not proof of stability: Super is not deterministic.
Known gap: the "term must occur in the section" check does not fold plurals, so "Hessian" is dropped from a
section that only says "Hessians".

## Search (S3-2..S3-4)

`backend/enrich.py` searches the web for the gaps in `gaps.json`. Settings are in `backend/search_config.py`:

| Setting | Value | Meaning |
|---|---|---|
| `SEARCH_PROVIDER` (env, default `tavily`) | `tavily` or `fake` | `fake` = no network, no key. New providers (Brave, Serper) = one small class with `name` and `search()` |
| `SEARCH_MAX_RESULTS` / `SEARCH_DEPTH` | 5 / `basic` | `basic` = 1 Tavily credit per search |
| `SEARCH_TIMEOUT_SEC` | 20 | per HTTP call |
| `SEARCH_MAX_RETRIES` | 2 | timeouts, connection errors, 5xx (waits 1 s, 2 s). 4xx: no retry. 429: one retry after `Retry-After` (max 30 s). 432/433: `SearchError` kind `quota`, no retry |
| `SEARCH_CACHE_TTL_DAYS` | 7 | cache in `backend/.data/search_cache/` (git-ignored; shared by all jobs; lost when the server's disk resets) |
| `SEARCH_CAP_PER_JOB` | 15 | real provider calls per job; cache hits do not count; a failed search counts |
| `SEARCH_QUERY_MODE` (env var wins) | `"model"` | `"term"` = the term alone, `"title"` = term + section title, `"model"` = the `query` Super wrote (the term if the gap has none). Default `"model"` (Tom, Oct 22). `SEARCH_QUERY_WITH_TITLE` stays as a read-only alias |

Key: `TAVILY_API_KEY` in `.env` (name in `.env.example`, never in git). Tavily request: `POST https://api.tavily.com/search`,
`Authorization: Bearer <key>`, body `{query, search_depth, max_results}` with answer/raw content/images off;
`content` becomes `snippet`. URLs are kept exactly as returned, results without a URL are dropped.

Files per job: `jobs/{id}/search.json` (one entry per search, cache hits included, with `cached` true/false: this is
what the judge will compare web links against) and `jobs/{id}/search_report.json` (searches made, cache hits, provider calls,
`skipped_cap`, errors). Order of searches: first gap of every section, then the second of every section, and so on.
Run: `cd backend && python -m enrich <job_id>` (`SEARCH_PROVIDER=fake` works end to end).
`python -m enrich` overwrites `search.json` for that run, while `search()` appends. Notes written from an earlier run
may point to URLs that are no longer in the file, so regenerate the notes after re-running enrich.

**Proven by live runs (Oct 22, Tavily, basic depth):** the real reply matches the adapter (`results[].title/url/content`, plus
`usage.credits` and `response_time`); one search takes about 1.3-2.8 s (timeout is 20 s); one basic search = 1 credit, and the
credits summed from `usage` equal our own count; on job_e2e_20261019_130712, 9 gaps -> 9 provider calls, 45 results, every result
has a url; a second `python -m enrich` makes 0 provider calls (9 cache hits). Caveat: the second run overwrites `search.json`,
so all its entries then say `cached: true` (the first run's `cached: false` is gone).
**What the live comparison showed (Oct 22, 3 modes, 9 + 8 gaps of one lecture):**
- Bare terms worked best for clear terms ("level set", "condition number"); an ambiguous term ("x star") returned boats and a finance site.
- Title mode drifted toward the other topics of the section (e.g. "level set" + title returned Hessian pages).
- Model queries gave mostly on-topic results for all 8 gaps, but sometimes over-specify ("level set contour plot" returned contour-plot
  software, "condition number convergence speed" narrowed to one aspect). "Hessian matrix convexity" still has the Hessian soldier page in the top 3.
- Adding one field word to an ambiguous term did not fix it: "x star optimization" returned Star Citizen, MasterCraft and a game calculator.

**Known weakness (backlog S3-1 T10):** tighten the prompt so the query is the term plus at most ONE word naming the lecture's field.

**Search provider:** S0-6 (is a third-party search API allowed?) is still waiting for the organizers' answer. The provider is a setting
(`SEARCH_PROVIDER` / `DEFAULT_PROVIDER` in `search_config.py`); a second provider is one more class in `enrich.py` next to `TavilyProvider`.

**Epic 3 status:** done. Proven live: Tavily reply format, latency (1.2-2.8 s), 1 credit per basic search, credits from `usage`, cap,
cache (a second run makes 0 provider calls), model-written queries. **Not proven live:** the 429 and 5xx paths, and the content quality of
the results (not judged, not checked against the lecture).

## Validated model answers (S4-3, `backend/validate.py`)

`call_validated(role, messages, parse_fn, job_id=, stage=, max_tokens=)` is the door for every stage that needs JSON from a model
(notes, slides, judge). It calls `call_model`, strips a code fence, and runs `parse_fn(text)`, which builds the objects and raises
`ValidationProblem` (at most 3 short problems with field paths, no raw data, keys scrubbed). On a problem it retries ONCE with a
short "Your last answer was invalid: ...; return only the corrected JSON." message (the bad answer is not sent back); a cut-off answer
(`finish_reason` "length") is retried once with doubled `max_tokens`. It never raises to the pipeline: the second failure, or an API
error that survived `call_model`'s own retries, comes back as `ValidatedResult(ok=False, error_kind, error_message, ...)`.
Costs, tokens and attempts of all tries are summed. **Status:** 15 tests with a fake client; used live by the notes and slide writers in every real job (Oct 22 job: 15 calls, all valid at the first try). The retry and API-error paths were only tested with a fake client.

## Notes writer (S4-1, `backend/notes.py`)

`python -m notes <job_id>` (from `backend/`) asks Super once per section (through `call_validated`) for short review notes and writes
`jobs/{id}/notes.json` (a list of `Statement`) and `notes_report.json`. Super sees the section title, the cleaned segments, that section's
gaps and the web snippets of its searches (ids `web_1`, `web_2`, ...; title and snippet only, urls are removed). It returns
`[{"text", "sources": [ids]}]`. **Code** builds the `Statement`: ids `st_0001...` over the whole lecture, `section_id`, lecture
`start/end` copied from the ORIGINAL `transcript.json`, web `url/title` copied from `search.json`. Guards, each reported in
`notes_report.json`: unknown id, id of another section, unknown web id (the id is dropped); no valid source ("unsupported"), empty text,
more than `NOTES_MAX_PER_SECTION` (10, `notes_config.py`, env override) statements (dropped); a failed section becomes an empty list with a flag.
`schemas.py` is unchanged. The prompt tells the model that snippets are untrusted data; this is a prompt rule plus URL removal, not a guarantee.

**Proven live (Oct 22, job_e2e_20261019_130712, Super, 3 calls, $0.0076):** one call per section returned valid JSON at the first try
(`finish_reason` "stop", 2-8 s; 1.9-5.9k prompt tokens, 0.8-1.8k completion tokens of which 0.6-1.5k reasoning); 13 statements (7 / 3 / 3), 8 with a web source;
0 dropped, 0 bad ids; lecture times equal the original transcript. **Not proven:** that the statements are TRUE (at that time nobody had checked them against
the lecture; the judge, Epic 5, ran on later jobs), the guards on real bad output (only tested with a fake client), the retry path and a section whose answer
is cut off, and long lectures. Observed weak points: the 75-segment section gave only 3 statements (thin coverage), and some statements are
backed only by web snippets (e.g. the convexity note), not by the lecture.

**Coverage rework (Oct 22, second live run, 3 Super calls, $0.0153):** the prompt now asks to cover each main idea in order and not to skip
topics in a long section (no number); a statement with ONLY web sources must name a gap term of its section (`web_only_off_topic`, same
normalization as `gaps.py`); at most `NOTES_MAX_SOURCES_PER_STATEMENT` (3, lecture first) sources per statement; `notes_report.json` has per
section `coverage` (distinct cited segments / segments), `web_only` and `sources_per_statement`. Before -> after on the e2e job:

| section | statements | web-only | coverage | cost | latency |
|---|---|---|---|---|---|
| sec_01 (14 seg) | 7 -> 10 | 1 -> 1 | 0.50 -> 0.64 | $0.0030 -> $0.0051 | 24 s |
| sec_02 (12 seg) | 3 -> 10 | 1 -> 0 | 0.83 -> 0.83 | $0.0013 -> $0.0040 | 17 s |
| sec_03 (75 seg) | 3 -> 10 | 1 -> 2 | 0.05 -> 0.27 | $0.0033 -> $0.0062 | 18 s |

Honest reading (one run, not proof of stability): sec_03 improved (real content: gradient, Hessian of the linear example, level sets, steepest
descent) and the guard fired where intended (1 web-only statement dropped). But the short sections got WORSE in quality: the model now goes
segment by segment and writes filler ("The lecturer says he has prepared for the crucial example."); sec_01 and sec_02 each produced 13-15
statements and the cap of 10 cut the LAST ones (the end of the section is lost); sec_02 lost its only web explanation; cost +100 %, latency 17-24 s.
Open design question then: cut by importance instead of by order, or ask for "one note per idea, not per sentence" (done: see the idea-level prompt below).

**Idea-level prompt (Oct 22, third live run, 3 calls, $0.0144):** one note per IDEA (not per sentence), lecture order, no remarks about what the lecturer
plans to do, no greetings or filler, a lecture segment is cited only for what it says itself (web-only claims cite the web id). `NOTES_MAX_PER_SECTION` (10) is
only a safety net; the report has `n_generated` and `n_cut_by_cap` per section. Source limits are now `NOTES_MAX_LECTURE_SOURCES` (6) and `NOTES_MAX_WEB_SOURCES` (3).
`web_only_off_topic` now matches word forms (`same_word_form`: lowercase, plural folded, equal or sharing the first 6 letters), so "convex" matches the term
"convexity". Known false positive of that rule: "derivative" ~ "derivation".

| section | version | generated | kept | cut by cap | web-only | coverage | sources cut | cost |
|---|---|---|---|---|---|---|---|---|
| sec_01 | v1 / v2 / v3 | 7 / 15 / 10 | 7 / 10 / 10 | 0 / 5 / 0 | 1 / 1 / 4 | 0.50 / 0.64 / 0.57 | 0 / 0 / 0 | $0.0030 / $0.0051 / $0.0047 |
| sec_02 | v1 / v2 / v3 | 3 / 13 / 8 | 3 / 10 / 8 | 0 / 3 / 0 | 1 / 0 / 1 | 0.83 / 0.83 / 0.67 | 0 / 0 / 0 | $0.0013 / $0.0040 / $0.0024 |
| sec_03 | v1 / v2 / v3 | 3 / 12 / 9 | 3 / 10 / 9 | 0 / 1 / 0 | 1 / 2 / 3 | 0.05 / 0.27 / 0.29 | 0 / 22 / 3 | $0.0033 / $0.0062 / $0.0073 |

Honest reading (one run, not proof of stability): the cap no longer cuts anything and the end of sec_01 is back (the condition number = 1/b and "slow
convergence when b is small" are statements 7 and 8). Most filler is gone, but not all ("The lecturer asks how the Hessian relates to the convexity of the function").
Web-only statements went UP (1 -> 4 in sec_01, 3 in sec_03), and one of them is the "pure quadratic = ax^2+bx+c" definition that differs from the lecture's
meaning (judge case d, see `context/backlog.md`). Coverage is lower than v2 in sec_02 (0.67 vs 0.83) and cost is about the same as v2 (more in sec_03, which was
the long one). Checked afterwards: a statement in sec_03 calls the level set 2x+5y=0 a "plane"; that is NOT a model slip, the lecturer says "the plane 2x plus 5y equal 0"
(seg_0068, seg_0072, seg_0073), so the note is faithful to the lecture even though it is loose maths. The other statements were not checked by hand then (the judge came later).

## Slide writer (S4-2, `backend/slides.py`)

`python -m slides <job_id>` (from `backend/`) builds one `schemas.Slide` per section FROM the validated statements in `notes.json`, and writes
`slides.json` and `slides_report.json`. Super sees the section title and that section's statements as `[{id, text}]` (no sources, no urls) and
returns `{"title", "example": id|null}` (since Oct 28; before, it also chose the bullet ids). **The model writes no claim and does not pick the bullets.** Code does the rest:
- `bullets` = copies of ALL statements of the section except the example, text and sources unchanged (a test checks this), in lecture order (by the first lecture time of each statement; web-only statements last), at most `SLIDE_MAX_BULLETS` (7) and `SLIDE_MAX_BULLET_CHARS` (700, bullets plus example): the first statement that does not fit and every later one go to the speaker notes.
- `example` = the text of the chosen example statement (its id must be one of the section's statements). It is not a bullet, so nothing is printed twice, and it does not count against the bullet limit.
  **Trade-off:** `Slide.example` is a plain string without sources, so code writes the sources of the example into the speaker notes
  ("Source of the example: lecture 00:42-00:49 (seg_0006); web: <title> <url>"). The Slide object itself therefore carries no structured sources for the
  example; the judge (S5-2) and the exporter (Epic 6) must read the statement from `notes.json`, or `Slide` needs an `example_sources` field (a schema
  change, not made; it must be announced to the team). A section with only one statement keeps it as a bullet and has no example box.
- `speaker_notes` = built by code only: the texts of the statements that are not shown, the source line of the example, and the lecture time range of
  the section for re-listening. The model writes no free speaker notes, so there are no unsourced "non-claim" notes.
- `title` = the model's short label for the topic (not a claim). If it is empty or longer than `SLIDE_MAX_TITLE_WORDS` the section title is used.
- Speaker notes: every statement that is not a bullet is printed with its sources (`[Source: lecture 01:10-01:16 (seg_0009); web: <title> <url>]`); a statement without sources is never printed there. The Sources slide of the `.pptx` lists the web sources of ALL statements of the job (deduplicated), also those that are only in the speaker notes; "No web sources were used" appears only when the job has none. The example box reads "Example: ..." and a leading "For example," / "For instance," is removed for display only. If a slide title promises a list ("Types", "Kinds", "Properties" ...) and statements went to the notes, `slides_report.json` and `pipeline_report.json` get a warning naming them; nothing is guessed.
- Limits in `slides_config.py`, enforced by code, not in the prompt: `SLIDE_MAX_BULLETS` (7), `SLIDE_MAX_BULLET_CHARS` (700), `SLIDE_MAX_WORDS_PER_BULLET` (30; a longer statement
  is not shown as a bullet because shortening it would rewrite it). Cut and too-long statements move to the speaker notes, nothing is lost.
- Guards, each listed in `slides_report.json`: an unknown or foreign example id is dropped; no bullets -> flagged, no slide; a failed section is flagged and the others go on.

**Proven live (Oct 22, job_e2e_20261019_130712, Super, 3 calls, 2.4-3.6 s each, 0.2-0.6k completion tokens):** valid JSON at the first try for both runs
(first run $0.0023; run after the notes rework $0.0017, with the example removed from the bullets: 3 / 3 / 2 bullets and an example box on all 3 slides).
Every bullet keeps its statement id and sources. **Not proven:** the judge has not checked the slides; retry and failure paths and the word limit with real
output (fake client only); the pptx export (Epic 6). **Weak points seen:** the slides are only as good as the notes; with the example removed, sec_03's slide
has only 2 bullets and none about level sets or convexity (they are in the speaker notes), because the model chose the example and the bullets from the first statements.

## Copy check (`backend/check_sources.py`)

`python -m check_sources <job_id>` (from `backend/`, no model, no network, exit code 1 on a failure) checks that texts, times and links were COPIED correctly:
(a) every statement has a source; (b) every web source url (exact) and title is in `search.json`; (c) every lecture source has `segment_id`, `start`, `end` equal to the
ORIGINAL `transcript.json`; (d) every slide bullet equals its statement in `notes.json` (text, section, sources); (e) the slide example equals the statement named by
`example_statement_id` in `slides_report.json`, and that statement is not also a bullet. It does NOT check that a statement is true or supported by its source (the judge, Epic 5).
Run on job_e2e_20261019_130712: a 27/27, b 8/8, c 40/40, d 8/8, e 3/3 passed. (The first run showed e failing, only because the old `slides_report.json` was made before
`example_statement_id` existed; the report was rebuilt from the saved live results, with no model call, and `slides.json` stayed identical.)

## Judge (S5-1, S5-2, `backend/judge.py`)

Ultra (a separate call, so no model grades its own work) checks every statement of `notes.json`. Run: `python -m judge <job_id> [statements_file]` (from `backend/`).

1. **Code checks first (S5-2, no tokens).** A statement is rejected before any model call when it has no source (`no_source`), a lecture source that does not exist, lies outside its segment or belongs to an unknown section (`bad_source`), or a web url that is not in `search.json` (`unknown_url`).
2. **One Ultra call per section** for the rest. Ultra reads the ORIGINAL transcript of the section (to find contradictions) and, for each statement, only its cited sources (lecture text, web title + snippet; urls are never sent). Verdicts: `pass`, `unsupported` (a claim is not in the cited sources), `contradicts` (the lecture says the opposite). The web snippets are untrusted; the prompt tells Ultra to ignore instructions inside them.
3. **Guards.** A statement the model skips, an unknown id or an unknown verdict word never becomes `pass`: it is `unjudged`. A section whose call fails (API error, or bad JSON twice via `validate.call_validated`) makes its statements `unjudged` and is flagged; other sections go on.

Files: `jobs/{id}/judge.json` (`[{statement_id, verdict, reason, by}]`, `by` = code / ultra / none) and `judge_report.json` (counts per verdict, rejections with reasons, flagged sections, calls, tokens, cost). Limits are in `judge_config.py`; the model comes from role `ultra` in `llm_config.py`.

### Fix-or-remove loop and final report (S5-3, S5-4, `backend/fix.py`)

Run: `python -m fix <job_id> [statements_file]` (from `backend/`; it reuses `judge.json` when it matches the statements, else runs the judge first).

| First verdict | What happens |
|---|---|
| `pass` | kept as it is |
| `unsupported`, `contradicts` | Super rewrites it ONCE from its own cited sources (same id, section and sources, only the text changes; no new facts, no urls). The rewrite goes through the code checks and Ultra again: `pass` -> the new text is kept, anything else -> dropped (`still_unsupported`, ...). No third round. |
| `no_source`, `bad_source`, `unknown_url` | dropped (the source is the problem, a new text cannot help) |
| `unjudged` | kept and marked `kept_unjudged` (the judge failed, not the statement) |

If Super fails, answers with an empty text or returns the same text, the statement is dropped (`fixer_failed`, `fixer_gave_up`, `fixer_no_change`). Since Oct 28 the fixer prompt tells Super to answer with an empty text when what is left after removing the unsupported part teaches nothing; `judge_report.json` `final.n_dropped_empty` counts these (`fixer_gave_up`). Since Oct 28 the judge prompt also asks, for a statement whose sources are all web results, whether the web text keeps the meaning the lecture gives to the same term; if not it answers `contradicts`.
Files: `notes_final.json` (survivors, original ids), `fix_log.json` (old text, new text, both verdicts and reasons, outcome) and `judge_report.json`, which now also holds `fix` (second round) and `final`: kept / passed first time / fixed / kept unjudged / dropped by reason, total calls and cost over all rounds. These are the numbers for the Devpost write-up.

**Status:** `judge.py` and `fix.py` have unit tests with a fake client and ran live in three jobs (Oct 22-28): 57 statements, 48 pass first time, 9 unsupported. In the Oct 28 job all 5 unsupported statements were rewritten once by Super and kept after the second check (judge cost $0.0321 of $0.0588). **Not proven:** false rejects, the code checks and drop paths with real output, and anything beyond three jobs. Not done: judging the slides, and wiring `notes_final.json` into the exports.

## Epic 4 status (Oct 23)

| Part | Done | Proven live (job_e2e_20261019_130712, Super) | Not proven |
|---|---|---|---|
| S4-3 `validate.py` | yes | used by notes and slides: 15 calls, all valid at the first try | the retry after invalid JSON / schema error, the doubled-`max_tokens` retry, and the API-error branch with the real API (fake client only) |
| S4-1 `notes.py` | yes (prompt v3 is the baseline) | 3 sections, 27 statements, times and links copied correctly (`check_sources`) | that the statements are TRUE beyond what the judge reads (the judge ran in later jobs, see Epic 5); long sections (sec_03 coverage 0.29); behavior on other lectures |
| S4-2 `slides.py` | yes | 3 slides, bullets keep statement id and sources, example not printed twice | slides through the judge; word limit and cap with real output beyond one run; pptx export (Epic 6) |
| Search provider S0-6 | no | Tavily works | the organizers have not answered whether a third-party search API is allowed |

**Epic 4 spend, from the call log** (`backend/.data/logs/calls.jsonl`, stages `notes_writer` and `slide_writer`): 15 calls, **$0.0412** (notes 9 calls $0.0372, slides 6 calls $0.0040), no errors, no retries.
**Project total from the same log, all stages:** 142 calls, **$0.2276** (cleaning $0.1510, topic split $0.0232, gap finder $0.0119, notes $0.0372, slides $0.0040, smoke test $0.0003);
a lower bound, because 2 timed-out cleaning attempts have no cost. Tavily is not in this number (credits: 26 of 1000 used before Epic 4).

## Output files, pipeline, Job API and frontend (Epics 6 and 7)

**Output files (`backend/export.py`, S6-1..S6-4).** Built by code only, no model call: `transcript.txt` (cleaned transcript, `[mm:ss]` per segment), `notes.md` (the statements that survived the judge, grouped by section, every point ends with 📍 lecture time range and 🌐 web link), `slides.pptx` (python-pptx, drawn by `backend/deck.py`, 16:9, Georgia and Calibri, no extra dependency: a navy title slide with the section, statement and "source-checked by the judge" counts, one slide per section with a time-range chip, the bullets each followed by its source line (lecture time ranges, web title and domain as a hyperlink with the exact url) and a tag "source-checked" / "rewritten" / "not judged" from `judge.json` and `fix_log.json`, an "EXAMPLE" box, speaker notes with the sources of every statement, and a two-column "Sources" slide: lecture time ranges per section and all web links of the job). The lecture title is not stored anywhere, so the title slide says "Lecture notes". Text is measured with an average character width, not rendered: if the bullets of a slide do not fit, the last ones move to the speaker notes and a warning goes to `pipeline_report.json`. Checked by opening the decks of three saved jobs in PowerPoint (slide images, Oct 28); Google Slides was not checked), and one `.zip` with the three files (built on download). Run: `python -m export <job_id>`. Tested by reading the files back with `python-pptx`; **not yet opened in real PowerPoint or Google Slides** (S6-3 asks for that).

**Pipeline (`backend/pipeline.py`, S7-7).** `run_pipeline` runs transcribe (or a .txt/.srt/.vtt upload) -> clean -> split -> gaps -> web search -> notes -> judge + fix -> slides -> export, and writes `jobs/{id}/job.json` after every stage (`transcribing, cleaning, enriching, writing, judging, exporting`). The slides are built from `notes_final.json`, so only statements the judge kept reach the slides. A failing stage makes the job `error` with `"<stage>: <message>"` (keys scrubbed, 300 characters at most). A failing web search is only a warning (the notes then rest on the lecture alone). `pipeline_report.json` has seconds per stage, warnings and the model-call totals. Tested end to end with a fake model that answers every stage; run with the real models in two jobs (Oct 27 `job_013207f9ae93`, 250 s, $0.044; Oct 28 `job_4423c587753f`, 415 s, $0.0588).

**Job API (`backend/jobs_api.py`, S7-2).** Same format as the old mock (`mock_jobs.py` is kept but no longer mounted); `JobResponse` got two optional fields, `sections` and `summary`.
`POST /jobs` (multipart `file`; audio/video or .txt/.srt/.vtt, max `MAX_UPLOAD_MB`=10 and the other limits in "Run locally with audio (GPU) vs deployed (transcript only)"; the pipeline runs as a FastAPI background task, the planned fallback to Nebius Serverless Jobs), `GET /jobs/{id}`, `GET /jobs/{id}/files/{transcript.txt|notes.md|slides.pptx|all.zip}`, and `POST /jobs/sample`.
Limits to know: background tasks die with the server process, and a job that was `running` when the server restarted stays `running` forever (no recovery yet).

**Sample lecture (S7-6).** `POST /jobs/sample` builds a finished job from `backend/samples/` (a short, hand-written gradient-descent lecture) and the results page says so. It is **not model output**; use it to show the layout and the downloads in seconds.

**Frontend (`frontend/app/`).** One page: drag-and-drop upload with type and size checks (S7-1), a progress list that polls every 2 s (S7-3), results grouped by section with a 📍 button (shows the lecture time range) and 🌐 links that open the source (S7-4), a judge summary, download buttons and a zip button, readable error messages (S7-5), and "Try a sample lecture" (S7-6). Plain Tailwind components, not shadcn/ui. `npm run build` and `eslint` pass; **we have not looked at the page in a browser yet.** Set `NEXT_PUBLIC_API_URL` for a deployed backend.

## Logging and stats (Epic 8)

**Call log (S8-1, `llm.py`).** Every model call attempt is one JSONL row in `backend/.data/logs/calls.jsonl` (override with `LLM_LOG_PATH`): job id, stage, role, model id, attempt, status, latency in ms, prompt, completion and reasoning tokens, estimated cost (`null` = unknown, never counted as zero).

**Stats (S8-2, `backend/stats.py`).** `GET /jobs/{id}/stats` returns calls, failed calls, tokens, model time and cost per stage and per model, seconds per pipeline stage, the judge's verdicts and rejection reasons (first 20, with the judge's one-sentence reason), what the rewrite loop fixed, and the web-search report. The pipeline saves the call sums as `jobs/{id}/call_stats.json` when a job ends, because the log file is local and a deployed server may lose it. The results page shows this in a collapsible "How this was made" panel. The sample job has no stats (nothing was run). The endpoint answers with real numbers (PROVEN LIVE); the panel is **not tested in a browser**.

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
