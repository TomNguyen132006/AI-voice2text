"""Transcript upload fallback (S1-3): .srt / .vtt / .txt -> list of Segment.

Used instead of transcribe.py when the user uploads a transcript, so the demo
still works without Parakeet. Output is the same as S1-1: Segments numbered
seg_0001, seg_0002, ... with times in seconds from the start of the recording.

- .srt / .vtt: one Segment per cue, times taken from the file.
- .txt with "[mm:ss]" or "[hh:mm:ss]" at the start of lines (our own S6-1 export
  format): one Segment per stamped line, ending where the next one starts.
- .txt without stamps: split into groups of 1-3 sentences with ESTIMATED times
  (~150 words per minute). Citations then point near, not exactly at, the moment.

Manual test:
    python transcript_import.py lecture.srt out.json
"""
import html
import re
from pathlib import Path

from schemas import Segment
from transcribe import merge_chunks

WORDS_PER_SEC = 150 / 60  # typical lecture speaking rate, for .txt without times
MAX_SENTENCES = 3  # plain .txt: max sentences per segment
TARGET_WORDS = 25  # plain .txt: start a new segment once this many words are collected
MAX_WORDS = 40  # plain .txt: longer "sentences" (no punctuation) are cut into pieces this size

_TIME = r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})"  # [hh:]mm:ss.mmm, SRT uses "," before ms
_CUE_TIME = re.compile(rf"{_TIME}\s*-->\s*{_TIME}")
_TAG = re.compile(r"<[^>]*>|\{\\[^}]*\}")  # <i>, <c.yellow>, <00:01.000>, {\an8}
_STAMP = re.compile(r"^\s*\[(?:(\d+):)?(\d{1,2}):(\d{2})(?:\.\d+)?\]\s*(.*)$")
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


class TranscriptImportError(Exception):
    """The file is not a transcript we can read."""


def _seconds(h, m, s, ms="0") -> float:
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def _clean(text) -> str:
    return " ".join(html.unescape(_TAG.sub("", text)).split())


def _words(text) -> int:
    return len(text.split())


def parse_subtitles(text) -> list[Segment]:
    """Parse .srt or .vtt: a cue starts at its "start --> end" line and runs to the
    next blank line. Everything else (WEBVTT header, NOTE/STYLE blocks, cue numbers
    and ids) is not inside a cue and is skipped."""
    raw, cue = [], None
    for line in text.splitlines():
        match = _CUE_TIME.search(line)
        if match:
            g = match.groups()
            cue = [_seconds(*g[:4]), _seconds(*g[4:]), []]
            raw.append(cue)
        elif not line.strip():
            cue = None
        elif cue is not None:
            cue[2].append(line)
    return merge_chunks([(0.0, [(start, end, _clean(" ".join(lines))) for start, end, lines in raw])])


def _parse_stamped_txt(lines) -> list[Segment]:
    raw = []  # [start, text]; unstamped lines continue the segment above them
    for line in lines:
        match = _STAMP.match(line)
        if match:
            h, m, s, rest = match.groups()
            raw.append([_seconds(h, m, s), rest])
        elif raw:
            raw[-1][1] += " " + line
        else:
            raw.append([0.0, line])
    texts = [_clean(text) for _, text in raw]
    ends = [nxt[0] for nxt in raw[1:]] + [raw[-1][0] + _words(texts[-1]) / WORDS_PER_SEC]
    return merge_chunks([(0.0, [(start, end, text) for (start, _), end, text in zip(raw, ends, texts)])])


def _parse_plain_txt(text) -> list[Segment]:
    pieces = []  # sentences, with very long ones cut to MAX_WORDS
    for sentence in _SENTENCE_END.split(_clean(text)):
        words = sentence.split()
        pieces += [" ".join(words[i : i + MAX_WORDS]) for i in range(0, len(words), MAX_WORDS)]

    groups, current = [], []
    for piece in pieces:
        current.append(piece)
        if len(current) >= MAX_SENTENCES or sum(map(_words, current)) >= TARGET_WORDS:
            groups.append(" ".join(current))
            current = []
    if current:
        groups.append(" ".join(current))

    raw, t = [], 0.0
    for group in groups:
        end = t + _words(group) / WORDS_PER_SEC
        raw.append((t, end, group))
        t = end
    return merge_chunks([(0.0, raw)])


def parse_txt(text) -> list[Segment]:
    lines = [line for line in text.splitlines() if line.strip()]
    if any(_STAMP.match(line) for line in lines):
        return _parse_stamped_txt(lines)
    return _parse_plain_txt(text)


PARSERS = {".srt": parse_subtitles, ".vtt": parse_subtitles, ".txt": parse_txt}


def _decode(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):  # Windows Notepad "Unicode"
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise TranscriptImportError("transcript must be saved as UTF-8") from e


def import_transcript(path) -> list[Segment]:
    """Read an uploaded .srt, .vtt or .txt transcript into Segments."""
    path = Path(path)
    parser = PARSERS.get(path.suffix.lower())
    if parser is None:
        raise TranscriptImportError(f"unsupported transcript type {path.suffix!r}, use one of {sorted(PARSERS)}")
    segments = parser(_decode(path.read_bytes()))
    if not segments:
        raise TranscriptImportError(f"no transcript text found in {path.name}")
    return segments


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Read a .srt/.vtt/.txt transcript into segments.")
    parser.add_argument("transcript")
    parser.add_argument("out_json")
    args = parser.parse_args()

    segments = import_transcript(args.transcript)
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump([s.model_dump() for s in segments], f, ensure_ascii=False, indent=1)
    print(f"segments: {len(segments)}")
    print(f"last end: {segments[-1].end:.1f} s")
