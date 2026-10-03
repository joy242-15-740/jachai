"""Shared fixtures: a small world that builds in well under a second."""

import pytest

from jachai.world.config import WorldConfig, load_patterns_config, load_world_config


def small_world_config(**overrides) -> WorldConfig:
    """The real world.yaml, scaled down. The window still spans the 1 Oct regime change."""
    data = load_world_config().model_dump()
    data["population"] = {"n_shops": 200, "n_customers": 2000, "n_agents": 40}
    data["calendar"]["start"] = "2026-09-16"
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
