"""Tests for slides.py (S4-2). Fake client only: no network, no keys."""
import json

import httpx2 as httpx  # openai 3.x ships httpx2, not httpx
import openai
import pytest

import llm
import slides
from schemas import Section, Slide, Statement
from storage import LocalStorage, job_key, load_json, save_json
from tests.test_clean import FakeClient, payload_of

REQUEST = httpx.Request("POST", "https://example.invalid/v1/chat/completions")

SECS = [
    Section(id="sec_01", title="Hessian Basics", start=0.0, end=75.5, segment_ids=["seg_0000"]),
    Section(id="sec_02", title="Descent", start=75.5, end=3700.0, segment_ids=["seg_0001"]),
]
LEC = {"type": "lecture", "segment_id": "seg_0000", "start": 1.0, "end": 9.5}
WEB = {"type": "web", "url": "https://en.wikipedia.org/wiki/Hessian_matrix", "title": "Hessian matrix - Wiki"}


def st(n, section="sec_01", text=None, sources=None):
    return Statement(id=f"st_{n:04d}", section_id=section, text=text or f"Statement number {n} is short.",
                     sources=sources if sources is not None else [LEC, WEB])


STATEMENTS = [st(1), st(2), st(3), st(4, "sec_02", sources=[LEC]), st(5, "sec_02")]


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "_sleep", lambda s: None)
    monkeypatch.setenv("LLM_LOG_PATH", str(tmp_path / "calls.jsonl"))
    monkeypatch.delenv("SLIDE_MAX_BULLETS", raising=False)
    monkeypatch.delenv("SLIDE_MAX_WORDS_PER_BULLET", raising=False)


def answer(bullets, title="Hessian topic", example=None):
    return json.dumps({"title": title, "bullets": bullets, "example": example})


def one(responder, section=SECS[0], statements=None, **kw):
    statements = statements if statements is not None else [s for s in STATEMENTS if s.section_id == section.id]
    client = FakeClient(responder)
    return slides.slide_for_section(section, statements, job_id="job_s1", client=client, **kw), client


def test_valid_slide_copies_text_and_sources_unchanged():
    r, client = one(lambda k, n: answer(["st_0001", "st_0002", "st_0003"], example="st_0002"))
    slide = r.slide
    assert isinstance(slide, Slide) and slide.section_id == "sec_01" and slide.title == "Hessian topic"
    assert [b.id for b in slide.bullets] == ["st_0001", "st_0003"]  # the model's order, without the example
    assert [b.text for b in slide.bullets] == [STATEMENTS[0].text, STATEMENTS[2].text]  # copied, not rewritten
    assert slide.bullets[0].sources == STATEMENTS[0].sources and [s.type for s in slide.bullets[0].sources] == ["lecture", "web"]
    assert slide.example == STATEMENTS[1].text and r.info["example"] == "st_0002"
    assert slide.bullets[0] is not STATEMENTS[0]  # a copy
    assert client.calls[0]["model"] == "nvidia/nemotron-3-super-120b-a12b" and r.info["flagged"] is None
    assert r.info["bullets"] == 2


def test_example_is_not_printed_twice_and_its_source_goes_to_the_speaker_notes():
    r, _ = one(lambda k, n: answer(["st_0001", "st_0002"], example="st_0002"))
    slide = r.slide
    assert slide.example not in [b.text for b in slide.bullets]
    notes = slide.speaker_notes.splitlines()
    assert notes[0] == STATEMENTS[2].text  # the statement that is neither bullet nor example
    assert notes[1] == ("Source of the example: lecture 00:01-00:09 (seg_0000); "
                        "web: Hessian matrix - Wiki <https://en.wikipedia.org/wiki/Hessian_matrix>.")
    assert notes[-1].startswith("Lecture time of this section")


def test_example_that_is_the_only_bullet_stays_a_bullet():
    r, _ = one(lambda k, n: answer(["st_0002"], example="st_0002"))
    assert [b.id for b in r.slide.bullets] == ["st_0002"] and r.slide.example is None and r.info["example"] is None
    assert r.info["dropped"][0]["reason"].startswith("example_is_the_only_bullet")


def test_model_cannot_change_the_text():
    r, _ = one(lambda k, n: json.dumps({"title": "T", "bullets": ["st_0001"], "text": "NEW CLAIM", "st_0001": "NEW CLAIM"}))
    assert r.slide.bullets[0].text == STATEMENTS[0].text and "NEW CLAIM" not in r.slide.model_dump_json()


def test_speaker_notes_hold_only_statement_texts_and_the_time_range():
    r, _ = one(lambda k, n: answer(["st_0001"]))
    assert r.slide.speaker_notes.splitlines() == [
        STATEMENTS[1].text, STATEMENTS[2].text, "Lecture time of this section: 00:00 - 01:15 (to listen again).",
    ]
    r2, _ = one(lambda k, n: answer(["st_0004", "st_0005"]), section=SECS[1])
    assert r2.slide.speaker_notes == "Lecture time of this section: 01:15 - 1:01:40 (to listen again)."


