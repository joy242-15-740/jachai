"""Single-feature sanity check (CLAUDE.md "Evaluation protocol").

For every model feature, how well does that feature *alone* separate misuse from
honest rows? Measured as strength = max(AUC, 1 - AUC), so a feature that is
strongly *lower* for misuse counts too. If any feature exceeds the threshold in
configs/thresholds.yaml (leakage.max_single_feature_auc), something is wrong:
either a feature leaks the label, or the synthetic world is too easy. Either way
the models' results would not mean much, so the check fails.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from jachai.eval.metrics import roc_auc
from jachai.features import feature_columns


class LeakageError(AssertionError):
    pass


def single_feature_auc(features: pd.DataFrame, truth: np.ndarray) -> pd.DataFrame:
    """One row per feature: AUC, strength and how many rows have a value.
    Missing values are scored as the lowest value (they mean "no history")."""
    rows = []
    for col in feature_columns(features):
        x = features[col].to_numpy(dtype=float)
        filled = np.where(np.isnan(x), np.nanmin(x) - 1 if np.isfinite(x).any() else 0, x)
        auc = roc_auc(truth, filled)
        rows.append(
            {
                "feature": col,
                "auc": auc,
                "strength": max(auc, 1 - auc),
                "coverage": float(np.isfinite(x).mean()),
            }
        )
    return pd.DataFrame(rows).sort_values("strength", ascending=False).reset_index(drop=True)


def check(table: pd.DataFrame, max_auc: float) -> pd.DataFrame:
    """Rows above the threshold (empty if the check passes)."""
    return table[table["strength"] > max_auc]


def assert_no_leakage(table: pd.DataFrame, max_auc: float, level: str) -> None:
    bad = check(table, max_auc)
    if len(bad):
        listing = ", ".join(f"{r.feature} ({r.strength:.3f})" for r in bad.itertuples())
        raise LeakageError(
            f"{level}: single features predict the true label too well "
            f"(> {max_auc}): {listing}. Either a feature leaks the label or the "
            f"synthetic world is too easy; see reports/leakage_check.md."
        )
