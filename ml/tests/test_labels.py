"""Labeling functions and the weak-label aggregator."""

import numpy as np
import pandas as pd
import pytest

from jachai.features import build_features
from jachai.features.config import load_thresholds
from jachai.labels import weak_label_table
from jachai.labels.aggregate import WeightedVote, weak_labels
from jachai.labels.config import RulesConfig, load_rules
from jachai.labels.functions import ABSTAIN, REGISTRY, apply_lfs
from jachai.world.world import TRUE_LABEL, TRUE_PATTERN

# Which pattern each misuse labeling function is meant to catch.
TARGET = {
    "lf_cash_desk": "round_amount_cash_desk",
    "lf_remittance_drain": "remittance_drain",
    "lf_turnover_burst": "turnover_burst",
    "lf_limit_bypass": "limit_bypass",
    "lf_incentive_splitting": "incentive_splitting",
}


@pytest.fixture(scope="module")
def labelled(pattern_world):
    feats = build_features(pattern_world.tables, pattern_world.config, load_thresholds().features)
    rules = load_rules()
    pay = feats["payments"]
    truth = pattern_world.tables["qr_payments"].set_index("payment_id")
    weak = weak_label_table(pay, "payment", rules, pattern_world.config)
    weak["truth"] = pay["payment_id"].map(truth[TRUE_LABEL]).to_numpy()
    weak["pattern"] = pay["payment_id"].map(truth[TRUE_PATTERN]).to_numpy()
    shop_weak = weak_label_table(feats["shop_day"], "shop_day", rules, pattern_world.config)
    shop_weak["shop_id"] = feats["shop_day"]["shop_id"].to_numpy()
    return weak, shop_weak


def test_rules_and_code_list_the_same_functions():
    assert set(load_rules().labeling_functions) == set(REGISTRY)


def test_votes_are_only_abstain_or_the_functions_own_label(labelled):
    weak, _ = labelled
    for name, lf in REGISTRY.items():
        if lf.level == "payment":
            assert set(np.unique(weak[name])) <= {ABSTAIN, lf.vote}, name


@pytest.mark.parametrize("name", sorted(TARGET))
def test_each_misuse_function_catches_its_pattern_and_is_mostly_right(labelled, name):
    weak, _ = labelled
    fired = weak[name] == 1
    assert (fired & (weak["pattern"] == TARGET[name])).any(), f"{name} never fired on its pattern"
    assert (weak.loc[fired, "truth"] == 1).mean() >= 0.6, f"{name} too often wrong"


def test_honest_functions_are_almost_always_right(labelled):
    weak, _ = labelled
    for name in ("lf_honest_small_ticket", "lf_honest_regular_customer"):
        fired = weak[name] == 0
        assert fired.any()
        assert (weak.loc[fired, "truth"] == 0).mean() >= 0.98, name


def test_weak_labels_beat_chance(labelled):
    weak, _ = labelled
    labelled_rows = weak[weak["weak_label"] != ABSTAIN]
    flagged = labelled_rows["weak_label"] == 1
    precision = (labelled_rows.loc[flagged, "truth"] == 1).mean()
    base_rate = (weak["truth"] == 1).mean()
    assert precision > 10 * base_rate


def test_p2p_function_flags_disguising_shops(pattern_world, labelled):
    _, shop_weak = labelled
    flagged = set(shop_weak.loc[shop_weak["weak_label"] == 1, "shop_id"])
    shops = pattern_world.tables["shops"].set_index("shop_id")[TRUE_PATTERN]
    assert flagged, "p2p function never fired"
    assert (shops.reindex(list(flagged)) == "p2p_disguise").mean() >= 0.8


def test_weighted_vote_maths():
    votes = pd.DataFrame({"a": [1, 1, -1, 0, -1], "b": [0, 1, -1, 0, 1], "c": [-1, -1, -1, 0, 0]})
    model = WeightedVote({"a": 2.0, "b": 1.0, "c": 1.0}).fit(votes)
    proba = model.predict_proba(votes)
    np.testing.assert_allclose(proba[[0, 1, 3, 4]], [2 / 3, 1.0, 0.0, 0.5])
    assert np.isnan(proba[2])  # nobody voted
    np.testing.assert_array_equal(weak_labels(proba, 0.5), [1, 1, ABSTAIN, 0, 1])


def test_unconfigured_function_fails_loudly(pattern_world):
    data = load_rules().model_dump()
    del data["labeling_functions"]["lf_cash_desk"]
    with pytest.raises(KeyError, match="mismatch"):
        apply_lfs(pd.DataFrame(), "payment", RulesConfig.model_validate(data), pattern_world.config)


def test_missing_setting_fails_loudly(pattern_world):
    data = load_rules().model_dump()
    data["labeling_functions"]["lf_cash_desk"] = {"weight": 1.0}
    feats = build_features(pattern_world.tables, pattern_world.config, load_thresholds().features)
    with pytest.raises(KeyError, match="missing labeling-function setting"):
        apply_lfs(
            feats["payments"], "payment", RulesConfig.model_validate(data), pattern_world.config
        )
