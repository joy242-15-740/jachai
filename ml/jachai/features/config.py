"""Load configs/thresholds.yaml."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from pydantic import Field, model_validator

from jachai.world.config import DEFAULT_CONFIG_DIR, _read_yaml, _Strict


class FeatureThresholds(_Strict):
    round_units: list[int] = Field(min_length=1)
    near_limit_share: float = Field(gt=0, le=1)
    just_under_cap_band: float = Field(gt=0)
    inflow_window_minutes: int = Field(gt=0)
    remittance_window_hours: int = Field(gt=0)
    category_median_lookback_days: int = Field(gt=0)
    short_window_days: int = Field(gt=0)
    long_window_days: int = Field(gt=0)
    far_payer_km: float = Field(gt=0)


class EvalThresholds(_Strict):
    warmup_days: int = Field(ge=0)
    analyst_capacity_shops: int = Field(gt=0)
    analyst_capacity_payments: int = Field(gt=0)
    ablation_seeds: list[int] = Field(min_length=1)


class SplitThresholds(_Strict):
    shop_shares: dict[str, float]
    train_end: dt.date
    validation_end: dt.date
    holdout_pattern: str | None = None

    @model_validator(mode="after")
    def _check(self) -> SplitThresholds:
        if set(self.shop_shares) != {"train", "validation", "test"}:
            raise ValueError("shop_shares needs exactly train, validation, test")
        if abs(sum(self.shop_shares.values()) - 1) > 1e-6:
            raise ValueError("shop_shares must sum to 1")
        if not self.train_end < self.validation_end:
            raise ValueError("train_end must be before validation_end")
        return self


class LeakageThresholds(_Strict):
    max_single_feature_auc: float = Field(gt=0.5, le=1)


class ThresholdsConfig(_Strict):
    features: FeatureThresholds
    eval: EvalThresholds
    split: SplitThresholds
    leakage: LeakageThresholds


def load_thresholds(path: Path | None = None) -> ThresholdsConfig:
    return ThresholdsConfig.model_validate(
        _read_yaml(path or DEFAULT_CONFIG_DIR / "thresholds.yaml")
    )
