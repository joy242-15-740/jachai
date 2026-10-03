"""Load configs/thresholds.yaml."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

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


class LeakageThresholds(_Strict):
    max_single_feature_auc: float = Field(gt=0.5, le=1)


class ThresholdsConfig(_Strict):
    features: FeatureThresholds
    leakage: LeakageThresholds


def load_thresholds(path: Path | None = None) -> ThresholdsConfig:
    return ThresholdsConfig.model_validate(
        _read_yaml(path or DEFAULT_CONFIG_DIR / "thresholds.yaml")
    )
