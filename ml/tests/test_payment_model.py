"""Training targets (rules + cases) and the calibrated payment model."""

import numpy as np
import pandas as pd
import pytest

from jachai.features.config import load_thresholds
from jachai.labels.config import TrainingTarget, load_rules
from jachai.labels.targets import build_targets, case_verdict_for_payments
from jachai.models.config import load_models_config
from jachai.models.payment import PaymentModel, best_f1_threshold
from jachai.models.train import prepare_payment_data, train_from_data
from jachai.world.world import TRUE_PATTERN

NAN = np.nan


def target_cfg(mode):
    return TrainingTarget(mode=mode, rule_weight=1.0, case_weight=3.0)


def test_soft_target_maths():
    weak = np.array([0.0, 1.0, NAN, NAN, 0.5])
    case = np.array([1.0, NAN, 0.0, NAN, 1.0])
    t = build_targets(weak, case, target_cfg("weak_and_cases"))
    np.testing.assert_allclose(t.weight, [4, 1, 3, 0, 4])
    np.testing.assert_allclose(t.soft[[0, 1, 2, 4]], [0.75, 1.0, 0.0, 0.875])
    assert np.isnan(t.soft[3])  # no evidence -> dropped
    np.testing.assert_array_equal(t.hard, [1, 1, 0, -1, 1])


def test_modes_use_only_their_evidence():
    weak, case = np.array([1.0, NAN]), np.array([NAN, 0.0])
    assert build_targets(weak, case, target_cfg("weak")).usable.tolist() == [True, False]
    assert build_targets(weak, case, target_cfg("cases")).usable.tolist() == [False, True]


def test_case_verdicts_respect_split_cutoff_and_closing_date():
    payments = pd.DataFrame(
        {
            "shop_id": ["A", "A", "B", "C", "D"],
            "ts": pd.to_datetime(
                ["2026-08-01", "2026-09-20", "2026-08-01", "2026-08-01", "2026-08-01"]
            ),
        }
    )
    split = pd.Series(["train", "train", "train", "test", "train"])
    cases = pd.DataFrame(
        {
            "shop_id": ["A", "B", "C", "D"],
            "closed_on": pd.to_datetime(["2026-09-01", "2026-10-20", "2026-08-10", None]),
            "verdict": [1, 0, 1, 1],
        }
    )
    v = case_verdict_for_payments(payments, split, cases, {"train": pd.Timestamp("2026-10-05")})
    assert v[0] == 1  # closed before cutoff, payment before closing
    assert np.isnan(v[1])  # payment after the case closed
    assert np.isnan(v[2])  # case closed after the training cutoff
    assert np.isnan(v[3])  # test shop: never used
    assert np.isnan(v[4])  # case still open


def test_best_f1_threshold_picks_the_obvious_cut():
    y = np.array([1, 1, 0, 0])
    p = np.array([0.9, 0.8, 0.3, 0.1])
    assert best_f1_threshold(y, p) == pytest.approx(0.8)


@pytest.fixture(scope="module")
def trained(pattern_world):
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
    rules = load_rules()
    data = prepare_payment_data(pattern_world.tables, pattern_world.config, thr, rules)
    models = load_models_config()
    lgbm = models.payment_model.lightgbm.model_copy(update={"num_boost_round": 60})
    models = models.model_copy(
        update={"payment_model": models.payment_model.model_copy(update={"lightgbm": lgbm})}
    )
    model = train_from_data(data, models, rules.training_target, pattern_world.config.seed)
    return pattern_world, thr, data, models, rules, model


def test_model_outputs_probabilities_and_a_frozen_threshold(trained):
    _, _, data, *_, model = trained
    p = model.predict_proba(data.payments)
    assert np.all((p >= 0) & (p <= 1))
    assert 0 < model.threshold <= 1
    assert model.meta["target_mode"] == "weak_and_cases"


def test_training_is_deterministic(trained):
    world, _, data, models, rules, model = trained
    again = train_from_data(data, models, rules.training_target, world.config.seed)
    assert again.fingerprint() == model.fingerprint()


def test_save_and_load_give_the_same_predictions(trained, tmp_path):
    _, _, data, *_, model = trained
    model.save(tmp_path)
    loaded = PaymentModel.load(tmp_path)
    np.testing.assert_allclose(
        loaded.predict_proba(data.payments), model.predict_proba(data.payments)
    )
    assert loaded.threshold == model.threshold


def test_training_never_sees_test_shops_or_the_held_out_pattern(trained):
    world, thr, data, *_ = trained
    t = data.targets(load_rules().training_target)
    # What training and tuning actually use: train/validation rows with evidence.
    used = np.isin(data.split.to_numpy(), ["train", "validation"]) & t.usable
    pattern = data.payments["payment_id"].map(
        world.tables["qr_payments"].set_index("payment_id")[TRUE_PATTERN]
    )
    assert not (pattern[used] == thr.split.holdout_pattern).any()
    assert not np.isin(data.split[used], ["test", ""]).any()
