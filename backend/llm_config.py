"""Model configuration (S2-1): the ONE place with model IDs, limits, prices and timeouts.

Roles: nano (clean, topic split), super (gaps, notes, slides), ultra (judge).
No other file may contain a Nemotron model ID (tests/test_no_hardcoded_models.py checks this).
The API key is NOT here: it is read from the environment (NEBIUS_API_KEY).

To re-check IDs, context limits and prices (read-only, no tokens used):
    python list_models.py nemotron
then update ROLES and PRICES_CHECKED_AT, and the table in README.md.
"""
from dataclasses import dataclass

BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
API_KEY_ENV = "NEBIUS_API_KEY"

DEFAULT_TIMEOUT_SEC = 120.0
# Nano thinks long: a call cut at 20000 tokens takes about 118 s, and the doubled retry (40000) about 235 s.
MAX_RETRIES = 3  # retries after the first call, so up to 4 calls in total
RETRY_BACKOFF_BASE_SEC = 1.0  # wait 1 s, 2 s, 4 s when the server sends no Retry-After
RETRY_AFTER_CAP_SEC = 30.0  # never wait longer than this, even if Retry-After says so

# Date (YYYY-MM-DD) when IDs, context limits and prices below were last compared
# with GET /v1/models?verbose=true.
PRICES_CHECKED_AT = "2026-10-16"


@dataclass(frozen=True)
class RoleConfig:
    model_id: str
    context_limit: int  # tokens
    price_in_per_1m: float  # USD per 1M prompt tokens
    price_out_per_1m: float  # USD per 1M completion tokens
    timeout_sec: float | None = None  # None = DEFAULT_TIMEOUT_SEC


ROLES = {
    "nano": RoleConfig("nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B", 262_144, 0.06, 0.24, timeout_sec=300.0),
    "super": RoleConfig("nvidia/nemotron-3-super-120b-a12b", 262_144, 0.30, 0.90),
    "ultra": RoleConfig("nvidia/Nemotron-3-Ultra-550b-a55b", 1_048_576, 1.00, 3.00),
}


def get_role(role: str) -> RoleConfig:
    try:
        return ROLES[role]
    except KeyError:
        raise ValueError(f"unknown model role {role!r}, use one of {sorted(ROLES)}") from None


def timeout_for(role: str) -> float:
    return get_role(role).timeout_sec or DEFAULT_TIMEOUT_SEC