def test_unknown_and_foreign_and_duplicate_ids_are_dropped():
    r, _ = one(lambda k, n: answer(["st_0001", "st_9999", "st_0004", "st_0001"]))
    assert [b.id for b in r.slide.bullets] == ["st_0001"]
    assert [(d["id"], d["reason"]) for d in r.info["dropped"]] == [
        ("st_9999", "unknown_statement_id"), ("st_0004", "unknown_statement_id"), ("st_0001", "duplicate_id"),
    ]


def test_no_valid_bullets_is_flagged_and_there_is_no_slide():
    r, _ = one(lambda k, n: answer(["st_9999"]))
    assert r.slide is None and r.info["flagged"] == "no_bullets"
    r, _ = one(lambda k, n: answer([]))
    assert r.slide is None and r.info["flagged"] == "no_bullets"


def test_too_many_bullets_are_cut_and_move_to_the_notes():
    many = [st(n, text=f"Note {n}.") for n in range(1, 8)]
    r, _ = one(lambda k, n: answer([s.id for s in many]), statements=many)
    assert len(r.slide.bullets) == 5  # default SLIDE_MAX_BULLETS
    assert [d["id"] for d in r.info["dropped"]] == ["st_0006", "st_0007"]
    assert "Note 6." in r.slide.speaker_notes and "Note 7." in r.slide.speaker_notes
    r, _ = one(lambda k, n: answer([s.id for s in many]), statements=many, max_bullets=2)
    assert len(r.slide.bullets) == 2


def test_env_overrides_the_limits(monkeypatch):
    monkeypatch.setenv("SLIDE_MAX_BULLETS", "1")
    r, _ = one(lambda k, n: answer(["st_0001", "st_0002"]))
    assert len(r.slide.bullets) == 1


def test_statement_with_too_many_words_is_not_a_bullet():
    long = st(1, text="word " * 40)
    r, _ = one(lambda k, n: answer(["st_0001", "st_0002"]), statements=[long, STATEMENTS[1]])
    assert [b.id for b in r.slide.bullets] == ["st_0002"]
    assert r.info["dropped"][0]["reason"].startswith("too_long_for_a_bullet")
    assert long.text in r.slide.speaker_notes  # nothing is lost


def test_example_must_be_one_of_the_bullets():
    r, _ = one(lambda k, n: answer(["st_0001"], example="st_0002"))
    assert r.slide.example is None and r.info["dropped"][0]["reason"] == "example_not_in_bullets"


def test_bad_title_falls_back_to_the_section_title():
    r, _ = one(lambda k, n: answer(["st_0001"], title="This title has far too many words to be a title"))
    assert r.slide.title == "Hessian Basics" and "title_empty_or_too_long" in r.info["dropped"][0]["reason"]


def test_prompt_has_no_sources_no_urls_and_only_this_sections_statements():
    r, client = one(lambda k, n: answer(["st_0001"]))
    everything = json.dumps(client.calls[0]["messages"])
    assert "http" not in everything and "segment_id" not in everything and "st_0004" not in everything
    assert [s["id"] for s in payload_of(client.calls[0])["statements"]] == ["st_0001", "st_0002", "st_0003"]
    prompt = slides.SYSTEM_PROMPT.replace("st_0001", "").replace("st_0002", "")
    assert not any(ch.isdigit() for ch in prompt)  # limits live in slides_config.py, not in the prompt


def test_invalid_answer_is_retried_once():
    r, client = one(lambda k, n: "nope" if n == 1 else answer(["st_0001"]))
    assert r.slide is not None and r.info["tries"] == 2 and len(client.calls) == 2


def test_failed_section_is_flagged_and_the_next_section_still_runs():
    def responder(kwargs, n):
        if payload_of(kwargs)["section_id"] == "sec_01":
            raise openai.APIStatusError("bad", response=httpx.Response(400, request=REQUEST), body=None)
        return answer(["st_0004"], example="st_0004")

    inputs = {"sections": SECS, "statements": STATEMENTS}
    result = slides.write_slides("job_s1", inputs, FakeClient(responder))
    assert [f["section_id"] for f in result.report["flagged"]] == ["sec_01"] and result.report["flagged"][0]["reason"] == "api_error"
    assert [s.section_id for s in result.slides] == ["sec_02"] and result.report["slide_count"] == 1


def test_section_without_statements_makes_no_call():
    r, client = one(lambda k, n: answer([]), statements=[])
    assert r.slide is None and r.info["flagged"] == "no_statements" and client.calls == []


def test_slides_job_saves_files(tmp_path):
    storage = LocalStorage(tmp_path)
    save_json(job_key("job_s2", "sections.json"), [s.model_dump() for s in SECS], storage)
    save_json(job_key("job_s2", "notes.json"), [s.model_dump() for s in STATEMENTS], storage)
    fake = FakeClient(lambda k, n: answer(["st_0001"] if payload_of(k)["section_id"] == "sec_01" else ["st_0004"]))
    result = slides.slides_job("job_s2", storage, fake)
    saved = [Slide(**s) for s in load_json(job_key("job_s2", "slides.json"), storage)]
    report = load_json(job_key("job_s2", "slides_report.json"), storage)
    assert [s.section_id for s in saved] == ["sec_01", "sec_02"] and saved[0].bullets[0].sources == STATEMENTS[0].sources
    assert report["slide_count"] == 2 and report["calls"] == 2 and "slide" in slides.format_table(result)
    assert "http" not in json.dumps(report)
