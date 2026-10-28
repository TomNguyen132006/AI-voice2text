"""Output files (Epic 6): transcript .txt (S6-1), notes .md (S6-2), slides .pptx (S6-3), one .zip with all three (S6-4).

All of them are built from files the earlier stages saved, by code only (no model call):
    transcript.txt   cleaned transcript, one line per segment: "[mm:ss] text"
    notes.md         notes_final.json (or notes.json) grouped by section; every point ends with its sources:
                     📍 lecture time range, 🌐 [web title](url)
    slides.pptx      title slide, the slides of slides.json (bullets with source tags, example, speaker notes),
                     a final "Sources" slide with every web link and the lecture time ranges
    all.zip          the three files, built when it is downloaded (see jobs_api.py)

Usage (from backend/):  python -m export <job_id>     (writes the three files next to the other job files)
"""
import io
import re
import sys
import zipfile

from pptx import Presentation
from pptx.util import Pt

from schemas import Section, Segment, Slide, Statement
from storage import get_storage, job_key, load_json, load_transcript
from topics import load_sections

FILES = {"txt": "transcript.txt", "md": "notes.md", "pptx": "slides.pptx"}
ZIP_NAME = "all.zip"
SOURCES_PER_SLIDE = 8


def clock(seconds: float) -> str:
    """75.5 -> "01:15"; one hour or more -> "1:02:03"."""
    total = int(seconds)
    if total >= 3600:
        return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"
    return f"{total // 60:02d}:{total % 60:02d}"


def _lecture_text(statement: Statement) -> str:
    times = [f"{clock(s.start)}-{clock(s.end)}" for s in statement.sources if s.type == "lecture"]
    return f"📍 {', '.join(times)}" if times else ""


def _md_escape(text: str) -> str:
    return " ".join(text.replace("[", "(").replace("]", ")").split())


def source_markdown(statement: Statement) -> str:
    """The sources of one statement as markdown: 📍 01:15-01:30 · 🌐 [Title](url)"""
    parts = [_lecture_text(statement)] if _lecture_text(statement) else []
    for s in statement.sources:
        if s.type == "web":
            parts.append(f"🌐 [{_md_escape(s.title) or s.url}]({s.url})")
    return " · ".join(parts)


def transcript_txt(segments: list[Segment]) -> str:
    return "\n".join(f"[{clock(s.start)}] {' '.join(s.text.split())}" for s in segments) + "\n"


NOT_JUDGED_LINE = ("**NOT JUDGED:** these notes did not go through the judge (no notes_final.json), "
                   "so a point may not be supported by its source.")


def notes_md(sections: list[Section], statements: list[Statement], title: str = "Lecture notes", judged: bool = True) -> str:
    """judged=False (the statements come from notes.json, not notes_final.json) adds a visible NOT JUDGED line to the header."""
    lines = [f"# {title}", ""]
    if not judged:
        lines += [NOT_JUDGED_LINE, ""]
    lines += ["Every point ends with its source: 📍 a time range in the lecture recording, 🌐 a web link.", ""]
    header = len(lines)
    for section in sections:
        own = [s for s in statements if s.section_id == section.id]
        if not own:
            continue
        lines += [f"## {section.title}", f"_Lecture time {clock(section.start)} - {clock(section.end)}_", ""]
        lines += [f"- {' '.join(s.text.split())}  \n  {source_markdown(s)}" for s in own]
        lines.append("")
    if len(lines) == header:
        lines.append("_No statement passed the checks._")
    return "\n".join(lines).rstrip() + "\n"


def _fit_font(texts: list[str]) -> int:
    total = sum(len(t) for t in texts)
    return 22 if total <= 350 else 18 if total <= 600 else 15


def _add_sources(paragraph, statement: Statement, size: int) -> None:
    """Small grey source tags after a bullet: lecture time ranges, and web titles as real hyperlinks."""
    def run(text, link=None):
        r = paragraph.add_run()
        r.text = text
        r.font.size = Pt(max(size - 8, 9))
        if link:
            r.hyperlink.address = link
        return r

    lecture = _lecture_text(statement)
    if lecture:
        run(f"  {lecture}")
    for s in statement.sources:
        if s.type == "web":
            run(f"  🌐 {s.title or s.url}", link=s.url)


EXAMPLE_LEAD = re.compile(r"^\s*for\s+(example|instance)\s*[,:]\s*", re.IGNORECASE)


def example_display(text: str) -> str:
    """For display only: the label is "Example:", so a leading "For example," / "For instance," is removed. notes.json is not changed."""
    text = " ".join(text.split())
    stripped = EXAMPLE_LEAD.sub("", text, count=1)
    return stripped[:1].upper() + stripped[1:] if stripped != text and stripped else text


