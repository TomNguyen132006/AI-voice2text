"""Tests for clean.py (S2-2). Fake client only: no network, no keys."""
import json
from types import SimpleNamespace

import httpx2 as httpx  # openai 3.x ships httpx2, not httpx
import openai
import pytest

import clean
import llm
from schemas import Segment
from storage import LocalStorage, job_key, load_json, save_transcript

REQUEST = httpx.Request("POST", "https://example.invalid/v1/chat/completions")


def seg(i, text=None, start=None):
    start = float(i * 10) if start is None else start
    return Segment(id=f"seg_{i:04d}", start=start, end=start + 9.5, text=text or f"uh text number {i}.")


def make_response(content, finish="stop", prompt=100, completion=200):
    usage = SimpleNamespace(
        prompt_tokens=prompt, completion_tokens=completion, completion_tokens_details=None
    )
    choice = SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish)
    return SimpleNamespace(choices=[choice], usage=usage)


def payload_of(kwargs):
    return json.loads(kwargs["messages"][1]["content"])


class FakeClient:
    """responder(kwargs, call_number) returns a string, a response object, or raises."""

    def __init__(self, responder):
        self.responder = responder
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        out = self.responder(kwargs, len(self.calls))
        return out if not isinstance(out, str) else make_response(out)


def as_json(items):
    return json.dumps([{"id": i, "text": t} for i, t in items])


def clean_all(kwargs, n):
    """A well-behaved model: removes 'uh ' and returns every requested segment."""
    return as_json((s["id"], s["text"].replace("uh ", "")) for s in payload_of(kwargs)["segments"])


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "_sleep", lambda s: None)
    monkeypatch.setenv("LLM_LOG_PATH", str(tmp_path / "calls.jsonl"))


def run(segments, responder, **kwargs):
    return clean.clean_transcript(segments, job_id="job_c1", client=FakeClient(responder), **kwargs)


# ---------- happy path ----------

def test_text_changes_but_ids_and_times_never_do():
    segments = [seg(i) for i in range(1, 6)]
    result = run(segments, clean_all)

    assert [s.id for s in result.segments] == [s.id for s in segments]
    assert [(s.start, s.end) for s in result.segments] == [(s.start, s.end) for s in segments]
    assert result.segments[0].text == "text number 1."
    assert result.report["reverted_count"] == 0 and result.report["changed_count"] == 5


def test_model_supplied_times_and_extra_keys_are_ignored():
    def responder(kwargs, n):
        return json.dumps([
            {"id": s["id"], "text": "ok text.", "start": 999, "end": 1000, "note": "x"}
            for s in payload_of(kwargs)["segments"]
        ])

    segments = [seg(1), seg(2)]
    result = run(segments, responder)
    assert [(s.start, s.end) for s in result.segments] == [(10.0, 19.5), (20.0, 29.5)]


def test_input_segments_are_not_modified():
    segments = [seg(1), seg(2)]
    before = [s.model_copy() for s in segments]
    run(segments, clean_all)
    assert segments == before


def test_reply_wrapped_in_code_fence_and_prose_is_parsed():
    def responder(kwargs, n):
        return "Here you go:\n```json\n" + clean_all(kwargs, n) + "\n```\nDone."

    result = run([seg(1)], responder)
    assert result.segments[0].text == "text number 1." and result.report["reverted_count"] == 0


def test_empty_transcript_makes_no_calls():
    client = FakeClient(clean_all)
    result = clean.clean_transcript([], job_id="job_c1", client=client)
    assert result.segments == [] and client.calls == []


# ---------- batching and context ----------

def test_batches_respect_segment_and_char_limits():
    segments = [seg(i) for i in range(1, 41)]
    batches = clean.make_batches(segments)
    assert [s.id for b in batches for s in b] == [s.id for s in segments]
    assert all(len(b) <= clean.BATCH_MAX_SEGMENTS for b in batches)

    long = [seg(i, "x" * 700) for i in range(1, 7)]
    assert all(sum(len(s.text) for s in b) <= clean.BATCH_MAX_CHARS for b in clean.make_batches(long))


def test_context_is_sent_but_must_not_be_returned():
    segments = [seg(i) for i in range(1, 21)]  # 2 batches of 15 + 5
    seen = []

    def responder(kwargs, n):
        seen.append(payload_of(kwargs))
        return clean_all(kwargs, n)

    run(segments, responder, max_workers=1)
    second = seen[1]
    assert [s["id"] for s in second["context_before"]] == ["seg_0013", "seg_0014", "seg_0015"]
    assert second["context_after"] == []

    def returns_context(kwargs, n):
        p = payload_of(kwargs)
        items = p["context_before"] + p["segments"]
        return as_json((s["id"], s["text"]) for s in items)

    result = run(segments, returns_context, max_workers=1)
    assert result.report["reverted_by_reason"].get("batch_invalid", 0) >= 5


def test_parallel_and_sequential_give_the_same_result():
    segments = [seg(i) for i in range(1, 61)]
    assert run(segments, clean_all, max_workers=1).segments == run(segments, clean_all, max_workers=4).segments


