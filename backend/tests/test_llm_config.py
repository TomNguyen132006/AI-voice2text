"""Sanity checks for llm_config.py (S2-1). No network."""
import re
from datetime import date

import pytest

import llm_config


def test_three_roles_with_distinct_ids_and_positive_numbers():
    assert set(llm_config.ROLES) == {"nano", "super", "ultra"}
    ids = [r.model_id for r in llm_config.ROLES.values()]
    assert len({i.lower() for i in ids}) == 3
    for r in llm_config.ROLES.values():
        assert r.context_limit > 0 and r.price_in_per_1m > 0 and r.price_out_per_1m > 0


def test_unknown_role_is_a_clear_error():
    with pytest.raises(ValueError, match="unknown model role 'mega'"):
        llm_config.get_role("mega")


def test_timeout_default_and_per_role_override(monkeypatch):
    assert llm_config.timeout_for("nano") == 300.0  # long enough for the doubled 40000-token retry
    assert llm_config.timeout_for("super") == llm_config.timeout_for("ultra") == llm_config.DEFAULT_TIMEOUT_SEC == 120.0
    custom = llm_config.RoleConfig("x/y", 1000, 1.0, 2.0, timeout_sec=7.5)
    monkeypatch.setitem(llm_config.ROLES, "ultra", custom)
    assert llm_config.timeout_for("ultra") == 7.5


def test_prices_checked_at_is_a_real_date():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", llm_config.PRICES_CHECKED_AT)
    date.fromisoformat(llm_config.PRICES_CHECKED_AT)


def test_retry_setting_is_three():
    assert llm_config.MAX_RETRIES == 3
