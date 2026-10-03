"""Zones, shops, customers and agents.

Everything sits on a synthetic flat map measured in km (not real geography).
A zone is a neighbourhood: a Dhaka ward, a district town, or a rural haat area.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from jachai.world.config import AREA_TYPES, WorldConfig
from jachai.world.ids import random_ids
from jachai.world.rng import stream
from jachai.world.world import HIDDEN_PREFIX, NORMAL, TRUE_LABEL, TRUE_PATTERN

ZONE_PREFIX = {"dhaka_urban": "DU", "district_town": "DT", "rural_haat": "RH"}
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
JITTER_KM = {"shops": 1.0, "customers": 2.0, "agents": 1.0}


def make_zones(cfg: WorldConfig) -> pd.DataFrame:
    rng = stream(cfg.seed, "zones")
    m = cfg.map
    cx, cy = m.dhaka_center_km
    rows = []

    n = cfg.areas["dhaka_urban"].n_zones
    r = m.dhaka_radius_km * np.sqrt(rng.random(n))  # uniform over a disc
    a = rng.uniform(0, 2 * np.pi, n)
    rows.append(("dhaka_urban", cx + r * np.cos(a), cy + r * np.sin(a)))

    n = cfg.areas["district_town"].n_zones
    margin = m.size_km * 0.05
    towns = rng.uniform(margin, m.size_km - margin, size=(n, 2))
    rows.append(("district_town", towns[:, 0], towns[:, 1]))

    # Rural haat zones sit near a randomly chosen district town.
    n = cfg.areas["rural_haat"].n_zones
    home = towns[rng.integers(0, len(towns), n)]
    r = m.rural_spread_km * np.sqrt(rng.random(n))
    a = rng.uniform(0, 2 * np.pi, n)
    rx = np.clip(home[:, 0] + r * np.cos(a), 0, m.size_km)
    ry = np.clip(home[:, 1] + r * np.sin(a), 0, m.size_km)
    rows.append(("rural_haat", rx, ry))

    frames = []
    for area, xs, ys in rows:
        k = len(xs)
        n_haat = cfg.areas[area].haat_days_per_week
        haat = [
            "|".join(WEEKDAYS[d] for d in sorted(rng.choice(7, n_haat, replace=False)))
            if n_haat
            else ""
            for _ in range(k)
        ]
        frames.append(
            pd.DataFrame(
                {
                    "zone_id": [f"{ZONE_PREFIX[area]}{i + 1:02d}" for i in range(k)],
                    "area_type": area,
                    "x_km": xs.round(2),
                    "y_km": ys.round(2),
                    "haat_days": haat,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def _place_in_zones(
    rng: np.random.Generator, zones: pd.DataFrame, areas: np.ndarray, jitter_km: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pick a random zone of each row's area type; return zone ids and jittered x, y."""
    zone_idx = np.empty(len(areas), dtype=np.int64)
    for area in AREA_TYPES:
        mask = areas == area
        candidates = np.flatnonzero(zones["area_type"].to_numpy() == area)
        zone_idx[mask] = rng.choice(candidates, size=int(mask.sum()))
    x = zones["x_km"].to_numpy()[zone_idx] + rng.normal(0, jitter_km, len(areas))
    y = zones["y_km"].to_numpy()[zone_idx] + rng.normal(0, jitter_km, len(areas))
    return zones["zone_id"].to_numpy()[zone_idx], x.round(2), y.round(2)


def _choice_by_share(rng: np.random.Generator, shares: dict[str, float], n: int) -> np.ndarray:
    keys = list(shares)
    return np.array(keys, dtype=object)[rng.choice(len(keys), size=n, p=list(shares.values()))]


