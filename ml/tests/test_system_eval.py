"""Evasion world, score-only system, and shop-level metrics."""

import numpy as np
import pandas as pd
import pytest

from jachai.eval.system_eval import shop_metrics
from jachai.features import build_features
from jachai.features.config import load_thresholds
from jachai.labels.config import load_rules
from jachai.models.config import load_models_config
from jachai.system import score_system
from jachai.world.config import EvasionCfg, load_patterns_config
from jachai.world.generate import generate_world
from jachai.world.world import TRUE_LABEL


@pytest.fixture(scope="module")
def evaded(pattern_world):
    patterns = load_patterns_config()
    patterns = patterns.model_copy(update={"evasion": EvasionCfg(remove_round_amounts=True)})
    return generate_world(pattern_world.config, patterns)


def test_evasion_removes_round_misuse_amounts_only(pattern_world, evaded):
    a, b = pattern_world.tables["qr_payments"], evaded.tables["qr_payments"]
    pd.testing.assert_frame_equal(a.drop(columns="amount"), b.drop(columns="amount"))
    misuse = (a[TRUE_LABEL] == 1).to_numpy()
    assert (a.loc[~misuse, "amount"].to_numpy() == b.loc[~misuse, "amount"].to_numpy()).all()
    assert (b.loc[misuse, "amount"] % 100 != 0).all()
    assert (b.loc[misuse, "amount"] < a.loc[misuse, "amount"]).all()  # only ever lowered
    cap = pattern_world.config.regulation.qr_incentive_cap
    split = b["_true_pattern"] == "incentive_splitting"
    assert (b.loc[split, "amount"] < cap).all()


def test_score_system_refits_nothing(small_system):
    world, system, scored = small_system
    # Same settings as the small_system fixture.
    thr = load_thresholds()
    split = thr.split.model_copy(
        update={
            "train_end": pd.Timestamp("2026-10-08").date(),
            "validation_end": pd.Timestamp("2026-10-14").date(),
        }
    )
    thr = thr.model_copy(
        update={"split": split, "eval": thr.eval.model_copy(update={"warmup_days": 5})}
    )
    models = load_models_config()
    models = models.model_copy(
        update={"network": models.network.model_copy(update={"window_days": 14})}
    )
    shop_day = build_features(world.tables, world.config, thr.features)["shop_day"]
    again = score_system(system, world.tables, shop_day, world.config, thr, load_rules(), models)
    np.testing.assert_allclose(again.shop_day["risk"], scored.shop_day["risk"])
    assert (again.shop_day["band"] == scored.shop_day["band"]).all()


def test_shop_metrics_by_hand():
    v = pd.DataFrame(
        {
            "truth": [1, 0, 1, 0],
            "misuse_taka": [100.0, 0.0, 300.0, 0.0],
            "pattern": ["limit_bypass", "hn_phone_purchase", "round_amount_cash_desk", "normal"],
        }
    )
    out = shop_metrics(v, np.array([0.9, 0.8, 0.1, 0.0]), k=2, n_band=2)
    assert out["k_precision"] == 0.5
    assert out["k_value_recall"] == 0.25  # caught Tk 100 of Tk 400
    assert out["k_honest_lookalikes"] == 1
    assert out["recall_limit_bypass"] == 1.0
    assert out["recall_round_amount_cash_desk"] == 0.0
