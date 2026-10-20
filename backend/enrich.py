"""Web search for the gaps (S3-2 search wrapper, S3-3 cache, S3-4 cap).

search(query, ...) -> [{"title", "url", "snippet"}]. Providers sit behind one small interface
(name + search(query, max_results, depth)), so Brave or Serper can be added next to Tavily.
URLs are kept EXACTLY as the provider returned them: the judge later checks that a web source
came from this file.

Files per job:
    jobs/{id}/search.json         one entry per search: {query, term, section_id, provider, timestamp,
                                  cached, results} (cache hits are recorded too)
    jobs/{id}/search_report.json  searches made, cache hits, skipped (cap), errors, provider calls
Cache (shared by all jobs): backend/.data/search_cache/ (SEARCH_CACHE_DIR to change), ignored by git.

Usage (from backend/):  python -m enrich <job_id>    (SEARCH_PROVIDER=fake runs without network or key)
"""
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx2 as httpx  # openai 3.x ships httpx2 (no plain httpx in this venv)

import search_config as cfg
from storage import DEFAULT_LOCAL_DIR, job_key, load_json, save_json
from topics import load_sections


class SearchError(Exception):
    """kind: timeout | network | server | rate_limit | quota | auth | client | no_key | bad_reply."""

    def __init__(self, message, *, kind, status_code=None, attempts=1):
        super().__init__(message)
        self.kind, self.status_code, self.attempts = kind, status_code, attempts


_sleep = time.sleep  # tests replace this
_now = time.time


# ---------------------------------------------------------------- providers

class TavilyProvider:
    name = "tavily"

    def __init__(self, client=None):
        self._client = client

    def _http(self):
        if self._client is None:
            self._client = httpx.Client()
        return self._client

    def search(self, query: str, max_results: int, depth: str) -> list[dict]:
        key = os.getenv(cfg.TAVILY_KEY_ENV, "").strip()
        if not key:
            raise SearchError(f"{cfg.TAVILY_KEY_ENV} is not set", kind="no_key", attempts=0)
        body = {
            "query": query, "search_depth": depth, "max_results": max_results,
            "include_answer": False, "include_raw_content": False, "include_images": False,
        }
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        data = self._post(body, headers)
        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list):
            raise SearchError("reply has no 'results' list", kind="bad_reply")
        out = []
        for r in results:
            url = r.get("url") if isinstance(r, dict) else None
            if not isinstance(url, str) or not url:
                continue  # a result without a url cannot be a source
            out.append({"title": r.get("title") or "", "url": url, "snippet": r.get("content") or ""})
        return out

    def _post(self, body: dict, headers: dict):
        """POST with the retry rules. Error messages never contain the headers (the key)."""
        rate_limited = False
        for attempt in range(1, cfg.SEARCH_MAX_RETRIES + 2):
            try:
                response = self._http().post(
                    cfg.TAVILY_URL, json=body, headers=headers, timeout=cfg.SEARCH_TIMEOUT_SEC)
            except httpx.TimeoutException:
                kind, status = "timeout", None
            except httpx.TransportError:
                kind, status = "network", None
            else:
                status = response.status_code
                if status == 200:
                    try:
                        return response.json()
                    except ValueError:
                        raise SearchError("reply is not JSON", kind="bad_reply", attempts=attempt) from None
                if status in (432, 433):  # plan limit: retrying cannot help
                    raise SearchError("plan limit exceeded", kind="quota", status_code=status, attempts=attempt)
                if status == 429:
                    if rate_limited:
                        raise SearchError("rate limited", kind="rate_limit", status_code=429, attempts=attempt)
                    rate_limited = True
                    _sleep(_retry_after(response))
                    continue
                if status < 500:
                    raise SearchError(
                        f"request rejected (HTTP {status})", status_code=status, attempts=attempt,
                        kind="auth" if status == 401 else "client",
                    )
                kind = "server"
            if attempt > cfg.SEARCH_MAX_RETRIES:
                raise SearchError(f"search failed after {attempt} attempts ({kind})", kind=kind,
                                  status_code=status, attempts=attempt)
            _sleep(cfg.RETRY_WAIT_BASE_SEC * 2 ** (attempt - 1))
        raise SearchError("rate limited", kind="rate_limit", status_code=429)  # the last attempt was a 429


