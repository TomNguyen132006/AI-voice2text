"""The real Job API (S7-2): same request and response format as the mock (mock_jobs.py), now backed by the pipeline.

    POST /jobs                       upload an audio/video file or a .txt/.srt/.vtt transcript; returns the queued job.
                                     The pipeline runs in a FastAPI background task (fallback from the plan: no Nebius job runner yet).
    POST /jobs/sample                a finished job from hand-written sample data (no model call), for the "Try a sample" button
    GET  /jobs/{id}                  status + stage; once done also the statements, the sections and a summary
    GET  /jobs/{id}/stats            calls, tokens, time, cost per stage and the judge's rejections (S8-2)
    GET  /jobs/{id}/files/{name}     transcript.txt, notes.md, slides.pptx, or all.zip (the three files together)

Job state lives in the job's storage (jobs/{id}/job.json), so it survives a restart and works with several workers.
"""
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Response, UploadFile

import export
import pipeline
import stats
import transcribe
import transcript_import
from schemas import Job, JobResponse, Section, Statement
from storage import StorageError, get_storage, job_key, load_json, save_json

router = APIRouter()

SAMPLES = Path(__file__).parent / "samples"
SAMPLE_JOB_ID = "job_sample"


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name) or default)
    except ValueError:
        return default


# Abuse limits for POST /jobs (the deployed server is public and every job spends money). A developer can raise
# them in .env. The two job counters live in this process only: fine for one server process (Render free).
MAX_UPLOAD_MB = _int_env("MAX_UPLOAD_MB", 10)
MAX_CONCURRENT_JOBS = _int_env("MAX_CONCURRENT_JOBS", 2)
MAX_JOBS_PER_DAY = _int_env("MAX_JOBS_PER_DAY", 10)
READ_CHUNK_BYTES = 1024 * 1024
# A job that was saved this long ago and is still queued/running lost its server (restart, free-tier sleep): report an error.
STALE_JOB_SEC = float(os.getenv("STALE_JOB_MINUTES") or 45) * 60
STALE_MESSAGE = "The server restarted or stopped while this job was running. Please upload the file again."
DOWNLOADS = {
    "transcript.txt": "text/plain; charset=utf-8",
    "notes.md": "text/markdown; charset=utf-8",
    "slides.pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    export.ZIP_NAME: "application/zip",
}


def _utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


class JobLimiter:
    """Counts jobs that are running now and jobs accepted today (UTC). A slot is reserved BEFORE the upload is
    read and given back with release() if the job never started (bad file, too big, storage error), so only
    jobs that were really queued use up the day's count. A job that starts and then fails in the pipeline stays
    counted (it may already have spent money)."""

    def __init__(self):
        self._lock = threading.Lock()
        self.running = 0
        self.day = _utc_today()
        self.today = 0

    def reserve(self) -> str | None:
        """None = slot reserved. Otherwise the 429 message."""
        with self._lock:
            if self.day != _utc_today():
                self.day, self.today = _utc_today(), 0
            if self.today >= MAX_JOBS_PER_DAY:
                return f"The daily limit of {MAX_JOBS_PER_DAY} lectures for this server has been reached. Try again tomorrow."
            if self.running >= MAX_CONCURRENT_JOBS:
                return "Server busy, try again in a few minutes."
            self.running += 1
            self.today += 1
            return None

    def release(self) -> None:
        """The reserved job never started."""
        with self._lock:
            self.running = max(0, self.running - 1)
            self.today = max(0, self.today - 1)

    def finished(self) -> None:
        with self._lock:
            self.running = max(0, self.running - 1)


limiter = JobLimiter()


def _run_limited(job_id: str, name: str) -> None:
    try:
        pipeline.run_pipeline(job_id, name)
    finally:
        limiter.finished()


def _read_limited(file: UploadFile) -> bytes:
    """Read the upload in chunks and stop as soon as it is over the limit (never the whole file in memory)."""
    limit = MAX_UPLOAD_MB * 1024 * 1024
    parts, size = [], 0
    while chunk := file.file.read(READ_CHUNK_BYTES):
        size += len(chunk)
        if size > limit:
            raise HTTPException(status_code=413, detail=f"The file is larger than {MAX_UPLOAD_MB} MB.")
        parts.append(chunk)
    return b"".join(parts)


def _check_transcript_length(name: str, data: bytes) -> None:
    """Transcript uploads: count the characters after parsing. Unreadable files are left to the pipeline, which
    reports them on the job. (Audio is counted after transcription, in pipeline._transcribe_stage.)"""
    parse = transcript_import.PARSERS.get(Path(name).suffix.lower())
    if parse is None:
        return
    try:
        chars = sum(len(seg.text) for seg in parse(transcript_import._decode(data)))
    except Exception:
        return
    if chars > pipeline.max_transcript_chars():
        raise HTTPException(status_code=413, detail=pipeline.too_long_message(chars))


