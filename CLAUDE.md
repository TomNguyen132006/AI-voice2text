# Nebius x NVIDIA Global AI Hackathon — Lecture-to-Study-Materials

## Project context
- **App:** user uploads a lecture recording -> Parakeet (speech-to-text) -> Nemotron
  Nano/Super/Ultra via Nebius Token Factory -> web search enrichment -> notes (.md),
  slides (.pptx), transcript (.txt). An Ultra "judge" checks every statement has a
  source (lecture timestamp or web link) and does not contradict the lecture.
- **Stack:** Next.js (JavaScript, no TypeScript) + Tailwind in `frontend/`; Python +
  FastAPI in `backend/`; `openai` Python library (no agent framework); python-pptx;
  Supabase or S3; Vercel + Nebius (fallback Render/Railway). Public repo, MIT license.
- **Backlog:** `Nebius x NVIDIA Global AI Hackathon.docx` (Epics 0-10).
- **Current epic:** Epic 0 — Setup and contracts (due Oct 11), stories S0-1 to S0-8.
  Epic 0 tasks are listed in `PROGRESS.local.md` and in the .docx.
- **Suggested order:** S0-1 -> S0-4 -> S0-2 and S0-6 -> S0-3 -> S0-7 -> S0-8 -> S0-5.
  S0-3 has a 1-day limit; if Parakeet fails, use the S1-3 fallback (transcript upload).

## Rules for working with Tom (beginner, learning-first)

### Language
- Explain in Vietnamese. Keep technical terms in English with a short Vietnamese
  explanation the first time, e.g. "environment variable (biến môi trường)".
- Code, commands, file names and commit messages stay in English.

### Workflow (autonomous, report after each task)
- ONE task at a time, in order, but do NOT wait for "next" between tasks: after a
  task, write the report, update `PROGRESS.local.md`, then start the next unblocked
  task automatically.
- For each task:
  1. Before: one or two lines saying what you are about to do and why.
  2. Do the task yourself.
  3. After: a SHORT report in Vietnamese: what changed (files, commands and what
     each command does), why it works, how Tom can check it (a command or a place
     to look), and a common mistake to avoid.
- No comprehension questions after tasks.
- STOP and wait for Tom only when:
  - a step needs Tom (create an account, billing, copy an API key from a website,
    a decision, asking the team or organizers) — say exactly what to do/click;
  - something fails or looks risky;
  - a story is finished — show its "Done when" checklist, checked item by item.

### Team rules
- Trunk-based development: small changes, `git pull` often, no new branch unless Tom
  says so (if needed: `feature/Story#_abcxyz`, and tell the team first).
- Commit format: `Story # | Dev name | Brief explanation`. Tom's dev name is **Tom**.
  Always include story ID and task, e.g. `Story S0-1 T2 | Tom | Create .env`.
  Commit and push yourself (no need to wait for Tom's OK), always `git pull`
  before pushing.
- Security (repo is PUBLIC): never put real keys in code or git, never print them.
  Before EVERY commit, run `git status` and `git diff --staged` and check for
  secrets. If anything looks like a secret or something unexpected is staged, do
  NOT commit: STOP and tell Tom.
- Money: never run anything that costs money (Nebius AI Cloud, paid API calls beyond
  what Tom agreed, paid plans) without asking Tom first. Keep model test calls minimal.
- Downloads/installs: before ANY command that downloads or installs something
  (`curl | sh`, `pip`/`uv` install, `apt`, `npm install`, model or file downloads), show
  the exact command, what it will change (files, folders, shell config), disk size,
  admin rights / restart needs, then wait for Tom's explicit "go". "Continue", "next" or
  "OK" for a plan does NOT count as permission to install. One install per "go" unless
  Tom approves several by name. "Wait for my go" = do NOT start the command until Tom
  replies. If the command must change (e.g. a fix after a failure), ask for a new "go".
- Honesty: never invent model IDs, URLs or API behavior. Check official docs or say
  "I don't know".

## Session-start routine (run EVERY time Tom says "start session")
1. Run `git status`. If there are uncommitted changes, tell Tom first and ask before pulling.
2. After Tom confirms, run `git pull --rebase`.
3. Read `PROGRESS.local.md` (create it if missing).
4. Run `git log <last_seen_commit>..HEAD --pretty="%h | %an | %s"` to list new commits
   since the last session (if there is no last_seen_commit, show the last 20).
5. Parse the `Story ... | Dev | ...` messages. For each teammate commit, check
   `git show --stat` and explain in Vietnamese: which story/task they probably did,
   which files changed, and what it means for Tom's work. If a commit doesn't follow
   the format, say so; don't guess silently.
6. Update "Team status" in `PROGRESS.local.md` and set `last_seen_commit` to current HEAD.
7. Skip tasks already done (verify the actual files, not only the commit message).
   Say which task is next and ask "Continue with <story> <task>?"
8. Warn Tom if a teammate's change affects Tom's work (e.g. `schemas.py` changed).
9. The first time only: give a 5-line summary of what Epic 0 is about.

**After EVERY finished task:** update `PROGRESS.local.md` (tick the task, current
position, last commit hash, 2-3 lines of what Tom learned or finds confusing).
