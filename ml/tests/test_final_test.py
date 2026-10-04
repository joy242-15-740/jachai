import pandas as pd

from jachai.eval.final_test import evaluate
from jachai.features.config import load_thresholds


def test_final_evaluation_compares_all_methods_at_identical_budgets():
    frame = pd.DataFrame(
        {
            "truth": [1, 0, 1, 0],
            "pattern": ["limit_bypass", "none", "round_amount_cash_desk", "none"],
            "misuse_taka": [100.0, 0.0, 50.0, 0.0],
            "band": ["high", "review", "low", "low"],
            "risk": [0.9, 0.8, 0.7, 0.1],
            "rules_only": [2.0, 0.0, 1.0, 0.0],
            "blanket_limit": [10.0, 40.0, 20.0, 30.0],
        }
    )
    result = evaluate(frame, load_thresholds())
    assert set(result["metrics"]) == {"Jachai with rules", "Rules only", "Blanket limit"}
    assert {row["bands_n"] for row in result["metrics"].values()} == {2}
    assert {row["k_n"] for row in result["metrics"].values()} == {4}
