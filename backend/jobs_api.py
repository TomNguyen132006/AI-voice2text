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
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Response, UploadFile

import export
import pipeline
import stats
from schemas import Job, JobResponse, Section, Statement
from storage import StorageError, get_storage, job_key, load_json, save_json

router = APIRouter()

SAMPLES = Path(__file__).parent / "samples"
SAMPLE_JOB_ID = "job_sample"
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB") or 500)
DOWNLOADS = {
    "transcript.txt": "text/plain; charset=utf-8",
    "notes.md": "text/markdown; charset=utf-8",
    "slides.pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    export.ZIP_NAME: "application/zip",
}


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
    limit = MAX_UPLOAD_MB * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status_code=413, detail=f"The file is larger than {MAX_UPLOAD_MB} MB.")
    if not data:
        raise HTTPException(status_code=400, detail="The file is empty.")
    storage = get_storage()
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    job = pipeline.create_job(job_id, name, data, storage)
    background.add_task(pipeline.run_pipeline, job_id, name, storage)
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
    return Response(content=data, media_type=DOWNLOADS[name], headers={"Content-Disposition": f'attachment; filename="{name}"'})
