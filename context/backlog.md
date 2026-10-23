# Backlog (Epics 0-10)

Source: `Nebius x NVIDIA Global AI Hackathon.docx` (not in git). Format per story:
goal, then "Done when" bullets.

## Due dates

| Epic | Due |
|---|---|
| 0 Setup and contracts | Oct 11 |
| 1 Transcription | Oct 16 |
| 2 Model layer, cleanup, topic split | Oct 18 |
| 3 Enrichment | Oct 21 |
| 4 Writing | Oct 23 |
| 5 Judge | Oct 25 |
| 6 Output files | Oct 26 (can start Oct 12 with sample data) |
| 7 Frontend | Oct 26 (can start Oct 12 with mock Job API) |
| 8 Logging | S8-1 Oct 18, S8-2 Oct 25 |
| 9 Deployment | Oct 26 |
| 10 Testing and submission | Oct 29 |

## Epic 0 — Setup and contracts (Oct 11)

- **S0-1 Token Factory access**: API key loaded from .env, no hard-coded secrets.
  - .env in .gitignore; .env.example lists variable names
- **S0-2 Nemotron smoke test**: one prompt to Nano, Super, Ultra.
  - Prints model, response time (ms), token counts for each
  - Model IDs and context limit (max tokens) per model in README
- **S0-3 Parakeet test**: run Parakeet on a ~10-min public lecture clip.
  - Know where it runs (Token Factory, Nebius, local) and how long it takes
  - 3 technical terms and 3 timestamps spot-checked against audio
  - Time limit 1 day; if it fails, switch to S1-3 fallback
- **S0-4 Repo scaffold**: public repo, frontend/ (Next.js + JS + Tailwind), backend/ (FastAPI), MIT license, README skeleton.
  - MIT license visible at top of repo page
  - Frontend from `npx create-next-app@latest frontend --js` (no tsconfig.json, .js/.jsx)
  - Backend deps in requirements.txt; ffmpeg noted as system requirement in README
- **S0-5 Hello-world deploy**: frontend + backend deployed with working /health call.
  - Public frontend URL shows a response from the backend
- **S0-6 Rules check**: written answers to open questions.
  - Answered: third-party search APIs allowed? Credit limits? Can Serverless host FastAPI?
- **S0-7 Data contracts**: all shared formats in one schemas.py (Pydantic) + one sample JSON each.
  - Segment {id, start, end, text}
  - Section {id, title, start, end, segment_ids}
  - Statement {id, section_id, text, sources: [lecture timestamp | web URL]}
  - Slide {section_id, title, bullets: [Statement], example, speaker_notes}
  - Job {id, status, stage, error, outputs: {txt, md, pptx}}
  - Samples in backend/samples/ (transcript, sections, statements, slides, job)
  - Changes to schemas.py after Oct 11 must be announced to the team
- **S0-8 Mock Job API**: POST /jobs and GET /jobs/{id} return fake data from samples/.
  - GET /jobs/{id} cycles through stages (transcribing -> ... -> done) on a timer
  - When done, returns sample statements and fake download links

## Epic 1 — Transcription (Oct 16)

- **S1-1 transcribe.py**: audio file -> segments with start/end.
  - Returns list of Segment
- **S1-2 Audio prep**: convert to 16 kHz mono WAV, split long files into chunks.
  - mp3, m4a, wav, mp4 work (ffmpeg); a 60-min file completes
  - Timestamps correct across chunk boundaries
- **S1-3 Transcript upload fallback**: accept .txt, .srt, .vtt instead of audio.
  - Same Segment format as S1-1
  - Required if S0-3 fails
- **S1-4 Transcript as source of truth**: raw transcript saved as JSON per job.
  - Saved to storage (Supabase or S3) at jobs/{id}/transcript.json
  - Local disk only during development

## Epic 2 — Model layer, cleanup, topic split (Oct 18)

- **S2-1 llm.py**: one `call_model(model, messages)` for all model calls.
  - Retries on timeouts or 5xx (max 3)
  - Model names from config
  - Build together with S8-1 (call log)
- **S2-2 clean.py**: Nano fixes misheard terms, removes fillers, keeps segment IDs.
  - Every cleaned segment keeps its original ID and times
  - No segment added or invented
- **S2-3 Topic split**: Nano groups segments into titled sections with time ranges.
  - Output list of Section, no gaps, no overlaps
