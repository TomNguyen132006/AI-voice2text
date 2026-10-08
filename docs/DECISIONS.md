# Decisions

Short record of team decisions: what we chose, when, why, and which files it affects.

## D1 — Lecture sources: the model picks a segment, code fills the times (S0-7)

- **Date:** Oct 7, 2026 — **final**
- **Decision:** For a lecture source the model outputs only `segment_id`
  (`LectureSourceDraft` inside a `StatementDraft`). Code copies `start`/`end` from the
  transcript with `fill_lecture_times`. An unknown `segment_id` is reported, never
  guessed (the pipeline retries once or drops the statement, see S4-3 / S5-3).
  `check_source_consistency` re-checks the result as a safety net.
- **Why:** a model can copy numbers wrongly (e.g. invent or shift a timestamp). The
  transcript is the single source of truth for times, so code looks them up instead.
- **Files:** `backend/schemas.py` (`LectureSourceDraft`, `StatementDraft`, `LectureSource`),
  `backend/sources.py` (`fill_lecture_times`, `check_source_consistency`),
  `backend/tests/test_sources.py`, `backend/validate_samples.py`.
