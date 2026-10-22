"""Tests for search_for_gaps and the per-job cap (S3-4). Fake provider only: no network, no key."""
import pytest

import enrich
import search_config as cfg
from enrich import FakeProvider, SearchCache, SearchError
from schemas import Section
from storage import LocalStorage, job_key, load_json, save_json

SECS = [Section(id=f"sec_0{i}", title=f"Title {i}", start=i * 10.0, end=i * 10.0 + 9.0, segment_ids=[f"seg_000{i}"])
        for i in (1, 2, 3)]
GAPS = [
    {"section_id": "sec_01", "term": "a1", "reason": "r"}, {"section_id": "sec_01", "term": "a2", "reason": "r"},
    {"section_id": "sec_01", "term": "a3", "reason": "r"},
    {"section_id": "sec_02", "term": "b1", "reason": "r"}, {"section_id": "sec_02", "term": "b2", "reason": "r"},
    {"section_id": "sec_03", "term": "c1", "reason": "r"},
]


@pytest.fixture
def env(tmp_path):
    storage = LocalStorage(tmp_path / "st")
    save_json(job_key("job_s4", "sections.json"), [s.model_dump() for s in SECS], storage)
    save_json(job_key("job_s4", "gaps.json"), GAPS, storage)
    return storage, SearchCache(tmp_path / "cache")


def run(env, provider=None, **kw):
    storage, cache = env
    provider = provider or FakeProvider()
    return enrich.search_for_gaps("job_s4", storage, provider=provider, cache=cache, **kw), provider


def test_round_robin_order():
    order = [g["term"] for g in enrich.round_robin(GAPS, SECS)]
    assert order == ["a1", "b1", "c1", "a2", "b2", "a3"]


def test_query_is_term_plus_section_title_or_term_alone(env):
    report, p = run(env)
    assert p.calls[:3] == ["a1 Title 1", "b1 Title 2", "c1 Title 3"]
    assert report["query_mode"] == "title"
    storage, cache = env
    p2 = FakeProvider()
    enrich.search_for_gaps("job_s4", storage, provider=p2, cache=SearchCache(cache.dir / "other"), mode="term")
    assert p2.calls[:3] == ["a1", "b1", "c1"]


def test_config_defaults():
    assert cfg.SEARCH_QUERY_MODE == "title" and cfg.SEARCH_QUERY_WITH_TITLE is True and cfg.SEARCH_CAP_PER_JOB == 15


def test_cap_is_respected_exactly_and_skipped_are_listed(env):
    report, p = run(env, cap=4)
    assert len(p.calls) == 4 and report["provider_calls"] == 4 and report["searches_made"] == 4
    assert [s["term"] for s in report["skipped_cap"]] == ["b2", "a3"]
    assert report["skipped_cap"][0] == {"section_id": "sec_02", "term": "b2", "query": "b2 Title 2"}
    storage, _ = env
    assert len(load_json(job_key("job_s4", "search.json"), storage)) == 4
    assert load_json(job_key("job_s4", "search_report.json"), storage) == report


def test_cap_zero_searches_nothing(env):
    report, p = run(env, cap=0)
    assert p.calls == [] and report["searches_made"] == 0 and len(report["skipped_cap"]) == 6
    storage, _ = env
    assert load_json(job_key("job_s4", "search.json"), storage) == []


def test_cap_larger_than_needed_searches_everything(env):
    report, p = run(env)
    assert len(p.calls) == 6 and report["skipped_cap"] == [] and report["cache_hits"] == 0


def test_cache_hits_do_not_count_and_are_reported(env):
    storage, cache = env
    enrich.search("a1 Title 1", provider=FakeProvider(), cache=cache)  # warm two entries
    enrich.search("b1 Title 2", provider=FakeProvider(), cache=cache)
    report, p = run(env, cap=2)
    assert report["cache_hits"] == 2 and report["provider_calls"] == 2 and report["searches_made"] == 4
    assert p.calls == ["c1 Title 3", "a2 Title 1"]
    assert [s["term"] for s in report["skipped_cap"]] == ["b2", "a3"]
    entries = load_json(job_key("job_s4", "search.json"), storage)
    assert [e["cached"] for e in entries] == [True, True, False, False]