def _optional(job_id: str, name: str, storage, default):
    try:
        return load_json(job_key(job_id, name), storage)
    except FileNotFoundError:
        return default


def _summary(job_id: str, storage) -> dict:
    """A few numbers for the results page: from judge_report.json ("final") and pipeline_report.json."""
    final = _optional(job_id, "judge_report.json", storage, {}).get("final", {})
    report = _optional(job_id, "pipeline_report.json", storage, {})
    calls = report.get("model_calls", {})
    out = dict(final)
    if report:
        out.update(total_seconds=report.get("total_seconds"), model_calls=calls.get("total_calls"),
                   est_cost_usd=calls.get("total_est_cost_usd"), warnings=report.get("warnings", []))
    return out


def job_response(job_id: str, storage=None) -> JobResponse:
    """Raises FileNotFoundError / StorageError when there is no such job."""
    storage = storage or get_storage()
    job = pipeline.load_job(job_id, storage)
    if job.status in ("queued", "running") and job.updated_at and time.time() - job.updated_at > STALE_JOB_SEC:
        job = job.model_copy(update={"status": "error", "error": f"{job.stage}: {STALE_MESSAGE}"})
    if job.status != "done":
        return JobResponse(**job.model_dump())
    statements = [Statement(**s) for s in _optional(job_id, "notes_final.json", storage, [])]
    sections = [Section(**s) for s in _optional(job_id, "sections.json", storage, [])]
    summary = _optional(job_id, "sample.json", storage, None) or _summary(job_id, storage)
    return JobResponse(**job.model_dump(), statements=statements, sections=sections, summary=summary)


@router.post("/jobs", response_model=JobResponse)
def create_job(background: BackgroundTasks, file: UploadFile = File(...)):
    name = Path(file.filename or "").name
    suffix = Path(name).suffix.lower()
    if suffix not in pipeline.ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type {suffix or '(none)'}. Use one of: "
                                                    + ", ".join(sorted(pipeline.ALLOWED_EXTENSIONS)))
    if suffix in pipeline.AUDIO_EXTENSIONS:
        ok, reason = transcribe.audio_available()
        if not ok:
            raise HTTPException(status_code=400, detail=reason)
    busy = limiter.reserve()
    if busy:
        raise HTTPException(status_code=429, detail=busy)
    try:
        data = _read_limited(file)
        if not data:
            raise HTTPException(status_code=400, detail="The file is empty.")
        _check_transcript_length(name, data)
        storage = get_storage()
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        job = pipeline.create_job(job_id, name, data, storage)
    except BaseException:
        limiter.release()
        raise
    background.add_task(_run_limited, job_id, name)
    return JobResponse(**job.model_dump())


@router.post("/jobs/sample", response_model=JobResponse)
def create_sample_job():
    """A finished job made from backend/samples/ (hand-written, NOT model output). Costs nothing and takes a moment."""
    storage = get_storage()
    for source, target in [("transcript.json", "transcript.json"), ("sections.json", "sections.json"),
                           ("statements.json", "notes.json"), ("statements.json", "notes_final.json"), ("slides.json", "slides.json")]:
        save_json(job_key(SAMPLE_JOB_ID, target), json.loads((SAMPLES / source).read_text(encoding="utf-8")), storage)
    save_json(job_key(SAMPLE_JOB_ID, "sample.json"), {"sample": True}, storage)
    export.export_job(SAMPLE_JOB_ID, storage)
    pipeline.save_job(Job(id=SAMPLE_JOB_ID, status="done", stage="done", outputs=pipeline.output_urls(SAMPLE_JOB_ID)), storage)
    return job_response(SAMPLE_JOB_ID, storage)


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str):
    try:
        return job_response(job_id)
    except (FileNotFoundError, StorageError):
        raise HTTPException(status_code=404, detail="Job not found")


@router.get("/jobs/{job_id}/stats")
def get_stats(job_id: str):
    """Numbers for the stats panel: calls, tokens, time and cost per stage, judge rejections. {"available": false} if none yet."""
    try:
        pipeline.load_job(job_id)
        return stats.job_stats(job_id)
    except (FileNotFoundError, StorageError):
        raise HTTPException(status_code=404, detail="Job not found")


@router.get("/jobs/{job_id}/files/{name}")
def download(job_id: str, name: str):
    if name not in DOWNLOADS:
        raise HTTPException(status_code=404, detail="No such file")
    storage = get_storage()
    try:
        job = pipeline.load_job(job_id, storage)
        if job.status != "done":
            raise HTTPException(status_code=409, detail="The job is not finished yet")
        if name == export.ZIP_NAME:
            data = export.build_zip({n: storage.load_bytes(job_key(job_id, n)) for n in export.FILES.values()})
        else:
            data = storage.load_bytes(job_key(job_id, name))
    except (FileNotFoundError, StorageError):
        raise HTTPException(status_code=404, detail="File not found")
    return Response(content=data, media_type=DOWNLOADS[name], headers={"Content-Disposition": f'attachment; filename="lecturesque-{name}"'})
