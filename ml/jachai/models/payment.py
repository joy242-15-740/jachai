"""Payment risk model: LightGBM on soft targets, isotonic calibration.

Training uses only observable things: point-in-time features and the soft
targets from jachai.labels.targets (rules' votes and/or past cases).
  1. train      LightGBM (cross-entropy on soft targets, weighted by evidence)
                on train rows with evidence; early stopping on validation
  2. calibrate  isotonic regression on validation: raw score -> target scale
  3. freeze     the flag threshold on validation (max F1 vs validation targets)
The hidden truth is never used here; it is only used once, on test.

Note: calibration is against the training evidence, not the truth. A "0.8"
means "our evidence would call this misuse 80% of the time", not an 80% chance
of real misuse. The test report shows how it lines up with the truth.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from jachai.features import feature_columns
from jachai.labels.targets import Targets
from jachai.models.config import PaymentModelConfig

MODEL_FILE, CALIBRATOR_FILE, META_FILE = (
    "payment_model.txt",
    "payment_calibrator.joblib",
    "payment_model.json",
)


@dataclass
class PaymentModel:
    booster: lgb.Booster
    calibrator: IsotonicRegression
    features: list[str]
    threshold: float
    meta: dict = field(default_factory=dict)

    def raw_score(self, df: pd.DataFrame) -> np.ndarray:
        return self.booster.predict(df[self.features], num_iteration=self.booster.best_iteration)

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        return self.calibrator.predict(self.raw_score(df))

    def flag(self, df: pd.DataFrame) -> np.ndarray:
        return self.predict_proba(df) >= self.threshold

    def save(self, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        self.booster.save_model(out_dir / MODEL_FILE)
        joblib.dump(self.calibrator, out_dir / CALIBRATOR_FILE)
        meta = {**self.meta, "features": self.features, "threshold": self.threshold}
        (out_dir / META_FILE).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, out_dir: Path) -> PaymentModel:
        meta = json.loads((out_dir / META_FILE).read_text(encoding="utf-8"))
        return cls(
            booster=lgb.Booster(model_file=str(out_dir / MODEL_FILE)),
            calibrator=joblib.load(out_dir / CALIBRATOR_FILE),
            features=meta.pop("features"),
            threshold=meta.pop("threshold"),
            meta=meta,
        )

    def fingerprint(self) -> str:
        """Hash of the trained model, used to log which model touched the test set."""
        text = (
            self.booster.model_to_string()
            + repr(self.calibrator.X_thresholds_)
            + str(self.threshold)
        )
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def best_f1_threshold(y: np.ndarray, p: np.ndarray) -> float:
    """Probability cut-off with the highest F1 against labels `y`."""
    order = np.argsort(-p, kind="stable")
    p_sorted, y_sorted = p[order], y[order]
    tp = np.cumsum(y_sorted)
    flagged = np.arange(1, len(y) + 1)
    f1 = 2 * tp / (flagged + y.sum())
    # Only cut where the probability changes, so ties are flagged together.
    distinct = np.r_[p_sorted[1:] != p_sorted[:-1], True]
    best = np.argmax(np.where(distinct, f1, -1))
    return float(p_sorted[best])


def train_payment_model(
    payments: pd.DataFrame,
    split: pd.Series,
    targets: Targets,
    cfg: PaymentModelConfig,
    seed: int,
) -> PaymentModel:
    """`split` and `targets` are aligned with `payments` rows."""
    features = feature_columns(payments)
    tr = (split.to_numpy() == "train") & targets.usable
    va = (split.to_numpy() == "validation") & targets.usable
    y, w, hard = targets.soft, targets.weight, targets.hard
    if hard[tr].min() == hard[tr].max() or hard[va].min() == hard[va].max():
        raise ValueError("training or validation targets are all one class")

    p = cfg.lightgbm
    params = {
        "objective": p.objective,
        "learning_rate": p.learning_rate,
        "num_leaves": p.num_leaves,
        "min_child_samples": p.min_child_samples,
        "feature_fraction": p.feature_fraction,
        "bagging_fraction": p.bagging_fraction,
        "bagging_freq": p.bagging_freq,
        "lambda_l2": p.lambda_l2,
        "seed": seed,
        "deterministic": True,
        "num_threads": 1,  # same result on every machine
        "verbosity": -1,
    }
    train_set = lgb.Dataset(payments.loc[tr, features], y[tr], weight=w[tr])
    val_set = lgb.Dataset(payments.loc[va, features], y[va], weight=w[va], reference=train_set)
    booster = lgb.train(
        params,
        train_set,
        num_boost_round=p.num_boost_round,
        valid_sets=[val_set],
        callbacks=[lgb.early_stopping(p.early_stopping_rounds, verbose=False)],
    )

    raw_val = booster.predict(payments.loc[va, features], num_iteration=booster.best_iteration)
    calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    calibrator.fit(raw_val, y[va], sample_weight=w[va])
    threshold = best_f1_threshold(hard[va], calibrator.predict(raw_val))

    meta = {
        "trained_on": "soft targets from rules and/or past cases; hidden truth not used",
        "train_rows": int(tr.sum()),
        "validation_rows": int(va.sum()),
        "train_mean_target": float(np.average(y[tr], weights=w[tr])),
        "best_iteration": int(booster.best_iteration),
        "threshold_rule": "max F1 vs validation targets",
        "seed": seed,
    }
    return PaymentModel(booster, calibrator, features, threshold, meta)
