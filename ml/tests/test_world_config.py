"""The world and pattern configs load, and bad values are rejected."""

import datetime as dt

import pytest
import yaml
from pydantic import ValidationError

from jachai.world.config import (
    DEFAULT_CONFIG_DIR,
    load_patterns_config,
    load_world_config,
)


def test_world_config_loads():
    cfg = load_world_config()
    assert cfg.calendar.days == 120
    assert cfg.calendar.end == dt.date(2026, 10, 28)
    assert cfg.calendar.start < cfg.calendar.regime_change <= cfg.calendar.end
    assert set(cfg.categories) == {
        "grocery",
        "tea_stall",
        "pharmacy",
        "mobile_phone_shop",
        "clothing",
        "electronics",
        "wholesaler",
    }


def test_patterns_config_has_six_misuse_patterns():
    cfg = load_patterns_config()
    misuse = [p.name for p in cfg.patterns if p.kind == "misuse"]
    assert misuse == [
        "round_amount_cash_desk",
        "remittance_drain",
        "turnover_burst",
        "limit_bypass",
        "incentive_splitting",
        "p2p_disguise",
    ]
    assert any(p.kind == "hard_negative" for p in cfg.patterns)


def test_env_seed_overrides_config(monkeypatch):
    monkeypatch.setenv("JACHAI_SEED", "7")
    assert load_world_config().seed == 7


def _write_modified_world(tmp_path, change):
    data = yaml.safe_load((DEFAULT_CONFIG_DIR / "world.yaml").read_text(encoding="utf-8"))
    change(data)
    path = tmp_path / "world.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_shares_must_sum_to_one(tmp_path):
    def bad(d):
        d["categories"]["grocery"]["shop_share"] = 0.9

    with pytest.raises(ValidationError, match="categories.shop_share"):
        load_world_config(_write_modified_world(tmp_path, bad))


def test_unknown_key_is_rejected(tmp_path):
    def typo(d):
        d["population"]["n_shop"] = 10

    with pytest.raises(ValidationError):
        load_world_config(_write_modified_world(tmp_path, typo))
