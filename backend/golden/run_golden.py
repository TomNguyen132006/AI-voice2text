"""Golden test (S2-5): clean + topic split on a short real excerpt, then print the differences.

Usage (from backend/):  python golden/run_golden.py [--save out.json]   (3-4 real Nano calls, about $0.004)

HARD checks fail the run (exit 1): segment ids preserved, times unchanged, sections have no gap and
no overlap and cover every segment exactly once.
SOFT checks (checks.json) are only reported and never change the exit code (the model is not
deterministic): must_fix, must_not_change, known_unfixed (ASR errors the cleaner cannot fix), the
boundary near the expected topic change and, if expected_*.json exist, similarity to the ideal text.
Data: excerpt.json (see NOTICE for the license). Nothing is written to disk except --save.
"""
import difflib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from dotenv import load_dotenv

load_dotenv(HERE.parent / ".env")

import clean
import llm
import topics
from schemas import Segment

JOB_ID = "golden"

CHECKS_PATH = HERE / "checks.json"  # soft checks: must_fix, must_not_change, known_unfixed, boundary
EXPECTED_CLEAN = HERE / "expected_clean.json"  # ideal cleaned text per segment (optional)
EXPECTED_SECTIONS = HERE / "expected_sections.json"  # [{"title", "first_segment_id"}] (optional)


def load_excerpt() -> list[Segment]:
    return [Segment(**s) for s in json.loads((HERE / "excerpt.json").read_text(encoding="utf-8"))]


def hard_checks(original, cleaned, sections) -> list[str]:
    """Return a list of problems; empty means all hard checks pass."""
    problems = []
    if [s.id for s in cleaned] != [s.id for s in original]:
        problems.append("segment ids changed or reordered by cleaning")
    elif any((a.start, a.end) != (b.start, b.end) for a, b in zip(original, cleaned)):
        problems.append("segment times changed by cleaning")
    by_id = {s.id: s for s in original}
    seen = [i for sec in sections for i in sec.segment_ids]
    if seen != [s.id for s in original]:
        problems.append("sections do not contain every segment exactly once, in order")
        return problems
    # A section starts at its first segment and ends where the next one starts (the last one at its
    # last segment's end), so the pause between two topics belongs to the earlier section.
    for n, sec in enumerate(sections):
        end = by_id[sections[n + 1].segment_ids[0]].start if n + 1 < len(sections) else by_id[sec.segment_ids[-1]].end
        if (sec.start, sec.end) != (by_id[sec.segment_ids[0]].start, end):
            problems.append(f"{sec.id} times do not match its segments")
    for a, b in zip(sections, sections[1:]):
        if a.end != b.start:
            problems.append(f"{a.id} -> {b.id}: {'gap' if a.end < b.start else 'overlap'} of {abs(b.start - a.end):.2f} s")
    return problems


def load_checks() -> dict:
    return json.loads(CHECKS_PATH.read_text(encoding="utf-8"))


def soft_checks(original, cleaned, sections, checks=None) -> dict:
    """The three lists from checks.json plus the boundary check. Each item: {ok, msg}. Never fatal."""
    checks = checks or load_checks()
    orig = {s.id: s.text for s in original}
    new = {s.id: s.text for s in cleaned}
    out = {"must_fix": [], "must_not_change": [], "known_unfixed": [], "boundary": None}
    for c in checks["must_fix"]:
        out["must_fix"].append({"ok": c["contains"] in new[c["id"]],
                                "msg": f"{c['id']} contains '{c['contains']}': {new[c['id']]!r}"})
    for c in checks["must_not_change"]:
        if "keeps" in c:
            out["must_not_change"].append({"ok": c["keeps"] in new[c["id"]],
                                           "msg": f"{c['id']} keeps '{c['keeps']}': {new[c['id']]!r}"})
        if c.get("no_new_symbols"):
            added = set(new[c["id"]]) - set(orig[c["id"]])
            bad = sorted(ch for ch in added if ch in clean.NEW_SYMBOL_CHARS or ch.isdigit())
            out["must_not_change"].append({"ok": not bad,
                                           "msg": f"{c['id']} gets no new digits/symbols (added: {bad or 'none'})"})
    for c in checks["known_unfixed"]:
        fixed = c["right"] in re.findall(r"[\w']+", new[c["id"]])
        state = "FIXED" if fixed else "still wrong (known, not a failure)"
        out["known_unfixed"].append({"ok": fixed, "msg": f"{c['id']} '{c['wrong']}' -> '{c['right']}': {state}"})
    index = {s.id: i for i, s in enumerate(original)}
    want = index[checks["boundary"]["expected_first_segment"]]
    cuts = [index[s.segment_ids[0]] for s in sections[1:]]
    nearest = min(cuts, key=lambda i: abs(i - want), default=None)
    dist = None if nearest is None else abs(nearest - want)
    where = "none found" if dist is None else f"nearest cut at {original[nearest].id}, {dist} segment(s) away"
    out["boundary"] = {"ok": dist is not None and dist <= checks["boundary"]["within_segments"], "distance": dist,
                       "msg": f"boundary near {checks['boundary']['expected_first_segment']}: {where}"}
    return out