def make_customers(cfg: WorldConfig, zones: pd.DataFrame) -> pd.DataFrame:
    rng = stream(cfg.seed, "customers")
    n = cfg.population.n_customers
    areas = _choice_by_share(rng, {k: a.customer_share for k, a in cfg.areas.items()}, n)
    zone_id, x, y = _place_in_zones(rng, zones, areas, JITTER_KM["customers"])
    receiver = rng.random(n) < cfg.remittances.receiver_share
    return pd.DataFrame(
        {
            "customer_id": random_ids(rng, n, "CU"),
            "zone_id": zone_id,
            "area_type": areas,
            "x_km": x,
            "y_km": y,
            f"{HIDDEN_PREFIX}segment": np.where(receiver, "remittance_receiver", "regular"),
        }
    )


def make_agents(cfg: WorldConfig, zones: pd.DataFrame, customers: pd.DataFrame) -> pd.DataFrame:
    """One agent per zone, the rest spread in proportion to where customers live."""
    rng = stream(cfg.seed, "agents")
    n = cfg.population.n_agents
    if n < len(zones):
        raise ValueError(f"need at least one agent per zone ({len(zones)}), got {n}")
    per_zone = customers["zone_id"].value_counts().reindex(zones["zone_id"], fill_value=0)
    p = per_zone.to_numpy() / per_zone.sum()
    extra = rng.choice(len(zones), size=n - len(zones), p=p)
    zone_idx = np.concatenate([np.arange(len(zones)), extra])
    jit = JITTER_KM["agents"]
    return pd.DataFrame(
        {
            "agent_id": random_ids(rng, n, "AG"),
            "zone_id": zones["zone_id"].to_numpy()[zone_idx],
            "area_type": zones["area_type"].to_numpy()[zone_idx],
            "x_km": (zones["x_km"].to_numpy()[zone_idx] + rng.normal(0, jit, n)).round(2),
            "y_km": (zones["y_km"].to_numpy()[zone_idx] + rng.normal(0, jit, n)).round(2),
        }
    )


def make_shops(cfg: WorldConfig, zones: pd.DataFrame) -> pd.DataFrame:
    rng = stream(cfg.seed, "shops")
    n = cfg.population.n_shops
    areas = _choice_by_share(rng, {k: a.shop_share for k, a in cfg.areas.items()}, n)
    zone_id, x, y = _place_in_zones(rng, zones, areas, JITTER_KM["shops"])
    lo, hi = cfg.qr.codes_per_shop
    return pd.DataFrame(
        {
            "shop_id": random_ids(rng, n, "SH"),
            "category": _choice_by_share(
                rng, {k: c.shop_share for k, c in cfg.categories.items()}, n
            ),
            "size_tier": _choice_by_share(rng, {k: t.share for k, t in cfg.size_tiers.items()}, n),
            "zone_id": zone_id,
            "area_type": areas,
            "x_km": x,
            "y_km": y,
            "opened_on": pd.Timestamp(cfg.calendar.start),
            "n_qr_codes": rng.integers(lo, hi + 1, size=n),
            # The owner's personal wallet, linked to the shop through merchant KYC.
            "owner_wallet_id": random_ids(rng, n, "WL"),
            TRUE_LABEL: np.zeros(n, dtype=np.int8),
            TRUE_PATTERN: NORMAL,
        }
    )


def regular_pools(
    cfg: WorldConfig, shops: pd.DataFrame, customers: pd.DataFrame
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Each shop's pool of regular customers, drawn from its own zone.

    Returns (pool, start, size): shop i's regulars are pool[start[i] : start[i] + size[i]],
    as row positions in `customers`.
    """
    rng = stream(cfg.seed, "regulars")
    by_zone = customers.groupby("zone_id").indices  # zone -> row positions
    pools, sizes = [], []
    for zone, tier in zip(shops["zone_id"], shops["size_tier"], strict=True):
        local = by_zone.get(zone, np.arange(len(customers)))
        lo, hi = cfg.size_tiers[tier].regulars
        k = min(int(rng.integers(lo, hi + 1)), len(local))
        pools.append(rng.choice(local, size=k, replace=False))
        sizes.append(k)
    size = np.array(sizes, dtype=np.int64)
    start = np.concatenate([[0], np.cumsum(size)[:-1]])
    return np.concatenate(pools), start, size
