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


def segs(n, step=100.0):
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
    s = segs(40, step=20.0)  # 800 s
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


def test_long_section_is_flagged_not_changed():
    s = segs(20)  # 2000 s
    r = run(s, lambda k, n: cuts_json(("A", "seg_0000"), ("B", "seg_0002")))
    assert [x.title for x in r.sections] == ["A", "B"]
    assert r.report["flagged"] == [{"id": "sec_02", "reason": "too_long", "seconds": 1799.5}]


# ---------- merging short sections (MIN_SECTION_SEC = 60 s; segs(n, 20) = 20 s per segment) ----------

def merge_run(n, *pairs):
    s = segs(n, step=20.0)
    r = run(s, lambda k, c: cuts_json(*pairs))
    return s, r


def test_short_middle_section_is_merged_into_the_previous_one():
    s, r = merge_run(12, ("A", "seg_0000"), ("B", "seg_0004"), ("C", "seg_0007"), ("D", "seg_0008"))
    assert [x.title for x in r.sections] == ["A", "B", "D"]
    assert r.sections[1].segment_ids == ["seg_0004", "seg_0005", "seg_0006", "seg_0007"]
    assert r.report["merged_short"] == [
        {"merged_title": "C", "seconds": 20.0, "into_title": "B", "result_title": "B", "at": 140.0}
    ]
    assert r.report["section_count"] == 3


def test_short_first_section_is_merged_into_the_next_one():
    s, r = merge_run(12, ("A", "seg_0000"), ("B", "seg_0002"), ("C", "seg_0006"))
    assert [x.title for x in r.sections] == ["B", "C"]
    assert r.sections[0].segment_ids[0] == "seg_0000" and r.sections[0].start == 0.0
    assert r.report["merged_short"][0]["merged_title"] == "A"


def test_short_last_section_is_merged_into_the_previous_one():
    s, r = merge_run(12, ("A", "seg_0000"), ("B", "seg_0005"), ("C", "seg_0010"))
    assert [x.title for x in r.sections] == ["A", "B"]
    assert r.sections[-1].end == s[-1].end


def test_merged_section_keeps_the_title_of_the_longer_part():
    s, r = merge_run(12, ("A", "seg_0000"), ("B", "seg_0001"), ("C", "seg_0005"))
    # A = 20 s (shortest) is merged into B = 80 s: the merged section is called "B"
    assert [x.title for x in r.sections] == ["B", "C"]
    assert r.report["merged_short"][0]["result_title"] == "B"


def test_all_sections_short_gives_one_section():
    s, r = merge_run(6, ("A", "seg_0000"), ("B", "seg_0002"), ("C", "seg_0004"))
    assert len(r.sections) == 1 and len(r.report["merged_short"]) == 2
    assert r.sections[0].segment_ids == [x.id for x in s]
    assert r.report["flagged"] == []


def test_lone_short_lecture_is_flagged():
    s, r = merge_run(2, ("A", "seg_0000"))
    assert r.report["flagged"][0]["reason"] == "too_short"


@pytest.mark.parametrize("seed", range(30))
def test_after_merging_every_segment_is_covered_exactly_once(seed):
    import random

    rnd = random.Random(seed)
    n = rnd.randint(1, 40)
    s = segs(n, step=rnd.choice([5.0, 20.0, 50.0]))
    starts = sorted({0, *rnd.sample(range(n), k=rnd.randint(0, n - 1))})
    r = run(s, lambda k, c: cuts_json(*[(f"T{i}", f"seg_{i:04d}") for i in starts]))
    assert [i for x in r.sections for i in x.segment_ids] == [x.id for x in s]
    for a, b in zip(r.sections, r.sections[1:]):
        assert a.end == b.start
    assert r.sections[0].start == s[0].start and r.sections[-1].end == s[-1].end
    if len(r.sections) > 1:
        assert all(x.end - x.start >= topics.MIN_SECTION_SEC for x in r.sections)


def test_prompt_has_no_numeric_target_but_explains_the_time_hints():
    p = topics.SYSTEM_PROMPT
    assert "minutes" not in p and "equal parts" in p and "NEW subject" in p and "Title Case" in p
    assert "start time" in p and "duration_sec" in p


def test_user_message_carries_start_times_and_duration_from_the_transcript():
    s = [Segment(id="seg_0001", start=0.04, end=7.5, text="one"),
         Segment(id="seg_0002", start=7.55, end=30.26, text="two")]
    client = FakeClient(lambda k, n: cuts_json(("A", "seg_0001")))
    topics.split_topics(s, job_id="j", client=client)
    sent = json.loads(client.calls[0]["messages"][1]["content"])
    assert sent == {
        "duration_sec": 30.3,
        "segments": [{"id": "seg_0001", "start": 0.0, "text": "one"},
                     {"id": "seg_0002", "start": 7.5, "text": "two"}],
    }


def test_start_or_duration_in_the_model_reply_is_ignored():
    s = segs(4)
    reply = json.dumps([{"title": "A", "first_segment_id": "seg_0000", "start": 5, "duration_sec": 9}])
    r = run(s, lambda k, n: reply)
    assert (r.sections[0].start, r.sections[0].end) == (s[0].start, s[-1].end)


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


