"""Small, fast settings shared by the ML and backend test suites.

Not used in production code. A 200-shop, 30-day world (22 Sep - 21 Oct) that still
spans the 1 Oct regime change, the P2P what-if start and the festival, plus the
matching shortened split dates and model settings.
"""

from __future__ import annotations

import pandas as pd

from jachai.features.config import ThresholdsConfig, load_thresholds
from jachai.models.config import ModelsConfig, load_models_config
from jachai.world.config import WorldConfig, load_world_config


def small_world_config(**overrides) -> WorldConfig:
    data = load_world_config().model_dump()
    data["population"] = {"n_shops": 200, "n_customers": 2000, "n_agents": 40}
    data["calendar"]["start"] = "2026-09-22"
    data["calendar"]["days"] = 30
    data["scenario"]["p2p_qr_start"] = "2026-10-05"
    for area, n in {"dhaka_urban": 3, "district_town": 4, "rural_haat": 6}.items():
        data["areas"][area]["n_zones"] = n
    # "seed=1" sets a top-level key; "scenario__p2p_qr_enabled=True" sets a nested one.
    for key, value in overrides.items():
        *path, last = key.split("__")
        target = data
        for part in path:
            target = target[part]
        target[last] = value
    return WorldConfig.model_validate(data)


def small_thresholds() -> ThresholdsConfig:
    thr = load_thresholds()
    split = thr.split.model_copy(
        update={
            "train_end": pd.Timestamp("2026-10-08").date(),
            "validation_end": pd.Timestamp("2026-10-14").date(),
        }
    )
    return thr.model_copy(
        update={"split": split, "eval": thr.eval.model_copy(update={"warmup_days": 5})}
    )


def small_models() -> ModelsConfig:
    models = load_models_config()
    lgbm = models.payment_model.lightgbm.model_copy(update={"num_boost_round": 60})
    forest = models.shop_model.isolation_forest.model_copy(
        update={"min_peer_shops": 5, "n_estimators": 50}
    )
    return models.model_copy(
        update={
            "payment_model": models.payment_model.model_copy(update={"lightgbm": lgbm}),
            "shop_model": models.shop_model.model_copy(update={"isolation_forest": forest}),
            "network": models.network.model_copy(update={"window_days": 14}),
        }
    )