def slides_pptx(slides: list[Slide], title: str = "Lecture slides", statements: list[Statement] | None = None) -> bytes:
    """statements = every statement of the job (also the ones that are only in the speaker notes): the Sources slide lists the web sources of all of them."""
    prs = Presentation()
    first = prs.slides.add_slide(prs.slide_layouts[0])
    first.shapes.title.text = title
    first.placeholders[1].text = "Every point shows its source: 📍 lecture time, 🌐 web link"

    web_sources: dict[str, str] = {}
    for slide in slides:
        s = prs.slides.add_slide(prs.slide_layouts[1])
        s.shapes.title.text = slide.title
        body = s.placeholders[1].text_frame
        body.word_wrap = True
        size = _fit_font([b.text for b in slide.bullets] + [slide.example or ""])
        for n, bullet in enumerate(slide.bullets):
            p = body.paragraphs[0] if n == 0 else body.add_paragraph()
            r = p.add_run()
            r.text = " ".join(bullet.text.split())
            r.font.size = Pt(size)
            _add_sources(p, bullet, size)
            for src in bullet.sources:
                if src.type == "web":
                    web_sources.setdefault(src.url, src.title or src.url)
        if slide.example:
            p = body.add_paragraph()
            r = p.add_run()
            r.text = f"Example: {example_display(slide.example)}"
            r.font.size = Pt(size - 2)
            r.font.italic = True
        s.notes_slide.notes_text_frame.text = slide.speaker_notes

    for statement in statements or []:
        for src in statement.sources:
            if src.type == "web":
                web_sources.setdefault(src.url, src.title or src.url)
    items = list(web_sources.items())
    pages = [items[i : i + SOURCES_PER_SLIDE] for i in range(0, len(items), SOURCES_PER_SLIDE)] or [[]]
    for page_no, page in enumerate(pages, start=1):
        s = prs.slides.add_slide(prs.slide_layouts[1])
        s.shapes.title.text = "Sources" + (f" ({page_no}/{len(pages)})" if len(pages) > 1 else "")
        body = s.placeholders[1].text_frame
        body.word_wrap = True
        if not page:
            body.text = "No web sources were used. Every point comes from the lecture (📍 time ranges are on each slide)."
        for n, (url, name) in enumerate(page):
            p = body.paragraphs[0] if n == 0 else body.add_paragraph()
            r = p.add_run()
            r.text = f"🌐 {name}"
            r.font.size = Pt(16)
            r.hyperlink.address = url
    buffer = io.BytesIO()
    prs.save(buffer)
    return buffer.getvalue()


def build_zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _load_statements(job_id: str, storage=None) -> tuple[list[Statement], bool]:
    """(statements, judged). notes_final.json is what the judge kept; without it we fall back to notes.json,
    which was never judged: say so loudly (stderr here, and a NOT JUDGED line in notes.md)."""
    for name in ("notes_final.json", "notes.json"):
        try:
            statements = [Statement(**s) for s in load_json(job_key(job_id, name), storage)]
        except FileNotFoundError:
            continue
        if name == "notes.json":
            print(f"WARNING: {job_key(job_id, 'notes_final.json')} is missing, exporting notes.json, which was NOT JUDGED.",
                  file=sys.stderr)
        return statements, name == "notes_final.json"
    raise FileNotFoundError(job_key(job_id, "notes_final.json"))


def _load_clean(job_id: str, storage=None) -> list[Segment]:
    try:
        return [Segment(**s) for s in load_json(job_key(job_id, "transcript_clean.json"), storage)]
    except FileNotFoundError:
        return load_transcript(job_id, storage)


def export_job(job_id: str, storage=None) -> dict[str, str]:
    """Write transcript.txt, notes.md and slides.pptx into the job's storage; return {"txt": key, "md": key, "pptx": key}."""
    storage = storage or get_storage()
    sections = load_sections(job_id, storage)
    statements, judged = _load_statements(job_id, storage)
    slides = [Slide(**s) for s in load_json(job_key(job_id, "slides.json"), storage)]
    data = {
        "txt": transcript_txt(_load_clean(job_id, storage)).encode("utf-8"),
        "md": notes_md(sections, statements, judged=judged).encode("utf-8"),
        "pptx": slides_pptx(slides, statements=statements),
    }
    keys = {}
    for kind, content in data.items():
        keys[kind] = job_key(job_id, FILES[kind])
        storage.save_bytes(keys[kind], content)
    return keys


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        sys.exit("usage: python -m export <job_id>   (run from backend/)")
    for kind, key in export_job(sys.argv[1]).items():
        print(f"{kind}: {key}")
