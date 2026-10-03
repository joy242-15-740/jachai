"""Weak labels: labeling functions vote, an aggregator turns votes into labels.

`weak_label_table(df, level, rules, cfg)` returns the vote matrix plus
`weak_proba` (P(misuse), NaN if nobody voted) and `weak_label` (1 / 0 / -1).
"""

from __future__ import annotations

import pandas as pd

from jachai.labels.aggregate import make_label_model, weak_labels
from jachai.labels.functions import apply_lfs
from jachai.world.config import WorldConfig


def weak_label_table(df: pd.DataFrame, level: str, rules, cfg: WorldConfig) -> pd.DataFrame:
    votes = apply_lfs(df, level, rules, cfg)
    model = make_label_model(rules).fit(votes)
    proba = model.predict_proba(votes)
    return votes.assign(weak_proba=proba, weak_label=weak_labels(proba, rules.aggregator.threshold))