def _retry_after(response) -> float:
    try:
        wait = float(response.headers.get("retry-after"))
    except (TypeError, ValueError):
        wait = cfg.RATE_LIMIT_DEFAULT_WAIT_SEC
    return min(max(wait, 0.0), cfg.RETRY_AFTER_CAP_SEC)


class FakeProvider:
    """No network, no key. Deterministic results; self.calls lists every query that reached it."""

    name = "fake"

    def __init__(self):
        self.calls: list[str] = []

    def search(self, query: str, max_results: int, depth: str) -> list[dict]:
        self.calls.append(query)
        slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-") or "empty"
        return [
            {"title": f"Fake result {i} for {query}", "url": f"https://example.com/fake/{slug}/{i}",
             "snippet": f"Fake snippet {i} about {query}."}
            for i in range(1, min(max_results, 3) + 1)
        ]


PROVIDERS = {"tavily": TavilyProvider, "fake": FakeProvider}


def get_provider(name: str | None = None):
    name = (name or os.getenv("SEARCH_PROVIDER") or cfg.DEFAULT_PROVIDER).strip().lower()
    if name not in PROVIDERS:
        raise ValueError(f"unknown SEARCH_PROVIDER {name!r}, use one of {sorted(PROVIDERS)}")
    return PROVIDERS[name]()


# ---------------------------------------------------------------- cache (S3-3)

def normalize_query(query: str) -> str:
    return " ".join(query.lower().split())


class SearchCache:
    """One JSON file per (provider, normalized query, max_results, depth). Errors are never stored;
    a missing, corrupt or expired file is simply a miss."""

    def __init__(self, directory=None, ttl_days: float | None = None):
        self.dir = Path(directory or os.getenv("SEARCH_CACHE_DIR") or DEFAULT_LOCAL_DIR / "search_cache")
        self.ttl_sec = (cfg.SEARCH_CACHE_TTL_DAYS if ttl_days is None else ttl_days) * 86400

    def _path(self, provider: str, query: str, max_results: int, depth: str) -> Path:
        raw = "|".join([provider, normalize_query(query), str(max_results), depth])
        return self.dir / (hashlib.sha256(raw.encode("utf-8")).hexdigest() + ".json")

    def get(self, provider, query, max_results, depth) -> list[dict] | None:
        try:
            saved = json.loads(self._path(provider, query, max_results, depth).read_text(encoding="utf-8"))
            if _now() - float(saved["stored_at"]) > self.ttl_sec:
                return None
            results = saved["results"]
            if not isinstance(results, list) or not all(isinstance(r, dict) and r.get("url") for r in results):
                return None
            return results
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def put(self, provider, query, max_results, depth, results: list[dict]) -> None:
        path = self._path(provider, query, max_results, depth)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"stored_at": _now(), "provider": provider, "query": query,
                                       "max_results": max_results, "depth": depth, "results": results},
                                      ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            pass  # a cache that cannot be written must not break the search


# ---------------------------------------------------------------- search

@dataclass(frozen=True)
class SearchOutcome:
    results: list[dict]
    cached: bool


def record_search(job_id: str, entry: dict, storage=None) -> None:
    key = job_key(job_id, "search.json")
    try:
        entries = load_json(key, storage)
    except FileNotFoundError:
        entries = []
    entries.append(entry)
    save_json(key, entries, storage)


def search_outcome(
    query: str, *, job_id=None, term=None, section_id=None, provider=None, cache=None, storage=None,
    max_results: int | None = None, allow_provider: bool = True,
) -> SearchOutcome | None:
    """Cache first, then the provider. Returns None only when allow_provider is False and the cache
    has no answer (used by the cap). Cache hits and real searches are both appended to the job's search.json."""
    provider = provider or get_provider()
    cache = cache or SearchCache()
    max_results = max_results or cfg.SEARCH_MAX_RESULTS
    depth = cfg.SEARCH_DEPTH
    results = cache.get(provider.name, query, max_results, depth)
    cached = results is not None
    if not cached:
        if not allow_provider:
            return None
        results = provider.search(query, max_results, depth)
        cache.put(provider.name, query, max_results, depth, results)
    if job_id:
        record_search(job_id, {
            "query": query, "term": term, "section_id": section_id, "provider": provider.name,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "cached": cached, "results": results,
        }, storage)
    return SearchOutcome(results, cached)


