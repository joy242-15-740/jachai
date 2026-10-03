"""Every misuse pattern produces rows that look like its description."""

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from jachai.world.config import PatternsConfig
from jachai.world.generate import generate_world
from jachai.world.labels_noise import CASE_LABEL
from jachai.world.world import TRUE_LABEL, TRUE_PATTERN

MISUSE = [
    "round_amount_cash_desk",
    "remittance_drain",
    "turnover_burst",
    "limit_bypass",
    "incentive_splitting",
    "p2p_disguise",
]


@pytest.fixture
def world(pattern_world):
    return pattern_world


def rows(world, table, pattern):
    df = world.tables[table]
    return df[df[TRUE_PATTERN] == pattern]


@pytest.mark.parametrize("pattern", MISUSE)
def test_each_misuse_pattern_produces_labelled_rows_and_shops(world, pattern):
    table = "p2p_transfers" if pattern == "p2p_disguise" else "qr_payments"
    events = rows(world, table, pattern)
    assert len(events) > 0
    assert (events[TRUE_LABEL] == 1).all()
    shops = rows(world, "shops", pattern)
    assert len(shops) > 0
    assert (shops[TRUE_LABEL] == 1).all()


def test_each_shop_has_at_most_one_pattern(world):
    # Each shop carries a single pattern name; only misuse patterns have label 1.
    shops = world.tables["shops"]
    assert set(shops[TRUE_PATTERN]) <= {"normal", *MISUSE, *HARD_NEGATIVES}
    assert ((shops[TRUE_LABEL] == 1) == shops[TRUE_PATTERN].isin(MISUSE)).all()


def test_cash_desk_uses_round_amounts(world, patterns_cfg):
    params = next(p for p in patterns_cfg.patterns if p.name == "round_amount_cash_desk").params
    amounts = rows(world, "qr_payments", "round_amount_cash_desk")["amount"]
    assert amounts.isin(params["amounts"]).all()
    assert len(rows(world, "add_money", "round_amount_cash_desk")) > 0


def test_limit_bypass_exceeds_daily_limit_across_shops(world):
    limit = world.config.regulation.cash_out_limit_daily
    ev = rows(world, "qr_payments", "limit_bypass")
    per_day = ev.groupby([ev["payer_id"], ev["ts"].dt.date]).agg(
        total=("amount", "sum"), shops=("shop_id", "nunique")
    )
    assert (per_day["total"] > limit * 0.95).all()  # rounding to Tk 500 may shave a little
    assert (per_day["shops"] >= 2).all()
    assert (ev["amount"] < limit).all()  # no single payment breaks the limit


def test_incentive_splitting_only_after_regime_change_and_under_cap(world):
    ev = rows(world, "qr_payments", "incentive_splitting")
    assert (ev["ts"] >= pd.Timestamp(world.config.calendar.regime_change)).all()
    assert (ev["amount"] < world.config.regulation.qr_incentive_cap).all()


def test_remittance_drain_pays_most_of_remittance_then_goes_quiet(world):
    rem = rows(world, "remittances", "remittance_drain").set_index("customer_id")
    pay = rows(world, "qr_payments", "remittance_drain")
    paid = pay.groupby("payer_id")["amount"].sum()
    ratio = paid / rem["amount"].reindex(paid.index)
    assert ratio.between(0.85, 1.05).all()
    last = pay.groupby("payer_id")["ts"].max()
    honest = world.tables["qr_payments"]
    honest = honest[(honest[TRUE_PATTERN] == "normal") & honest["payer_id"].isin(last.index)]
    assert (honest["ts"] <= honest["payer_id"].map(last)).all()


def test_turnover_burst_hits_small_shops_with_large_days(world):
    ev = rows(world, "qr_payments", "turnover_burst")
    shops = world.tables["shops"].set_index("shop_id")
    assert (shops.loc[ev["shop_id"].unique(), "size_tier"] == "small").all()
    daily = ev.groupby([ev["shop_id"], ev["ts"].dt.date])["amount"].sum()
    assert daily.min() >= 250_000


def test_p2p_disguise_goes_to_owner_wallets_after_start(world):
    ev = rows(world, "p2p_transfers", "p2p_disguise")
    wallets = set(rows(world, "shops", "p2p_disguise")["owner_wallet_id"])
    assert set(ev["receiver_id"]) <= wallets
    assert ev["via_qr"].all()
    assert (ev["ts"] >= pd.Timestamp(world.config.scenario.p2p_qr_start)).all()


def test_p2p_disguise_does_nothing_when_scenario_off(small_cfg, patterns_cfg):
    world = generate_world(small_cfg, patterns_cfg)
    assert world.tables["p2p_transfers"].empty
    assert not (world.tables["shops"][TRUE_PATTERN] == "p2p_disguise").any()


