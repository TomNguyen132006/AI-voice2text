"""Validate every file in samples/ against schemas.py, then check that ids match.

Usage: python validate_samples.py   (exit code 0 = all good, 1 = problems found)
"""
import json
import sys
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from schemas import Job, Section, Segment, Slide, Statement

SAMPLES = Path(__file__).parent / "samples"

FILES = {
    "transcript.json": list[Segment],
    "sections.json": list[Section],
    "statements.json": list[Statement],
    "slides.json": list[Slide],
    "job.json": Job,
}

problems = []
data = {}

# 1. Each file matches its schema
for name, schema in FILES.items():
    try:
        raw = json.loads((SAMPLES / name).read_text(encoding="utf-8"))
        data[name] = TypeAdapter(schema).validate_python(raw)
        print(f"OK    {name}")
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        problems.append(f"{name}: {error}")
        print(f"FAIL  {name}")

# 2. Ids point to things that exist (only if all files loaded)
if not problems:
    segments = {s.id: s for s in data["transcript.json"]}
    section_ids = {s.id for s in data["sections.json"]}

    for section in data["sections.json"]:
        for seg_id in section.segment_ids:
            if seg_id not in segments:
                problems.append(f"section {section.id}: unknown segment {seg_id}")

    statements = data["statements.json"] + [b for s in data["slides.json"] for b in s.bullets]
    for st in statements:
        if st.section_id not in section_ids:
            problems.append(f"statement {st.id}: unknown section {st.section_id}")
        for src in st.sources:
            if src.type == "lecture":
                seg = segments.get(src.segment_id)
                if seg is None:
                    problems.append(f"statement {st.id}: unknown segment {src.segment_id}")
                elif not (seg.start <= src.start <= src.end <= seg.end):
                    problems.append(f"statement {st.id}: time {src.start}-{src.end} outside {seg.id}")

    for slide in data["slides.json"]:
        if slide.section_id not in section_ids:
            problems.append(f"slide '{slide.title}': unknown section {slide.section_id}")

    print("OK    ids match across files" if not problems else "FAIL  ids do not match")

for p in problems:
    print("  -", p)
sys.exit(1 if problems else 0)
