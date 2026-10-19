"""Golden test (S2-5): clean + topic split on a short real excerpt, then print the differences.

Usage (from backend/):  python golden/run_golden.py      (2-3 real Nano calls, well under $0.01)

HARD checks fail the run (exit 1): segment ids preserved, times unchanged, sections have no gap and
no overlap and cover every segment exactly once.
SOFT checks are only reported (the model is not deterministic): known mistakes that should be fixed,
words that should be left alone, how many segments changed or were reverted.
Data: excerpt.json (see NOTICE for the license). Nothing is written to disk.
"""
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

# (segment id, wrong text, right text). Wording from our own listening checks (Oct 8, Oct 17).
MUST_FIX = [
    ("seg_0005", "was", "plus"),  # "x1 squared was bx2 squared": the math needs "plus"
    ("seg_0026", "Hesians", "Hessians"),
]
# (segment id, text that must still be there, why). The cleaner must leave these alone.
MUST_KEEP = [
    ("seg_0018", "minima", "heard by ear: the speaker really said it"),
]
NO_NEW_SYMBOLS = ["seg_0021"]  # speaker said "x star is zero zero": formatting like "(0,0)" is invented


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


def soft_checks(original, cleaned) -> list[tuple[bool, str]]:
    orig = {s.id: s.text for s in original}
    new = {s.id: s.text for s in cleaned}
    out = []
    for sid, wrong, right in MUST_FIX:
        ok = right in new[sid] and wrong not in re.findall(r"[\w']+", new[sid])
        out.append((ok, f"{sid} fix '{wrong}' -> '{right}': {new[sid]!r}"))
    for sid, word, why in MUST_KEEP:
        out.append((word in new[sid], f"{sid} keeps '{word}' ({why})"))
    for sid in NO_NEW_SYMBOLS:
        added = set(new[sid]) - set(orig[sid])
        bad = {c for c in added if c in clean.NEW_SYMBOL_CHARS or c.isdigit()}
        out.append((not bad, f"{sid} adds no symbols/digits (added: {sorted(bad) or 'none'})"))
    return out


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
        "soft": soft_checks(segments, cleaned_result.segments),
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
    print("\n== SOFT checks (report only) ==")
    for ok, msg in r["soft"]:
        print(f"  [{'ok' if ok else 'MISS'}] {msg}")
    print(f"  soft: {sum(ok for ok, _ in r['soft'])} of {len(r['soft'])} ok")
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