def search(query: str, *, job_id=None, term=None, section_id=None, **kwargs) -> list[dict]:
    """[{"title", "url", "snippet"}]. Raises SearchError. With job_id the search is appended to search.json."""
    return search_outcome(query, job_id=job_id, term=term, section_id=section_id, **kwargs).results


# ---------------------------------------------------------------- the gaps of a job (S3-4)

def round_robin(gaps: list[dict], sections) -> list[dict]:
    """First gap of every section, then the second of every section, ... (sections in lecture order)."""
    queues = [[g for g in gaps if g["section_id"] == s.id] for s in sections]
    return [q[r] for r in range(max((len(q) for q in queues), default=0)) for q in queues if r < len(q)]


def search_for_gaps(
    job_id: str, storage=None, *, provider=None, cache=None, cap: int | None = None,
    with_title: bool | None = None,
) -> dict:
    """Search every gap of the job (gaps.json), within the cap on real provider calls. Writes search.json
    (fresh for this run) and search_report.json; returns the report. A search that reached the provider
    counts against the cap even if it failed; a cache hit never does."""
    provider = provider or get_provider()
    cache = cache or SearchCache()
    cap = cfg.SEARCH_CAP_PER_JOB if cap is None else cap
    with_title = cfg.SEARCH_QUERY_WITH_TITLE if with_title is None else with_title
    sections = load_sections(job_id, storage)
    titles = {s.id: s.title for s in sections}
    gaps = load_json(job_key(job_id, "gaps.json"), storage)
    save_json(job_key(job_id, "search.json"), [], storage)

    report = {"job_id": job_id, "provider": provider.name, "cap": cap, "query_with_title": with_title,
              "max_results": cfg.SEARCH_MAX_RESULTS, "gaps_total": len(gaps), "searches_made": 0,
              "cache_hits": 0, "provider_calls": 0, "skipped_cap": [], "errors": []}
    for gap in round_robin(gaps, sections):
        term, sid = gap["term"], gap["section_id"]
        query = f"{term} {titles.get(sid, '')}".strip() if with_title else term
        room = report["provider_calls"] < cap
        try:
            outcome = search_outcome(
                query, job_id=job_id, term=term, section_id=sid, provider=provider, cache=cache,
                storage=storage, allow_provider=room,
            )
        except SearchError as error:
            report["provider_calls"] += 1
            report["errors"].append({"section_id": sid, "term": term, "query": query,
                                     "kind": error.kind, "status_code": error.status_code})
            continue
        if outcome is None:
            report["skipped_cap"].append({"section_id": sid, "term": term, "query": query})
            continue
        report["searches_made"] += 1
        if outcome.cached:
            report["cache_hits"] += 1
        else:
            report["provider_calls"] += 1
    save_json(job_key(job_id, "search_report.json"), report, storage)
    return report


def format_report(report: dict) -> str:
    lines = [f"job {report['job_id']}: provider {report['provider']}, cap {report['cap']}, "
             f"query with title: {report['query_with_title']}",
             f"{report['searches_made']} of {report['gaps_total']} gaps searched, "
             f"{report['provider_calls']} provider calls, {report['cache_hits']} cache hits, "
             f"{len(report['skipped_cap'])} skipped (cap), {len(report['errors'])} errors"]
    lines += [f"  skipped_cap {s['section_id']} {s['term']!r}" for s in report["skipped_cap"]]
    lines += [f"  ERROR {e['section_id']} {e['term']!r}: {e['kind']} {e['status_code'] or ''}".rstrip()
              for e in report["errors"]]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        sys.exit("usage: python -m enrich <job_id>   (run from backend/)")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(format_report(search_for_gaps(sys.argv[1])))
