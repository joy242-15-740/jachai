"""Load configs/models.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field

from jachai.world.config import DEFAULT_CONFIG_DIR, _read_yaml, _Strict


class LightGBMParams(_Strict):
    objective: Literal["binary", "cross_entropy"]
    learning_rate: float = Field(gt=0)
    num_leaves: int = Field(gt=1)
    min_child_samples: int = Field(gt=0)
    feature_fraction: float = Field(gt=0, le=1)
    bagging_fraction: float = Field(gt=0, le=1)
    bagging_freq: int = Field(ge=0)
    lambda_l2: float = Field(ge=0)
    num_boost_round: int = Field(gt=0)
    early_stopping_rounds: int = Field(gt=0)


class PaymentModelConfig(_Strict):
    lightgbm: LightGBMParams
    threshold_metric: Literal["f1"]


class TurnoverConfig(_Strict):
    inputs: list[str] = Field(min_length=1)
    loss: Literal["absolute_error", "squared_error"]
    max_iter: int = Field(gt=0)
    learning_rate: float = Field(gt=0)


class IsolationForestConfig(_Strict):
    peer_group: list[str] = Field(min_length=1)
    min_peer_shops: int = Field(gt=0)
    features: list[str] = Field(min_length=1)
    log_features: list[str]
    snapshot_every_days: int = Field(gt=0)
    n_estimators: int = Field(gt=0)


class ShopModelConfig(_Strict):
    turnover: TurnoverConfig
    isolation_forest: IsolationForestConfig


class NetworkConfig(_Strict):
    window_days: int = Field(gt=0)
    snapshot_every_days: int = Field(gt=0)
    link_min_day_total_share: float = Field(gt=0)
    link_min_shops_same_day: int = Field(gt=1)
    min_shared_payers: int = Field(gt=0)
    max_shops_per_payer: int = Field(gt=1)


class ModelsConfig(_Strict):
    payment_model: PaymentModelConfig
    shop_model: ShopModelConfig
    network: NetworkConfig


def load_models_config(path: Path | None = None) -> ModelsConfig:
    return ModelsConfig.model_validate(_read_yaml(path or DEFAULT_CONFIG_DIR / "models.yaml"))
