"""Source checks for a finished job (S4 close): pure code, no model, no network.

Usage (from backend/):  python -m check_sources <job_id>      (exit code 1 when a check fails)

Reads jobs/{id}/notes.json, search.json, transcript.json (the ORIGINAL transcript), and, when they exist,
slides.json, slides_report.json and notes_final.json. Works on the raw JSON so a missing key is a failure, not a default.
Slides are built from notes_final.json (the statements the judge kept, some of them rewritten), so checks d and e compare
against notes_final.json when it exists and against notes.json otherwise. Checks a, b and c always read notes.json.
Checks (each counts passed/failed per item, the first 5 failures are printed):
  a  has_source           every statement has at least one source
  b  web_in_search        every web source: its url is in search.json (exact match) with the same title
                          (the raw title, or the title with urls removed, which is what notes.py stores)
  c  lecture_matches_original  every lecture source has segment_id, start and end, equal to transcript.json
  d  bullets_match_notes  every slide bullet has the text, section and sources of the statement with its id
                          (in notes_final.json when it exists, else notes.json)
  e  example_matches_notes    the slide example equals the text of the statement (same file as d) named in
                          slides_report.json (example_statement_id), and that statement is not also a bullet
These checks prove that texts, times and links were COPIED correctly. They say nothing about whether a
statement is TRUE or supported by its source: that is the judge's job (Epic 5).
"""
from storage import job_key, load_json

CHECKS = {
    "a": "has_source",
    "b": "web_in_search",
    "c": "lecture_matches_original",
    "d": "bullets_match_notes",
    "e": "example_matches_notes",
}
MAX_SHOWN = 5


def _optional(job_id: str, name: str, storage=None):
    try:
        return load_json(job_key(job_id, name), storage)
    except FileNotFoundError:
        return None


def _new() -> dict:
    return {"passed": 0, "failed": 0, "failures": [], "skipped": None}


def _record(check: dict, ok: bool, message: str) -> None:
    if ok:
        check["passed"] += 1
    else:
        check["failed"] += 1
        check["failures"].append(message)


def _web_titles(search: list[dict]) -> dict[str, set[str]]:
    """url -> titles that are acceptable for it."""
    from notes import strip_urls

    out: dict[str, set[str]] = {}
    for entry in search:
        for r in entry.get("results", []):
            raw = r.get("title") or ""
            out.setdefault(r.get("url"), set()).update({raw, " ".join(raw.split()), strip_urls(raw)})
    return out


def check_job(job_id: str, storage=None) -> dict:
    """{"a": {...}, ..., "e": {...}}: passed, failed, failures (all of them) and skipped (why, or None)."""
    notes = load_json(job_key(job_id, "notes.json"), storage)
    search = _optional(job_id, "search.json", storage)
    original = load_json(job_key(job_id, "transcript.json"), storage)
    slides = _optional(job_id, "slides.json", storage)
    slides_report = _optional(job_id, "slides_report.json", storage)
    final = _optional(job_id, "notes_final.json", storage)
    result = {key: _new() for key in CHECKS}
    by_id = {st.get("id"): st for st in (notes if final is None else final)}  # what the slides were built from (checks d, e)
    segments = {seg["id"]: seg for seg in original}
    titles = _web_titles(search) if search is not None else None

    for st in notes:
        sid = st.get("id")
        _record(result["a"], bool(st.get("sources")), f"{sid}: no source")

        for src in st.get("sources") or []:
            if src.get("type") == "web":
                if titles is None:
                    result["b"]["skipped"] = "search.json is missing"
                    continue
                url, title = src.get("url"), src.get("title")
                if url not in titles:
                    _record(result["b"], False, f"{sid}: url {url!r} is not in search.json")
                else:
                    _record(result["b"], title in titles[url], f"{sid}: title {title!r} differs from search.json for {url}")
            elif src.get("type") == "lecture":
                seg = segments.get(src.get("segment_id"))
                if seg is None:
                    _record(result["c"], False, f"{sid}: segment {src.get('segment_id')!r} is not in transcript.json")
                    continue
                missing = [k for k in ("segment_id", "start", "end") if k not in src]
                same = not missing and src["start"] == seg["start"] and src["end"] == seg["end"]
                why = f"missing {missing}" if missing else f"{src.get('start')}-{src.get('end')} but transcript.json says {seg['start']}-{seg['end']}"
                _record(result["c"], same, f"{sid} {src.get('segment_id')}: {why}")
            else:
                _record(result["c"], False, f"{sid}: source type {src.get('type')!r} is neither lecture nor web")

    if slides is None:
        result["d"]["skipped"] = result["e"]["skipped"] = "slides.json is missing"
        return result

    example_ids = {s.get("section_id"): s.get("example_statement_id") for s in (slides_report or {}).get("slides", [])}
    for slide in slides:
        sec = slide.get("section_id")
        for b in slide.get("bullets", []):
            st = by_id.get(b.get("id"))
            if st is None:
                _record(result["d"], False, f"{sec}: bullet {b.get('id')} is not in {'notes.json' if final is None else 'notes_final.json'}")
                continue
            problems = [name for name in ("text", "section_id", "sources") if b.get(name) != st.get(name)]
            _record(result["d"], not problems, f"{sec}: bullet {b['id']} differs from its statement in {', '.join(problems)}")
        if slide.get("example") is not None:
            if slides_report is None:
                result["e"]["skipped"] = "slides_report.json is missing"
                continue
            ex_id = example_ids.get(sec)
            st = by_id.get(ex_id)
            if ex_id is None or st is None:
                _record(result["e"], False, f"{sec}: example has no valid example_statement_id in slides_report.json ({ex_id!r})")
            elif slide["example"] != st.get("text"):
                _record(result["e"], False, f"{sec}: example text differs from statement {ex_id}")
            elif ex_id in {b.get("id") for b in slide.get("bullets", [])}:
                _record(result["e"], False, f"{sec}: example statement {ex_id} is also a bullet")
            else:
                _record(result["e"], True, "")
    return result


def format_result(result: dict) -> str:
    lines = [f"{'check':32} {'passed':>6} {'failed':>6}"]
    for key, name in CHECKS.items():
        c = result[key]
        lines.append(f"{key} {name:30} {c['passed']:>6} {c['failed']:>6}" + (f"   (skipped: {c['skipped']})" if c["skipped"] else ""))
    for key, name in CHECKS.items():
        c = result[key]
        lines += [f"  FAIL {key} {name}: {m}" for m in c["failures"][:MAX_SHOWN]]
        if len(c["failures"]) > MAX_SHOWN:
            lines.append(f"  ... and {len(c['failures']) - MAX_SHOWN} more {key} failures")
    total = sum(c["failed"] for c in result.values())
    lines.append("")
    lines.append("ALL CHECKS PASSED" if total == 0 else f"{total} FAILURE(S)")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        sys.exit("usage: python -m check_sources <job_id>   (run from backend/)")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    outcome = check_job(sys.argv[1])
    print(format_result(outcome))
    sys.exit(1 if any(c["failed"] for c in outcome.values()) else 0)
