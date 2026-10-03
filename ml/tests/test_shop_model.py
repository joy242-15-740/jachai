"""Shop score parts: turnover plausibility and peer anomaly."""

import numpy as np
import pandas as pd
import pytest

from jachai.features import build_features
from jachai.features.config import load_thresholds
from jachai.models.config import load_models_config
from jachai.models.shop import ShopModel
from jachai.world.world import TRUE_LABEL, TRUE_PATTERN

FIT_UNTIL = pd.Timestamp("2026-10-08")


@pytest.fixture(scope="module")
def shop_setup(pattern_world):
    cfg = load_models_config().shop_model
    # Small world: fewer shops per peer group, so lower the minimum.
    forest = cfg.isolation_forest.model_copy(update={"min_peer_shops": 5, "n_estimators": 50})
    cfg = cfg.model_copy(update={"isolation_forest": forest})
    sd = build_features(pattern_world.tables, pattern_world.config, load_thresholds().features)[
        "shop_day"
    ]
    train = (sd["day"] <= FIT_UNTIL).to_numpy()
    model = ShopModel(cfg, pattern_world.config.seed).fit(sd, train)
    return pattern_world, cfg, sd, train, model, model.score(sd)


def test_scores_every_shop_day(shop_setup):
    _, _, sd, _, _, scores = shop_setup
    assert len(scores) == len(sd)
    assert scores["peer_anomaly"].notna().all()


def test_honest_shops_look_normal_and_cash_desks_do_not(shop_setup):
    world, _, sd, _, _, scores = shop_setup
    pattern = sd["shop_id"].map(world.tables["shops"].set_index("shop_id")[TRUE_PATTERN])
    last = (sd["day"] == sd["day"].max()).to_numpy()
    normal = last & (pattern == "normal").to_numpy()
    desk = last & (pattern == "round_amount_cash_desk").to_numpy()
    assert abs(np.nanmedian(scores.loc[normal, "turnover_z"])) < 1.0
    assert np.nanmedian(scores.loc[desk, "turnover_z"]) > 2.0
    assert scores.loc[desk, "peer_anomaly"].median() > scores.loc[normal, "peer_anomaly"].median()


def test_fit_uses_no_labels_and_only_the_training_rows(shop_setup):
    world, cfg, sd, train, model, scores = shop_setup
    # Scrambling everything outside the training rows must not change the fitted model.
    scrambled = sd.copy()
    cols = ["turnover_7d", *cfg.isolation_forest.features]
    rng = np.random.default_rng(0)
    for c in cols:
        values = scrambled.loc[~train, c].to_numpy()
        scrambled.loc[~train, c] = rng.permutation(values)
    again = ShopModel(cfg, world.config.seed).fit(scrambled, train)
    np.testing.assert_allclose(again.score(sd)["turnover_z"], scores["turnover_z"])
    np.testing.assert_allclose(again.score(sd)["peer_anomaly"], scores["peer_anomaly"])
    assert TRUE_LABEL not in sd.columns


def test_small_peer_groups_fall_back_to_category(shop_setup):
    world, cfg, sd, train, *_ = shop_setup
    strict = cfg.model_copy(
        update={
            "isolation_forest": cfg.isolation_forest.model_copy(update={"min_peer_shops": 10_000})
        }
    )
    model = ShopModel(strict, world.config.seed).fit(sd, train)
    assert set(model.forests) == set(sd["category"].astype(str))
    assert set(model.score(sd)["peer_group"]) <= set(sd["category"].astype(str))