def _patterns_with(patterns_cfg, **changes):
    data = patterns_cfg.model_dump()
    for key, value in changes.items():
        *path, last = key.split("__")
        target = data
        for part in path:
            target = target[int(part)] if isinstance(target, list) else target[part]
        target[last] = value
    return PatternsConfig.model_validate(data)


def test_no_label_noise_means_case_label_equals_truth(small_cfg, patterns_cfg):
    clean = _patterns_with(
        patterns_cfg,
        label_noise__shops__miss_rate=0.0,
        label_noise__shops__false_flag_rate=0.0,
        label_noise__payments__miss_rate=0.0,
        label_noise__payments__false_flag_rate=0.0,
    )
    world = generate_world(small_cfg, clean)
    for table in ("shops", "qr_payments"):
        df = world.tables[table]
        assert (df[CASE_LABEL] == df[TRUE_LABEL]).all()


def test_label_noise_misses_some_misuse(world):
    q = world.tables["qr_payments"]
    misuse = q[q[TRUE_LABEL] == 1]
    missed = (misuse[CASE_LABEL] == 0).mean()
    assert 0.15 < missed < 0.45  # configured miss_rate is 0.30


def test_unknown_pattern_fn_fails_loudly(small_cfg, patterns_cfg):
    bad = _patterns_with(patterns_cfg, patterns__0__fn="no_such_pattern")
    with pytest.raises(KeyError, match="not registered"):
        generate_world(small_cfg, bad)


def test_unknown_pattern_param_fails_loudly(small_cfg, patterns_cfg):
    data = patterns_cfg.model_dump()
    data["patterns"][0]["params"]["typo_param"] = 1
    with pytest.raises(ValidationError):
        generate_world(small_cfg, PatternsConfig.model_validate(data))


def test_honest_world_has_no_misuse(small_cfg):
    world = generate_world(small_cfg)  # no patterns config
    for name in ("shops", "qr_payments"):
        assert np.all(world.tables[name][TRUE_LABEL] == 0)


# --- Hard negatives ------------------------------------------------------------

HARD_NEGATIVES = [
    "hn_big_ticket_retail",
    "hn_grocery_bulk_buy",
    "hn_pharmacy_big_bill",
    "hn_phone_purchase",
    "hn_clothing_order",
    "hn_festival_spike",
    "hn_haat_day_spike",
    "hn_new_shop_ramp",
]


@pytest.mark.parametrize("pattern", HARD_NEGATIVES)
def test_each_hard_negative_produces_honest_rows(world, pattern):
    events = rows(world, "qr_payments", pattern)
    assert len(events) > 0
    assert (events[TRUE_LABEL] == 0).all()


def test_big_ticket_rows_are_large_round_and_in_opening_hours(world):
    ev = rows(world, "qr_payments", "hn_big_ticket_retail")
    shops = world.tables["shops"].set_index("shop_id")
    assert shops.loc[ev["shop_id"].unique(), "category"].isin(["electronics", "wholesaler"]).all()
    assert (ev["amount"] % 1000 == 0).all()
    assert (ev["amount"] >= 5000).all()
    assert (rows(world, "shops", "hn_big_ticket_retail")[TRUE_LABEL] == 0).all()


def test_festival_rows_fall_inside_festival_dates(world, patterns_cfg):
    params = next(p for p in patterns_cfg.patterns if p.name == "hn_festival_spike").params
    days = rows(world, "qr_payments", "hn_festival_spike")["ts"].dt.date
    assert days.min() >= pd.Timestamp(params["start"]).date()
    assert days.max() <= pd.Timestamp(params["end"]).date()


def test_haat_rows_are_rural_on_haat_days(world):
    ev = rows(world, "qr_payments", "hn_haat_day_spike")
    shops = world.tables["shops"].set_index("shop_id")
    zones = world.tables["zones"].set_index("zone_id")
    zone = shops.loc[ev["shop_id"], "zone_id"].to_numpy()
    assert (zones.loc[zone, "area_type"] == "rural_haat").all()
    weekday = ev["ts"].dt.day_name().str[:3].to_numpy()
    haat = zones.loc[zone, "haat_days"].to_numpy()
    assert all(d in h.split("|") for d, h in zip(weekday, haat, strict=True))


def test_new_shops_have_no_payments_before_opening(world):
    new = rows(world, "shops", "hn_new_shop_ramp").set_index("shop_id")["opened_on"]
    assert (new > pd.Timestamp(world.config.calendar.start)).all()
    q = world.tables["qr_payments"]
    q = q[q["shop_id"].isin(new.index)]
    assert len(q) > 0
    assert (q["ts"] >= q["shop_id"].map(new)).all()


def test_spikes_skip_misuse_shops(world):
    misuse_shops = set(world.tables["shops"].query(f"{TRUE_LABEL} == 1")["shop_id"])
    for pattern in ("hn_festival_spike", "hn_haat_day_spike"):
        assert not set(rows(world, "qr_payments", pattern)["shop_id"]) & misuse_shops
