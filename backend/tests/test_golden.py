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
                       {"title": "Gradient", "first_segment_id": "seg_0016"}])


def test_excerpt_is_the_real_data_with_the_known_spots():
    seg = {s.id: s for s in golden.load_excerpt()}
    assert " was bx2" in seg["seg_0005"].text and "Hesians" in seg["seg_0026"].text
    assert 120 <= seg["seg_0030"].end - seg["seg_0001"].start <= 240


def test_run_with_a_good_model_passes_all_checks():
    r = golden.run(client=FakeClient(fixing_model))
    assert r["hard"] == []
    assert all(ok for ok, _ in r["soft"]), r["soft"]
    assert [s.id for s in r["sections"]] == ["sec_01", "sec_02"]


def test_soft_checks_report_a_missed_fix_without_failing():
    seg = golden.load_excerpt()
    soft = golden.soft_checks(seg, seg)  # "cleaning" that changed nothing
    assert [ok for ok, _ in soft if "seg_0005" in _ or "Hesians" in _ or "seg_0026" in _] == [False, False]


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
