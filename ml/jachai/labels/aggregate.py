"""Turn many weak votes into one weak label per row.

`LabelModel` is the interface: `fit(votes)` then `predict_proba(votes)`. The
first implementation is a plain weighted vote. A learned label model (e.g. one
that estimates each function's accuracy from their agreements) can replace it
later without touching the callers.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np
import pandas as pd

from jachai.labels.functions import ABSTAIN, MISUSE


class LabelModel(Protocol):
    def fit(self, votes: pd.DataFrame) -> LabelModel: ...

    def predict_proba(self, votes: pd.DataFrame) -> np.ndarray:
        """Probability of misuse per row; NaN where every function abstained."""
        ...


class WeightedVote:
    """P(misuse) = weighted share of the non-abstaining votes that say misuse."""

    def __init__(self, weights: dict[str, float]):
        self.weights = weights

    def fit(self, votes: pd.DataFrame) -> WeightedVote:
        return self  # nothing to learn

    def predict_proba(self, votes: pd.DataFrame) -> np.ndarray:
        w = np.array([self.weights[c] for c in votes.columns])
        v = votes.to_numpy()
        voted = v != ABSTAIN
        total = (voted * w).sum(axis=1)
        misuse = ((v == MISUSE) * w).sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(total > 0, misuse / total, np.nan)


def weak_labels(proba: np.ndarray, threshold: float) -> np.ndarray:
    """1 / 0 from the probability; -1 (abstain) where no function voted."""
    return np.where(np.isnan(proba), ABSTAIN, (proba >= threshold).astype(int)).astype(np.int8)


def make_label_model(rules) -> LabelModel:
    if rules.aggregator.kind == "weighted_vote":
        return WeightedVote({k: v.weight for k, v in rules.labeling_functions.items()})
    raise ValueError(f"unknown aggregator {rules.aggregator.kind!r}")