- **S2-4 Long-transcript handling**: overlapping windows if transcript exceeds context; later steps per section.
  - Topic split sees whole lecture or overlapping windows
  - Gap finder, writing, judge run per section
  - 60-min lecture completes without context errors
- **S2-5 Golden test clip**: fixed clip with saved expected outputs.
  - Script runs pipeline on the clip and shows differences
- **Later items from Epic 2 (small, not for now)**:
  - Re-split sections flagged too long: run the topic split again on that section's segments (the 52-minute lecture gave 4 sections, 1419 s and 733 s flagged).
  - Cleaning prompt rule against replacing a valid technical word with a variant (seg_0018 "minima" -> "minimum" fails the golden check in 3 of 3 runs).
  - Open risk: where Parakeet runs in production (the deployed server has no GPU).
  - Open risk: whether third-party web search APIs are allowed for the web-sources step.

## Epic 3 — Enrichment (Oct 21)

- **S3-1 Gap finder**: Super lists terms/examples per section needing more explanation.
  - Returns JSON [{section_id, term, reason}]
- **S3-2 enrich.py search wrapper**: one function calls search API, returns {title, url, snippet}.
  - Provider (Tavily, Brave, Serper) chosen in config
  - Results saved to jobs/{id}/search.json (judge checks web sources came from our search)
  - Can start right after S0-6 (doesn't depend on Epic 2)
- **S3-3 Search cache**: cache results by query (save credits on re-runs).
- **S3-4 Search cap**: max searches per lecture.
  - Default cap (e.g. 15) configurable
- **S3-1 T10 (added Oct 22) Tighter search query**: change the gap-finder prompt so `query` = the term plus at most ONE word naming the lecture's field
  (e.g. "level set", "Hessian matrix"); model queries over-specify ("level set contour plot"), and "x star optimization" still returns boats/games.

## Epic 4 — Writing notes and slides (Oct 23)

- **S4-1 Notes writer**: Super writes short review notes per section using Statement schema.
- **S4-2 Slide writer**: Super produces slide content per section (title, bullets, example, speaker notes).
- **S4-3 JSON validation**: validate model output against schemas.py, one retry on failure.

## Epic 5 — Judge (Oct 25)

- **S5-1 judge.py**: Ultra (separate call) checks each statement: has a source, source supports it, doesn't contradict lecture.
  - Returns {statement_id, verdict, reason} for every statement
  - Can be built early using samples/statements.json
- **S5-2 Code checks first**: before Ultra: missing source, timestamp out of range, URL not in our search results.
- **S5-3 Fix-or-remove loop**: failed statement rewritten once by Super and re-judged; second failure drops it.
- **S5-4 Judge report**: saved verdict counts and rejection reasons (numbers for Devpost).

## Epic 6 — Output files (Oct 26)

- **S6-1 Transcript .txt**: cleaned transcript with [mm:ss] stamps.
- **S6-2 Notes .md**: timestamps and source links on each point.
- **S6-3 Slides .pptx**: python-pptx deck: title slide, 1+ slides per section, speaker notes, final sources slide.
  - Opens in PowerPoint and Google Slides
- **S6-4 Zip download**: one button downloads all three files as .zip.

## Epic 7 — Frontend (Oct 26)

- **S7-1 Upload page**: drag-and-drop with file type and size checks.
- **S7-2 Real Job API**: POST /jobs, GET /jobs/{id} connected to real pipeline (background).
  - Same response format as the mock
- **S7-3 Progress view**: poll job, show stages (transcribing -> cleaning -> enriching -> writing -> judging -> exporting).
- **S7-4 Results page**: notes with clickable sources and download buttons.
  - Lecture citation shows its timestamp; web citation opens its link
- **S7-5 Error states**: clear message when a stage fails (no endless spinner).
- **S7-6 Sample lecture button**: "Try a sample lecture" loads precomputed results.
- **S7-7 pipeline.py**: runs all steps in order (transcribe -> clean -> split -> enrich -> write -> judge -> export), updating job stage.
  - Each stage output saved to storage before next stage
  - On failure: status error, with stage name and message
  - Called by the real Job API (S7-2)

## Epic 8 — Logging and metrics

- **S8-1 Call log (Oct 18, with S2-1)**: every model call logged to JSONL (job, stage, model, tokens, ms).
- **S8-2 Stats view (Oct 25)**: per-job panel (calls, tokens, time, judge rejections by reason).

## Epic 9 — Deployment (Oct 26)

- **S9-1 Backend deploy**: backend on Nebius (or fallback host) with background jobs.
  - ffmpeg installed on the server
- **S9-2 Frontend deploy**: correct env variables and CORS to reach live backend.
- **S9-3 Secrets check**: no keys anywhere in git history.

## Epic 10 — Testing and submission (Oct 29)

- **S10-1 Friend testing**: 3-5 friends try it on their lectures and fill a short form.
- **S10-2 README**: setup, run, Nemotron usage, Token Factory, other Nebius tools, Parakeet CC BY 4.0 credit.
- **S10-3 Demo video**: public YouTube, 3 min or less, shows app, Token Factory, models.
- **S10-4 Devpost write-up**: what / why / how, measured numbers, tool feedback.
- **S10-5 Final checklist and submit**: Official Rules checklist, submit Oct 29 (deadline Oct 30 noon).


## Judge test cases (Epic 5) (added Oct 22)
Real cases from job_e2e_20261019_130712 (a lecture on optimization), described by segment id and wording because statement ids change on every notes run. Each should become a test for the judge (S5-2) and for the retry/drop rule (S5-3).
- **(a) Lecture source does not support the claim.** A statement says "the gradient points in the direction of steepest ascent" and cites `seg_0001`. That segment only says "Be sure to make some comments about the gradient and the Hessian and the role of convexity before we see the big ... crucial example", so it mentions the gradient in passing. Expected: not supported by the lecture source (the claim is only supported by a web page, if at all).
- **(b) Speech recognition (ASR) dropped words.** A statement says "x* = (0,0)" and cites `seg_0021`, whose text is "So the minimum point, x star, zero, of course." The speaker said "x star is zero zero of course". Expected: weakly supported / differs because of speech recognition, not "contradicts".
- **(c) ASR error changes the meaning.** A statement says "x1^2 + b x2^2" and cites `seg_0005`, whose text says "x1 squared was bx2 squared" ("was" instead of "plus"). Expected: weakly supported / differs because of speech recognition.
- **(d) Web statement true in general, but different from how the lecture uses the term.** A statement defines "pure quadratic" as f(x) = ax^2 + bx + c (from a web page), while the lecture means a quadratic form x^T S x with a symmetric matrix S (`seg_0005`). Expected: not a contradiction of a fact, but the judge must notice that the web definition does not match the lecture's meaning (flag, or "differs").

**Notes for the judge design:**
- For statements that are added from the web, ALSO check that they do not contradict the lecture text of the same section (not only that the web snippet says it).
- Allow a level between "supported" and "unsupported", for example "weakly supported / differs because of speech recognition", so cases (b) and (c) are not treated as contradictions.
- The ASR mistakes in (b) and (c) are in BOTH the original and the cleaned text (cleaning only removed "uh"; checked for seg_0005 and seg_0021), so the judge cannot fix them by reading the other version. Keep the timestamps so a human can re-listen.

## Epic 4 follow-ups (added at Epic 4 close; notes prompt v3 is the baseline, the judge measures quality from here)
- **Long sections need chunked writing or a re-split.** sec_03 of job_e2e_20261019_130712 is 9 minutes (75 segments): coverage 0.29 (22 of 75 segments cited), and its slide has only 2 bullets (level sets and convexity are in the speaker notes). Options: write the notes in chunks of consecutive segments, or split long sections again in the topic step (S2-3).
- **Statements that rest on the web only are too many and can conflict with the lecture.** In sec_01 they rose from 1 (v1) to 4 (v3); one is the "pure quadratic = ax^2+bx+c" definition that differs from the lecture's meaning (judge case d). Decide a limit, or let the judge handle it (see "Judge test cases").
- **Word-form match is loose:** "derivative" matches "derivation" under the 6-letter rule (they share "deriva"). Accepted, rare; the rule only decides whether a web-only note names a gap term.
- **Short, mostly set-up sections give process remarks.** sec_02 (12 segments, 1.5 minutes) mostly describes the setup of the example ("we can take steps of steepest descent", "the key question is how many iterations..."), so many of its notes are process remarks, not facts to learn. A rule such as "skip sections that teach nothing" or merging such a section into the next one is open.
- **Slide.example has no sources.** The example's sources are only written as text in the speaker notes; the structured link is `example_statement_id` in `slides_report.json`. Adding `example_sources` to `schemas.Slide` would be cleaner (needs a team announcement).
- **Lecturer wording is kept even when loose.** The lecturer calls the line 2x+5y=0 "the plane"; the notes say "plane" too (faithful). The judge should not treat this as an unsupported claim.