def expected_report(original, cleaned, sections) -> dict | None:
    """Compare with expected_clean.json / expected_sections.json when both exist: text similarity per
    segment and how far each expected boundary is from the nearest actual one. Report only."""
    if not (EXPECTED_CLEAN.is_file() and EXPECTED_SECTIONS.is_file()):
        return None
    exp = {s["id"]: s["text"] for s in json.loads(EXPECTED_CLEAN.read_text(encoding="utf-8"))}
    sim = {s.id: difflib.SequenceMatcher(None, s.text, exp[s.id]).ratio() for s in cleaned}
    index = {s.id: i for i, s in enumerate(original)}
    got = [index[s.segment_ids[0]] for s in sections[1:]]
    moved = []
    for e in json.loads(EXPECTED_SECTIONS.read_text(encoding="utf-8"))[1:]:
        i = index[e["first_segment_id"]]
        moved.append((e["first_segment_id"], min((abs(g - i) for g in got), default=None)))
    return {"similarity": sim, "boundary_moved": moved}


def run(client=None, segments=None) -> dict:
    segments = segments or load_excerpt()
    client = client or llm.make_client()
    cleaned_result = clean.clean_transcript(segments, job_id=JOB_ID, client=client, max_workers=1)
    split_result = topics.split_topics(cleaned_result.segments, job_id=JOB_ID, client=client)
    return {
        "original": segments,
        "cleaned": cleaned_result.segments,
        "sections": split_result.sections,
        "clean_report": cleaned_result.report,
        "topics_report": split_result.report,
        "hard": hard_checks(segments, cleaned_result.segments, split_result.sections),
        "soft": soft_checks(segments, cleaned_result.segments, split_result.sections),
        "expected": expected_report(segments, cleaned_result.segments, split_result.sections),
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    r = run()
    cr, tr = r["clean_report"], r["topics_report"]
    print(f"== Differences (original -> cleaned), {cr['changed_count']} of {cr['total_segments']} changed ==")
    for a, b in zip(r["original"], r["cleaned"]):
        if a.text != b.text:
            print(f"{a.id}\n  - {a.text}\n  + {b.text}")
    print(f"\n== Reverted by guards: {cr['reverted_count']} {cr['reverted_by_reason']} ==")
    for x in cr["reverted"]:
        print(f"  {x['id']}: {x['reason']}")
    print(f"\n== Sections ({len(r['sections'])}, fallback used: {tr['used_fallback']}) ==")
    for s in r["sections"]:
        print(f"  {s.id} {s.start:7.1f}-{s.end:7.1f}  {len(s.segment_ids):2d} segs  {s.title}")
    soft = r["soft"]
    print("\n== SOFT checks (report only, never change the exit code) ==")
    for name in ("must_fix", "must_not_change", "known_unfixed"):
        items = soft[name]
        word = "fixed" if name == "known_unfixed" else "pass"
        print(f"  {name}: {sum(i['ok'] for i in items)} of {len(items)} {word}")
        for i in items:
            mark = ("FIXED" if i["ok"] else "known") if name == "known_unfixed" else ("ok" if i["ok"] else "FAIL")
            print(f"    [{mark}] {i['msg']}")
    print(f"  boundary: [{'ok' if soft['boundary']['ok'] else 'MISS'}] {soft['boundary']['msg']}")
    if r["expected"]:
        sims = r["expected"]["similarity"]
        print(f"  vs expected: mean similarity {sum(sims.values()) / len(sims):.3f}; "
              f"below 1.0: {[f'{k} {v:.2f}' for k, v in sims.items() if v < 1.0]}")
        print(f"  expected boundaries: distance to nearest actual cut (segments): {r['expected']['boundary_moved']}")
    if "--save" in sys.argv:
        out = {"cleaned": {s.id: s.text for s in r["cleaned"]}, "cuts": [s.segment_ids[0] for s in r["sections"]],
               "titles": [s.title for s in r["sections"]], "reverted": cr["reverted"],
               "changed": cr["changed_count"], "cost": cr["est_cost_usd"] + tr["est_cost_usd"],
               "soft": {k: ([i["ok"] for i in v] if isinstance(v, list) else v["ok"]) for k, v in soft.items()}}
        Path(sys.argv[sys.argv.index("--save") + 1]).write_text(json.dumps(out, indent=1), encoding="utf-8")
    cost = cr["est_cost_usd"] + tr["est_cost_usd"]
    print(f"\ncalls: clean {cr['calls']} + topics {tr['calls']}; "
          f"tokens: {cr['prompt_tokens'] + tr['prompt_tokens']} prompt + "
          f"{cr['completion_tokens'] + tr['completion_tokens']} completion; est cost ${cost:.4f}")
    print("\n== HARD checks ==")
    if r["hard"]:
        for p in r["hard"]:
            print(f"  FAIL: {p}")
        return 1
    print("  all passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
