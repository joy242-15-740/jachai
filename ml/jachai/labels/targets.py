"""Training targets for the payment model: rules' votes + past cases, as soft labels.

Each payment may have up to two pieces of evidence:
  rules  the weighted vote of the labeling functions (weak_proba), if any voted
  case   the verdict of a past investigation of the payment's shop, if the case
         - belongs to a shop of the same split (test shops' cases are never used),
         - closed on or before that split's cutoff date, and
         - closed on or after the payment (the investigation covered it)
Soft target = weighted average of the available evidence; weight = sum of their
weights (configs/rules.yaml `training_target`). Rows with no evidence get weight 0
and are dropped from training.

Three modes for the ablation: "weak" (rules only), "cases" (cases only),
"weak_and_cases" (both).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from jachai.labels.config import TrainingTarget


@dataclass
class Targets:
    soft: np.ndarray  # in [0, 1]; NaN where there is no evidence
    weight: np.ndarray  # 0 where there is no evidence

    @property
    def usable(self) -> np.ndarray:
        return self.weight > 0

    @property
    def hard(self) -> np.ndarray:
        """1 / 0 from the soft target (-1 where unusable), for metrics on validation."""
        return np.where(self.usable, (np.nan_to_num(self.soft) >= 0.5).astype(int), -1)


def case_verdict_for_payments(
    payments: pd.DataFrame,
    split: pd.Series,
    cases: pd.DataFrame,
    cutoffs: dict[str, pd.Timestamp],
) -> np.ndarray:
    """Usable case verdict per payment (NaN if none). `cutoffs`: split -> last usable
    case-closing day for that split. Splits not in `cutoffs` (e.g. test) get none."""
    verdict = np.full(len(payments), np.nan)
    closed = cases.dropna(subset=["closed_on"]).drop_duplicates("shop_id").set_index("shop_id")
    if closed.empty:
        return verdict
    shop_closed = payments["shop_id"].map(closed["closed_on"])
    shop_verdict = payments["shop_id"].map(closed["verdict"]).to_numpy(dtype=float)
    split_arr = split.to_numpy()
    for name, cutoff in cutoffs.items():
        ok = (
            (split_arr == name)
            & shop_closed.notna().to_numpy()
            & (shop_closed <= cutoff).to_numpy()
            & (payments["ts"] <= shop_closed).to_numpy()
        )
        verdict[ok] = shop_verdict[ok]
    return verdict


def build_targets(weak_proba: np.ndarray, case_verdict: np.ndarray, cfg: TrainingTarget) -> Targets:
    use_rules = cfg.mode in ("weak", "weak_and_cases")
    use_cases = cfg.mode in ("cases", "weak_and_cases")
    has_rule = use_rules & ~np.isnan(weak_proba)
    has_case = use_cases & ~np.isnan(case_verdict)
    w_rule = np.where(has_rule, cfg.rule_weight, 0.0)
    w_case = np.where(has_case, cfg.case_weight, 0.0)
    weight = w_rule + w_case
    with np.errstate(invalid="ignore", divide="ignore"):
        soft = (w_rule * np.nan_to_num(weak_proba) + w_case * np.nan_to_num(case_verdict)) / weight
    return Targets(soft=np.where(weight > 0, soft, np.nan), weight=weight)
