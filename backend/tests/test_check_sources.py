"""Tests for check_sources.py: good and bad fixtures, no model, no network."""
import copy

import pytest

import check_sources
from storage import LocalStorage, job_key, save_json

ORIGINAL = [
    {"id": "seg_0000", "start": 0.0, "end": 9.5, "text": "uh first words"},
    {"id": "seg_0001", "start": 10.0, "end": 19.5, "text": "second words"},
]
SEARCH = [{"section_id": "sec_01", "term": "t", "results": [
    {"title": "Hessian matrix - Wiki", "url": "https://en.wikipedia.org/wiki/Hessian_matrix", "snippet": "s"},
    {"title": "Page https://x.org/leak title", "url": "https://example.org/two", "snippet": "s"},
]}]
LEC0 = {"type": "lecture", "segment_id": "seg_0000", "start": 0.0, "end": 9.5}
LEC1 = {"type": "lecture", "segment_id": "seg_0001", "start": 10.0, "end": 19.5}
WEB0 = {"type": "web", "url": "https://en.wikipedia.org/wiki/Hessian_matrix", "title": "Hessian matrix - Wiki"}
WEB1 = {"type": "web", "url": "https://example.org/two", "title": "Page title"}  # notes.py stores the title without urls
NOTES = [
    {"id": "st_0001", "section_id": "sec_01", "text": "First.", "sources": [LEC0, WEB0]},
    {"id": "st_0002", "section_id": "sec_01", "text": "Second.", "sources": [LEC1]},
    {"id": "st_0003", "section_id": "sec_01", "text": "Third.", "sources": [WEB1]},
]
SLIDES = [{
    "section_id": "sec_01", "title": "Topic", "example": "Third.", "speaker_notes": "...",
    "bullets": [copy.deepcopy(NOTES[0]), copy.deepcopy(NOTES[1])],
}]
SLIDES_REPORT = {"slides": [{"section_id": "sec_01", "example_statement_id": "st_0003"}]}


def make(tmp_path, notes=NOTES, search=SEARCH, slides=SLIDES, slides_report=SLIDES_REPORT, original=ORIGINAL, final=None):
    storage = LocalStorage(tmp_path)
    for name, data in [("notes.json", notes), ("search.json", search), ("transcript.json", original),
                       ("slides.json", slides), ("slides_report.json", slides_report), ("notes_final.json", final)]:
        if data is not None:
            save_json(job_key("job_c1", name), copy.deepcopy(data), storage)
    return check_sources.check_job("job_c1", storage)


def failed(result):
    return {k: v["failed"] for k, v in result.items() if v["failed"]}


def test_good_fixture_passes_everything(tmp_path):
    result = make(tmp_path)
    assert failed(result) == {}
    assert result["a"]["passed"] == 3 and result["b"]["passed"] == 2 and result["c"]["passed"] == 2
    assert result["d"]["passed"] == 2 and result["e"]["passed"] == 1
    assert "ALL CHECKS PASSED" in check_sources.format_result(result)


def test_a_statement_without_source(tmp_path):
    notes = copy.deepcopy(NOTES)
    notes[1]["sources"] = []
    result = make(tmp_path, notes=notes, slides=None)
    assert failed(result) == {"a": 1} and "st_0002: no source" in result["a"]["failures"]


def test_b_url_not_in_search_and_title_mismatch(tmp_path):
    notes = copy.deepcopy(NOTES)
    notes[0]["sources"][1]["url"] = "https://en.wikipedia.org/wiki/Hessian_matrix/"  # one slash more: not an exact match
    notes[2]["sources"][0]["title"] = "A made-up title"
    result = make(tmp_path, notes=notes, slides=None)
    assert failed(result) == {"b": 2}
    assert "is not in search.json" in result["b"]["failures"][0] and "differs from search.json" in result["b"]["failures"][1]


def test_b_raw_title_with_url_is_also_accepted(tmp_path):
    notes = copy.deepcopy(NOTES)
    notes[2]["sources"][0]["title"] = "Page https://x.org/leak title"
    assert failed(make(tmp_path, notes=notes, slides=None)) == {}


@pytest.mark.parametrize("change", [
    {"start": 0.5}, {"end": 9.0}, {"segment_id": "seg_0099"}, {"start": None},
])
def test_c_lecture_source_must_equal_the_original_transcript(tmp_path, change):
    notes = copy.deepcopy(NOTES)
    notes[0]["sources"][0].update(change)
    result = make(tmp_path, notes=notes, slides=None)
    assert failed(result) == {"c": 1}


