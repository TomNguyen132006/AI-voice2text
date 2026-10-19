"""Tests for golden/run_golden.py (S2-5). Fake client only: no network, no keys."""
import importlib.util
import json
from pathlib import Path

import pytest

import llm
from schemas import Section
from tests.test_clean import FakeClient, as_json, payload_of

spec = importlib.util.spec_from_file_location(
    "run_golden", Path(__file__).resolve().parent.parent / "golden" / "run_golden.py"
)
golden = importlib.util.module_from_spec(spec)
spec.loader.exec_module(golden)


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "_sleep", lambda s: None)
    monkeypatch.setenv("LLM_LOG_PATH", str(tmp_path / "calls.jsonl"))


def fixing_model(kwargs, n):
    """Clean call: fixes the two known mistakes. Topic call: two sections."""
    user = payload_of(kwargs)
    if "segments" in user and "duration_sec" not in user:
        return as_json(
            (s["id"], s["text"].replace("uh ", "").replace(" was b", " plus b").replace("Hesians", "Hessians"))
            for s in user["segments"]
        )
    return json.dumps([{"title": "Pure Quadratic", "first_segment_id": "seg_0001"},
                       {"title": "Gradient", "first_segment_id": "seg_0027"}])


def test_excerpt_is_the_real_data_with_the_known_spots():
    seg = {s.id: s for s in golden.load_excerpt()}
    assert " was bx2" in seg["seg_0005"].text and "Hesians" in seg["seg_0026"].text
    assert 240 <= seg["seg_0036"].end - seg["seg_0001"].start <= 280


def test_run_with_a_good_model_passes_all_checks():
    r = golden.run(client=FakeClient(fixing_model))
    assert r["hard"] == []
    soft = r["soft"]
    assert all(i["ok"] for k in ("must_fix", "must_not_change") for i in soft[k]), soft
    assert soft["boundary"]["ok"] and soft["boundary"]["distance"] == 0
    assert [o["ok"] for o in soft["optional_boundaries"]] == [False]  # seg_0015 is optional: absent is fine
    assert [s.id for s in r["sections"]] == ["sec_01", "sec_02"]


def test_soft_checks_report_failures_and_known_unfixed_without_raising():
    seg = golden.load_excerpt()
    one = [Section(id="sec_01", title="A", start=seg[0].start, end=seg[-1].end, segment_ids=[s.id for s in seg])]
    soft = golden.soft_checks(seg, seg, one)  # "cleaning" that changed nothing
    assert [i["ok"] for i in soft["must_fix"]] == [False]  # Hesians still there
    assert [i["ok"] for i in soft["must_not_change"]] == [True, True]
    assert [i["ok"] for i in soft["known_unfixed"]] == [False]  # "was" still there: known, not a failure
    assert soft["boundary"]["ok"] is False and soft["boundary"]["distance"] is None


def test_must_not_change_fails_when_minima_is_rewritten_or_symbols_added():
    seg = golden.load_excerpt()
    one = [Section(id="sec_01", title="A", start=seg[0].start, end=seg[-1].end, segment_ids=[s.id for s in seg])]
    bad = [s.model_copy(update={"text": {"seg_0018": "So I'm a minimum.", "seg_0021": "x star is (0,0)"}.get(s.id, s.text)})
           for s in seg]
    assert [i["ok"] for i in golden.soft_checks(seg, bad, one)["must_not_change"]] == [False, False]


def test_expected_report_is_none_without_expected_files(monkeypatch, tmp_path):
    monkeypatch.setattr(golden, "EXPECTED_CLEAN", tmp_path / "nope.json")
    seg = golden.load_excerpt()
    assert golden.expected_report(seg, seg, []) is None


def test_expected_report_similarity_and_boundary_distance(monkeypatch, tmp_path):
    seg = golden.load_excerpt()
    (tmp_path / "c.json").write_text(json.dumps([s.model_dump() for s in seg]), encoding="utf-8")
    (tmp_path / "s.json").write_text(json.dumps([{"title": "A", "first_segment_id": "seg_0001"},
                                                  {"title": "B", "first_segment_id": "seg_0027"}]), encoding="utf-8")
    monkeypatch.setattr(golden, "EXPECTED_CLEAN", tmp_path / "c.json")
    monkeypatch.setattr(golden, "EXPECTED_SECTIONS", tmp_path / "s.json")
    secs = [Section(id="a", title="A", start=0, end=1, segment_ids=["seg_0001"]),
            Section(id="b", title="B", start=1, end=2, segment_ids=["seg_0025"])]
    rep = golden.expected_report(seg, seg, secs)
    assert set(rep["similarity"].values()) == {1.0}
    assert rep["boundary_moved"] == [("seg_0027", 2)]


def test_hard_checks_catch_changed_times_missing_ids_and_gaps():
    seg = golden.load_excerpt()
    ok_sections = [Section(id="sec_01", title="A", start=seg[0].start, end=seg[-1].end,
                           segment_ids=[s.id for s in seg])]
    assert golden.hard_checks(seg, seg, ok_sections) == []
    moved = [s.model_copy(update={"end": s.end + 1}) if s.id == "seg_0003" else s for s in seg]
    assert "times changed" in golden.hard_checks(seg, moved, ok_sections)[0]
    assert "ids changed" in golden.hard_checks(seg, seg[:-1], ok_sections)[0]
    split = [Section(id="sec_01", title="A", start=seg[0].start, end=seg[9].end, segment_ids=[s.id for s in seg[:10]]),
             Section(id="sec_02", title="B", start=seg[10].start + 1, end=seg[-1].end,
                     segment_ids=[s.id for s in seg[10:]])]
    assert any("gap" in p or "do not match" in p for p in golden.hard_checks(seg, seg, split))
    dup = ok_sections + [ok_sections[0]]
    assert "exactly once" in golden.hard_checks(seg, seg, dup)[0]
