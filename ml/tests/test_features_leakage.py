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