def test_cached_term_is_served_even_after_the_cap_is_reached(env):
    storage, cache = env
    enrich.search("a3 Title 1", provider=FakeProvider(), cache=cache)  # the LAST term in the order
    report, p = run(env, cap=1)
    assert "a3 Title 1" not in p.calls and report["cache_hits"] == 1 and report["provider_calls"] == 1
    assert "a3" not in [s["term"] for s in report["skipped_cap"]]


def test_a_failing_search_is_reported_and_does_not_stop_the_rest(env):
    class Flaky(FakeProvider):
        def search(self, query, max_results, depth):
            if query.startswith("b1"):
                raise SearchError("down", kind="server", status_code=503)
            return super().search(query, max_results, depth)

    report, p = run(env, Flaky())
    assert report["errors"] == [{"section_id": "sec_02", "term": "b1", "query": "b1 Title 2",
                                 "kind": "server", "status_code": 503}]
    assert report["searches_made"] == 5 and report["provider_calls"] == 6
    storage, _ = env
    assert "b1" not in [e["term"] for e in load_json(job_key("job_s4", "search.json"), storage)]


def test_a_failing_search_uses_one_unit_of_the_cap(env):
    class AlwaysFails(FakeProvider):
        def search(self, query, max_results, depth):
            raise SearchError("quota", kind="quota", status_code=432)

    report, _ = run(env, AlwaysFails(), cap=3)
    assert len(report["errors"]) == 3 and len(report["skipped_cap"]) == 3 and report["searches_made"] == 0


def test_running_twice_makes_no_provider_call_the_second_time(env):
    first, p1 = run(env)
    second, p2 = run(env)
    assert len(p1.calls) == 6 and p2.calls == []
    assert second["cache_hits"] == 6 and second["provider_calls"] == 0
    storage, _ = env
    assert len(load_json(job_key("job_s4", "search.json"), storage)) == 6  # fresh file, not 12


def test_job_without_gaps_searches_nothing(env):
    storage, cache = env
    save_json(job_key("job_s4", "gaps.json"), [], storage)
    report, p = run(env)
    assert p.calls == [] and report["gaps_total"] == 0


def test_format_report_mentions_numbers_and_skipped(env):
    text = enrich.format_report(run(env, cap=1)[0])
    assert "1 provider calls" in text and "skipped_cap" in text and "provider fake" in text


def test_report_sums_provider_credits_and_skips_cache_hits(env):
    class Metered(FakeProvider):
        last_meta = {"credits": 1, "response_time": 0.5}

    storage, cache = env
    enrich.search("a1 Title 1", provider=FakeProvider(), cache=cache)  # one cache hit later
    report, _ = run(env, Metered(), cap=3)
    assert report["cache_hits"] == 1 and report["provider_calls"] == 3
    assert report["credits_reported"] == 3 and report["max_response_sec"] == 0.5


def test_report_has_no_credits_when_the_provider_gives_none(env):
    report, _ = run(env)
    assert report["credits_reported"] is None and report["max_response_sec"] is None


MODEL_GAPS = [
    {"section_id": "sec_01", "term": "x star", "reason": "r", "query": "optimal point x* minimizer"},
    {"section_id": "sec_02", "term": "level set", "reason": "r"},  # no query: the term is used
]


@pytest.mark.parametrize("mode,expected", [
    ("term", ["x star", "level set"]),
    ("title", ["x star Title 1", "level set Title 2"]),
    ("model", ["optimal point x* minimizer", "level set"]),
])
def test_each_query_mode_builds_the_expected_query(env, mode, expected):
    storage, cache = env
    save_json(job_key("job_s4", "gaps.json"), MODEL_GAPS, storage)
    report, p = run(env, mode=mode)
    assert p.calls == expected and report["query_mode"] == mode


def test_cache_key_uses_the_final_query_text(env):
    storage, cache = env
    save_json(job_key("job_s4", "gaps.json"), MODEL_GAPS, storage)
    run(env, mode="model")
    report, p = run(env, mode="model")           # same final queries: all hits
    assert p.calls == [] and report["cache_hits"] == 2
    report, p = run(env, mode="term")            # "level set" is the same final text in both modes: hit
    assert p.calls == ["x star"] and report["cache_hits"] == 1


def test_unknown_mode_is_refused_and_env_and_old_boolean_still_work(env, monkeypatch):
    with pytest.raises(ValueError):
        run(env, mode="bogus")
    monkeypatch.setenv("SEARCH_QUERY_MODE", "term")
    assert run(env)[0]["query_mode"] == "term"
    assert run(env, with_title=True)[0]["query_mode"] == "title"
