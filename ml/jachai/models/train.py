"""Training pipeline shared by `make train`, the ablation and the tests."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from jachai.eval import metrics as m
from jachai.eval.splits import assign_split
from jachai.features import build_features
from jachai.features.config import ThresholdsConfig
from jachai.labels import weak_label_table
from jachai.labels.config import RulesConfig, TrainingTarget
from jachai.labels.targets import Targets, build_targets, case_verdict_for_payments
from jachai.models.config import ModelsConfig
from jachai.models.payment import PaymentModel, train_payment_model
from jachai.world.config import WorldConfig


@dataclass
class PaymentData:
    payments: pd.DataFrame  # features
    split: pd.Series
    weak_proba: np.ndarray  # NaN where every labeling function abstained
    weak_label: np.ndarray
    case_verdict: np.ndarray  # usable past-case verdict per payment, NaN if none

    def targets(self, cfg: TrainingTarget) -> Targets:
        return build_targets(self.weak_proba, self.case_verdict, cfg)


def case_cutoffs(thr: ThresholdsConfig) -> dict[str, pd.Timestamp]:
    """Train may use train-shop cases closed by train_end; validation may use
    validation-shop cases closed by validation_end; test shops' cases: never."""
    return {
        "train": pd.Timestamp(thr.split.train_end),
        "validation": pd.Timestamp(thr.split.validation_end),
    }


def prepare_payment_data(
    tables: dict[str, pd.DataFrame],
    cfg: WorldConfig,
    thr: ThresholdsConfig,
    rules: RulesConfig,
    cases: pd.DataFrame | None = None,
) -> PaymentData:
    """`cases` overrides tables["cases"] (used by the case-coverage ablation)."""
    payments = build_features(tables, cfg, thr.features)["payments"]
    split = assign_split(payments, tables, cfg, thr)
    weak = weak_label_table(payments, "payment", rules, cfg)
    cases = tables["cases"] if cases is None else cases
    verdict = case_verdict_for_payments(payments, split, cases, case_cutoffs(thr))
    return PaymentData(
        payments, split, weak["weak_proba"].to_numpy(), weak["weak_label"].to_numpy(), verdict
    )


def train_from_data(
    data: PaymentData, models: ModelsConfig, target: TrainingTarget, seed: int
) -> PaymentModel:
    model = train_payment_model(
        data.payments, data.split, data.targets(target), models.payment_model, seed
    )
    model.meta["target_mode"] = target.mode
    return model


def validation_report(model: PaymentModel, data: PaymentData, target: TrainingTarget) -> dict:
    """How the model does on validation against its own *targets* (no truth)."""
    t = data.targets(target)
    va = (data.split.to_numpy() == "validation") & t.usable
    y = t.hard[va]
    p = model.predict_proba(data.payments[va])
    flag = p >= model.threshold
    return {
        "against": "validation targets (hidden truth not used)",
        "rows": int(va.sum()),
        "pr_auc": m.pr_auc(y, p),
        "precision": m.precision(y, flag),
        "recall": m.recall(y, flag),
        "threshold": model.threshold,
    }
