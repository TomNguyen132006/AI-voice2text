"""Tests for enrich.py, search wrapper (S3-2). Fake HTTP client only: no network, no key."""
import httpx2 as httpx  # openai 3.x ships httpx2, not httpx
import pytest

import enrich
import search_config as cfg
from enrich import SearchError, TavilyProvider
from storage import LocalStorage, job_key, load_json

KEY = "test-key-not-real"
sleeps: list[float] = []


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(enrich, "_sleep", lambda s: sleeps.append(s))
    monkeypatch.setenv("SEARCH_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv(cfg.TAVILY_KEY_ENV, KEY)
    monkeypatch.delenv("SEARCH_PROVIDER", raising=False)
    sleeps.clear()


def reply(status=200, results=None, headers=None):
    body = {"query": "q", "results": results if results is not None else []}
    return httpx.Response(status, json=body, headers=headers, request=httpx.Request("POST", cfg.TAVILY_URL))


class FakeHttp:
    """responder(call_number) returns a Response or raises."""

    def __init__(self, responder):
        self.responder, self.calls = responder, []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return self.responder(len(self.calls))


def tavily(responder):
    http = FakeHttp(responder)
    return TavilyProvider(client=http), http


def result(url, title="T", content="C"):
    return {"title": title, "url": url, "content": content, "score": 0.9}


def test_success_maps_content_to_snippet_and_sends_the_documented_request():
    provider, http = tavily(lambda n: reply(results=[result("https://a.org/x", "Title A", "Text A")]))
    out = provider.search("gradient descent", 5, "basic")
    assert out == [{"title": "Title A", "url": "https://a.org/x", "snippet": "Text A"}]
    call = http.calls[0]
    assert call["url"] == "https://api.tavily.com/search" and call["timeout"] == cfg.SEARCH_TIMEOUT_SEC
    assert call["headers"]["Authorization"] == f"Bearer {KEY}"
    assert call["json"] == {"query": "gradient descent", "search_depth": "basic", "max_results": 5,
                            "include_answer": False, "include_raw_content": False, "include_images": False}


def test_result_without_url_is_dropped_and_url_is_kept_exactly():
    odd = "HTTPS://Example.org/A%20b/?q=1&x=Y#Frag"
    provider, _ = tavily(lambda n: reply(results=[result(""), {"title": "no url"}, result(odd), result(None)]))
    assert [r["url"] for r in provider.search("q", 5, "basic")] == [odd]


def test_missing_title_or_content_becomes_empty_string():
    provider, _ = tavily(lambda n: reply(results=[{"url": "https://a.org"}]))
    assert provider.search("q", 5, "basic") == [{"title": "", "url": "https://a.org", "snippet": ""}]


def test_timeout_then_success_waits_and_retries():
    def responder(n):
        if n == 1:
            raise httpx.ReadTimeout("slow")
        return reply(results=[result("https://a.org")])

    provider, http = tavily(responder)
    assert len(provider.search("q", 5, "basic")) == 1
    assert len(http.calls) == 2 and sleeps == [1.0]


def test_connection_error_is_retried_like_a_timeout():
    def responder(n):
        if n < 3:
            raise httpx.ConnectError("down")
        return reply(results=[])

    provider, http = tavily(responder)
    assert provider.search("q", 5, "basic") == [] and len(http.calls) == 3 and sleeps == [1.0, 2.0]


def test_5xx_every_time_raises_after_the_limit():
    provider, http = tavily(lambda n: reply(503))
    with pytest.raises(SearchError) as e:
        provider.search("q", 5, "basic")
    assert e.value.kind == "server" and e.value.status_code == 503
    assert len(http.calls) == cfg.SEARCH_MAX_RETRIES + 1 and e.value.attempts == 3


def test_timeout_every_time_raises_timeout_kind():
    def responder(n):
        raise httpx.ReadTimeout("slow")

    provider, http = tavily(responder)
    with pytest.raises(SearchError) as e:
        provider.search("q", 5, "basic")
    assert e.value.kind == "timeout" and len(http.calls) == 3


@pytest.mark.parametrize("status,kind", [(400, "client"), (401, "auth"), (422, "client"), (404, "client")])
def test_4xx_is_not_retried(status, kind):
    provider, http = tavily(lambda n: reply(status))
    with pytest.raises(SearchError) as e:
        provider.search("q", 5, "basic")
    assert e.value.kind == kind and e.value.status_code == status and len(http.calls) == 1 and sleeps == []


def test_429_retries_once_after_retry_after():
    provider, http = tavily(lambda n: reply(429, headers={"Retry-After": "7"}) if n == 1
                            else reply(results=[result("https://a.org")]))
    assert len(provider.search("q", 5, "basic")) == 1
    assert len(http.calls) == 2 and sleeps == [7.0]


def test_429_wait_is_capped_and_has_a_default():
    provider, _ = tavily(lambda n: reply(429, headers={"Retry-After": "999"}) if n == 1 else reply())
    provider.search("q", 5, "basic")
    provider2, _ = tavily(lambda n: reply(429) if n == 1 else reply())
    provider2.search("q", 5, "basic")
    assert sleeps == [cfg.RETRY_AFTER_CAP_SEC, cfg.RATE_LIMIT_DEFAULT_WAIT_SEC]


def test_429_twice_raises_rate_limit_after_one_retry_only():
    provider, http = tavily(lambda n: reply(429, headers={"Retry-After": "1"}))
    with pytest.raises(SearchError) as e:
        provider.search("q", 5, "basic")
    assert e.value.kind == "rate_limit" and len(http.calls) == 2


@pytest.mark.parametrize("status", [432, 433])
def test_plan_limit_is_a_quota_error_without_retry(status):
    provider, http = tavily(lambda n: reply(status))
    with pytest.raises(SearchError) as e:
        provider.search("q", 5, "basic")
    assert e.value.kind == "quota" and len(http.calls) == 1


def test_missing_key_fails_before_any_call(monkeypatch):
    monkeypatch.delenv(cfg.TAVILY_KEY_ENV)
    provider, http = tavily(lambda n: reply())
    with pytest.raises(SearchError) as e:
        provider.search("q", 5, "basic")
    assert e.value.kind == "no_key" and http.calls == []


def test_the_key_never_appears_in_an_error_message():
    provider, _ = tavily(lambda n: reply(401))
    with pytest.raises(SearchError) as e:
        provider.search("q", 5, "basic")
    assert KEY not in str(e.value) and KEY not in repr(e.value)


def test_reply_without_results_list_is_bad_reply():
    provider, _ = tavily(lambda n: httpx.Response(200, json={"oops": 1}, request=httpx.Request("POST", "http://x")))
    with pytest.raises(SearchError) as e:
        provider.search("q", 5, "basic")
    assert e.value.kind == "bad_reply"


def test_one_search_json_entry_per_search(tmp_path):
    storage = LocalStorage(tmp_path / "st")
    provider, _ = tavily(lambda n: reply(results=[result(f"https://a.org/{n}")]))
    kw = dict(job_id="job_s1", provider=provider, storage=storage)
    enrich.search("first query", term="gradient", section_id="sec_01", **kw)
    enrich.search("second query", term="Hessian", section_id="sec_02", **kw)
    entries = load_json(job_key("job_s1", "search.json"), storage)
    assert [e["query"] for e in entries] == ["first query", "second query"]
    first = entries[0]
    assert set(first) == {"query", "term", "section_id", "provider", "timestamp", "cached", "results"}
    assert (first["term"], first["section_id"], first["provider"], first["cached"]) == ("gradient", "sec_01", "tavily", False)
    assert first["results"] == [{"title": "T", "url": "https://a.org/1", "snippet": "C"}]


def test_search_without_job_id_writes_nothing(tmp_path):
    storage = LocalStorage(tmp_path / "st")
    enrich.search("q", provider=enrich.FakeProvider(), storage=storage)
    assert not (tmp_path / "st").exists()


def test_get_provider_default_env_and_unknown(monkeypatch):
    assert enrich.get_provider().name == "tavily"
    monkeypatch.setenv("SEARCH_PROVIDER", "fake")
    assert enrich.get_provider().name == "fake"
    with pytest.raises(ValueError):
        enrich.get_provider("brave")
