"""Notes writer settings (S4-1): the ONE place with limits.

NOTES_MAX_PER_SECTION can be overridden by the environment variable of the same name.
"""
import os

NOTES_MAX_PER_SECTION = 10  # statements kept per section; the rest are cut and listed in notes_report.json
NOTES_SNIPPET_MAX_CHARS = 600  # a web snippet longer than this is cut before it goes into the prompt
# Super's thinking counts as output tokens. A cut-off answer is retried once with double (validate.py).
NOTES_MAX_TOKENS = 16000


def max_per_section() -> int:
    raw = os.getenv("NOTES_MAX_PER_SECTION")
    try:
        value = int(raw) if raw else NOTES_MAX_PER_SECTION
    except ValueError:
        value = NOTES_MAX_PER_SECTION
    return max(1, value)
