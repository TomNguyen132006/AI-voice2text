"""Mock Job API (S0-8): fake jobs that move through the stages on a timer.

Lets the frontend be built before the real pipeline exists. The real Job API
(S7-2) must keep the same request and response format.
"""
import json
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile

from schemas import JobOutputs, JobResponse, Statement

router = APIRouter()

SAMPLES = Path(__file__).parent / "samples"
STAGES = ["transcribing", "cleaning", "enriching", "writing", "judging", "exporting"]
SECONDS_PER_STAGE = 3

# job id -> creation time. In memory only: restarting the server forgets all jobs.
_jobs: dict[str, float] = {}


def _load_samples():
    statements = json.loads((SAMPLES / "statements.json").read_text(encoding="utf-8"))
    job = json.loads((SAMPLES / "job.json").read_text(encoding="utf-8"))
    return [Statement(**s) for s in statements], JobOutputs(**job["outputs"])


def _job_at(job_id: str, elapsed: float) -> JobResponse:
    """Work out the job's stage from how many seconds have passed since creation."""
    step = int(elapsed // SECONDS_PER_STAGE)
    if step < len(STAGES):
        return JobResponse(id=job_id, status="running", stage=STAGES[step])
    statements, outputs = _load_samples()
    return JobResponse(id=job_id, status="done", stage="done", outputs=outputs, statements=statements)


@router.post("/jobs", response_model=JobResponse)
def create_job(file: Optional[UploadFile] = File(None)):
    """Start a fake job. The uploaded file (optional in the mock) is ignored."""
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    _jobs[job_id] = time.time()
    return _job_at(job_id, 0)


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_at(job_id, time.time() - _jobs[job_id])
