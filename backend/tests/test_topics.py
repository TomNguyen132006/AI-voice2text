"""Tests for topics.py (S2-3). Fake client only: no network, no keys."""
import json

import httpx2 as httpx  # openai 3.x ships httpx2, not httpx
import openai
import pytest

import llm
import topics
from schemas import Segment
from storage import LocalStorage, job_key, save_json
from tests.test_clean import FakeClient, make_response


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "_sleep", lambda s: None)
    monkeypatch.setenv("LLM_LOG_PATH", str(tmp_path / "calls.jsonl"))


def segs(n, step=20.0):
    return [Segment(id=f"seg_{i:04d}", start=i * step, end=i * step + step - 0.5, text=f"text {i}")
            for i in range(n)]


def cuts_json(*pairs):
    return json.dumps([{"title": t, "first_segment_id": f} for t, f in pairs])


def run(segments, responder):
    return topics.split_topics(segments, job_id="job_t1", client=FakeClient(responder))


def test_sections_have_no_gap_no_overlap_and_cover_every_segment():
    s = segs(10)
    r = run(s, lambda k, n: cuts_json(("A", "seg_0000"), ("B", "seg_0004"), ("C", "seg_0007")))
    assert [x.title for x in r.sections] == ["A", "B", "C"]
    assert [x.id for x in r.sections] == ["sec_01", "sec_02", "sec_03"]
    assert [i for x in r.sections for i in x.segment_ids] == [x.id for x in s]
    for a, b in zip(r.sections, r.sections[1:]):
        assert a.end == b.start
    assert r.sections[0].start == s[0].start and r.sections[-1].end == s[-1].end
    assert r.report["used_fallback"] is False and r.report["calls"] == 1


def test_times_come_from_the_transcript_not_the_model():
    s = segs(4)
    reply = json.dumps([{"title": "A", "first_segment_id": "seg_0000", "start": 999, "end": 1000}])
    r = run(s, lambda k, n: reply)
    assert (r.sections[0].start, r.sections[0].end) == (0.0, s[-1].end)


@pytest.mark.parametrize("bad", [
    "not json at all",
    cuts_json(("A", "seg_0001")),  # does not start at the first segment
    cuts_json(("A", "seg_0000"), ("B", "seg_9999")),  # unknown id
    cuts_json(("A", "seg_0000"), ("B", "seg_0003"), ("C", "seg_0002")),  # out of order
    cuts_json(("A", "seg_0000"), ("B", "seg_0000")),  # repeat
    cuts_json(("", "seg_0000")),  # empty title
    "[]",
])
def test_bad_reply_is_retried_once_with_a_hint(bad):
    good = cuts_json(("A", "seg_0000"), ("B", "seg_0002"))
    client = FakeClient(lambda k, n: bad if n == 1 else good)
    r = topics.split_topics(segs(5), job_id="j", client=client)
    assert len(client.calls) == 2 and "rejected" in client.calls[1]["messages"][2]["content"]
    assert [x.title for x in r.sections] == ["A", "B"] and not r.report["used_fallback"]


def test_bad_twice_uses_equal_time_parts_and_says_so():
    s = segs(40)  # 800 s
    r = run(s, lambda k, n: "nope")
    assert r.report["used_fallback"] and r.report["fallback_reason"] == "invalid_reply"
    assert [x.title for x in r.sections] == ["Part 1", "Part 2", "Part 3"]
    assert [i for x in r.sections for i in x.segment_ids] == [x.id for x in s]


def test_truncated_is_retried_with_double_max_tokens():
    def responder(k, n):
        if n == 1:
            return make_response("", finish="length", completion=topics.MAX_TOKENS)
        return cuts_json(("A", "seg_0000"))

    client = FakeClient(responder)
    r = topics.split_topics(segs(3), job_id="j", client=client)
    assert [c["max_tokens"] for c in client.calls] == [topics.MAX_TOKENS, topics.MAX_TOKENS * 2]
    assert not r.report["used_fallback"]


def test_llm_error_uses_fallback_and_does_not_crash():
    def responder(k, n):
        request = httpx.Request("POST", "http://x")
        raise openai.BadRequestError("bad", response=httpx.Response(400, request=request), body=None)

    r = run(segs(3), responder)
    assert r.report["used_fallback"] and r.report["fallback_reason"] == "llm_error"
    assert len(r.sections) == 1


def test_short_and_long_sections_are_flagged_not_changed():
    s = segs(50)  # 1000 s
    r = run(s, lambda k, n: cuts_json(("A", "seg_0000"), ("B", "seg_0001"), ("C", "seg_0002")))
    assert r.report["flagged"] == [
        {"id": "sec_01", "reason": "too_short", "seconds": 20.0},
        {"id": "sec_02", "reason": "too_short", "seconds": 20.0},
        {"id": "sec_03", "reason": "too_long", "seconds": 959.5},
    ]


def test_empty_transcript_makes_no_call():
    client = FakeClient(lambda k, n: "x")
    r = topics.split_topics([], job_id="j", client=client)
    assert r.sections == [] and client.calls == []


def test_split_job_reads_clean_transcript_and_saves_two_files(tmp_path):
    st = LocalStorage(root=tmp_path / "store")
    save_json(job_key("job_t2", "transcript_clean.json"), [s.model_dump() for s in segs(6)], st)
    client = FakeClient(lambda k, n: cuts_json(("A", "seg_0000"), ("B", "seg_0003")))
    r = topics.split_job("job_t2", storage=st, client=client)
    assert topics.load_sections("job_t2", st) == r.sections
    saved = json.loads(st.load_bytes(job_key("job_t2", "topics_report.json")))
    assert saved["section_count"] == 2