def test_c_missing_key_and_unknown_source_type(tmp_path):
    notes = copy.deepcopy(NOTES)
    del notes[0]["sources"][0]["end"]
    notes[1]["sources"].append({"type": "video", "x": 1})
    result = make(tmp_path, notes=notes, slides=None)
    assert failed(result) == {"c": 2} and "missing ['end']" in result["c"]["failures"][0]


def test_d_bullet_text_or_sources_changed(tmp_path):
    slides = copy.deepcopy(SLIDES)
    slides[0]["bullets"][0]["text"] = "First, but rewritten."
    slides[0]["bullets"][1]["sources"] = []
    result = make(tmp_path, slides=slides)
    assert failed(result) == {"d": 2}
    assert "text" in result["d"]["failures"][0] and "sources" in result["d"]["failures"][1]


def test_d_unknown_statement_id(tmp_path):
    slides = copy.deepcopy(SLIDES)
    slides[0]["bullets"][0]["id"] = "st_9999"
    assert failed(make(tmp_path, slides=slides)) == {"d": 1}


def test_e_example_text_differs_or_has_no_statement_id_or_is_also_a_bullet(tmp_path):
    slides = copy.deepcopy(SLIDES)
    slides[0]["example"] = "Third, rewritten."
    assert failed(make(tmp_path, slides=slides)) == {"e": 1}
    assert failed(make(tmp_path, slides_report={"slides": [{"section_id": "sec_01", "example_statement_id": None}]})) == {"e": 1}
    slides = copy.deepcopy(SLIDES)
    slides[0]["example"] = "First."
    report = {"slides": [{"section_id": "sec_01", "example_statement_id": "st_0001"}]}
    result = make(tmp_path, slides=slides, slides_report=report)
    assert failed(result) == {"e": 1} and "also a bullet" in result["e"]["failures"][0]


def test_slide_without_example_and_missing_slide_files(tmp_path):
    slides = copy.deepcopy(SLIDES)
    slides[0]["example"] = None
    result = make(tmp_path, slides=slides)
    assert failed(result) == {} and result["e"]["passed"] == 0
    result = make(tmp_path / "other", slides=None, slides_report=None)  # a fresh folder: no slide files
    assert result["d"]["skipped"] and result["e"]["skipped"] and failed(result) == {}


def test_only_the_first_five_failures_are_printed(tmp_path):
    notes = [{"id": f"st_{i:04d}", "section_id": "sec_01", "text": "t", "sources": []} for i in range(8)]
    result = make(tmp_path, notes=notes, slides=None)
    text = check_sources.format_result(result)
    assert result["a"]["failed"] == 8 and text.count("FAIL a") == 5 and "and 3 more a failures" in text
    assert "8 FAILURE(S)" in text


def test_d_and_e_use_notes_final_when_it_exists(tmp_path):
    """The judge rewrote st_0002 and the slides were built from notes_final.json: d and e must compare with it."""
    final = copy.deepcopy(NOTES)
    final[1]["text"] = "Second, rewritten by the fixer."
    slides = copy.deepcopy(SLIDES)
    slides[0]["bullets"][1]["text"] = final[1]["text"]
    assert failed(make(tmp_path, slides=slides, final=final)) == {}
    # without notes_final.json the same slides differ from notes.json
    assert failed(make(tmp_path / "no_final", slides=slides)) == {"d": 1}


def test_d_bullet_that_differs_from_notes_final_fails(tmp_path):
    final = copy.deepcopy(NOTES)
    final[1]["text"] = "Second, rewritten by the fixer."
    result = make(tmp_path, final=final)  # slides still carry the ORIGINAL text of st_0002
    assert failed(result) == {"d": 1} and "bullet st_0002 differs from its statement in text" in result["d"]["failures"][0]


def test_d_bullet_of_a_dropped_statement_fails(tmp_path):
    final = [copy.deepcopy(NOTES[0]), copy.deepcopy(NOTES[2])]  # st_0002 was dropped by the judge
    result = make(tmp_path, final=final)
    assert failed(result) == {"d": 1} and "bullet st_0002 is not in notes_final.json" in result["d"]["failures"][0]
