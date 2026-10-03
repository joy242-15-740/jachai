"""Training pipeline shared by `make train` and the tests."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from jachai.eval import metrics as m
from jachai.eval.splits import assign_split
from jachai.features import build_features
from jachai.features.config import ThresholdsConfig
from jachai.labels import weak_label_table
from jachai.labels.config import RulesConfig
from jachai.models.config import ModelsConfig
from jachai.models.payment import PaymentModel, train_payment_model
from jachai.world.config import WorldConfig


@dataclass
class PaymentData:
    payments: pd.DataFrame  # features
    split: pd.Series
    weak_label: np.ndarray


def prepare_payment_data(
    tables: dict[str, pd.DataFrame],
    cfg: WorldConfig,
    thr: ThresholdsConfig,
    rules: RulesConfig,
) -> PaymentData:
    payments = build_features(tables, cfg, thr.features)["payments"]
    split = assign_split(payments, tables, cfg, thr)
    weak = weak_label_table(payments, "payment", rules, cfg)["weak_label"].to_numpy()
    return PaymentData(payments, split, weak)


def train_from_data(data: PaymentData, models: ModelsConfig, seed: int) -> PaymentModel:
    return train_payment_model(
        data.payments, data.split, data.weak_label, models.payment_model, seed
    )


def validation_report(model: PaymentModel, data: PaymentData) -> dict:
    """How the model does on validation against *weak labels* (no truth)."""
    va = (data.split.to_numpy() == "validation") & (data.weak_label != -1)
    y = data.weak_label[va]
    p = model.predict_proba(data.payments[va])
    flag = p >= model.threshold
    return {
        "against": "validation weak labels (hidden truth not used)",
        "rows": int(va.sum()),
        "pr_auc": m.pr_auc(y, p),
        "precision": m.precision(y, flag),
        "recall": m.recall(y, flag),
        "threshold": model.threshold,
    }
