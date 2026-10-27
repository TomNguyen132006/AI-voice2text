# What we still need to do for the app to work

Status on Oct 27: all code for Epics 0-9 that can be written without our accounts is in the repo and tested with fake models
(445 backend tests, frontend build and lint pass). **Nothing has been run with the real models, the real search API or a real GPU.**
Submission deadline: Oct 29 (Devpost closes Oct 30, noon). Work through this list in order.

## 1. Accounts and keys (nobody else can do this)

| Need | Used for | Where it goes |
|---|---|---|
| Nebius Token Factory API key | Nano, Super, Ultra (every model step) | `NEBIUS_API_KEY` in `.env` (local) and on the backend host |
| Tavily API key | web search for the gaps | `TAVILY_API_KEY` (or `SEARCH_PROVIDER=fake` to skip) |
| Nebius Object Storage bucket + access keys | job files that survive a restart | `STORAGE_BACKEND=s3`, `S3_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` |
| Render (backend) and Vercel (frontend) access | live demo URL | see README "Deployment" |

Copy `.env.example` to `.env` and fill it in. Never commit `.env`.

## 2. First real run on your own machine (do this before anything else)

This gives the first real numbers (cost, time, judge results) and shows whether the prompts work with the real models.

1. `cd backend && python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt`
2. Start the backend: `uvicorn main:app --reload` (port 8000). In another terminal: `cd frontend && npm install && npm run dev` (port 3000).
3. Open http://localhost:3000. Upload a **transcript** (`.srt`, `.vtt` or `.txt`; for example one made from the test lecture in `backend/golden/excerpt.json`) and watch the six stages.
4. Open the results page. Check by eye: every point has 📍 or 🌐, the 📍 button shows a time, the 🌐 links open, the "How this was made" panel shows calls, tokens, cost and the judge's rejections.
5. Download the zip. **Open `slides.pptx` in real PowerPoint and in Google Slides** (S6-3 asks for both), open `notes.md` and `transcript.txt`.
6. Fix what breaks. Most likely trouble spots, because they were only tested with fake models: the Ultra judge prompt (does it reject too much or too little?), the rewrite step, a stage timeout (Nano can take about 2-4 minutes per call), and long lectures.

If a stage fails, the job page shows `"<stage>: <message>"`, and `backend/.data/jobs/<id>/` has every file the earlier stages saved. The call log is `backend/.data/logs/calls.jsonl`.

Command-line alternatives for single stages (from `backend/`): `python run_epic2.py <transcript.json>`, `python -m gaps <job>`, `python -m notes <job>`, `python -m judge <job>`, `python -m fix <job>`, `python -m slides <job>`, `python -m export <job>`.

## 3. Audio (decision needed)

The pipeline accepts audio, but transcribing it needs Parakeet on an NVIDIA GPU, and **the deployed backend has no GPU**, so it refuses audio and only takes transcripts.
Pick one:

- **A. Demo with transcripts only** on the live site, and show audio on a GPU machine in the video. No extra code. Say this honestly in the Devpost text.
- **B. Run the backend (or a small transcription service) on a GPU machine** with the Parakeet environment from README "Parakeet local test environment" and `TRANSCRIBE_ENGINE=local`.
- **C. Add a remote Parakeet engine** (a new class in `backend/transcribe.py`, listed in `ENGINES`) if Token Factory or a Nebius GPU endpoint serves Parakeet. We have **not checked** whether it does (open item from S0-3).

Also still open from Epic 1: the manual 60-minute audio test (S1-2) and the real Parakeet run (S1-1). The Nebius Object Storage test (S1-4) is part of step 4 below.

## 4. Deploy

1. Backend: set the environment variables from section 1 on the host. `FRONTEND_ORIGINS` must contain the Vercel URL (no trailing `/`). The current Render service uses the plain Python runtime (fine for transcripts, no ffmpeg); to get ffmpeg or to use Nebius Serverless Endpoint, deploy `backend/Dockerfile`. **The Dockerfile has never been built** (no Docker on the dev machine); build it once and fix what fails.
2. Frontend: `NEXT_PUBLIC_API_URL` = backend URL (no trailing `/`), then **redeploy** (it is baked in at build time).
3. Wake the free Render backend (`<backend URL>/health`) and run one real job on the live URLs. Check that the files are in the bucket (`jobs/<id>/...`).
4. Free-tier caveat: a job running when it restarts or sleeps is reported as an error after 45 minutes (`STALE_JOB_MINUTES`). Keep the page open while a job runs.

## 5. Questions and risks that can block the submission

- **S0-6, still unanswered:** are third-party search APIs (Tavily) allowed by the Official Rules, what are the credit limits, can Serverless host FastAPI? Read the rules and write the answers in `context/epic.md`. If search is not allowed, do not use `SEARCH_PROVIDER=fake` in the demo (its results are not real sources); instead leave the web search out, and the notes then rest on the lecture alone.
- **Next.js 16.4.0 is reported as having a known security vulnerability** by its own build output. Upgrading was not done (nobody asked); decide whether to upgrade before submission, then rebuild.
- **Sample lecture data is hand-written**, not model output. The page says so. Do not present it as a result of the models.
- **No real-model numbers exist yet.** The README and the Devpost text must only use numbers from a real run (the stats panel and `judge_report.json` / `pipeline_report.json` hold them).
- **Git working tree:** `CLAUDE.md` is modified, `context/README.md` and `context/project.md` are deleted, and `context/epic.md` and `context/idea.md` are untracked. They were like this before our work and are **not** in the pushed commits. Decide whether to commit them. `context/epic.md` has the up-to-date story statuses.

## 6. Epic 10, remaining (due Oct 29)

- S10-1 friend testing: 3-5 people try their own lectures (transcripts, or audio on the GPU machine) and fill in a short form.
- S10-2 README: finish it (Nemotron usage, Token Factory, other Nebius tools, Parakeet CC BY 4.0 credit, the sections marked _TBD_), and replace "not proven live" notes with the real results.
- S10-3 demo video: public YouTube, 3 minutes or less, showing the app, Token Factory and the models. Wake the backend first.
- S10-4 Devpost write-up: what / why / how, with measured numbers and our feedback on the tools.
- S10-5 final checklist against the Official Rules, then submit on Oct 29 (one day of buffer).
