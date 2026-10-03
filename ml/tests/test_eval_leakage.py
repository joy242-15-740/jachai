"""The single-feature check flags a planted leak and passes honest noise."""

import numpy as np
import pandas as pd
import pytest

from jachai.eval.leakage import LeakageError, assert_no_leakage, single_feature_auc


def frame(seed=0, n=2000):
    rng = np.random.default_rng(seed)
    truth = (rng.random(n) < 0.1).astype(int)
    df = pd.DataFrame(
        {
            "payment_id": [f"P{i}" for i in range(n)],
            "noise": rng.normal(size=n),
            "weak_signal": truth * 0.5 + rng.normal(size=n),
        }
    )
    return df, truth


def test_planted_leak_is_caught():
    df, truth = frame()
    df["leak"] = truth + rng_noise(len(df)) * 0.01  # basically the label
    table = single_feature_auc(df, truth)
    assert table.iloc[0]["feature"] == "leak"
    with pytest.raises(LeakageError, match="leak"):
        assert_no_leakage(table, 0.95, "payment")


def test_reversed_leak_is_caught_too():
    df, truth = frame()
    df["anti_leak"] = -truth.astype(float)
    with pytest.raises(LeakageError, match="anti_leak"):
        assert_no_leakage(single_feature_auc(df, truth), 0.95, "payment")


def test_honest_features_pass():
    df, truth = frame()
    table = single_feature_auc(df, truth)
    assert_no_leakage(table, 0.95, "payment")
    assert set(table["feature"]) == {"noise", "weak_signal"}  # IDs are not features


def rng_noise(n):
    return np.random.default_rng(1).normal(size=n)
