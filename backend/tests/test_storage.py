"""Tests for storage.py (S1-4). The s3 backend uses a fake client: no network, no keys."""
import pytest

import storage
from schemas import Segment
from storage import LocalStorage, S3Storage, StorageError, job_key, load_transcript, save_transcript

SEGMENTS = [
    Segment(id="seg_0001", start=0.0, end=12.4, text="Today we talk about gradient descent."),
    Segment(id="seg_0002", start=12.4, end=27.9, text="Hàm mất mát đo sai số."),
]


class FakeS3Client:
    class NoSuchKey(Exception):
        response = {"Error": {"Code": "NoSuchKey"}}

    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body):
        self.objects[(Bucket, Key)] = Body

    def get_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise self.NoSuchKey()
        body = self.objects[(Bucket, Key)]
        return {"Body": type("Body", (), {"read": lambda self: body})()}


def test_local_transcript_round_trip(tmp_path):
    store = LocalStorage(tmp_path)

    save_transcript("job_ab12", SEGMENTS, store)

    assert (tmp_path / "jobs" / "job_ab12" / "transcript.json").is_file()
    assert load_transcript("job_ab12", store) == SEGMENTS


def test_s3_transcript_round_trip_uses_job_key():
    client = FakeS3Client()
    store = S3Storage(bucket="lectures", client=client)

    save_transcript("job_ab12", SEGMENTS, store)

    assert list(client.objects) == [("lectures", "jobs/job_ab12/transcript.json")]
    assert load_transcript("job_ab12", store) == SEGMENTS


@pytest.mark.parametrize("store_factory", [lambda tmp: LocalStorage(tmp), lambda tmp: S3Storage("b", FakeS3Client())])
def test_missing_transcript_raises_file_not_found(tmp_path, store_factory):
    with pytest.raises(FileNotFoundError):
        load_transcript("job_none", store_factory(tmp_path))


@pytest.mark.parametrize("bad_id", ["../etc", "job/1", "", "job 1"])
def test_bad_job_ids_are_rejected(bad_id):
    with pytest.raises(StorageError, match="invalid job id"):
        job_key(bad_id, "transcript.json")


def test_local_storage_refuses_keys_outside_its_folder(tmp_path):
    with pytest.raises(StorageError, match="outside"):
        LocalStorage(tmp_path / "data").save_bytes("../escape.txt", b"x")


def test_backend_choice_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    assert isinstance(storage.get_storage(), LocalStorage)

    monkeypatch.setenv("STORAGE_BACKEND", "dropbox")
    with pytest.raises(StorageError, match="unknown STORAGE_BACKEND"):
        storage.get_storage()

    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.delenv("S3_BUCKET", raising=False)
    with pytest.raises(StorageError, match="S3_BUCKET"):
        storage.get_storage()
