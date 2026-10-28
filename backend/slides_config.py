"""Slide writer settings (S4-2): the ONE place with limits, enforced by code (the prompt contains no numbers).

SLIDE_MAX_BULLETS, SLIDE_MAX_BULLET_CHARS and SLIDE_MAX_WORDS_PER_BULLET can be overridden by the environment variable of the same name.
"""
import os

SLIDE_MAX_BULLETS = 7  # bullets per slide; the others go to the speaker notes
SLIDE_MAX_BULLET_CHARS = 700  # characters of all bullets plus the example that still fit on a slide (export.py shrinks the font above 350 and 600)
SLIDE_MAX_WORDS_PER_BULLET = 30  # a longer statement is not shown as a bullet (it cannot be shortened without rewriting it)
SLIDE_MAX_TITLE_WORDS = 8  # a longer title is replaced by the section title
SLIDE_MAX_TOKENS = 8000  # Super's thinking counts as output tokens; a cut-off answer is retried once with double


def _int_setting(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    return max(1, value)


def max_bullets() -> int:
    return _int_setting("SLIDE_MAX_BULLETS", SLIDE_MAX_BULLETS)


def max_bullet_chars() -> int:
    return _int_setting("SLIDE_MAX_BULLET_CHARS", SLIDE_MAX_BULLET_CHARS)


def max_words_per_bullet() -> int:
    return _int_setting("SLIDE_MAX_WORDS_PER_BULLET", SLIDE_MAX_WORDS_PER_BULLET)
