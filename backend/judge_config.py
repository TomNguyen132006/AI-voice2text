"""Judge settings (S5-1): the ONE place with limits.

JUDGE_REASON_MAX_CHARS can be overridden by the environment variable of the same name. The web snippet length is shared with the notes
writer: search_config.SNIPPET_MAX_CHARS.
"""
import os

import search_config

JUDGE_REASON_MAX_CHARS = 300  # the judge's reason is cut to this length before it is saved
JUDGE_SNIPPET_MAX_CHARS = search_config.SNIPPET_MAX_CHARS  # same value as the notes writer sees (one shared constant)
# Ultra's thinking counts as output tokens. A cut-off answer is retried once with double (validate.py).
JUDGE_MAX_TOKENS = 16000


def _int_setting(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    return max(1, value)


def reason_max_chars() -> int:
    return _int_setting("JUDGE_REASON_MAX_CHARS", JUDGE_REASON_MAX_CHARS)


def snippet_max_chars() -> int:
    return search_config.snippet_max_chars()