# ---------- validation, retry, fallback ----------

@pytest.mark.parametrize("bad", [
    lambda items: items[:-1],                       # missing id
    lambda items: items + [("seg_9999", "extra")],  # invented segment
    lambda items: list(reversed(items)),            # wrong order
    lambda items: [(i, 5) for i, _ in items],       # text is not a string
])
def test_bad_batch_is_retried_once_with_a_hint_then_ok(bad):
    def responder(kwargs, n):
        items = [(s["id"], s["text"].replace("uh ", "")) for s in payload_of(kwargs)["segments"]]
        return as_json(bad(items)) if n == 1 else as_json(items)

    client = FakeClient(responder)
    result = clean.clean_transcript([seg(1), seg(2), seg(3)], job_id="job_c1", client=client)

    assert len(client.calls) == 2 and "rejected" in client.calls[1]["messages"][-1]["content"]
    assert result.report["reverted_count"] == 0


def test_bad_batch_twice_reverts_whole_batch_to_original():
    def responder(kwargs, n):
        return "this is not json"

    segments = [seg(1), seg(2)]
    result = run(segments, responder)

    assert [s.text for s in result.segments] == [s.text for s in segments]
    assert result.report["reverted_count"] == 2
    assert result.report["reverted_by_reason"] == {"batch_invalid": 2}
    assert {r["id"] for r in result.report["reverted"]} == {"seg_0001", "seg_0002"}


def test_truncated_batch_is_retried_with_doubled_max_tokens():
    def responder(kwargs, n):
        if n == 1:
            return make_response("", finish="length", completion=clean.MAX_TOKENS)
        return clean_all(kwargs, n)

    client = FakeClient(responder)
    result = clean.clean_transcript([seg(1), seg(2)], job_id="job_c1", client=client)

    assert [c["max_tokens"] for c in client.calls] == [clean.MAX_TOKENS, clean.MAX_TOKENS * 2]
    assert result.report["reverted_count"] == 0


def test_truncated_twice_reverts_with_reason_truncated():
    result = run([seg(1)], lambda kw, n: make_response("[", finish="length"))
    assert result.report["reverted_by_reason"] == {"batch_truncated": 1}
    assert result.segments[0].text == seg(1).text


def test_llm_error_reverts_batch_and_does_not_crash():
    def responder(kwargs, n):
        response = httpx.Response(400, request=REQUEST)
        raise openai.BadRequestError("bad", response=response, body=None)

    result = run([seg(1), seg(2)], responder)
    assert result.report["reverted_by_reason"] == {"llm_error": 2}
    assert result.report["cost_is_lower_bound"] is True


def test_empty_text_reverts_only_that_segment():
    def responder(kwargs, n):
        return as_json(
            (s["id"], "" if s["id"] == "seg_0002" else "fine.") for s in payload_of(kwargs)["segments"]
        )

    result = run([seg(1), seg(2), seg(3)], responder)
    assert result.segments[1].text == seg(2).text and result.segments[0].text == "fine."
    assert result.report["reverted_by_reason"] == {"empty_text": 1}


def test_wildly_longer_or_shorter_text_reverts_that_segment():
    original = "The condition number is the ratio of the largest to the smallest eigenvalue."

    def too_long(kwargs, n):
        return as_json((s["id"], original + " " + "And much more invented text. " * 10) for s in payload_of(kwargs)["segments"])

    def too_short(kwargs, n):
        return as_json((s["id"], "Okay.") for s in payload_of(kwargs)["segments"])

    assert run([seg(1, original)], too_long).report["reverted_by_reason"] == {"too_long": 1}
    assert run([seg(1, original)], too_short).report["reverted_by_reason"] == {"too_short": 1}


def test_short_original_may_shrink_a_lot():
    result = run([seg(1, "Uh, yes.")], lambda kw, n: as_json([("seg_0001", "Yes.")]))
    assert result.segments[0].text == "Yes." and result.report["reverted_count"] == 0


# ---------- report ----------

def test_report_counts_calls_tokens_and_cost():
    segments = [seg(i) for i in range(1, 21)]  # 2 batches
    result = run(segments, lambda kw, n: make_response(clean_all(kw, n), prompt=100, completion=200), max_workers=1)
    report = result.report

    assert report["total_segments"] == 20 and report["batches"] == 2 and report["calls"] == 2
    assert report["prompt_tokens"] == 200 and report["completion_tokens"] == 400
    assert report["est_cost_usd"] == pytest.approx(2 * llm.estimate_cost("nano", 100, 200))
    assert report["cost_is_lower_bound"] is False
    assert report["model_id"].startswith("nvidia/")


def test_unchanged_text_is_not_counted_as_changed():
    segments = [seg(1, "Already clean.")]
    result = run(segments, lambda kw, n: as_json([("seg_0001", "Already clean.")]))
    assert result.report["changed_count"] == 0 and result.report["unchanged_count"] == 1


# ---------- storage ----------

