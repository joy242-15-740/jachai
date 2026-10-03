"""Metrics on hand-made examples, and both baselines on the small world."""

import math

import numpy as np
import pytest

from jachai.eval import metrics as m
from jachai.eval.baselines import blanket_limit, evaluation_window, run_baselines
from jachai.features import build_features
from jachai.features.config import load_thresholds
from jachai.labels.config import load_rules

TRUTH = np.array([1, 0, 1, 0, 0, 1])
SCORE = np.array([0.9, 0.8, 0.7, 0.2, 0.1, 0.05])
FLAG = np.array([1, 1, 1, 0, 0, 0])
AMOUNT = np.array([100, 50, 300, 10, 10, 600])


def test_precision_recall_and_fpr():
    assert m.precision(TRUTH, FLAG) == pytest.approx(2 / 3)
    assert m.recall(TRUTH, FLAG) == pytest.approx(2 / 3)
    assert m.false_positive_rate(TRUTH, FLAG) == pytest.approx(1 / 3)


def test_value_weighted_recall_counts_taka_not_rows():
    # Caught 100 + 300 of 1,000 misuse taka, though 2 of 3 misuse rows.
    assert m.value_weighted_recall(TRUTH, FLAG, AMOUNT) == pytest.approx(0.4)


def test_precision_at_k():
    assert m.precision_at_k(TRUTH, SCORE, 1) == 1.0
    assert m.precision_at_k(TRUTH, SCORE, 3) == pytest.approx(2 / 3)


def test_pr_auc_perfect_and_undefined():
    assert m.pr_auc([0, 1, 0, 1], [0.1, 0.9, 0.2, 0.8]) == pytest.approx(1.0)
    assert math.isnan(m.pr_auc([0, 0], [0.1, 0.2]))


@pytest.fixture(scope="module")
def setup(pattern_world):
    thr = load_thresholds()
    # The small world is only 30 days; use a short warm-up so something is left.
    thr = thr.model_copy(update={"eval": thr.eval.model_copy(update={"warmup_days": 7})})
    feats = build_features(pattern_world.tables, pattern_world.config, thr.features)
    return pattern_world, feats, thr


def test_baselines_report_every_metric_in_range(setup):
    world, feats, thr = setup
    table = run_baselines(world.tables, feats, world.config, thr, load_rules())
    assert list(table.index) == ["rules_only", "blanket_limit"]
    values = table.to_numpy(dtype=float)
    ok = np.isnan(values) | ((values >= 0) & (values <= 1))
    assert ok.all()


def test_rules_beat_blanket_limit_on_ranking(setup):
    world, feats, thr = setup
    table = run_baselines(world.tables, feats, world.config, thr, load_rules())
    assert table.loc["rules_only", "payment_pr_auc"] > table.loc["blanket_limit", "payment_pr_auc"]


def test_blanket_limit_blocks_only_payments_past_the_cap(setup):
    world, feats, thr = setup
    rules = load_rules()
    window = evaluation_window(feats["payments"], world.config, thr.eval.warmup_days)
    result = blanket_limit(feats, rules, window)
    pay = feats["payments"][window.to_numpy()].set_index("payment_id")
    blocked = pay.loc[result.payment_flag[result.payment_flag].index]
    cap = rules.baselines.blanket_limit.daily_cap
    # A blocked payment pushed its shop's day total past the cap.
    day_total = pay.groupby([pay["shop_id"], pay["ts"].dt.normalize()])["amount"].transform("sum")
    assert (day_total.loc[blocked.index] > cap).all()
