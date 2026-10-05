"""Evaluation metrics from the project evaluation protocol.

pr_auc                 area under the precision-recall curve; honest with rare misuse
precision_at_k         of the k highest-scored cases (analyst capacity), share truly misuse
value_weighted_recall  share of misuse *taka* caught, not just misuse rows
false_positive_rate    share of honest rows (e.g. honest shops) wrongly flagged
"""

from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score


def _arrays(*xs):
    return [np.asarray(x) for x in xs]


def pr_auc(truth, score) -> float:
    truth, score = _arrays(truth, score)
    if truth.sum() == 0:
        return float("nan")
    return float(average_precision_score(truth, np.nan_to_num(score, nan=0.0)))


def roc_auc(truth, score) -> float:
    truth, score = _arrays(truth, score)
    if truth.min() == truth.max():
        return float("nan")
    return float(roc_auc_score(truth, np.nan_to_num(score, nan=0.0)))


def precision_at_k(truth, score, k: int) -> float:
    """Ties at the cut-off are broken by row order (stable sort), so it is reproducible."""
    truth, score = _arrays(truth, score)
    k = min(k, len(truth))
    top = np.argsort(-np.nan_to_num(score, nan=-np.inf), kind="stable")[:k]
    return float(truth[top].mean()) if k else float("nan")


def precision(truth, flag) -> float:
    truth, flag = _arrays(truth, flag)
    flag = flag.astype(bool)
    return float(truth[flag].mean()) if flag.any() else float("nan")


def recall(truth, flag) -> float:
    truth, flag = _arrays(truth, flag)
    pos = truth == 1
    return float(flag.astype(bool)[pos].mean()) if pos.any() else float("nan")


def value_weighted_recall(truth, flag, amount) -> float:
    truth, flag, amount = _arrays(truth, flag, amount)
    pos = truth == 1
    total = amount[pos].sum()
    return float(amount[pos & flag.astype(bool)].sum() / total) if total else float("nan")


def false_positive_rate(truth, flag) -> float:
    truth, flag = _arrays(truth, flag)
    neg = truth == 0
    return float(flag.astype(bool)[neg].mean()) if neg.any() else float("nan")
