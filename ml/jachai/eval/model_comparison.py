"""Compare review-ranking approaches on the same features and the same split.

    JACHAI_PROFILE=fast python -m jachai.eval.model_comparison

Writes reports/onsite/ai/model_comparison.json, model_comparison.md and
model_comparison.svg. Validation only: the hidden truth grades the report and
is not used to train or to choose a threshold. The test split is not scored.

The fast profile is the on-site default. A reference-world run is much longer
and needs --allow-long.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import warnings
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

from jachai.eval import metrics as m
from jachai.eval.splits import shop_groups
from jachai.features import feature_columns
from jachai.models.payment import best_f1_threshold, train_payment_model
from jachai.models.train import prepare_payment_data
from jachai.provenance import provenance
from jachai.world.config import REPO_ROOT, load_patterns_config, load_world_config
from jachai.world.generate import generate_world
from jachai.world.summary import md_table
from jachai.world.world import TRUE_LABEL

# Same three seeds as the reference ablation. The fast profile narrows
# eval.ablation_seeds to one seed for the long ablation job; this comparison
# still repeats the three reference seeds on the fast world.
COMPARISON_SEEDS = (42, 7, 2026)
OUT_DIR = REPO_ROOT / "reports" / "onsite" / "ai"
N_BOOT = 200
AE_HIDDEN = 16
AE_MAX_ITER = 40
AE_TIME_LIMIT_S = 120.0
# Fixed before any run. Not searched on the hidden truth.
CANDIDATES = ("logistic_regression", "random_forest", "xgboost", "lightgbm")
OURS = "lightgbm"
CI_METRICS = (
    "precision",
    "recall",
    "f1",
    "false_positive_rate",
    "pr_auc",
    "precision_at_k",
    "value_recall",
)
LABELS = {
    "rules_only": "Rules",
    "graph_shared_payers": "Graph",
    "logistic_regression": "LogReg",
    "random_forest": "RF",
    "xgboost": "XGBoost",
    "lightgbm": "LightGBM",
    "isolation_forest": "IsoForest",
    "autoencoder": "Autoenc",
}
FULL_NAMES = {
    "rules_only": "rules only",
    "graph_shared_payers": "the shared-payer graph rule",
    "logistic_regression": "logistic regression",
    "random_forest": "random forest",
    "xgboost": "XGBoost",
    "lightgbm": "LightGBM",
    "isolation_forest": "isolation forest",
    "autoencoder": "the autoencoder",
}
SENTENCE = {
    "rules_only": "The rules baseline",
    "graph_shared_payers": "The shared-payer graph rule",
    "logistic_regression": "Logistic regression",
    "random_forest": "Random forest",
    "xgboost": "XGBoost",
    "lightgbm": "LightGBM",
    "isolation_forest": "Isolation forest",
    "autoencoder": "The autoencoder",
}
CHART_METRICS = (
    ("precision", "Precision", False),
    ("recall", "Recall", False),
    ("f1", "F1", False),
    ("false_positive_rate", "FPR", True),
)
CHART_COLOURS = {
    "precision": "#1d4e89",
    "recall": "#2f7d4a",
    "f1": "#d08c1f",
    "false_positive_rate": "#b23a48",
}


def _f1(precision: float, recall: float) -> float:
    if np.isnan(precision) or np.isnan(recall):
        return float("nan")
    if precision + recall == 0:
        return 0.0
    return float(2 * precision * recall / (precision + recall))


def metrics_at(
    truth: np.ndarray, score: np.ndarray, flag: np.ndarray, amount: np.ndarray, k: int
) -> dict[str, float]:
    """One operating point. `k` is capped at the number of rows."""
    truth = np.asarray(truth).astype(int)
    score = np.nan_to_num(np.asarray(score, dtype=float), nan=0.0)
    flag = np.asarray(flag).astype(bool)
    amount = np.asarray(amount, dtype=float)
    k_used = int(min(max(k, 0), len(truth)))
    precision = m.precision(truth, flag)
    recall = m.recall(truth, flag)
    return {
        "n": float(len(truth)),
        "positives": float(truth.sum()),
        "precision": precision,
        "recall": recall,
        "f1": _f1(precision, recall),
        "false_positive_rate": m.false_positive_rate(truth, flag),
        "pr_auc": m.pr_auc(truth, score),
        "precision_at_k": m.precision_at_k(truth, score, k_used),
        "k": float(k_used),
        "value_recall": m.value_weighted_recall(truth, flag, amount),
        "flags": float(flag.sum()),
    }


def _ci_from_store(store: dict[str, np.ndarray]) -> dict[str, list[float]]:
    out = {}
    for key, values in store.items():
        if np.isfinite(values).sum() == 0:
            out[key] = [float("nan"), float("nan")]
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            lo = float(np.nanpercentile(values, 2.5))
            hi = float(np.nanpercentile(values, 97.5))
        out[key] = [lo, hi]
    return out


def bootstrap_clusters(
    truth: np.ndarray,
    score: np.ndarray,
    flag: np.ndarray,
    amount: np.ndarray,
    shop_ids: np.ndarray,
    k: int,
    n_boot: int,
    rng: np.random.Generator,
) -> dict[str, list[float]]:
    """Percentile CI with shops drawn with replacement (payments stay with their shop)."""
    _shops, inverse = np.unique(shop_ids, return_inverse=True)
    buckets = [np.flatnonzero(inverse == i) for i in range(len(_shops))]
    n_shops = len(buckets)
    store = {key: np.empty(n_boot) for key in CI_METRICS}
    for i in range(n_boot):
        draw = rng.integers(0, n_shops, size=n_shops)
        idx = np.concatenate([buckets[j] for j in draw])
        got = metrics_at(truth[idx], score[idx], flag[idx], amount[idx], k)
        for key in CI_METRICS:
            store[key][i] = got[key]
    return _ci_from_store(store)


def bootstrap_rows(
    truth: np.ndarray,
    score: np.ndarray,
    flag: np.ndarray,
    amount: np.ndarray,
    k: int,
    n_boot: int,
    rng: np.random.Generator,
) -> dict[str, list[float]]:
    """Percentile CI resampling shops, when each row is already one shop."""
    n = len(truth)
    store = {key: np.empty(n_boot) for key in CI_METRICS}
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        got = metrics_at(truth[idx], score[idx], flag[idx], amount[idx], k)
        for key in CI_METRICS:
            store[key][i] = got[key]
    return _ci_from_store(store)


def shared_payer_counts(payments: pd.DataFrame, include: np.ndarray) -> np.ndarray:
    """Point-in-time count of payers who also paid another included shop.

    The count on day D uses payer–shop links whose first payment is before day D.
    Same-day links show up the next day. `include` drops test shops so the
    baseline does not read held-out shops.
    """
    include = np.asarray(include, dtype=bool)
    day = payments["ts"].dt.normalize().to_numpy()
    hist = pd.DataFrame(
        {
            "payer_id": payments["payer_id"].to_numpy()[include],
            "shop_id": payments["shop_id"].to_numpy()[include],
            "day": day[include],
        }
    )
    if hist.empty:
        return np.zeros(len(payments), dtype=float)
    pairs = hist.groupby(["payer_id", "shop_id"], sort=False)["day"].min().reset_index()
    by_day = {d: g for d, g in pairs.groupby("day", sort=False)}
    payer_shops: dict[object, set] = defaultdict(set)
    shop_shared: dict[object, int] = defaultdict(int)
    snap: dict[object, dict[object, int]] = {}
    for d in sorted(pd.unique(day)):
        snap[d] = dict(shop_shared)
        block = by_day.get(d)
        if block is None:
            continue
        for payer, shop in block[["payer_id", "shop_id"]].itertuples(index=False):
            seen = payer_shops[payer]
            if shop in seen:
                continue
            n_other = len(seen)
            seen.add(shop)
            if n_other == 0:
                continue
            if n_other == 1:
                previous = next(iter(seen - {shop}))
                shop_shared[previous] += 1
            shop_shared[shop] += 1
    days, shops, counts = [], [], []
    for d, mapping in snap.items():
        for shop, count in mapping.items():
            days.append(d)
            shops.append(shop)
            counts.append(count)
    if not counts:
        return np.zeros(len(payments), dtype=float)
    lookup = pd.Series(
        counts,
        index=pd.MultiIndex.from_arrays([days, shops], names=["day", "shop_id"]),
    )
    keys = pd.MultiIndex.from_arrays(
        [day, payments["shop_id"].to_numpy()], names=["day", "shop_id"]
    )
    return lookup.reindex(keys).fillna(0.0).to_numpy(dtype=float)


def impute_train_median(x: np.ndarray, train: np.ndarray) -> np.ndarray:
    """Fill non-finite values with the train-row median. The median is not fit on validation."""
    out = np.array(x, dtype=float, copy=True)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="All-NaN slice")
        median = np.nanmedian(out[train], axis=0)
    median = np.where(np.isfinite(median), median, 0.0)
    bad = ~np.isfinite(out)
    rows, cols = np.nonzero(bad)
    out[rows, cols] = median[cols]
    return out


def scale_from_train(x: np.ndarray, train: np.ndarray) -> np.ndarray:
    scaler = StandardScaler()
    scaler.fit(x[train])
    return scaler.transform(x)


def _threshold(y: np.ndarray, score: np.ndarray, usable: np.ndarray) -> float:
    """Max-F1 cut on validation targets. +inf flags nobody when there is no target."""
    if int(usable.sum()) == 0:
        return float("inf")
    return best_f1_threshold(y[usable].astype(float), score[usable])


def _fit_xgboost(
    x: np.ndarray,
    soft: np.ndarray,
    weight: np.ndarray,
    usable: np.ndarray,
    train: np.ndarray,
    valid: np.ndarray,
    seed: int,
) -> xgb.Booster:
    tr = train & usable
    va = valid & usable
    dtrain = xgb.DMatrix(x[tr], label=soft[tr], weight=weight[tr])
    dval = xgb.DMatrix(x[va], label=soft[va], weight=weight[va])
    params = {
        "objective": "binary:logistic",
        "eval_metric": "logloss",
        "max_depth": 4,
        "eta": 0.08,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "lambda": 1.0,
        "min_child_weight": 5.0,
        "tree_method": "hist",
        "seed": seed,
        "nthread": 1,
        "verbosity": 0,
    }
    return xgb.train(
        params,
        dtrain,
        num_boost_round=80,
        evals=[(dval, "validation")],
        early_stopping_rounds=10,
        verbose_eval=False,
    )


def _xgb_scores(booster: xgb.Booster, x: np.ndarray) -> np.ndarray:
    best = getattr(booster, "best_iteration", None)
    matrix = xgb.DMatrix(x)
    if best is None:
        return booster.predict(matrix)
    return booster.predict(matrix, iteration_range=(0, int(best) + 1))


def shop_view(
    shop_ids: np.ndarray,
    score: np.ndarray,
    flag: np.ndarray,
    amount: np.ndarray,
    pay_truth: np.ndarray,
    shop_labels: pd.Series,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """One row per shop: max score, any-payment flag, shop label, misuse taka."""
    frame = pd.DataFrame(
        {
            "shop_id": np.asarray(shop_ids),
            "score": score,
            "flag": np.asarray(flag, dtype=bool),
            "misuse_taka": np.where(pay_truth == 1, amount, 0.0),
        }
    )
    grouped = frame.groupby("shop_id", sort=False)
    shop_score = grouped["score"].max()
    shop_flag = grouped["flag"].max().to_numpy(dtype=bool)
    taka = grouped["misuse_taka"].sum().to_numpy(dtype=float)
    truth = shop_labels.reindex(shop_score.index).to_numpy(dtype=float)
    if np.isnan(truth).any():
        raise ValueError("a validation shop has no hidden label")
    return (
        shop_score.to_numpy(dtype=float),
        shop_flag,
        truth.astype(int),
        taka,
        shop_score.index.to_numpy(),
    )


def _failed(name: str, message: str, n_pay: int, pos_pay: int, n_shop: int, pos_shop: int) -> dict:
    def block(n: int, positives: int) -> dict[str, float]:
        out = {key: float("nan") for key in CI_METRICS}
        out.update(
            {"n": float(n), "positives": float(positives), "k": float("nan"), "flags": float("nan")}
        )
        return out

    return {
        "name": name,
        "error": message,
        "threshold": None,
        "train_seconds": float("nan"),
        "inference_seconds": float("nan"),
        "train_rows": 0,
        "payment": block(n_pay, pos_pay),
        "shop": block(n_shop, pos_shop),
        "bootstrap_95ci": {"payment": {}, "shop": {}},
    }


def _package(
    name: str,
    score: np.ndarray,
    flag: np.ndarray,
    threshold: float,
    train_seconds: float,
    inference_seconds: float,
    train_rows: int,
    pay_truth: np.ndarray,
    pay_amount: np.ndarray,
    shop_ids: np.ndarray,
    shop_labels: pd.Series,
    k_pay: int,
    k_shop: int,
    n_boot: int,
    seed: int,
    error: str | None = None,
) -> dict:
    shop_score, shop_flag, shop_truth, shop_taka, _shops = shop_view(
        shop_ids, score, flag, pay_amount, pay_truth, shop_labels
    )
    payment = metrics_at(pay_truth, score, flag, pay_amount, k_pay)
    shop = metrics_at(shop_truth, shop_score, shop_flag, shop_taka, k_shop)
    pay_ci = bootstrap_clusters(
        pay_truth,
        score,
        flag,
        pay_amount,
        shop_ids,
        k_pay,
        n_boot,
        np.random.default_rng(seed + 17_000),
    )
    shop_ci = bootstrap_rows(
        shop_truth,
        shop_score,
        shop_flag,
        shop_taka,
        k_shop,
        n_boot,
        np.random.default_rng(seed + 19_000),
    )
    return {
        "name": name,
        "error": error,
        "threshold": None if np.isnan(threshold) or np.isinf(threshold) else float(threshold),
        "train_seconds": float(train_seconds),
        "inference_seconds": float(inference_seconds),
        "train_rows": int(train_rows),
        "payment": payment,
        "shop": shop,
        "bootstrap_95ci": {"payment": pay_ci, "shop": shop_ci},
    }


def run_seed(seed: int, n_boot: int) -> dict:
    """One synthetic world. Metrics are validation rows only."""
    started = time.perf_counter()
    base = load_world_config()
    cfg = base.model_copy(update={"seed": seed})
    patterns = load_patterns_config()
    from jachai.features.config import load_thresholds
    from jachai.labels.config import load_rules
    from jachai.models.config import load_models_config

    thr = load_thresholds()
    rules = load_rules()
    models = load_models_config()
    world = generate_world(cfg, patterns)
    tables = world.tables
    data = prepare_payment_data(tables, cfg, thr, rules)
    payments = data.payments
    split = data.split.to_numpy()
    targets = data.targets(rules.training_target)
    features = feature_columns(payments)
    if any(str(col).startswith("_true_") for col in features):
        raise RuntimeError("hidden label leaked into model features")

    groups = shop_groups(tables["shops"], thr, cfg.seed)
    train = split == "train"
    valid = split == "validation"
    train_shops = set(payments.loc[train, "shop_id"])
    valid_shops = set(payments.loc[valid, "shop_id"])
    test_shops = set(groups[groups == "test"].index)
    if not train_shops.isdisjoint(valid_shops) or not valid_shops.isdisjoint(test_shops):
        raise RuntimeError("shop split leaked between train, validation and test")

    q = tables["qr_payments"].set_index("payment_id").loc[payments["payment_id"].to_numpy()]
    truth = q[TRUE_LABEL].to_numpy().astype(int)
    amount = q["amount"].to_numpy().astype(float)
    shop_labels = tables["shops"].set_index("shop_id")[TRUE_LABEL].astype(int)
    include = payments["shop_id"].map(groups).to_numpy() != "test"

    va_truth = truth[valid]
    va_amount = amount[valid]
    va_shops = payments.loc[valid, "shop_id"].to_numpy()
    # Shop count is known after the first successful aggregation; use labels for the failure path.
    n_pay = int(valid.sum())
    pos_pay = int(va_truth.sum())
    k_pay = int(thr.eval.analyst_capacity_payments)
    k_shop = int(thr.eval.analyst_capacity_shops)
    y = targets.hard
    soft = np.nan_to_num(targets.soft, nan=0.0)
    weight = targets.weight
    usable = targets.usable

    x_raw = payments[features].to_numpy(dtype=float)
    x_imp = impute_train_median(x_raw, train)
    x_scaled = scale_from_train(x_imp, train)

    def finish(name, score, flag, threshold, train_s, infer_s, train_rows, error=None) -> dict:
        return _package(
            name,
            np.nan_to_num(score, nan=0.0),
            flag,
            threshold,
            train_s,
            infer_s,
            train_rows,
            va_truth,
            va_amount,
            va_shops,
            shop_labels,
            k_pay,
            k_shop,
            n_boot,
            seed,
            error,
        )

    results = []

    t0 = time.perf_counter()
    rule_score = np.nan_to_num(data.weak_proba[valid], nan=0.0)
    rule_flag = data.weak_label[valid] == 1
    infer_s = time.perf_counter() - t0
    results.append(
        finish(
            "rules_only",
            rule_score,
            rule_flag,
            float(rules.aggregator.threshold),
            0.0,
            infer_s,
            0,
        )
    )

    t0 = time.perf_counter()
    graph_all = shared_payer_counts(payments, include)
    train_s = time.perf_counter() - t0
    graph_score = graph_all[valid]
    t1 = time.perf_counter()
    _ = graph_score.copy()
    infer_s = time.perf_counter() - t1
    graph_threshold = _threshold(y[valid], graph_score, usable[valid])
    results.append(
        finish(
            "graph_shared_payers",
            graph_score,
            graph_score >= graph_threshold,
            graph_threshold,
            train_s,
            infer_s,
            int(include.sum()),
        )
    )

    supervised = (
        (
            "logistic_regression",
            "imputed and standardised",
            lambda: _fit_logistic(x_scaled, y, weight, usable, train, seed),
            _positive_proba,
        ),
        (
            "random_forest",
            "imputed",
            lambda: _fit_forest(x_imp, y, weight, usable, train, seed),
            _positive_proba,
        ),
    )
    for name, _prep, fitter, scorer in supervised:
        results.append(
            _supervised_numpy(
                name,
                fitter,
                scorer,
                x_imp if name == "random_forest" else x_scaled,
                y,
                usable,
                train,
                valid,
                va_truth,
                va_amount,
                va_shops,
                shop_labels,
                k_pay,
                k_shop,
                n_boot,
                seed,
                n_pay,
                pos_pay,
            )
        )

    results.append(
        _supervised_xgb(
            x_imp,
            soft,
            weight,
            y,
            usable,
            train,
            valid,
            va_truth,
            va_amount,
            va_shops,
            shop_labels,
            k_pay,
            k_shop,
            n_boot,
            seed,
            n_pay,
            pos_pay,
        )
    )
    results.append(
        _supervised_lgb(
            payments,
            data.split,
            targets,
            models,
            seed,
            valid,
            y,
            usable,
            va_truth,
            va_amount,
            va_shops,
            shop_labels,
            k_pay,
            k_shop,
            n_boot,
            n_pay,
            pos_pay,
        )
    )
    results.append(
        _fit_isolation(
            x_scaled,
            train,
            valid,
            y,
            usable,
            seed,
            va_truth,
            va_amount,
            va_shops,
            shop_labels,
            k_pay,
            k_shop,
            n_boot,
            n_pay,
            pos_pay,
        )
    )
    results.append(
        _fit_autoencoder(
            x_scaled,
            train,
            valid,
            y,
            usable,
            seed,
            va_truth,
            va_amount,
            va_shops,
            shop_labels,
            k_pay,
            k_shop,
            n_boot,
            n_pay,
            pos_pay,
        )
    )

    shop_n = int(results[0]["shop"]["n"])
    shop_pos = int(results[0]["shop"]["positives"])
    print(
        f"seed {seed} done in {time.perf_counter() - started:.1f}s "
        f"({n_pay} validation payments, {pos_pay} misuse; {shop_n} shops, {shop_pos} misuse)",
        flush=True,
    )
    return {
        "seed": seed,
        "validation_payments": n_pay,
        "validation_payment_positives": pos_pay,
        "validation_shops": shop_n,
        "validation_shop_positives": shop_pos,
        "payment_k": int(results[0]["payment"]["k"]),
        "shop_k": int(results[0]["shop"]["k"]),
        "features": features,
        "lightgbm_params": models.payment_model.lightgbm.model_dump(),
        "target_mode": rules.training_target.mode,
        "models": results,
        "dataset": {
            "n_shops": cfg.population.n_shops,
            "n_customers": cfg.population.n_customers,
            "n_agents": cfg.population.n_agents,
            "calendar_start": str(cfg.calendar.start),
            "calendar_days": cfg.calendar.days,
            "holdout_pattern": thr.split.holdout_pattern,
            "analyst_capacity_payments": k_pay,
            "analyst_capacity_shops": k_shop,
            "train_end": str(thr.split.train_end),
            "validation_end": str(thr.split.validation_end),
        },
    }


def _supervised_numpy(
    name,
    fitter,
    scorer,
    x,
    y,
    usable,
    train,
    valid,
    va_truth,
    va_amount,
    va_shops,
    shop_labels,
    k_pay,
    k_shop,
    n_boot,
    seed,
    n_pay,
    pos_pay,
) -> dict:
    try:
        t0 = time.perf_counter()
        est = fitter()
        train_s = time.perf_counter() - t0
        t1 = time.perf_counter()
        score = np.asarray(scorer(est, x[valid]), dtype=float)
        infer_s = time.perf_counter() - t1
        threshold = _threshold(y[valid], score, usable[valid])
        return _package(
            name,
            score,
            score >= threshold,
            threshold,
            train_s,
            infer_s,
            int((train & usable).sum()),
            va_truth,
            va_amount,
            va_shops,
            shop_labels,
            k_pay,
            k_shop,
            n_boot,
            seed,
        )
    except (ValueError, np.linalg.LinAlgError) as err:
        n_shop = len(np.unique(va_shops))
        return _failed(name, f"{type(err).__name__}: {err}", n_pay, int(va_truth.sum()), n_shop, 0)


def _positive_proba(est, rows: np.ndarray) -> np.ndarray:
    """Probability of class 1, independent of `classes_` order."""
    classes = list(est.classes_)
    return np.asarray(est.predict_proba(rows)[:, classes.index(1)], dtype=float)


def _fit_logistic(x, y, weight, usable, train, seed):
    tr = train & usable
    if len(np.unique(y[tr])) < 2:
        raise ValueError("training targets are a single class")
    model = LogisticRegression(C=1.0, max_iter=400, solver="lbfgs", random_state=seed)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        model.fit(x[tr], y[tr].astype(int), sample_weight=weight[tr])
    return model


def _fit_forest(x, y, weight, usable, train, seed):
    tr = train & usable
    if len(np.unique(y[tr])) < 2:
        raise ValueError("training targets are a single class")
    model = RandomForestClassifier(
        n_estimators=80,
        max_depth=10,
        min_samples_leaf=15,
        max_features="sqrt",
        random_state=seed,
        n_jobs=1,
    )
    model.fit(x[tr], y[tr].astype(int), sample_weight=weight[tr])
    return model


def _supervised_xgb(
    x,
    soft,
    weight,
    y,
    usable,
    train,
    valid,
    va_truth,
    va_amount,
    va_shops,
    shop_labels,
    k_pay,
    k_shop,
    n_boot,
    seed,
    n_pay,
    pos_pay,
) -> dict:
    try:
        t0 = time.perf_counter()
        booster = _fit_xgboost(x, soft, weight, usable, train, valid, seed)
        train_s = time.perf_counter() - t0
        t1 = time.perf_counter()
        score = _xgb_scores(booster, x[valid])
        infer_s = time.perf_counter() - t1
        threshold = _threshold(y[valid], score, usable[valid])
        return _package(
            "xgboost",
            score,
            score >= threshold,
            threshold,
            train_s,
            infer_s,
            int((train & usable).sum()),
            va_truth,
            va_amount,
            va_shops,
            shop_labels,
            k_pay,
            k_shop,
            n_boot,
            seed,
        )
    except (ValueError, xgb.core.XGBoostError) as err:
        n_shop = len(np.unique(va_shops))
        return _failed(
            "xgboost", f"{type(err).__name__}: {err}", n_pay, int(va_truth.sum()), n_shop, 0
        )


def _supervised_lgb(
    payments,
    split,
    targets,
    models,
    seed,
    valid,
    y,
    usable,
    va_truth,
    va_amount,
    va_shops,
    shop_labels,
    k_pay,
    k_shop,
    n_boot,
    n_pay,
    pos_pay,
) -> dict:
    try:
        t0 = time.perf_counter()
        model = train_payment_model(payments, split, targets, models.payment_model, seed)
        train_s = time.perf_counter() - t0
        t1 = time.perf_counter()
        score = model.predict_proba(payments.loc[valid])
        infer_s = time.perf_counter() - t1
        return _package(
            "lightgbm",
            score,
            score >= model.threshold,
            float(model.threshold),
            train_s,
            infer_s,
            int(model.meta["train_rows"]),
            va_truth,
            va_amount,
            va_shops,
            shop_labels,
            k_pay,
            k_shop,
            n_boot,
            seed,
        )
    except ValueError as err:
        n_shop = len(np.unique(va_shops))
        return _failed(
            "lightgbm", f"{type(err).__name__}: {err}", n_pay, int(va_truth.sum()), n_shop, 0
        )


def _fit_isolation(
    x,
    train,
    valid,
    y,
    usable,
    seed,
    va_truth,
    va_amount,
    va_shops,
    shop_labels,
    k_pay,
    k_shop,
    n_boot,
    n_pay,
    pos_pay,
) -> dict:
    try:
        t0 = time.perf_counter()
        model = IsolationForest(
            n_estimators=100,
            max_samples=min(512, int(train.sum())),
            contamination="auto",
            random_state=seed,
            n_jobs=1,
        )
        model.fit(x[train])
        train_s = time.perf_counter() - t0
        t1 = time.perf_counter()
        # decision_function is higher for normal rows. Flip it so higher means more unusual.
        score = -model.decision_function(x[valid])
        infer_s = time.perf_counter() - t1
        threshold = _threshold(y[valid], score, usable[valid])
        return _package(
            "isolation_forest",
            score,
            score >= threshold,
            threshold,
            train_s,
            infer_s,
            int(train.sum()),
            va_truth,
            va_amount,
            va_shops,
            shop_labels,
            k_pay,
            k_shop,
            n_boot,
            seed,
        )
    except ValueError as err:
        n_shop = len(np.unique(va_shops))
        return _failed(
            "isolation_forest",
            f"{type(err).__name__}: {err}",
            n_pay,
            int(va_truth.sum()),
            n_shop,
            0,
        )


def _fit_autoencoder(
    x,
    train,
    valid,
    y,
    usable,
    seed,
    va_truth,
    va_amount,
    va_shops,
    shop_labels,
    k_pay,
    k_shop,
    n_boot,
    n_pay,
    pos_pay,
) -> dict:
    """One hidden layer, trained to reconstruct the row. Score is squared error.

    This is a small autoencoder, not a deep network. It is dropped if the fit
    exceeds the two-minute budget.
    """
    try:
        t0 = time.perf_counter()
        n_train = int(train.sum())
        model = MLPRegressor(
            hidden_layer_sizes=(AE_HIDDEN,),
            activation="relu",
            solver="adam",
            learning_rate_init=1e-3,
            max_iter=AE_MAX_ITER,
            random_state=seed,
            early_stopping=n_train >= 20,
            validation_fraction=0.1,
            n_iter_no_change=5,
            tol=1e-4,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ConvergenceWarning)
            model.fit(x[train], x[train])
        train_s = time.perf_counter() - t0
        if train_s > AE_TIME_LIMIT_S:
            n_shop = len(np.unique(va_shops))
            return _failed(
                "autoencoder",
                f"fit took {train_s:.1f}s, over the {AE_TIME_LIMIT_S:.0f}s budget",
                n_pay,
                int(va_truth.sum()),
                n_shop,
                0,
            )
        t1 = time.perf_counter()
        recon = model.predict(x[valid])
        score = np.mean((x[valid] - recon) ** 2, axis=1)
        infer_s = time.perf_counter() - t1
        threshold = _threshold(y[valid], score, usable[valid])
        packed = _package(
            "autoencoder",
            score,
            score >= threshold,
            threshold,
            train_s,
            infer_s,
            n_train,
            va_truth,
            va_amount,
            va_shops,
            shop_labels,
            k_pay,
            k_shop,
            n_boot,
            seed,
        )
        packed["autoencoder_iterations"] = int(model.n_iter_)
        packed["autoencoder_hidden"] = AE_HIDDEN
        return packed
    except ValueError as err:
        n_shop = len(np.unique(va_shops))
        return _failed(
            "autoencoder", f"{type(err).__name__}: {err}", n_pay, int(va_truth.sum()), n_shop, 0
        )


def summarise(per_seed: list[dict]) -> pd.DataFrame:
    rows = []
    for seed_result in per_seed:
        for model in seed_result["models"]:
            flat: dict[str, object] = {"model": model["name"], "seed": seed_result["seed"]}
            for level in ("payment", "shop"):
                for key, value in model[level].items():
                    flat[f"{level}_{key}"] = value
            flat["train_seconds"] = model["train_seconds"]
            flat["inference_seconds"] = model["inference_seconds"]
            flat["threshold"] = (
                model["threshold"] if model["threshold"] is not None else float("nan")
            )
            rows.append(flat)
    frame = pd.DataFrame(rows)
    numeric = [c for c in frame.columns if c not in ("model", "seed")]
    grouped = frame.groupby("model", sort=False)[numeric]
    out = grouped.mean().add_suffix("_mean").join(grouped.std(ddof=1).add_suffix("_std"))
    out["seeds"] = frame.groupby("model", sort=False)["seed"].count()
    return out


def _num(value: float | None) -> str:
    if value is None:
        return "n/a"
    number = float(value)
    if np.isnan(number):
        return "n/a"
    return f"{number:.3f}"


def _pm(mean: float, std: float) -> str:
    if pd.isna(mean):
        return "n/a"
    if pd.isna(std):
        return f"{mean:.3f}"
    return f"{mean:.3f} ± {std:.3f}"


def _count(mean: float) -> str:
    if pd.isna(mean):
        return "n/a"
    return f"{int(round(float(mean))):,}"


def _stat(summary: pd.DataFrame, model: str, column: str) -> str:
    return _pm(summary.loc[model, f"{column}_mean"], summary.loc[model, f"{column}_std"])


def _metric_cell(summary: pd.DataFrame, model: str, level: str, metric: str) -> str:
    text = _stat(summary, model, f"{level}_{metric}")
    n = _count(summary.loc[model, f"{level}_n_mean"])
    pos = _count(summary.loc[model, f"{level}_positives_mean"])
    extra = ""
    if metric == "precision_at_k":
        extra = f", k={_count(summary.loc[model, f'{level}_k_mean'])}"
    return f"{text} (N={n}, pos={pos}{extra})"


def feature_paragraph(columns: list[str]) -> str:
    listed = ", ".join(f"`{col}`" for col in columns)
    return (
        "Every learner uses the same point-in-time columns from `feature_columns`, "
        "the payment, payer-history and shop-history features already used by the "
        "payment model. They were chosen because each one is known at payment time "
        "and lines up with a misuse mechanism in this synthetic world: round amounts, "
        "tickets just under the incentive cap, payer totals near the daily cash-out "
        "limit, money paid soon after an inflow or a remittance, payer–shop distance, "
        "first visits, and shop turnover against the shop's own history and against "
        "similar shops. Identifiers, timestamps, peer-group labels and hidden "
        "`_true_*` columns are excluded, so a model cannot memorise a shop id or read "
        "the label. Columns were not added or dropped using validation accuracy; a "
        "second selection pass on the split we report would inflate the comparison. "
        "LightGBM keeps missing values as missing, which is how the frozen payment "
        "model is trained. Logistic regression, random forest, XGBoost, isolation "
        "forest and the autoencoder get a median fill fit on train rows only, because "
        "those algorithms need finite inputs. Logistic regression, isolation forest "
        "and the autoencoder are also standardised with a scaler fit on train rows "
        f"only, because their geometry depends on units. This run used {len(columns)} "
        f"columns: {listed}."
    )


def _seed_wins(per_seed: list[dict], leader: str, other: str, metric: str) -> int:
    """How many seeds `leader` beats `other` on one payment metric."""
    wins = 0
    for seed_result in per_seed:
        rows = {item["name"]: item for item in seed_result["models"]}
        a = rows[leader]["payment"][metric]
        b = rows[other]["payment"][metric]
        if a is None or b is None or np.isnan(a) or np.isnan(b):
            continue
        if a > b:
            wins += 1
    return wins


def _mean(summary: pd.DataFrame, model: str, column: str) -> float:
    if model not in summary.index:
        return float("nan")
    return float(summary.loc[model, column])


def decision_paragraph(summary: pd.DataFrame, per_seed: list[dict]) -> str:
    """One paragraph. The keep rule is fixed in code and applied to these numbers."""
    available = []
    for name in CANDIDATES:
        value = _mean(summary, name, "payment_pr_auc_mean")
        if not np.isnan(value):
            available.append(name)
    if not available:
        return "No supervised model produced a validation PR-AUC, so this run has no model to keep."

    def noise(a: str, b: str) -> tuple[float, float, bool]:
        gap = _mean(summary, a, "payment_pr_auc_mean") - _mean(summary, b, "payment_pr_auc_mean")
        spread = abs(_mean(summary, a, "payment_pr_auc_std")) + abs(
            _mean(summary, b, "payment_pr_auc_std")
        )
        spread = 0.0 if np.isnan(spread) else spread
        return gap, spread, abs(gap) > spread

    best = max(available, key=lambda name: _mean(summary, name, "payment_pr_auc_mean"))
    ours_ok = OURS in available
    gap, spread, clear = (0.0, 0.0, False)
    if ours_ok:
        gap, spread, clear = noise(best, OURS)
        gap = _mean(summary, best, "payment_pr_auc_mean") - _mean(
            summary, OURS, "payment_pr_auc_mean"
        )
    kept = OURS if ours_ok and (best == OURS or not clear) else best
    if kept != OURS and ours_ok and clear:
        best_time = _mean(summary, best, "train_seconds_mean")
        ours_time = _mean(summary, OURS, "train_seconds_mean")
        explainable = best in {"random_forest", "xgboost", "logistic_regression", "lightgbm"}
        fast_enough = best_time <= max(60.0, 2.0 * ours_time)
        if not (explainable and fast_enough):
            kept = OURS

    def ci_text(model: str) -> str:
        parts = []
        for seed_result in per_seed:
            row = next(item for item in seed_result["models"] if item["name"] == model)
            bounds = row["bootstrap_95ci"]["payment"].get("pr_auc")
            if not bounds:
                continue
            parts.append(f"seed {seed_result['seed']} {bounds[0]:.3f}–{bounds[1]:.3f}")
        return ", ".join(parts) if parts else "n/a"

    def combined_std(a: str, b: str, column: str = "payment_pr_auc_std") -> float:
        total = 0.0
        for name in (a, b):
            value = _mean(summary, name, column)
            total += 0.0 if np.isnan(value) else abs(value)
        return total

    rules_gap = _mean(summary, "rules_only", "payment_pr_auc_mean") - _mean(
        summary, kept, "payment_pr_auc_mean"
    )
    rules_spread = combined_std("rules_only", kept)
    graph_name = "graph_shared_payers"

    def ahead(metric: str, plain: str, higher: bool = True) -> str:
        pool = [
            name
            for name in (
                *CANDIDATES,
                "isolation_forest",
                "autoencoder",
                "rules_only",
                graph_name,
            )
            if name in summary.index and not np.isnan(_mean(summary, name, f"{metric}_mean"))
        ]
        if kept not in pool:
            return ""
        sign = 1.0 if higher else -1.0
        leader = max(pool, key=lambda name: sign * _mean(summary, name, f"{metric}_mean"))
        if leader == kept:
            return ""
        gap_m = _mean(summary, leader, f"{metric}_mean") - _mean(summary, kept, f"{metric}_mean")
        if not higher:
            gap_m = -gap_m
        spread_m = combined_std(leader, kept, f"{metric}_std")
        if gap_m <= spread_m:
            return ""
        return (
            f"{SENTENCE[leader]} is better on {plain} "
            f"({_stat(summary, leader, metric)} versus {_stat(summary, kept, metric)}, "
            f"gap {gap_m:.3f}, combined std {spread_m:.3f}). "
        )

    frozen = (
        " The running service still loads LightGBM until a later change swaps the payment model."
        if kept != OURS
        else ""
    )
    why = f"We keep {FULL_NAMES[kept]}."
    if kept == OURS and best == OURS:
        why += " It has the highest supervised payment PR-AUC in this run."
    elif kept == OURS and not clear:
        wins = _seed_wins(per_seed, best, OURS, "pr_auc")
        why += (
            f" {SENTENCE[best]} leads mean supervised payment PR-AUC by {gap:.3f}, "
            f"inside the combined seed-to-seed std ({spread:.3f}). "
            f"It is ahead of LightGBM on that metric in {wins} of {len(per_seed)} seeds. "
            "The pre-set bar for swapping the frozen payment model is a mean gap larger than "
            "that combined std, so we keep LightGBM. "
            + (
                "The direction of the lead is consistent across seeds; what the std leaves open "
                "is the size of the lead. "
                if wins == len(per_seed)
                else ""
            )
        )
    elif kept == OURS and clear:
        why += (
            f" {FULL_NAMES[best]} is clearly ahead on payment PR-AUC by {gap:.3f} "
            f"(combined std {spread:.3f}). We still keep LightGBM because that leader is "
            "slower than the on-site budget or is not a tree or linear model we can explain "
            "to an analyst, and LightGBM is already the calibrated payment score in the system."
        )
    else:
        why += (
            f" It leads the supervised models on payment PR-AUC by {gap:.3f} over LightGBM "
            f"(combined std {spread:.3f}), it trains in {_stat(summary, kept, 'train_seconds')} s, "
            "and a tree or a linear model can be explained feature by feature."
        )
    why += (
        f"On validation payments its precision is {_stat(summary, kept, 'payment_precision')}, "
        f"recall {_stat(summary, kept, 'payment_recall')}, "
        f"F1 {_stat(summary, kept, 'payment_f1')}, "
        f"false-positive rate {_stat(summary, kept, 'payment_false_positive_rate')}, "
        f"PR-AUC {_stat(summary, kept, 'payment_pr_auc')}, "
        f"and share of misuse taka caught {_stat(summary, kept, 'payment_value_recall')} "
        f"(N={_count(_mean(summary, kept, 'payment_n_mean'))}, "
        f"pos={_count(_mean(summary, kept, 'payment_positives_mean'))}). "
        f"At shop level its F1 is {_stat(summary, kept, 'shop_f1')} and its PR-AUC is "
        f"{_stat(summary, kept, 'shop_pr_auc')} "
        f"(N={_count(_mean(summary, kept, 'shop_n_mean'))}, "
        f"pos={_count(_mean(summary, kept, 'shop_positives_mean'))}). "
        f"Train time is {_stat(summary, kept, 'train_seconds')} s and inference is "
        f"{_stat(summary, kept, 'inference_seconds')} s. "
        f"Shop-cluster bootstrap 95% CIs for its payment PR-AUC: {ci_text(kept)}. "
        + ahead("payment_f1", "payment F1")
        + ahead("payment_value_recall", "share of misuse taka caught")
        + ahead("payment_false_positive_rate", "payment false-positive rate", higher=False)
        + f"Rules-only payment PR-AUC is {_stat(summary, 'rules_only', 'payment_pr_auc')} "
        f"(gap versus the kept model {rules_gap:+.3f}, combined std {rules_spread:.3f}). "
        + (
            "Rules rank higher on this normal synthetic world, which matches the overlap "
            "between the labeling functions and the synthetic typologies. "
            if rules_gap > rules_spread
            else "The kept model ranks above rules on payment PR-AUC in this run. "
            if rules_gap < -rules_spread
            else "The gap versus rules is inside the combined seed-to-seed std. "
        )
        + "Behaviour-shift numbers stay the ones already published in reports/final_test.md. "
        "The shared-payer graph rule has payment PR-AUC "
        f"{_stat(summary, graph_name, 'payment_pr_auc')}. "
        "Its hypothesis is that a shop sharing many payers with other shops is a ring; "
        "ordinary neighbours share regulars as well, and the count updates only on the next "
        "day, so a same-day ring is invisible to it until tomorrow. Isolation forest and the "
        "autoencoder are unsupervised baselines trained without the weak labels. "
        "A higher score only raises a case in the human review queue." + frozen
    )
    return why


def caveats(per_seed: list[dict], profile: str) -> list[str]:
    data = per_seed[0]["dataset"]
    lines = [
        f"Profile `{profile}`: {data['n_shops']} shops, {data['n_customers']} customers, "
        f"{data['n_agents']} agents, {data['calendar_days']} days from {data['calendar_start']}. "
        "Same generator, patterns, features and shop+time split as the reference world. "
        f"These numbers are the {profile} profile. The frozen reference metrics stay in "
        "reports/validation_evaluation.md and reports/final_test.md.",
        "Thresholds maximise F1 against validation targets from rules and past cases. "
        "LightGBM's isotonic calibrator is fit on those same validation targets, as in the "
        "frozen payment model. The hidden truth is used only to grade. Flag metrics on this "
        "split are therefore a little optimistic. PR-AUC and precision at k use the ranking, "
        "not the cut.",
        "Supervised models train on soft targets (rules plus past cases) for LightGBM and "
        "XGBoost. Logistic regression and random forest need a hard 0/1 label, so they use "
        "the soft target cut at 0.5 with the same evidence weights. That difference is a "
        "property of the libraries, and it can move their thresholded metrics.",
        f"The held-out pattern `{data['holdout_pattern']}` is forced into test by the project "
        "split, using the hidden pattern name only to place shops. Those shops are absent "
        "from these metrics. Peer-group medians still come from the existing feature pipeline.",
        f"{len(per_seed)} seeds is a small sample, so the std is itself noisy. The bootstrap "
        "resamples shops inside one seed; it is a different uncertainty from the seed-to-seed std.",
        "Shop-level value recall treats a flagged shop as catching all of its validation "
        "misuse taka. Payment-level value recall counts only the flagged payments.",
    ]
    ceilings = []
    for row in per_seed:
        pay_ceil = row["validation_payment_positives"] / max(row["payment_k"], 1)
        shop_ceil = row["validation_shop_positives"] / max(row["shop_k"], 1)
        ceilings.append(
            f"seed {row['seed']}: payment precision@k ≤ {pay_ceil:.3f} "
            f"(k={row['payment_k']}, positives={row['validation_payment_positives']}, "
            f"N={row['validation_payments']}); shop precision@k ≤ {shop_ceil:.3f} "
            f"(k={row['shop_k']}, positives={row['validation_shop_positives']}, "
            f"N={row['validation_shops']})"
        )
    lines.append(
        "Precision at analyst capacity cannot exceed positives/k. "
        "When that ceiling is near the positive rate, most models tie and the metric stops "
        "separating them. PR-AUC, F1 and misuse taka caught still separate them. "
        + "; ".join(ceilings)
        + "."
    )
    thin = [row for row in per_seed if row["validation_payment_positives"] < 15]
    if thin:
        lines.append(
            "A seed with very few misuse payments widens the std: "
            + ", ".join(
                f"seed {row['seed']}: {row['validation_payment_positives']} misuse payments, "
                f"{row['validation_shop_positives']} misuse shops"
                for row in thin
            )
            + "."
        )
    shop_pos = [row["validation_shop_positives"] for row in per_seed]
    if max(shop_pos) < 20:
        lines.append(
            "Shop-level metrics rest on few misuse shops ("
            + ", ".join(
                f"seed {row['seed']}: {row['validation_shop_positives']}" for row in per_seed
            )
            + "). A perfect shop F1 or PR-AUC on that count is a small sample."
        )
    capped = [
        f"seed {row['seed']}: payment k={row['payment_k']} of N={row['validation_payments']}, "
        f"shop k={row['shop_k']} of N={row['validation_shops']}"
        for row in per_seed
        if row["payment_k"] < data["analyst_capacity_payments"]
        or row["shop_k"] < data["analyst_capacity_shops"]
    ]
    if capped:
        lines.append(
            "Analyst capacity is the configured top-k, capped at the number of validation rows. "
            "When k equals N, precision at k equals the positive rate. "
            + "; ".join(capped)
            + f". Configured capacity is {data['analyst_capacity_payments']} payments and "
            f"{data['analyst_capacity_shops']} shops."
        )
    failed = [
        f"{model['name']} (seed {row['seed']}): {model['error']}"
        for row in per_seed
        for model in row["models"]
        if model["error"]
    ]
    if failed:
        lines.append("Failed fits, excluded from a claim of accuracy: " + "; ".join(failed) + ".")
    return lines


def _xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_chart(summary: pd.DataFrame, profile: str, seeds: list[int]) -> str:
    """Grouped bars of the four judge metrics. Whiskers are the sample std."""
    models = [name for name in summary.index if name in LABELS]
    width, height = 1100, 620
    margin_l, margin_r, margin_t, margin_b = 52, 16, 86, 78
    gap = 28
    panel_w = (width - margin_l - margin_r - gap) / 2
    panel_h = height - margin_t - margin_b
    bar_w, bar_gap, group_gap = 11, 3, 16
    group_w = len(CHART_METRICS) * bar_w + (len(CHART_METRICS) - 1) * bar_gap + group_gap
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#fbfaf7"/>',
        '<defs><pattern id="fprHatch" width="6" height="6" patternUnits="userSpaceOnUse">'
        '<rect width="6" height="6" fill="#b23a48"/>'
        '<path d="M0 6 L6 0" stroke="#fbfaf7" stroke-width="1.2"/>'
        "</pattern></defs>",
        "<style>text{font-family:Helvetica,Arial,sans-serif;fill:#1c1915}</style>",
        f'<text x="{width / 2}" y="28" text-anchor="middle" font-size="18" font-weight="700">'
        "Validation metrics by model</text>",
        f'<text x="{width / 2}" y="50" text-anchor="middle" font-size="12" fill="#4a453e">'
        f"{_xml(profile)} profile, mean over seeds {', '.join(str(s) for s in seeds)}. "
        "Whiskers are the sample standard deviation.</text>",
    ]
    legend_x = margin_l
    for key, label, lower_better in CHART_METRICS:
        fill = "url(#fprHatch)" if lower_better else CHART_COLOURS[key]
        parts.append(
            f'<rect x="{legend_x}" y="62" width="12" height="12" fill="{fill}" '
            'stroke="#1c1915" stroke-width="0.4"/>'
        )
        note = " (shorter is better)" if lower_better else ""
        parts.append(f'<text x="{legend_x + 16}" y="73" font-size="12">{_xml(label + note)}</text>')
        legend_x += 150 if lower_better else 110
    for panel, level, title in (
        (0, "payment", "Payment level"),
        (1, "shop", "Shop level"),
    ):
        origin_x = margin_l + panel * (panel_w + gap)
        origin_y = margin_t
        parts.append(
            f'<text x="{origin_x + panel_w / 2}" y="{origin_y + 16}" text-anchor="middle" '
            f'font-size="14" font-weight="700">{title}</text>'
        )
        plot_top = origin_y + 28
        plot_h = panel_h - 36
        axis_y = plot_top + plot_h
        parts.append(
            f'<line x1="{origin_x}" y1="{axis_y}" x2="{origin_x + panel_w - 8}" y2="{axis_y}" '
            'stroke="#1c1915" stroke-width="1"/>'
        )
        for tick in (0, 0.5, 1):
            y = axis_y - tick * plot_h
            parts.append(
                f'<line x1="{origin_x}" y1="{y}" x2="{origin_x + panel_w - 8}" y2="{y}" '
                'stroke="#e4dfd6" stroke-width="1"/>'
            )
            parts.append(
                f'<text x="{origin_x - 8}" y="{y + 4}" text-anchor="end" '
                f'font-size="11">{tick:.1f}</text>'
            )
        for i, model in enumerate(models):
            gx = origin_x + 8 + i * group_w
            for j, (key, _label, _lower) in enumerate(CHART_METRICS):
                mean = float(summary.loc[model, f"{level}_{key}_mean"])
                std = float(summary.loc[model, f"{level}_{key}_std"])
                if np.isnan(mean):
                    continue
                shown = min(max(mean, 0.0), 1.0)
                bh = shown * plot_h
                x = gx + j * (bar_w + bar_gap)
                y = axis_y - bh
                fill = "url(#fprHatch)" if key == "false_positive_rate" else CHART_COLOURS[key]
                parts.append(
                    f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w}" height="{bh:.1f}" '
                    f'fill="{fill}"/>'
                )
                if not np.isnan(std):
                    lo = min(max(mean - std, 0.0), 1.0)
                    hi = min(max(mean + std, 0.0), 1.0)
                    y_lo = axis_y - lo * plot_h
                    y_hi = axis_y - hi * plot_h
                    cx = x + bar_w / 2
                    parts.append(
                        f'<line x1="{cx:.1f}" y1="{y_hi:.1f}" x2="{cx:.1f}" y2="{y_lo:.1f}" '
                        'stroke="#1c1915" stroke-width="1"/>'
                    )
            label_x = gx + (len(CHART_METRICS) * (bar_w + bar_gap) - bar_gap) / 2
            parts.append(
                f'<text x="{label_x:.1f}" y="{axis_y + 18}" text-anchor="end" font-size="11" '
                f'transform="rotate(-35 {label_x:.1f} {axis_y + 18})">{_xml(LABELS[model])}</text>'
            )
    parts.append(
        f'<text x="{width / 2}" y="{height - 16}" text-anchor="middle" font-size="11" '
        'fill="#4a453e">'
        "Synthetic data only. Hatched bars are the false-positive rate; taller is worse."
        "</text></svg>"
    )
    return "\n".join(parts)


def _level_table(summary: pd.DataFrame, level: str) -> pd.DataFrame:
    rows = []
    for model in summary.index:
        row = {"Model": LABELS.get(model, model)}
        for metric, label in (
            ("precision", "Precision"),
            ("recall", "Recall"),
            ("f1", "F1"),
            ("false_positive_rate", "FPR"),
            ("pr_auc", "PR-AUC"),
            ("precision_at_k", "Precision@k"),
            ("value_recall", "Misuse taka caught"),
        ):
            row[label] = _metric_cell(summary, model, level, metric)
        rows.append(row)
    return pd.DataFrame(rows)


def _time_table(summary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for model in summary.index:
        rows.append(
            {
                "Model": LABELS.get(model, model),
                "Train s": _stat(summary, model, "train_seconds"),
                "Inference s": _stat(summary, model, "inference_seconds"),
                "Threshold": _stat(summary, model, "threshold"),
                "N payments (positives)": (
                    f"{_count(summary.loc[model, 'payment_n_mean'])} "
                    f"({_count(summary.loc[model, 'payment_positives_mean'])})"
                ),
                "N shops (positives)": (
                    f"{_count(summary.loc[model, 'shop_n_mean'])} "
                    f"({_count(summary.loc[model, 'shop_positives_mean'])})"
                ),
            }
        )
    return pd.DataFrame(rows)


def _bootstrap_table(per_seed: list[dict], level: str) -> pd.DataFrame:
    rows = []
    for name in LABELS:
        for metric in CI_METRICS:
            row = {"Model": LABELS[name], "Metric": metric}
            present = False
            for seed_result in per_seed:
                model = next(item for item in seed_result["models"] if item["name"] == name)
                point = model[level].get(metric, float("nan"))
                bounds = model["bootstrap_95ci"][level].get(metric)
                n = model[level]["n"]
                pos = model[level]["positives"]
                header = f"seed {seed_result['seed']} (N={int(n)}, pos={int(pos)})"
                if bounds:
                    present = True
                    row[header] = f"{_num(point)} [{_num(bounds[0])}, {_num(bounds[1])}]"
                else:
                    row[header] = "n/a"
            if present:
                rows.append(row)
    return pd.DataFrame(rows)


def _seed_pr_table(per_seed: list[dict]) -> pd.DataFrame:
    rows = []
    for name in LABELS:
        row = {"Model": LABELS[name]}
        for seed_result in per_seed:
            model = next(item for item in seed_result["models"] if item["name"] == name)
            n = int(model["payment"]["n"])
            pos = int(model["payment"]["positives"])
            value = model["payment"]["pr_auc"]
            text = (
                "n/a"
                if value is None or (isinstance(value, float) and np.isnan(value))
                else f"{value:.3f}"
            )
            row[f"seed {seed_result['seed']} (N={n}, pos={pos})"] = text
        rows.append(row)
    return pd.DataFrame(rows)


def _shown(frame: pd.DataFrame) -> str:
    """Markdown table without the default RangeIndex column."""
    if "Model" in frame.columns:
        frame = frame.set_index("Model")
    return md_table(frame)


def render(result: dict, summary: pd.DataFrame) -> str:
    seeds = result["seeds"]
    profile = result["profile"]
    data = result["per_seed"][0]["dataset"]
    sizes = "; ".join(
        f"seed {row['seed']}: {row['validation_payments']:,} payments "
        f"({row['validation_payment_positives']:,} misuse), "
        f"{row['validation_shops']:,} shops ({row['validation_shop_positives']:,} misuse)"
        for row in result["per_seed"]
    )
    protocol = (
        f"Generated by `python -m jachai.eval.model_comparison` with profile `{profile}`. "
        "Synthetic data only. Every metric is on the validation shop-and-time split, against "
        "the hidden true label, as mean ± sample standard deviation (n−1) over seeds "
        f"{', '.join(str(s) for s in seeds)}. Counts (N, positives) sit in the same cell as "
        f"every metric. Validation size: {sizes}. Configured analyst capacity is "
        f"{data['analyst_capacity_payments']} payments and {data['analyst_capacity_shops']} shops; "
        "precision@k uses min(capacity, N). The test split is not scored "
        f"(test_set_touched={str(result['test_set_touched']).lower()}). "
        f"Compute time: {result['compute_seconds']:.1f}s."
    )
    sections = [
        "# Model comparison (validation)",
        protocol,
        "## Model we keep",
        result["decision"],
        "## Feature selection",
        result["feature_selection"],
        "## Payment level",
        "Same features, same split, threshold fit on validation targets only. "
        "Misuse taka caught is the share of truly misuse payment amount that was flagged.",
        _shown(_level_table(summary, "payment")),
        "## Shop level",
        "Shop score is the maximum payment score in the validation window. A shop is flagged "
        "when any of its validation payments is flagged. Misuse taka caught is the share of "
        "validation misuse taka sitting at flagged shops. N is validation shops that have a "
        "validation payment.",
        _shown(_level_table(summary, "shop")),
        "## Chart",
        "![Validation precision, recall, F1 and false-positive rate](model_comparison.svg)",
        "## Train time, inference time and threshold",
        "Rules have no fitted parameters, so their train time is 0. The graph rule's train time "
        "is the point-in-time shared-payer count. LightGBM's train time includes isotonic "
        "calibration. Thresholds are the validation-target F1 cut, except rules, which keep the "
        f"configured vote threshold ({data.get('rules_threshold', 'see JSON')}).",
        _shown(_time_table(summary)),
        "## Bootstrap 95% CI by shop",
        f"Percentile interval from {result['n_bootstrap']} resamples. Payment rows are redrawn "
        "by shop. Shop rows are redrawn directly. The cell is the seed's point estimate and its "
        "interval, with that seed's N and positives in the column header.",
        "### Payment",
        _shown(_bootstrap_table(result["per_seed"], "payment")),
        "### Shop",
        _shown(_bootstrap_table(result["per_seed"], "shop")),
        "## Payment PR-AUC per seed",
        _shown(_seed_pr_table(result["per_seed"])),
        "## Caveats",
        "\n".join(f"- {line}" for line in result["caveats"]),
        "## Reproduce",
        "```bash\nJACHAI_PROFILE=fast python -m jachai.eval.model_comparison\n```",
        "The reference world is a long job and is refused unless `--allow-long` is passed. "
        "This command does not write the test metrics and does not edit reports/summary.md, "
        "reports/validation_evaluation.md or reports/final_test.md.",
    ]
    return "\n\n".join(sections) + "\n"


def _jsonable(value):
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return None if np.isnan(number) else number
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def run(seeds: list[int], n_boot: int, jobs: int) -> tuple[dict, pd.DataFrame]:
    t0 = time.perf_counter()
    if jobs > 1 and len(seeds) > 1:
        import multiprocessing as mp

        ctx = mp.get_context("spawn")
        with ctx.Pool(min(jobs, len(seeds))) as pool:
            per_seed = pool.starmap(run_seed, [(seed, n_boot) for seed in seeds])
    else:
        per_seed = [run_seed(seed, n_boot) for seed in seeds]
    summary = summarise(per_seed)
    profile = os.environ.get("JACHAI_PROFILE", "").strip() or "reference"
    # The configured rule threshold is identical across seeds; surface it for the markdown.
    from jachai.labels.config import load_rules

    per_seed[0]["dataset"]["rules_threshold"] = float(load_rules().aggregator.threshold)
    result = {
        "profile": profile,
        "synthetic_data_only": True,
        "evaluated_on": "validation shops and dates, against the hidden true label",
        "test_set_touched": False,
        "test_metrics_computed": False,
        "threshold_rule": (
            "max F1 against validation targets from rules and past cases; "
            "rules-only keeps its configured vote threshold"
        ),
        "seeds": list(seeds),
        "n_bootstrap": n_boot,
        "bootstrap": "percentile 95% CI, shops drawn with replacement, 2.5 and 97.5 percentiles",
        "std": "sample standard deviation across seeds, divisor n-1",
        "features": per_seed[0]["features"],
        "feature_selection": feature_paragraph(per_seed[0]["features"]),
        "hyperparameters": {
            "logistic_regression": {"C": 1.0, "max_iter": 400, "solver": "lbfgs"},
            "random_forest": {
                "n_estimators": 80,
                "max_depth": 10,
                "min_samples_leaf": 15,
                "max_features": "sqrt",
            },
            "xgboost": {
                "max_depth": 4,
                "eta": 0.08,
                "num_boost_round": 80,
                "early_stopping_rounds": 10,
                "subsample": 0.8,
                "colsample_bytree": 0.8,
            },
            "lightgbm": per_seed[0]["lightgbm_params"],
            "isolation_forest": {"n_estimators": 100, "max_samples": 512, "contamination": "auto"},
            "autoencoder": {
                "hidden": AE_HIDDEN,
                "max_iter": AE_MAX_ITER,
                "time_limit_seconds": AE_TIME_LIMIT_S,
                "score": "mean squared reconstruction error",
            },
            "target_mode": per_seed[0]["target_mode"],
            "note": (
                "Fixed in this script or in configs/models.yaml. "
                "The hidden truth was not used to search them."
            ),
        },
        "preprocessing": {
            "lightgbm": "raw columns, missing values left missing, then isotonic calibration",
            "random_forest_xgboost": "train-median impute",
            "logistic_isolation_autoencoder": (
                "train-median impute, then standard scaler fit on train"
            ),
            "rules_only": "configured labeling functions",
            "graph_shared_payers": "point-in-time shared-payer count, test shops excluded",
        },
        "per_seed": per_seed,
        "compute_seconds": time.perf_counter() - t0,
        "provenance": provenance(),
    }
    result["decision"] = decision_paragraph(summary, per_seed)
    result["caveats"] = caveats(per_seed, profile)
    result["kept_model"] = _kept_name(summary)
    return result, summary


def _kept_name(summary: pd.DataFrame) -> str:
    """Same keep rule as the decision paragraph, as a model id for the JSON."""
    available = [
        name
        for name in CANDIDATES
        if name in summary.index and not np.isnan(_mean(summary, name, "payment_pr_auc_mean"))
    ]
    if not available:
        return ""
    best = max(available, key=lambda name: _mean(summary, name, "payment_pr_auc_mean"))
    if OURS not in available:
        return best
    gap = _mean(summary, best, "payment_pr_auc_mean") - _mean(summary, OURS, "payment_pr_auc_mean")
    spread = abs(_mean(summary, best, "payment_pr_auc_std")) + abs(
        _mean(summary, OURS, "payment_pr_auc_std")
    )
    if np.isnan(spread):
        spread = 0.0
    if best == OURS or abs(gap) <= spread:
        return OURS
    best_time = _mean(summary, best, "train_seconds_mean")
    ours_time = _mean(summary, OURS, "train_seconds_mean")
    explainable = best in {"random_forest", "xgboost", "logistic_regression", "lightgbm"}
    if explainable and best_time <= max(60.0, 2.0 * ours_time):
        return best
    return OURS


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, nargs="*", default=list(COMPARISON_SEEDS))
    parser.add_argument("--bootstraps", type=int, default=N_BOOT)
    parser.add_argument("--jobs", type=int, default=min(3, os.cpu_count() or 1))
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument(
        "--allow-long",
        action="store_true",
        help="permit a run when JACHAI_PROFILE is not fast",
    )
    parser.add_argument(
        "--justify",
        action="store_true",
        help="write feature_justification.* instead of model_comparison.*",
    )
    args = parser.parse_args(argv)
    if args.justify:
        from jachai.eval.feature_justification import main as justify_main

        forwarded = ["--seeds", *[str(s) for s in args.seeds], "--out", str(args.out)]
        if args.allow_long:
            forwarded.append("--allow-long")
        justify_main(forwarded)
        return
    profile = os.environ.get("JACHAI_PROFILE", "").strip() or "reference"
    if profile != "fast" and not args.allow_long:
        raise SystemExit(
            "Refusing a long run. Use JACHAI_PROFILE=fast, or pass --allow-long for the "
            "reference world."
        )
    result, summary = run(args.seeds, args.bootstraps, args.jobs)
    # kept_model was computed twice if decision_paragraph also chooses. Recompute with seeds.
    result["kept_model"] = _kept_name(summary)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    chart = render_chart(summary, result["profile"], result["seeds"])
    (out / "model_comparison.svg").write_text(chart, encoding="utf-8")
    text = render(result, summary)
    (out / "model_comparison.md").write_text(text, encoding="utf-8")
    (out / "model_comparison.json").write_text(
        json.dumps(_jsonable(result), indent=2) + "\n", encoding="utf-8"
    )
    print(text)
    print(f"Wrote {out / 'model_comparison.md'}")


if __name__ == "__main__":
    main()
