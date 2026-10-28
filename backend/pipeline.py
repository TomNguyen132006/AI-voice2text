"""The whole pipeline for one job (S7-7): upload -> transcribe -> clean -> split -> gaps -> search -> notes -> judge/fix -> slides -> export.

run_pipeline(job_id) runs every stage in order. After each stage its files are already saved in the job's storage
(the stage modules do that), and jobs/{id}/job.json is updated, so GET /jobs/{id} can show the progress:

    stage (Job.stage)   what runs
    transcribing        audio -> Parakeet (transcribe.py), or a .txt/.srt/.vtt upload -> segments (transcript_import.py)
    cleaning            clean_job (Nano), split_job (Nano)
    enriching           gaps_job (Super), search_for_gaps (web search; a failure here is only a warning, notes then use the lecture alone)
    writing             notes_job (Super)
    judging             fix_job: judge (Ultra), rewrite once (Super), judge again -> notes_final.json
    exporting           slides_job (Super, from notes_final.json), then transcript.txt, notes.md, slides.pptx

If a stage raises, the job becomes status "error", stage = the stage that failed, error = "<stage>: <short message>".
The pipeline itself never raises. Extra files per job: upload/<name> (the uploaded file), job.json, pipeline_report.json.
"""
import os
import tempfile
import time
from pathlib import Path

import llm
import stats
from schemas import Job, JobOutputs
from storage import get_storage, job_key, load_json, save_json, save_transcript
from validate import _clip

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".mp4", ".webm", ".flac", ".ogg", ".aac", ".mov", ".mkv"}
TRANSCRIPT_EXTENSIONS = {".txt", ".srt", ".vtt"}
ALLOWED_EXTENSIONS = AUDIO_EXTENSIONS | TRANSCRIPT_EXTENSIONS
STAGES = ["transcribing", "cleaning", "enriching", "writing", "judging", "exporting"]
ERROR_MAX_CHARS = 300
DEFAULT_MAX_TRANSCRIPT_CHARS = 15000


def max_transcript_chars() -> int:
    """MAX_TRANSCRIPT_CHARS from the environment, read at every call so a .env change or a test takes effect."""
    try:
        return int(os.getenv("MAX_TRANSCRIPT_CHARS") or DEFAULT_MAX_TRANSCRIPT_CHARS)
    except ValueError:
        return DEFAULT_MAX_TRANSCRIPT_CHARS


def too_long_message(chars: int) -> str:
    return f"The transcript has {chars:,} characters; the limit is {max_transcript_chars():,}. Upload a shorter lecture."


def output_urls(job_id: str) -> JobOutputs:
    """Download paths (relative to the API root) of the three files."""
    return JobOutputs(**{kind: f"/jobs/{job_id}/files/{name}" for kind, name in
                         {"txt": "transcript.txt", "md": "notes.md", "pptx": "slides.pptx"}.items()})


def save_job(job: Job, storage=None) -> None:
    save_json(job_key(job.id, "job.json"), job.model_copy(update={"updated_at": time.time()}).model_dump(), storage)


def load_job(job_id: str, storage=None) -> Job:
    """Raises FileNotFoundError when the job does not exist."""
    return Job(**load_json(job_key(job_id, "job.json"), storage))


def upload_key(job_id: str, filename: str) -> str:
    return job_key(job_id, f"upload/{Path(filename).name}")


def create_job(job_id: str, filename: str, data: bytes, storage=None) -> Job:
    """Save the upload and a queued job. The caller starts run_pipeline afterwards."""
    storage = storage or get_storage()
    storage.save_bytes(upload_key(job_id, filename), data)
    job = Job(id=job_id, status="queued", stage="queued")
    save_job(job, storage)
    return job


