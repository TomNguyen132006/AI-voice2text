"""Tests for the search cache (S3-3). Fake provider only: no network, no key."""
import json

import pytest

import enrich
from enrich import FakeProvider, SearchCache
from storage import LocalStorage, job_key, load_json


@pytest.fixture
def cache(tmp_path):
    return SearchCache(tmp_path / "cache")


class OtherProvider(FakeProvider):
    name = "other"


def test_second_identical_query_makes_no_provider_call(cache):
    p = FakeProvider()
    first = enrich.search("gradient descent", provider=p, cache=cache)
    second = enrich.search("gradient descent", provider=p, cache=cache)
    assert p.calls == ["gradient descent"] and second == first


def test_case_and_spaces_do_not_change_the_key(cache):
    p = FakeProvider()
    enrich.search("Gradient Descent", provider=p, cache=cache)
    out = enrich.search_outcome("  gradient   DESCENT ", provider=p, cache=cache)
    assert out.cached and len(p.calls) == 1


def test_different_provider_or_max_results_is_a_miss(cache):
    a, b = FakeProvider(), OtherProvider()
    enrich.search("q", provider=a, cache=cache)
    assert not enrich.search_outcome("q", provider=b, cache=cache).cached
    assert not enrich.search_outcome("q", provider=a, cache=cache, max_results=2).cached
    assert len(a.calls) == 2 and len(b.calls) == 1


def test_hit_is_still_recorded_in_search_json_with_cached_true(cache, tmp_path):
    storage = LocalStorage(tmp_path / "st")
    p = FakeProvider()
    enrich.search("q", provider=p, cache=cache, job_id="job_c1", storage=storage)
    enrich.search("q", provider=p, cache=cache, job_id="job_c2", storage=storage)  # another job
    assert len(p.calls) == 1
    a = load_json(job_key("job_c1", "search.json"), storage)
    b = load_json(job_key("job_c2", "search.json"), storage)
    assert [e["cached"] for e in a] == [False] and [e["cached"] for e in b] == [True]
    assert a[0]["results"] == b[0]["results"] and b[0]["results"][0]["url"].startswith("https://")


def test_corrupt_cache_file_is_ignored_and_replaced(cache):
    p = FakeProvider()
    enrich.search("q", provider=p, cache=cache)
    (path,) = list(cache.dir.glob("*.json"))
    for junk in ("{not json", "[]", '{"stored_at": "x"}', '{"stored_at": 1, "results": [{"title": "no url"}]}'):
        path.write_text(junk, encoding="utf-8")
        assert not enrich.search_outcome("q", provider=p, cache=cache).cached  # refetched, no crash
    assert enrich.search_outcome("q", provider=p, cache=cache).cached  # and the refetch repaired the file


def test_expired_entry_is_refetched(cache, monkeypatch):
    p = FakeProvider()
    t = [1_000_000.0]
    monkeypatch.setattr(enrich, "_now", lambda: t[0])
    enrich.search("q", provider=p, cache=cache)
    t[0] += 6.9 * 86400
    assert enrich.search_outcome("q", provider=p, cache=cache).cached
    t[0] += 0.2 * 86400  # now 7.1 days old
    assert not enrich.search_outcome("q", provider=p, cache=cache).cached
    assert len(p.calls) == 2


def test_errors_are_never_cached(cache):
    class Failing(FakeProvider):
        def search(self, query, max_results, depth):
            raise enrich.SearchError("boom", kind="server")

    with pytest.raises(enrich.SearchError):
        enrich.search("q", provider=Failing(), cache=cache)
    assert not cache.dir.exists() or list(cache.dir.glob("*.json")) == []


def test_unwritable_cache_does_not_break_the_search(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    cache = SearchCache(blocker / "sub")  # a directory cannot be created below a file
    assert enrich.search("q", provider=FakeProvider(), cache=cache)


def test_cache_file_holds_urls_exactly_as_returned(cache):
    class Odd(FakeProvider):
        def search(self, query, max_results, depth):
            return [{"title": "t", "url": "HTTPS://Example.org/A%20b?x=1#F", "snippet": "s"}]

    enrich.search("q", provider=Odd(), cache=cache)
    (path,) = list(cache.dir.glob("*.json"))
    assert json.loads(path.read_text(encoding="utf-8"))["results"][0]["url"] == "HTTPS://Example.org/A%20b?x=1#F"