def test_clean_job_saves_separate_files_and_leaves_original_untouched(tmp_path):
    store = LocalStorage(tmp_path)
    segments = [seg(1), seg(2)]
    save_transcript("job_c1", segments, store)
    original_bytes = store.load_bytes(job_key("job_c1", "transcript.json"))

    result = clean.clean_job("job_c1", storage=store, client=FakeClient(clean_all))

    assert store.load_bytes(job_key("job_c1", "transcript.json")) == original_bytes
    saved = load_json(job_key("job_c1", "transcript_clean.json"), store)
    assert saved == [s.model_dump() for s in result.segments]
    assert load_json(job_key("job_c1", "clean_report.json"), store) == result.report
    assert clean.load_clean_transcript("job_c1", store) == result.segments


SEG_21 = "So the minimum point, x star, zero, of course."


@pytest.mark.parametrize(
    "original, cleaned, reason",
    [
        (SEG_21, "So the minimum point, x star, is (0,0), of course.", "new_symbol"),
        ("The answer is two.", "The answer is 2.", "new_symbol"),
        ("It is a x star here.", "It is a x-star here.", "new_symbol"),
        ("The cat sat on the mat today.", "The big red furry cat sat on the mat today.", "new_words"),
        # allowed edits
        ("The formula was a x squared was b y squared.", "The formula was a x squared plus b y squared.", None),
        ("So uh the condition number is uh big.", "So the condition number is big.", None),
        ("so the minimum point x star zero of course", "So, the minimum point, x star, zero, of course.", None),
        ("So I'm minima, I haven't put it.", "So I'm minimizing, I haven't put it.", None),
    ],
)
def test_guard_new_symbols_and_new_words(original, cleaned, reason):
    assert clean._segment_problem(original, cleaned) == reason


def test_seg_0021_is_reverted_and_reported_in_a_full_run():
    segs = [seg(1, SEG_21), seg(2, "So uh we go on.")]

    def responder(kwargs, n):
        return as_json([("seg_0001", "So the minimum point, x star, is (0,0), of course."),
                        ("seg_0002", "So we go on.")])

    result = clean.clean_transcript(segs, job_id="j", client=FakeClient(responder))
    assert result.segments[0].text == SEG_21
    assert result.segments[1].text == "So we go on."
    assert result.report["reverted_by_reason"] == {"new_symbol": 1}


def test_removal_guard_accepts_two_removed_words_and_reverts_six():
    two = "Well uh so the gradient is zero here."
    six = "Well so the gradient is zero here and the Hessian is flat."
    segs = [seg(1, two), seg(2, six)]

    def responder(kwargs, n):
        return as_json([("seg_0001", "Well, the gradient is zero here."),
                        ("seg_0002", "Well, the gradient is zero.")])

    result = clean.clean_transcript(segs, job_id="j", client=FakeClient(responder))
    assert result.segments[0].text == "Well, the gradient is zero here."
    assert result.segments[1].text == six
    assert result.report["reverted"] == [{"id": "seg_0002", "reason": "removed_too_much"}]
    assert result.report["reverted_by_reason"] == {"removed_too_much": 1}


# ---------- checkpoint and resume (S2-4 T2) ----------

def test_failed_batch_is_not_paid_again_on_rerun(tmp_path):
    store = LocalStorage(tmp_path)
    segments = [seg(i) for i in range(1, 46)]  # 45 segments = 3 batches of 15
    save_transcript("job_c2", segments, store)
    assert len(clean.make_batches(segments)) == 3

    def fails_on_batch_3(kwargs, n):
        ids = [s["id"] for s in payload_of(kwargs)["segments"]]
        if "seg_0031" in ids:  # third batch
            raise openai.BadRequestError(
                "bad", response=httpx.Response(400, request=REQUEST), body=None
            )
        return clean_all(kwargs, n)

    first = FakeClient(fails_on_batch_3)
    r1 = clean.clean_job("job_c2", storage=store, client=first, max_workers=1)
    assert r1.report["reverted_by_reason"] == {"llm_error": 15}
    assert len(first.calls) == 3
    assert load_json(job_key("job_c2", "clean_batches/batch_0000.json"), store)["ids"][0] == "seg_0001"

    second = FakeClient(clean_all)
    r2 = clean.clean_job("job_c2", storage=store, client=second, max_workers=1)
    assert len(second.calls) == 1  # only the missing third batch
    assert "seg_0031" in [s["id"] for s in payload_of(second.calls[0])["segments"]]
    assert r2.report["resumed_batches"] == 2 and r2.report["reverted_count"] == 0
    assert [s.text for s in r2.segments] == [s.text.replace("uh ", "") for s in segments]


def test_checkpoint_from_other_segments_is_ignored(tmp_path):
    store = LocalStorage(tmp_path)
    save_transcript("job_c3", [seg(1), seg(2)], store)
    clean.clean_job("job_c3", storage=store, client=FakeClient(clean_all))
    changed = [seg(1), seg(3)]  # same batch number, different ids
    save_transcript("job_c3", changed, store)
    client = FakeClient(clean_all)
    clean.clean_job("job_c3", storage=store, client=client)
    assert len(client.calls) == 1
