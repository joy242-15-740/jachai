"""The ablation's per-variant scoring on validation rows."""

import numpy as np
import pandas as pd

from jachai.eval.ablation import score_on_validation
from jachai.features.config import load_thresholds
from jachai.models.train import PaymentData


def test_scores_only_validation_rows_and_measures_flag_overlap():
    split = pd.Series(["train", "validation", "validation", "validation", "test"])
    data = PaymentData(
        payments=pd.DataFrame({"shop_id": list("abcde")}),
        split=split,
        weak_proba=np.zeros(5),
        weak_label=np.zeros(5),
        case_verdict=np.full(5, np.nan),
    )
    truth = np.array([1, 1, 0, 1, 1])
    amount = np.array([10, 100, 10, 300, 10])
    score = np.array([0.9, 0.8, 0.1, 0.7, 0.9])
    flag = np.array([True, True, False, False, True])
    rules_flag = np.array([False, True, False, True, False])
    row = score_on_validation("x", score, flag, data, truth, amount, rules_flag, load_thresholds())
    assert row["flags"] == 1  # train and test rows are ignored
    assert row["value_recall"] == 100 / 400
    # validation: variant flags {1}, rules flag {1, 3} -> overlap 1 / 2
    assert row["flag_overlap_with_rules"] == 0.5


def test_matched_budget_flags_the_same_number_for_everyone():
    split = pd.Series(["validation"] * 4)
    data = PaymentData(
        payments=pd.DataFrame({"shop_id": ["a", "a", "b", "c"]}),
        split=split,
        weak_proba=np.zeros(4),
        weak_label=np.zeros(4),
        case_verdict=np.full(4, np.nan),
    )
    truth = np.array([1, 0, 0, 1])
    amount = np.array([100, 10, 10, 300])
    score = np.array([0.9, 0.8, 0.7, 0.1])
    rules_flag = np.array([True, False, True, False])  # rules flag 2 -> budget 2
    row = score_on_validation(
        "x", score, score > 0, data, truth, amount, rules_flag, load_thresholds()
    )
    assert row["rules_budget_n"] == 2
    # top-2 scores: rows 0 (misuse) and 1 (honest, shop a)
    assert row["rules_budget_precision"] == 0.5
    assert row["rules_budget_value_recall"] == 100 / 400
    assert row["rules_budget_honest_shops_flagged"] == 1
