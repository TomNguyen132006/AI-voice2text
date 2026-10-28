"""Tests for fix.py (S5-3, S5-4). Fake client only: no network, no keys."""
import json

import pytest

import fix
import judge
import llm
import llm_config
from storage import LocalStorage, job_key, load_json, save_json, save_transcript
from tests.test_clean import FakeClient, payload_of
from tests.test_judge import ORIGINAL, SEARCH, SECS, lec, st, web

ULTRA = llm_config.get_role("ultra").model_id
SUPER = llm_config.get_role("super").model_id


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "_sleep", lambda s: None)
    monkeypatch.setenv("LLM_LOG_PATH", str(tmp_path / "calls.jsonl"))


class Models:
    """Fake Ultra + Super. judge_for(text) -> (verdict, reason) is what Ultra says about a statement text;
    fixer_for(payload) -> the rewritten text (or a raw reply string)."""

    def __init__(self, judge_for, fixer_for=lambda p: "A better statement."):
        self.judge_for, self.fixer_for = judge_for, fixer_for
        self.fixer_calls, self.judge_calls = [], []

    def __call__(self, kwargs, n):
        payload = payload_of(kwargs)
        if kwargs["model"] == ULTRA:
            self.judge_calls.append(payload)
            answers = []
            for s in payload["statements"]:
                verdict, reason = self.judge_for(s["text"])
                answers.append({"statement_id": s["id"], "verdict": verdict, "reason": reason})
            return json.dumps(answers)
        assert kwargs["model"] == SUPER
        self.fixer_calls.append(payload)
        out = self.fixer_for(payload)
        if out.startswith("RAW:"):
            return out[4:]
        return out if out.startswith("{") else json.dumps({"text": out})


def run(statements, models, search=SEARCH):
    client = FakeClient(models)
    first = judge.judge_statements("job_f1", statements, ORIGINAL, SECS, search, client)
    result = fix.fix_statements("job_f1", statements, first, ORIGINAL, SECS, search, client)
    return result, first


def bad_first(text):
    return ("unsupported", "not in the source") if text.startswith("Bad") else ("pass", "ok")


def test_all_pass_means_no_fixer_call():
    models = Models(lambda t: ("pass", "ok"))
    result, _ = run([st(1), st(2)], models)
    assert [s.id for s in result.statements] == ["st_0001", "st_0002"]
    assert models.fixer_calls == [] and result.log == []
    f = result.report["final"]
    assert f["kept"] == 2 and f["passed_first_time"] == 2 and f["dropped"] == 0 and f["fixed"] == 0


def test_failed_statement_is_fixed_and_rejudged():
    models = Models(lambda t: ("pass", "ok") if t == "A better statement." or not t.startswith("Bad") else ("unsupported", "claim missing"))
    result, _ = run([st(1, text="Bad claim."), st(2)], models)
    got = {s.id: s for s in result.statements}
    assert got["st_0001"].text == "A better statement."
    assert got["st_0001"].sources == st(1).sources and got["st_0001"].section_id == "sec_01"  # only the text changes
    assert len(models.fixer_calls) == 1  # only the failed one is rewritten
    p = models.fixer_calls[0]
    assert p["statement"]["text"] == "Bad claim." and p["problem"] == {"verdict": "unsupported", "reason": "claim missing"}
    entry = result.log[0]
    assert entry["outcome"] == "fixed" and entry["second_verdict"] == "pass" and entry["old_text"] == "Bad claim."
    f = result.report["final"]
    assert (f["kept"], f["fixed"], f["dropped"]) == (2, 1, 0)


def test_rewrite_that_fails_again_is_dropped_and_not_rewritten_twice():
    models = Models(lambda t: ("pass", "ok") if t == "A fine statement." else ("unsupported", "still wrong"))
    result, _ = run([st(1, text="Bad claim."), st(2, text="A fine statement.")], models)
    assert [s.id for s in result.statements] == ["st_0002"]
    assert len(models.fixer_calls) == 1  # no third round
    assert result.log[0]["outcome"] == "dropped" and result.log[0]["reason"] == "still_unsupported"
    assert result.report["final"]["dropped_by_reason"] == {"still_unsupported": 1}


def test_contradicts_is_fixed_too():
    models = Models(lambda t: ("pass", "ok") if t == "A better statement." else ("contradicts", "lecture says no"))
    result, _ = run([st(1, text="Bad claim.")], models)
    assert result.log[0]["first_verdict"] == "contradicts" and result.log[0]["outcome"] == "fixed"


def test_code_rejected_statements_are_dropped_without_fixer():
    models = Models(lambda t: ("pass", "ok"))
    result, _ = run([st(1, sources=[]), st(2, sources=[web("https://made-up.example/x")]), st(3)], models)
    assert [s.id for s in result.statements] == ["st_0003"]
    assert models.fixer_calls == []
    assert result.report["final"]["dropped_by_reason"] == {"no_source": 1, "unknown_url": 1}