# ---------- windows for long lectures (S2-4 T3) ----------
# 15 segments of 10 s (150 s). WINDOW 120 s / OVERLAP 40 s / factor 1.0 -> two windows:
#   window 0 = seg 0..11, window 1 = seg 8..14, seam at 80 + 20 = 100 s (seg 10 and later come from window 1).

@pytest.fixture
def windows_on(monkeypatch):
    monkeypatch.setattr(topics, "WINDOW_SEC", 120.0)
    monkeypatch.setattr(topics, "OVERLAP_SEC", 40.0)
    monkeypatch.setattr(topics, "WINDOW_TRIGGER_FACTOR", 1.0)
    monkeypatch.setattr(topics, "MIN_SECTION_SEC", 0.0)


def window_responder(answers):
    """answers: {first segment id of the window: reply text}"""
    def responder(kwargs, n):
        first = json.loads(kwargs["messages"][1]["content"])["segments"][0]["id"]
        return answers[first]
    return responder


def ids_of(sections):
    return [x.segment_ids[0] for x in sections]


@pytest.fixture(autouse=True)
def no_windows_by_default(monkeypatch):
    monkeypatch.setattr(topics, "WINDOW_SEC", 1e9)


def test_windows_are_cut_on_segment_boundaries_and_overlap(windows_on):
    assert topics.make_windows(segs(15, step=10.0)) == [(0, 12), (8, 15)]
    assert topics.needs_windows(segs(15, step=10.0)) and not topics.needs_windows(segs(10, step=10.0))


def test_seam_boundaries_come_from_the_correct_window(windows_on):
    answers = {
        "seg_0000": cuts_json(("W0a", "seg_0000"), ("W0b", "seg_0004"), ("W0c", "seg_0007"), ("OLD11", "seg_0011")),
        "seg_0008": cuts_json(("SKIP", "seg_0008"), ("TOOEARLY", "seg_0009"), ("NEW11", "seg_0011"), ("W1b", "seg_0014")),
    }
    r = run(segs(15, step=10.0), window_responder(answers))
    assert [x.title for x in r.sections] == ["W0a", "W0b", "W0c", "NEW11", "W1b"]
    assert ids_of(r.sections) == ["seg_0000", "seg_0004", "seg_0007", "seg_0011", "seg_0014"]
    assert r.report["windows_count"] == 2 and r.report["calls"] == 2
    assert r.report["windows"][0]["boundaries_outside_range"] == [("seg_0011", 110.0)]


def test_boundaries_closer_than_three_segments_collapse_to_the_earlier_one(windows_on):
    answers = {
        "seg_0000": cuts_json(("W0a", "seg_0000"), ("EARLY", "seg_0009")),
        "seg_0008": cuts_json(("SKIP", "seg_0008"), ("LATE", "seg_0010")),
    }
    r = run(segs(15, step=10.0), window_responder(answers))
    assert [x.title for x in r.sections] == ["W0a", "EARLY"]
    assert r.report["seam_collapsed"] == [{"dropped": "seg_0010", "kept": "seg_0009"}]


def test_bad_window_falls_back_to_parts_for_that_window_only(windows_on, monkeypatch):
    monkeypatch.setattr(topics, "FALLBACK_PART_SEC", 30.0)
    answers = {
        "seg_0000": cuts_json(("W0a", "seg_0000"), ("W0b", "seg_0005")),
        "seg_0008": "nope",
    }
    r = run(segs(15, step=10.0), window_responder(answers))
    assert [x.title for x in r.sections] == ["W0a", "W0b", "Part 1", "Part 2"]
    assert [w["used_fallback"] for w in r.report["windows"]] == [False, True]
    assert r.report["windows"][1]["fallback_reason"] == "invalid_reply"
    assert r.report["used_fallback"] and r.report["fallback_reason"] == "window"


@pytest.mark.parametrize("seed", range(40))
def test_windowed_sections_cover_every_segment_exactly_once(seed, monkeypatch):
    import random

    rnd = random.Random(seed)
    n = rnd.randint(1, 80)
    step = rnd.choice([3.0, 10.0, 25.0])
    monkeypatch.setattr(topics, "WINDOW_SEC", rnd.choice([60.0, 120.0, 300.0]))
    monkeypatch.setattr(topics, "OVERLAP_SEC", rnd.choice([0.0, 20.0, 40.0]))
    monkeypatch.setattr(topics, "WINDOW_TRIGGER_FACTOR", 1.0)
    monkeypatch.setattr(topics, "MIN_SECTION_SEC", rnd.choice([0.0, 30.0, 90.0]))
    s = segs(n, step=step)

    def responder(kwargs, call):
        got = json.loads(kwargs["messages"][1]["content"])["segments"]
        picks = {0, *rnd.sample(range(len(got)), k=rnd.randint(0, len(got) - 1))}
        if rnd.random() < 0.15:
            return "garbage"
        return cuts_json(*[(f"T{i}", got[i]["id"]) for i in sorted(picks)])

    r = run(s, responder)
    assert [i for x in r.sections for i in x.segment_ids] == [x.id for x in s]
    assert r.sections[0].segment_ids[0] == s[0].id
    for a, b in zip(r.sections, r.sections[1:]):
        assert a.end == b.start
    assert r.sections[0].start == s[0].start and r.sections[-1].end == s[-1].end
    assert len({x.id for x in r.sections}) == len(r.sections)
