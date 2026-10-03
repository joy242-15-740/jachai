"""No future leakage: features of a payment must not change when later data is removed."""

import pandas as pd
import pytest

from jachai.features.config import load_thresholds
from jachai.features.payment import build_payment_features
from jachai.world.world import EVENT_TABLES, HIDDEN_PREFIX


def cut_off(tables: dict[str, pd.DataFrame], t: pd.Timestamp) -> dict[str, pd.DataFrame]:
    """The world as it looked at time t: every event table keeps only rows before t."""
    return {
        name: (df[df["ts"] < t].copy() if name in EVENT_TABLES else df)
        for name, df in tables.items()
    }


@pytest.fixture(scope="module")
def full_features(pattern_world):
    return build_payment_features(
        pattern_world.tables, pattern_world.config, load_thresholds().features
    )


# Cut-offs: mid-afternoon, just after midnight, and just after the regime change.
CUTS = ["2026-09-29 15:37:11", "2026-10-03 00:00:01", "2026-10-01 09:00:00"]


@pytest.mark.parametrize("cut", CUTS)
def test_payment_features_do_not_use_the_future(pattern_world, full_features, cut):
    t = pd.Timestamp(cut)
    past = build_payment_features(
        cut_off(pattern_world.tables, t), pattern_world.config, load_thresholds().features
    )
    expected = full_features[full_features["ts"] < t].reset_index(drop=True)
    assert len(past) == len(expected) > 0
    pd.testing.assert_frame_equal(
        past.set_index("payment_id").sort_index(),
        expected.set_index("payment_id").sort_index(),
        check_dtype=False,
    )


def test_payment_features_have_no_hidden_columns(full_features):
    assert not [c for c in full_features.columns if c.startswith(HIDDEN_PREFIX)]
    assert "case_label" not in full_features.columns


def test_payment_features_basic_values(pattern_world, full_features):
    f = full_features.set_index("payment_id")
    q = pattern_world.tables["qr_payments"].set_index("payment_id")
    cap = pattern_world.config.regulation.qr_incentive_cap
    # just_under_cap matches its definition
    jc = q["amount"].between(cap - 200, cap - 1)
    assert (f["just_under_cap"].astype(bool) == jc.reindex(f.index)).all()
    # the very first payment of a payer at a shop is a first visit, later ones are not
    first = f.groupby(["payer_id", "shop_id"])["first_visit"].sum()
    assert (first == 1).all()
    # a payer's running day total never decreases within a day
    day = f["ts"].dt.normalize()
    assert (f.groupby([f["payer_id"], day])["payer_day_total"].diff().dropna() >= 0).all()
    # distances are non-negative and account ages positive
    assert (f["payer_shop_distance_km"] >= 0).all()
    assert (f["payer_account_age_days"] > 0).all()


def test_drain_payments_spend_most_of_recent_remittance(pattern_world, full_features):
    q = pattern_world.tables["qr_payments"].set_index("payment_id")
    f = full_features.set_index("payment_id")
    drain = q.index[q["_true_pattern"] == "remittance_drain"]
    honest = q.index[q["_true_pattern"] == "normal"]
    assert f.loc[drain, "paid_share_of_recent_remittance"].median() > 0.5
    assert f.loc[honest, "paid_share_of_recent_remittance"].median() == 0


# --- Payer and shop history ---------------------------------------------------

from jachai.features import build_features  # noqa: E402


@pytest.fixture(scope="module")
def all_features(pattern_world):
    return build_features(pattern_world.tables, pattern_world.config, load_thresholds().features)


@pytest.mark.parametrize("cut", CUTS)
def test_joined_features_do_not_use_the_future(pattern_world, all_features, cut):
    t = pd.Timestamp(cut)
    past = build_features(
        cut_off(pattern_world.tables, t), pattern_world.config, load_thresholds().features
    )
    full = all_features["payments"]
    expected = full[full["ts"] < t]
    pd.testing.assert_frame_equal(
        past["payments"].set_index("payment_id").sort_index(),
        expected.set_index("payment_id").sort_index(),
        check_dtype=False,
    )
    # Shop-day rows up to and including the cut day only look at earlier days.
    sd_full = all_features["shop_day"]
    sd_past = past["shop_day"]
    keep = t.normalize()
    pd.testing.assert_frame_equal(
        sd_past[sd_past["day"] <= keep].reset_index(drop=True),
        sd_full[sd_full["day"] <= keep].reset_index(drop=True),
        check_dtype=False,
    )


def test_shop_day_has_every_shop_every_day(pattern_world, all_features):
    sd = all_features["shop_day"]
    n_shops = len(pattern_world.tables["shops"])
    assert len(sd) == n_shops * pattern_world.config.calendar.days
    first_day = sd["day"].min()
    assert sd.loc[sd["day"] == first_day, "turnover_7d"].isna().all()  # no history yet


def test_burst_and_cash_desk_shops_stand_out_from_peers(pattern_world, all_features):
    sd = all_features["shop_day"]
    shops = pattern_world.tables["shops"].set_index("shop_id")["_true_pattern"]
    last = sd[sd["day"] == sd["day"].max()].set_index("shop_id")
    pattern = shops.reindex(last.index)
    desk, normal = pattern == "round_amount_cash_desk", pattern == "normal"
    assert (
        last.loc[desk, "round_1000_share_30d"].median()
        > last.loc[normal, "round_1000_share_30d"].median()
    )
    assert last.loc[desk, "turnover_vs_peers_7d"].median() > 2


def test_payer_history_is_filled_for_payments(all_features):
    p = all_features["payments"]
    assert p["payer_payments_7d"].notna().all()
    assert (p["payer_payments_7d"] >= 0).all()
    assert p["qr_codes_per_account"].between(1, 5).all()