def test_unjudged_statement_is_kept_and_marked():
    client = FakeClient(lambda kwargs, n: json.dumps([]))  # Ultra skips every statement
    first = judge.judge_statements("job_f1", [st(1)], ORIGINAL, SECS, SEARCH, client)
    result = fix.fix_statements("job_f1", [st(1)], first, ORIGINAL, SECS, SEARCH, client)
    assert [s.id for s in result.statements] == ["st_0001"]
    assert result.log[0]["outcome"] == "kept_unjudged"
    assert result.report["final"]["kept_unjudged"] == 1 and result.report["final"]["dropped"] == 0


@pytest.mark.parametrize("reply, reason", [
    ("", "fixer_gave_up"),
    ("Bad claim.", "fixer_no_change"),
    ("RAW:not json at all", "fixer_failed"),
])
def test_fixer_failures_drop_the_statement(reply, reason):
    models = Models(bad_first, fixer_for=lambda p: reply)
    result, _ = run([st(1, text="Bad claim."), st(2)], models)
    assert [s.id for s in result.statements] == ["st_0002"]
    assert result.log[0]["reason"] == reason
    assert all(c["statement"]["id"] == "st_0001" for c in models.fixer_calls)


def test_urls_are_stripped_from_the_rewrite():
    models = Models(
        lambda t: ("pass", "ok") if t == "Fixed text." else bad_first(t),
        fixer_for=lambda p: "Fixed text. https://evil.example/x",
    )
    result, _ = run([st(1, text="Bad claim.")], models)
    assert result.statements[0].text == "Fixed text."


def test_fixer_prompt_has_sources_and_no_urls():
    models = Models(bad_first)
    run([st(1, text="Bad claim.", sources=[lec(1), web()])], models)
    p = models.fixer_calls[0]
    assert p["statement"]["sources"] == ["seg_0001", "web_1"]
    assert p["web"][0]["id"] == "web_1" and "https://" not in json.dumps(p)


def test_report_totals_cost_of_all_rounds():
    models = Models(lambda t: ("pass", "ok") if t == "A better statement." else bad_first(t))
    result, first = run([st(1, text="Bad claim.")], models)
    f, r = result.report["final"], result.report
    assert f["total_calls"] == first.report["calls"] + r["fix"]["fixer_calls"] + r["fix"]["second_round"]["calls"] == 3
    assert f["total_est_cost_usd"] == pytest.approx(
        first.report["est_cost_usd"] + r["fix"]["fixer_est_cost_usd"] + r["fix"]["second_round"]["est_cost_usd"]
    )
    assert r["fix"]["attempted"] == 1 and r["fix"]["fixed"] == 1
    assert "1 statements -> 1 kept" in fix.format_table(result)


def test_fix_job_saves_files_and_reuses_judge_json(tmp_path):
    storage = LocalStorage(tmp_path / "data")
    save_transcript("job_f2", ORIGINAL, storage)
    save_json(job_key("job_f2", "sections.json"), [s.model_dump() for s in SECS], storage)
    save_json(job_key("job_f2", "search.json"), SEARCH, storage)
    save_json(job_key("job_f2", "notes.json"), [st(1, text="Bad claim.").model_dump(), st(2).model_dump()], storage)
    models = Models(lambda t: ("pass", "ok") if t == "A better statement." else bad_first(t))
    client = FakeClient(models)
    fix.fix_job("job_f2", storage=storage, client=client)
    assert [s["text"] for s in load_json(job_key("job_f2", "notes_final.json"), storage)] == ["A better statement.", "Statement 2."]
    assert load_json(job_key("job_f2", "fix_log.json"), storage)[0]["outcome"] == "fixed"
    assert load_json(job_key("job_f2", "judge_report.json"), storage)["final"]["fixed"] == 1
    ultra_calls = len(models.judge_calls)
    fix.fix_job("job_f2", storage=storage, client=client)  # second run: judge.json is reused, not asked again
    assert len(models.judge_calls) == ultra_calls + 1  # only the re-judge of the rewrite


def test_prompt_lets_the_fixer_drop_a_statement_that_teaches_nothing():
    prompt = fix.SYSTEM_PROMPT
    assert "teach something a student could be asked about" in prompt
    assert "instead of a vague rewrite" in prompt and "there was a problem that was not easy to do" in prompt
    assert not any(ch.isdigit() for ch in prompt.replace("st_0001", ""))


def test_empty_answer_is_counted_as_dropped_empty():
    models = Models(bad_first, fixer_for=lambda p: "")
    result, _ = run([st(1, text="Bad claim one."), st(2, text="Bad claim two."), st(3)], models)
    final = result.report["final"]
    assert [s.id for s in result.statements] == ["st_0003"]
    assert final["n_dropped_empty"] == 2 and final["dropped_by_reason"] == {"fixer_gave_up": 2}


def test_vague_rewrite_is_dropped_when_the_fixer_follows_the_new_rule():
    # the fixer sees the rule and answers with an empty text for a claim that has nothing left; a real rewrite is still fixed
    def fixer(payload):
        return "" if payload["statement"]["text"].startswith("Bad vague") else "A better statement."

    models = Models(bad_first, fixer_for=fixer)
    result, _ = run([st(1, text="Bad vague claim."), st(2, text="Bad claim with content.")], models)
    assert [s.id for s in result.statements] == ["st_0002"] and result.report["final"]["n_dropped_empty"] == 1
    assert result.report["final"]["fixed"] == 1
