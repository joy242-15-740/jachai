"""Fusion: ranks, weights, frozen bands; and the full system on the small world."""

import numpy as np
import pandas as pd
import pytest

from jachai.features.config import BandThresholds, load_thresholds
from jachai.models.config import FusionConfig
from jachai.models.fusion import Fusion, payment_components
from jachai.world.world import TRUE_LABEL


def test_ranks_are_share_of_training_values_below():
    cfg = FusionConfig(payment_window_days=7, rules_window_days=30, weights={"a": 1.0, "b": 3.0})
    comp = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0], "b": [0.0, 0.0, 1.0, np.nan]})
    f = Fusion(cfg).fit_ranks(comp, np.array([True, True, True, False]))
    r = f.ranks(comp)
    np.testing.assert_allclose(r["a"], [0, 1 / 3, 2 / 3, 1.0])
    np.testing.assert_allclose(r["b"], [0, 0, 2 / 3, 0])  # missing = no evidence = 0
    np.testing.assert_allclose(f.risk(comp), (r["a"] + 3 * r["b"]) / 4)


def test_bands_are_frozen_cutoffs():
    f = Fusion(FusionConfig(payment_window_days=7, rules_window_days=30, weights={"a": 1.0}))
    f.freeze_bands(np.linspace(0, 1, 101), BandThresholds(high_quantile=0.9, review_quantile=0.5))
    assert f.cutoffs == pytest.approx({"review": 0.5, "high": 0.9})
    assert list(f.band(np.array([0.1, 0.6, 0.95]))) == ["low", "review", "high"]


def test_payment_components_use_only_earlier_days():
    day = pd.Timestamp("2026-08-10")
    payments = pd.DataFrame(
        {"shop_id": ["S"] * 4, "ts": [day - pd.Timedelta(days=d) for d in (0, 1, 2, 9)]}
    )
    proba = np.array([0.99, 0.2, 0.6, 0.9])  # same-day 0.99 and 9-days-old 0.9 must not count
    shop_day = pd.DataFrame({"shop_id": ["S"], "day": [day]})
    comp = payment_components(payments, proba, 0.5, shop_day, window_days=7)
    assert comp["payment_top3_7d"].iloc[0] == pytest.approx(0.4)  # mean of 0.2 and 0.6
    assert comp["payment_flag_share_7d"].iloc[0] == pytest.approx(0.5)


def test_system_scores_every_shop_day_with_a_band(small_system):
    _, _, scored = small_system
    s = scored.shop_day
    assert s["risk"].between(0, 1).all()
    assert set(s["band"]) <= {"low", "review", "high"}
    assert (s.loc[s["split"] == "validation", "band"] == "high").any()


def test_misuse_shops_rank_higher_than_honest(small_system):
    world, _, scored = small_system
    s = scored.shop_day
    last = s[s["day"] == s["day"].max()]
    truth = last["shop_id"].map(world.tables["shops"].set_index("shop_id")[TRUE_LABEL])
    assert last.loc[truth == 1, "risk"].median() > last.loc[truth == 0, "risk"].median()


def test_bands_frozen_on_validation_only(small_system):
    _, system, scored = small_system
    s = scored.shop_day
    val = s.loc[s["split"] == "validation", "risk"].to_numpy()
    thr = load_thresholds().bands
    assert system.fusion.cutoffs["high"] == pytest.approx(np.quantile(val, thr.high_quantile))


def test_rules_component_counts_earlier_flags_only():
    from jachai.models.fusion import rules_component

    day = pd.Timestamp("2026-08-31")
    payments = pd.DataFrame(
        {"shop_id": ["S"] * 4, "ts": [day - pd.Timedelta(days=d) for d in (0, 1, 5, 40)]}
    )
    weak = np.array([1, 1, 1, 1])  # same day and 40 days ago must not count
    shop_day = pd.DataFrame({"shop_id": ["S"], "day": [day]})
    assert rules_component(payments, weak, shop_day, window_days=30).iloc[0] == 2