def _transcribe_stage(job_id, filename, storage, engine):
    data = storage.load_bytes(upload_key(job_id, filename))
    suffix = Path(filename).suffix.lower()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"upload{suffix}"
        path.write_bytes(data)
        if suffix in TRANSCRIPT_EXTENSIONS:
            from transcript_import import import_transcript
            segments = import_transcript(path)
        else:
            from transcribe import transcribe
            segments = transcribe(path, engine=engine)
    if not segments:
        raise ValueError("no speech found in the file")
    chars = sum(len(s.text) for s in segments)
    if chars > max_transcript_chars():  # audio: the length is only known now (transcript uploads are checked at POST /jobs)
        raise ValueError(too_long_message(chars))
    save_transcript(job_id, segments, storage)


def _clean_stage(job_id, storage, client):
    import clean
    import topics
    clean.clean_job(job_id, storage=storage, client=client)
    topics.split_job(job_id, storage=storage, client=client)


def _enrich_stage(job_id, storage, client, provider, warnings):
    import enrich
    import gaps
    gaps.gaps_job(job_id, storage=storage, client=client)
    try:
        enrich.search_for_gaps(job_id, storage, provider=provider)
    except Exception as error:  # web search is optional: the notes can rest on the lecture alone
        save_json(job_key(job_id, "search.json"), [], storage)
        warnings.append(f"web search skipped: {_clip(error)}")


def _write_stage(job_id, storage, client):
    import notes
    notes.notes_job(job_id, storage=storage, client=client)


def _judge_stage(job_id, storage, client):
    import fix
    fix.fix_job(job_id, "notes.json", storage=storage, client=client)


def _export_stage(job_id, storage, client):
    import export
    import slides
    slides.slides_job(job_id, storage=storage, client=client, statements_file="notes_final.json")
    export.export_job(job_id, storage)


def run_pipeline(job_id: str, filename: str, storage=None, client=None, engine=None, provider=None) -> Job:
    """Run every stage for an uploaded file. Never raises: a failure becomes a Job with status "error"."""
    storage = storage or get_storage()
    warnings: list[str] = []
    steps = [
        ("transcribing", lambda: _transcribe_stage(job_id, filename, storage, engine)),
        ("cleaning", lambda: _clean_stage(job_id, storage, client)),
        ("enriching", lambda: _enrich_stage(job_id, storage, client, provider, warnings)),
        ("writing", lambda: _write_stage(job_id, storage, client)),
        ("judging", lambda: _judge_stage(job_id, storage, client)),
        ("exporting", lambda: _export_stage(job_id, storage, client)),
    ]
    seconds: dict[str, float] = {}
    started = time.time()
    job = Job(id=job_id, status="running", stage="queued")
    for stage, run in steps:
        job = Job(id=job_id, status="running", stage=stage)
        save_job(job, storage)
        began = time.time()
        try:
            run()
        except Exception as error:
            seconds[stage] = round(time.time() - began, 1)
            job = Job(id=job_id, status="error", stage=stage, error=f"{stage}: {_clip(error) or type(error).__name__}"[:ERROR_MAX_CHARS])
            save_job(job, storage)
            _save_report(job_id, storage, job, seconds, started, warnings)
            return job
        seconds[stage] = round(time.time() - began, 1)
    job = Job(id=job_id, status="done", stage="done", outputs=output_urls(job_id))
    save_job(job, storage)
    _save_report(job_id, storage, job, seconds, started, warnings)
    return job


def _save_report(job_id, storage, job, seconds, started, warnings) -> None:
    try:
        save_json(job_key(job_id, "pipeline_report.json"), {
            "job_id": job_id, "status": job.status, "stage": job.stage, "error": job.error, "warnings": warnings,
            "seconds_per_stage": seconds, "total_seconds": round(time.time() - started, 1),
            "model_calls": llm.summarize_log(job_id=job_id),
        }, storage)
        save_json(job_key(job_id, "call_stats.json"), stats.call_stats(job_id), storage)  # survives a restart (the log is local)
    except Exception:  # the report is a bonus: it must never hide the real result
        pass
