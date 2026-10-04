"""Shared fixtures: a small world that builds in well under a second."""

import pytest

from jachai.testing import small_world_config
from jachai.world.config import WorldConfig, load_patterns_config


@pytest.fixture
def small_cfg() -> WorldConfig:
    return small_world_config()


@pytest.fixture
def patterns_cfg():
    return load_patterns_config()


@pytest.fixture
def make_cfg():
    """Factory fixture: make_cfg(seed=1, scenario__p2p_qr_enabled=True)."""
    return small_world_config


@pytest.fixture(scope="session")
def pattern_world():
    """A small world with every pattern and the P2P scenario on. Built once per run;
    tests must not modify it."""
    from jachai.world.generate import generate_world

    return generate_world(small_world_config(scenario__p2p_qr_enabled=True), load_patterns_config())


@pytest.fixture(scope="session")
def small_system(pattern_world):
    """The full system trained on the small world (shortened settings). Built once."""
    import pandas as pd

    from jachai.features import build_features
    from jachai.features.config import load_thresholds
    from jachai.labels.config import load_rules
    from jachai.models.config import load_models_config
    from jachai.system import train_system

    thr = load_thresholds()
    split = thr.split.model_copy(
        update={
            "train_end": pd.Timestamp("2026-10-08").date(),
            "validation_end": pd.Timestamp("2026-10-14").date(),
        }
    )
    thr = thr.model_copy(
        update={"split": split, "eval": thr.eval.model_copy(update={"warmup_days": 5})}
    )
    models = load_models_config()
    lgbm = models.payment_model.lightgbm.model_copy(update={"num_boost_round": 60})
    forest = models.shop_model.isolation_forest.model_copy(
        update={"min_peer_shops": 5, "n_estimators": 50}
    )
    models = models.model_copy(
        update={
            "payment_model": models.payment_model.model_copy(update={"lightgbm": lgbm}),
            "shop_model": models.shop_model.model_copy(update={"isolation_forest": forest}),
            "network": models.network.model_copy(update={"window_days": 14}),
        }
    )
    sd = build_features(pattern_world.tables, pattern_world.config, thr.features)["shop_day"]
    return pattern_world, *train_system(
        pattern_world.tables, sd, pattern_world.config, thr, load_rules(), models
    )
