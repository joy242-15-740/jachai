"""Combined-feature sanity probe. NOT the Jachai payment model.

Question it answers: once no single feature gives the answer away, do all
features *together* still carry signal beyond the rules? It trains a stock
scikit-learn gradient-boosting classifier on past cases (sparse, shop-level:
a closed case's verdict applies to that shop's payments; shops without a case are
dropped) for 70% of shops, then scores the other 30% of shops (never seen in training)
against the hidden truth, next to the rules-only baseline on the same payments.
The real model (LightGBM, calibrated, proper time split) replaces this later.
"""

from __future__ import annotations

import zlib

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from jachai.eval import metrics as m
from jachai.eval.baselines import evaluation_window
from jachai.features import feature_columns
from jachai.labels import weak_label_table
from jachai.world.world import TRUE_LABEL

TEST_SHARE = 0.3


def shop_split(shop_ids: pd.Series, seed: int) -> np.ndarray:
    """True for test shops. Stable per shop ID: a shop is never in both sides."""
    h = shop_ids.map(lambda s: zlib.crc32(f"{seed}:{s}".encode()) % 1000)
    return (h < TEST_SHARE * 1000).to_numpy()


def run_probe(tables, feats, cfg, thr, rules) -> pd.DataFrame:
    pay = feats["payments"]
    pay = pay[evaluation_window(pay, cfg, thr.eval.warmup_days).to_numpy()].reset_index(drop=True)
    q = tables["qr_payments"].set_index("payment_id").loc[pay["payment_id"]]
    truth, amount = q[TRUE_LABEL].to_numpy(), q["amount"].to_numpy()
    closed = tables["cases"].dropna(subset=["closed_on"]).drop_duplicates("shop_id")
    case = pay["shop_id"].map(closed.set_index("shop_id")["verdict"]).to_numpy(dtype=float)
    test = shop_split(pay["shop_id"], cfg.seed)
    cols = feature_columns(pay)

    train = ~test & ~np.isnan(case)
    model = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1, random_state=cfg.seed)
    model.fit(pay.loc[train, cols], case[train].astype(int))
    model_score = model.predict_proba(pay.loc[test, cols])[:, 1]

    weak = weak_label_table(pay[test], "payment", rules, cfg)
    rules_score = np.nan_to_num(weak["weak_proba"].to_numpy())
    rules_flag = weak["weak_label"].to_numpy() == 1
    # Fair comparison: let the model flag as many payments as the rules do.
    k = int(rules_flag.sum())
    model_flag = np.zeros(len(model_score), dtype=bool)
    model_flag[np.argsort(-model_score, kind="stable")[:k]] = True

    t, a = truth[test], amount[test]
    k_cap = thr.eval.analyst_capacity_payments
    rows = {}
    for name, score, flag in (
        ("rules_only", rules_score, rules_flag),
        ("probe", model_score, model_flag),
    ):
        rows[name] = {
            "pr_auc": m.pr_auc(t, score),
            f"precision_at_{k_cap}": m.precision_at_k(t, score, k_cap),
            "precision_same_flag_count": m.precision(t, flag),
            "recall_same_flag_count": m.recall(t, flag),
            "value_recall_same_flag_count": m.value_weighted_recall(t, flag, a),
        }
    out = pd.DataFrame(rows).T.rename_axis("detector")
    out.attrs["test_payments"], out.attrs["flag_count"] = int(test.sum()), k
    return out
