"""Notes writer settings (S4-1): the ONE place with limits.

NOTES_MAX_PER_SECTION (a safety net, not a target), NOTES_MAX_LECTURE_SOURCES and NOTES_MAX_WEB_SOURCES can be overridden by the environment variable of the same name.
"""
import os

NOTES_MAX_PER_SECTION = 10  # statements kept per section; the rest are cut and listed in notes_report.json
NOTES_MAX_LECTURE_SOURCES = 6  # lecture sources kept per statement; extra ones are dropped and reported
NOTES_MAX_WEB_SOURCES = 3  # web sources kept per statement; extra ones are dropped and reported
NOTES_SNIPPET_MAX_CHARS = 600  # a web snippet longer than this is cut before it goes into the prompt
# Super's thinking counts as output tokens. A cut-off answer is retried once with double (validate.py).
NOTES_MAX_TOKENS = 16000


def _int_setting(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    return max(1, value)


def max_per_section() -> int:
    return _int_setting("NOTES_MAX_PER_SECTION", NOTES_MAX_PER_SECTION)


def max_lecture_sources() -> int:
    return _int_setting("NOTES_MAX_LECTURE_SOURCES", NOTES_MAX_LECTURE_SOURCES)


def max_web_sources() -> int:
    return _int_setting("NOTES_MAX_WEB_SOURCES", NOTES_MAX_WEB_SOURCES)
