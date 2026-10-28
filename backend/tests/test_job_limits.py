"""Abuse limits of POST /jobs (hardening): size, transcript length, concurrent jobs, jobs per day. No network, no keys."""
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

import jobs_api
import pipeline
import transcribe
from schemas import Segment
from storage import get_storage

SRT = "1\n00:00:00,000 --> 00:00:05,000\n{}\n"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setattr(jobs_api, "limiter", jobs_api.JobLimiter())
    monkeypatch.setattr(jobs_api, "MAX_CONCURRENT_JOBS", 2)
    monkeypatch.setattr(jobs_api, "MAX_JOBS_PER_DAY", 10)
    monkeypatch.setattr(pipeline, "run_pipeline", lambda job_id, name, storage=None: None)
    app = FastAPI()
    app.include_router(jobs_api.router)
    return TestClient(app)


def upload(client, data=SRT.format("hello").encode(), name="lecture.srt"):
    return client.post("/jobs", files={"file": (name, data)})


def srt_with_chars(n):
    return SRT.format("a" * n).encode()


# --- upload size -------------------------------------------------------------------------------------------

def test_upload_exactly_at_the_limit_is_accepted_and_one_byte_over_is_413(client, monkeypatch):
    monkeypatch.setattr(jobs_api, "MAX_UPLOAD_MB", 1)
    monkeypatch.setattr(jobs_api, "READ_CHUNK_BYTES", 1000)  # several chunks
    monkeypatch.setenv("MAX_TRANSCRIPT_CHARS", str(10 * 1024 * 1024))
    limit = 1024 * 1024
    head = SRT.format("").encode()
    exact = head + b"a" * (limit - len(head))
    assert len(exact) == limit
    assert upload(client, exact).status_code == 200
    over = upload(client, exact + b"a")
    assert over.status_code == 413 and "1 MB" in over.json()["detail"]


def test_upload_is_read_in_chunks_and_stops_at_the_limit(monkeypatch):
    monkeypatch.setattr(jobs_api, "MAX_UPLOAD_MB", 1)
    sizes = []

    class Reader:
        def __init__(self):
            self.left = 50 * 1024 * 1024  # a 50 MB upload

        def read(self, n=-1):
            sizes.append(n)
            n = min(n, self.left)
            self.left -= n
            return b"a" * n

    class FakeUpload:
        file = Reader()

    with pytest.raises(jobs_api.HTTPException) as e:
        jobs_api._read_limited(FakeUpload())
    assert e.value.status_code == 413
    assert all(0 < n <= jobs_api.READ_CHUNK_BYTES for n in sizes)  # never a read of "everything"
    assert len(sizes) <= 3  # stopped right after the limit; the other 49 MB were never read


# --- transcript length -------------------------------------------------------------------------------------

def test_transcript_exactly_at_the_limit_is_accepted_and_one_over_is_413(client, monkeypatch):
    monkeypatch.setenv("MAX_TRANSCRIPT_CHARS", "100")
    assert upload(client, srt_with_chars(100)).status_code == 200
    r = upload(client, srt_with_chars(101))
    assert r.status_code == 413
    assert "101" in r.json()["detail"] and "100" in r.json()["detail"]


def test_audio_transcript_over_the_limit_fails_the_job_at_the_transcribing_stage(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("MAX_TRANSCRIPT_CHARS", "100")
    storage = get_storage()
    pipeline.create_job("job_audio", "talk.mp3", b"x", storage)

    monkeypatch.setattr(transcribe, "transcribe", lambda path, engine=None: [Segment(id="seg_0001", start=0, end=5, text="a" * 101)])
    job = pipeline.run_pipeline("job_audio", "talk.mp3", storage)
    assert job.status == "error" and job.stage == "transcribing" and "limit is 100" in job.error

    monkeypatch.setattr(transcribe, "transcribe", lambda path, engine=None: [Segment(id="seg_0001", start=0, end=5, text="a" * 100)])
    pipeline._transcribe_stage("job_audio", "talk.mp3", storage, None)  # exactly at the limit: no error


# --- concurrent jobs ---------------------------------------------------------------------------------------

def test_job_over_the_concurrent_limit_is_429_busy(client):
    jobs_api.limiter.running = 2
    r = upload(client)
    assert r.status_code == 429 and "busy" in r.json()["detail"].lower()


def test_slots_up_to_the_concurrent_limit_are_reserved(client):
    jobs_api.limiter.running = 1
    assert jobs_api.limiter.reserve() is None  # the second slot, exactly at the limit
    assert jobs_api.limiter.reserve() is not None  # one over


def test_slot_is_freed_when_the_pipeline_finishes_or_crashes(client, monkeypatch):
    assert upload(client).status_code == 200
    assert jobs_api.limiter.running == 0  # the stub pipeline returned

    def boom(job_id, name, storage=None):
        raise RuntimeError("crash")

    monkeypatch.setattr(pipeline, "run_pipeline", boom)
    with pytest.raises(RuntimeError):
        upload(client)
    assert jobs_api.limiter.running == 0


# --- jobs per day ------------------------------------------------------------------------------------------

def test_daily_limit_exactly_at_and_one_over(client, monkeypatch):
    monkeypatch.setattr(jobs_api, "MAX_JOBS_PER_DAY", 3)
    assert [upload(client).status_code for _ in range(3)] == [200, 200, 200]
    r = upload(client)
    assert r.status_code == 429 and "daily limit of 3" in r.json()["detail"]


def test_daily_count_resets_on_a_new_utc_day(client, monkeypatch):
    monkeypatch.setattr(jobs_api, "MAX_JOBS_PER_DAY", 1)
    monkeypatch.setattr(jobs_api, "_utc_today", lambda: "2026-10-28")
    assert upload(client).status_code == 200
    assert upload(client).status_code == 429
    monkeypatch.setattr(jobs_api, "_utc_today", lambda: "2026-10-29")
    assert upload(client).status_code == 200


def test_a_job_that_fails_to_start_does_not_use_up_the_day(client, monkeypatch):
    """Chosen rule: the slot is reserved first and given back when the job never started (400, 413, storage error).
    Only a job that was really queued counts, even if its pipeline fails later."""
    monkeypatch.setattr(jobs_api, "MAX_JOBS_PER_DAY", 1)
    monkeypatch.setenv("MAX_TRANSCRIPT_CHARS", "100")
    assert upload(client, b"").status_code == 400  # empty
    assert upload(client, srt_with_chars(500)).status_code == 413  # transcript too long
    assert upload(client, name="notes.pdf").status_code == 400  # bad type
    with monkeypatch.context() as m:
        m.setattr(jobs_api, "MAX_UPLOAD_MB", 0)
        assert upload(client).status_code == 413  # too big

    def storage_down(*a, **k):
        raise OSError("disk full")

    with monkeypatch.context() as m:
        m.setattr(pipeline, "create_job", storage_down)
        with pytest.raises(OSError):
            upload(client)
    assert jobs_api.limiter.today == 0 and jobs_api.limiter.running == 0
    assert upload(client).status_code == 200  # the one allowed job of the day is still available


def test_a_job_rejected_as_busy_does_not_count_for_the_day(client):
    jobs_api.limiter.running = 2
    assert upload(client).status_code == 429
    assert jobs_api.limiter.today == 0


def test_sample_job_is_not_limited(client, monkeypatch):
    """POST /jobs/sample reads backend/samples/ and writes files: no model call, no Tavily call, so it is not counted."""
    monkeypatch.setattr(jobs_api, "MAX_JOBS_PER_DAY", 0)
    assert client.post("/jobs/sample").status_code == 200
