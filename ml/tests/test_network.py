"""Network score: point in time, deterministic, finds limit-bypass rings."""

import pandas as pd
import pytest

from jachai.features.config import load_thresholds
from jachai.labels.config import load_rules
from jachai.models.config import load_models_config
from jachai.models.network import build_network_features, shop_links
from jachai.world.world import EVENT_TABLES, TRUE_PATTERN


def build(world, tables=None):
    cfg, mc = world.config, load_models_config()
    # Small world: weekly snapshots, 14-day window so there are several snapshots.
    net_cfg = mc.network.model_copy(update={"window_days": 14})
    return build_network_features(
        tables or world.tables,
        pd.Timestamp(cfg.calendar.start),
        cfg.calendar.days,
        net_cfg,
        load_rules().ring_flag,
        load_thresholds().features.far_payer_km,
        cfg.regulation.cash_out_limit_daily,
        cfg.seed,
    )


@pytest.fixture(scope="module")
def network(pattern_world):
    return build(pattern_world)


def test_snapshots_do_not_use_the_future(pattern_world, network):
    cut = pd.Timestamp("2026-10-10 13:00")
    past_tables = {
        k: (v[v["ts"] < cut] if k in EVENT_TABLES else v) for k, v in pattern_world.tables.items()
    }
    past = build(pattern_world, past_tables)
    keep = network["snapshot"] <= cut.normalize()
    pd.testing.assert_frame_equal(
        past[past["snapshot"] <= cut.normalize()].reset_index(drop=True),
        network[keep].reset_index(drop=True),
    )


def test_deterministic(pattern_world, network):
    pd.testing.assert_frame_equal(build(pattern_world), network)


def test_ring_flag_finds_limit_bypass_shops(pattern_world, network):
    # A ring is only active on some days, so ask: flagged in any snapshot?
    ever = network.groupby("shop_id")["ring_flag"].max()
    pattern = pattern_world.tables["shops"].set_index("shop_id")[TRUE_PATTERN].reindex(ever.index)
    assert ever[pattern == "limit_bypass"].mean() >= 0.5
    assert ever[pattern == "normal"].mean() <= 0.1


def test_links_need_the_same_payer_on_the_same_day():
    day1, day2 = pd.Timestamp("2026-08-01"), pd.Timestamp("2026-08-02")
    pairs = pd.DataFrame(
        {
            "payer_id": ["p1", "p1", "p2", "p2", "p3", "p3"],
            "day": [day1, day1, day1, day1, day1, day2],
            "shop_id": ["A", "B", "A", "B", "A", "C"],
        }
    )
    cfg = load_models_config().network.model_copy(update={"min_shared_payers": 2})
    links = shop_links(pairs, cfg)
    assert list(map(tuple, links[["shop_id_a", "shop_id_b"]].to_numpy())) == [("A", "B")]
    assert links["shared"].tolist() == [2]  # p3 paid A and C on different days: no link
