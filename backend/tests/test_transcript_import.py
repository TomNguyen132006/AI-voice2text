"""Tests for transcript_import.py (S1-3): .srt / .vtt / .txt -> Segments."""
import pytest

from schemas import Segment
from transcript_import import (
    TranscriptImportError,
    import_transcript,
    parse_subtitles,
    parse_txt,
)

SRT = """1
00:00:01,000 --> 00:00:04,500
<i>Today we talk about</i>
gradient descent.

2
00:00:04,500 --> 00:01:02,25
The loss measures &amp; scores errors.

3
00:01:02,250 --> 00:01:03,000

"""

VTT = """WEBVTT - lecture 3

NOTE this block is a comment
and can span lines

STYLE
::cue { color: yellow }

intro
00:05.000 --> 00:07.250 align:start position:10%
<v Professor>Hello <c.yellow>class</c>.

01:00:00.000 --> 01:00:02.000
One hour in.
"""


def test_srt_cues_become_segments():
    segments = parse_subtitles(SRT)

    assert segments == [
        Segment(id="seg_0001", start=1.0, end=4.5, text="Today we talk about gradient descent."),
        Segment(id="seg_0002", start=4.5, end=62.25, text="The loss measures & scores errors."),
    ]  # the empty 3rd cue is dropped


def test_vtt_skips_header_style_and_cue_settings():
    segments = parse_subtitles(VTT)

    assert [(s.start, s.end, s.text) for s in segments] == [
        (5.0, 7.25, "Hello class."),
        (3600.0, 3602.0, "One hour in."),
    ]


def test_txt_with_stamps_uses_them():
    text = "[00:00] Intro to the course.\n[01:15] Gradient descent\ncontinues here.\n[1:02:03] Wrap up now.\n"

    segments = parse_txt(text)

    assert [(s.id, s.start, s.text) for s in segments] == [
        ("seg_0001", 0.0, "Intro to the course."),
        ("seg_0002", 75.0, "Gradient descent continues here."),
        ("seg_0003", 3723.0, "Wrap up now."),
    ]
    assert segments[0].end == 75.0 and segments[1].end == 3723.0  # ends where the next starts
    assert segments[2].end == pytest.approx(3723.0 + 3 / 2.5)  # last one estimated from its words


def test_plain_txt_gets_estimated_increasing_times():
    sentences = [f"Sentence number {i} has exactly seven words." for i in range(10)]

    segments = parse_txt(" ".join(sentences))

    assert all(len(s.text.split()) <= 3 * 7 for s in segments)
    assert segments[0].start == 0.0
    for prev, nxt in zip(segments, segments[1:]):
        assert nxt.start == pytest.approx(prev.end, abs=0.01)  # no gaps, always increasing
    assert segments[-1].end == pytest.approx(70 / 2.5, abs=0.05)  # 70 words at 150 wpm


def test_plain_txt_without_punctuation_is_cut_into_pieces():
    segments = parse_txt("word " * 100)

    assert [len(s.text.split()) for s in segments] == [40, 40, 20]


def test_import_reads_bom_crlf_and_utf16(tmp_path):
    srt = tmp_path / "a.SRT"
    srt.write_bytes("﻿1\r\n00:00:01,000 --> 00:00:02,000\r\nXin chào\r\n".encode("utf-8"))
    vtt = tmp_path / "b.vtt"
    vtt.write_bytes("WEBVTT\n\n00:01.000 --> 00:02.000\nhi\n".encode("utf-16"))

    assert import_transcript(srt) == [Segment(id="seg_0001", start=1.0, end=2.0, text="Xin chào")]
    assert import_transcript(vtt)[0].text == "hi"


def test_import_rejects_bad_files(tmp_path):
    pdf = tmp_path / "notes.pdf"
    pdf.write_text("x")
    empty = tmp_path / "empty.srt"
    empty.write_text("WEBVTT\n\n")
    latin1 = tmp_path / "old.txt"
    latin1.write_bytes("caf\xe9".encode("latin-1"))

    with pytest.raises(TranscriptImportError, match="unsupported"):
        import_transcript(pdf)
    with pytest.raises(TranscriptImportError, match="no transcript text"):
        import_transcript(empty)
    with pytest.raises(TranscriptImportError, match="UTF-8"):
        import_transcript(latin1)
