"""Tests for jobs_api.py (S7-2). The pipeline itself is replaced by a stub here: no network, no keys."""
import io
import zipfile

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

import jobs_api
import pipeline
from schemas import Job
from storage import get_storage, job_key


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    calls = []
    monkeypatch.setattr(pipeline, "run_pipeline", lambda job_id, name, storage=None: calls.append((job_id, name)))
    app = FastAPI()
    app.include_router(jobs_api.router)
    c = TestClient(app)
    c.pipeline_calls = calls
    return c


def upload(client, name="lecture.srt", data=b"1\n00:00:00,000 --> 00:00:05,000\nhello\n"):
    return client.post("/jobs", files={"file": (name, data)})


def test_post_job_saves_upload_and_starts_pipeline(client):
    r = upload(client)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "queued" and body["stage"] == "queued" and body["id"].startswith("job_")
    assert client.pipeline_calls == [(body["id"], "lecture.srt")]
    assert get_storage().load_bytes(pipeline.upload_key(body["id"], "lecture.srt")).startswith(b"1\n")
    assert client.get(f"/jobs/{body['id']}").json()["status"] == "queued"


@pytest.mark.parametrize("name, data, status", [("notes.pdf", b"x", 400), ("lecture.mp3", b"", 400), ("../../evil.txt", b"hi", 200)])
def test_upload_checks(client, name, data, status):
    assert upload(client, name, data).status_code == status


def test_upload_too_large(client, monkeypatch):
    monkeypatch.setattr(jobs_api, "MAX_UPLOAD_MB", 0)
    assert upload(client).status_code == 413


def test_unknown_and_bad_job_ids_are_404(client):
    assert client.get("/jobs/job_nope").status_code == 404
    assert client.get("/jobs/..%2F..%2Fx").status_code == 404
    assert client.get("/jobs/job_nope/files/notes.md").status_code == 404


def test_running_and_error_jobs_have_no_results(client):
    storage = get_storage()
    pipeline.save_job(Job(id="job_run", status="running", stage="writing"), storage)
    pipeline.save_job(Job(id="job_err", status="error", stage="judging", error="judging: boom"), storage)
    assert client.get("/jobs/job_run").json()["stage"] == "writing"
    err = client.get("/jobs/job_err").json()
    assert err["status"] == "error" and err["error"] == "judging: boom" and err["statements"] == []
    assert client.get("/jobs/job_run/files/notes.md").status_code == 409


def test_sample_job_is_done_with_statements_and_downloads(client):
    r = client.post("/jobs/sample")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "done" and body["id"] == "job_sample" and len(body["statements"]) == 4
    assert [s["title"] for s in body["sections"]] == ["Loss and gradient", "Choosing the learning rate"]
    assert body["summary"] == {"sample": True}
    assert body["outputs"]["md"] == "/jobs/job_sample/files/notes.md"
    assert client.get(body["outputs"]["md"]).text.startswith("# Lecture notes")
    assert client.get(body["outputs"]["txt"]).text.startswith("[00:00]")
    pptx = client.get(body["outputs"]["pptx"])
    assert pptx.content[:2] == b"PK" and "attachment" in pptx.headers["content-disposition"]
    z = client.get("/jobs/job_sample/files/all.zip")
    assert sorted(zipfile.ZipFile(io.BytesIO(z.content)).namelist()) == ["notes.md", "slides.pptx", "transcript.txt"]
    assert client.get("/jobs/job_sample/files/secrets.json").status_code == 404


def test_done_job_summary_comes_from_the_reports(client):
    from storage import save_json

    storage = get_storage()
    for name, data in [("sections.json", []), ("notes_final.json", []),
                       ("judge_report.json", {"final": {"kept": 3, "fixed": 1, "dropped": 2}}),
                       ("pipeline_report.json", {"total_seconds": 12.5, "warnings": ["w"], "model_calls": {"total_calls": 9, "total_est_cost_usd": 0.5}})]:
        save_json(job_key("job_done", name), data, storage)
    pipeline.save_job(Job(id="job_done", status="done", stage="done", outputs=pipeline.output_urls("job_done")), storage)
    s = client.get("/jobs/job_done").json()["summary"]
    assert s == {"kept": 3, "fixed": 1, "dropped": 2, "total_seconds": 12.5, "model_calls": 9, "est_cost_usd": 0.5, "warnings": ["w"]}


def test_stats_endpoint(client):
    from storage import save_json

    assert client.get("/jobs/job_nope/stats").status_code == 404
    storage = get_storage()
    pipeline.save_job(Job(id="job_st", status="done", stage="done"), storage)
    assert client.get("/jobs/job_st/stats").json() == {"available": False}
    save_json(job_key("job_st", "pipeline_report.json"), {"total_seconds": 5.0, "seconds_per_stage": {"writing": 2.0}}, storage)
    save_json(job_key("job_st", "call_stats.json"), {"total": {"calls": 3}}, storage)
    body = client.get("/jobs/job_st/stats").json()
    assert body["available"] is True and body["total_seconds"] == 5.0 and body["calls"] == {"total": {"calls": 3}}
