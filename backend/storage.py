"""Job file storage (S1-4): one place where every pipeline step saves and loads
its files, under jobs/{job_id}/...

The raw transcript is saved once per job as jobs/{id}/transcript.json, so cleanup
and the judge can always compare against what was actually said.

The backend is pluggable (STORAGE_BACKEND in .env):
- "local": files under backend/.data/ (or STORAGE_DIR). Dev only: deployed
  servers (Render) lose local files on restart.
- "s3": any S3-compatible bucket, e.g. Nebius Object Storage (S3_ENDPOINT_URL,
  S3_REGION, S3_BUCKET, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY).
"""
import json
import os
import re
from pathlib import Path

from schemas import Segment

try:  # python-dotenv is not installed in the Parakeet venv; env vars still work there
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

DEFAULT_LOCAL_DIR = Path(__file__).parent / ".data"
_JOB_ID = re.compile(r"^[A-Za-z0-9_-]+$")


class StorageError(Exception):
    """Storage could not be used (bad config, bad key)."""


class LocalStorage:
    """Files on this machine's disk. Dev only."""

    def __init__(self, root=None):
        self.root = Path(root or os.getenv("STORAGE_DIR") or DEFAULT_LOCAL_DIR).resolve()

    def _path(self, key) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise StorageError(f"key {key!r} points outside the storage folder")
        return path

    def save_bytes(self, key, data: bytes):
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def load_bytes(self, key) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise FileNotFoundError(key)
        return path.read_bytes()


class S3Storage:
    """An S3-compatible bucket (Nebius Object Storage, AWS S3, ...)."""

    def __init__(self, bucket=None, client=None):
        self.bucket = bucket or os.getenv("S3_BUCKET")
        if not self.bucket:
            raise StorageError("S3_BUCKET is not set")
        if client is None:
            import boto3  # only needed for the s3 backend

            client = boto3.client(
                "s3",
                endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,
                region_name=os.getenv("S3_REGION") or None,
            )  # keys come from AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
        self.client = client

    def save_bytes(self, key, data: bytes):
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)

    def load_bytes(self, key) -> bytes:
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except Exception as e:
            code = getattr(e, "response", {}).get("Error", {}).get("Code")
            if code in ("NoSuchKey", "404"):
                raise FileNotFoundError(key) from e
            raise


BACKENDS = {"local": LocalStorage, "s3": S3Storage}


def get_storage():
    name = (os.getenv("STORAGE_BACKEND") or "local").strip().lower()
    if name not in BACKENDS:
        raise StorageError(f"unknown STORAGE_BACKEND {name!r}, use one of {sorted(BACKENDS)}")
    return BACKENDS[name]()


def job_key(job_id, name) -> str:
    """Key of a job's file, e.g. job_key("job_ab12", "transcript.json") -> "jobs/job_ab12/transcript.json"."""
    if not _JOB_ID.match(str(job_id)):
        raise StorageError(f"invalid job id {job_id!r}")
    return f"jobs/{job_id}/{name}"


def save_json(key, data, storage=None):
    storage = storage or get_storage()
    storage.save_bytes(key, json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8"))


def load_json(key, storage=None):
    storage = storage or get_storage()
    return json.loads(storage.load_bytes(key).decode("utf-8"))


def save_transcript(job_id, segments: list[Segment], storage=None):
    """Save the raw transcript (from transcribe() or import_transcript()) for a job."""
    save_json(job_key(job_id, "transcript.json"), [s.model_dump() for s in segments], storage)


def load_transcript(job_id, storage=None) -> list[Segment]:
    return [Segment(**s) for s in load_json(job_key(job_id, "transcript.json"), storage)]
