"""Build the whole synthetic world and write it to disk.

Order: entities -> honest events -> pattern injectors -> label noise
-> finalize (sort by time, assign random event IDs).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from jachai.world.config import PatternsConfig, WorldConfig
from jachai.world.entities import (
    make_agents,
    make_customers,
    make_shops,
    make_zones,
    regular_pools,
)
from jachai.world.events import (
    make_add_money,
    make_p2p_transfers,
    make_qr_payments,
    make_remittances,
)
from jachai.world.ids import random_ids
from jachai.world.labels_noise import apply_label_noise
from jachai.world.patterns import run_patterns
from jachai.world.rng import stream
from jachai.world.world import ENTITY_TABLES, EVENT_ID, EVENT_TABLES, World


def build_base(cfg: WorldConfig, patterns: PatternsConfig | None = None) -> World:
    """Entities and honest background events, before any pattern is injected."""
    zones = make_zones(cfg)
    customers = make_customers(cfg, zones)
    agents = make_agents(cfg, zones, customers)
    shops = make_shops(cfg, zones)
    pools = regular_pools(cfg, shops, customers)
    world = World(config=cfg, patterns=patterns)
    world.tables = {
        "zones": zones,
        "shops": shops,
        "customers": customers,
        "agents": agents,
        "qr_payments": make_qr_payments(cfg, shops, customers, pools),
        "remittances": make_remittances(cfg, customers),
        "add_money": make_add_money(cfg, customers, agents),
        "p2p_transfers": make_p2p_transfers(cfg, customers),
    }
    world.pools = pools
    return world


def finalize(world: World) -> World:
    """Sort every event table by time and give each row a random ID."""
    for table in EVENT_TABLES:
        df = world.tables[table].sort_values("ts", kind="stable").reset_index(drop=True)
        id_col, prefix = EVENT_ID[table]
        df.insert(
            0, id_col, random_ids(stream(world.config.seed, f"ids:{table}"), len(df), prefix, 12)
        )
        world.tables[table] = df
    return world


def generate_world(cfg: WorldConfig, patterns: PatternsConfig | None = None) -> World:
    """The full world. Without a patterns config, only honest activity is generated."""
    world = build_base(cfg, patterns)
    run_patterns(world)
    apply_label_noise(world)
    return finalize(world)


def config_fingerprint(cfg: WorldConfig, patterns: PatternsConfig | None) -> str:
    """Short hash of both configs, stored in the manifest to trace data back to settings."""
    payload = cfg.model_dump_json() + (patterns.model_dump_json() if patterns else "")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def write_world(world: World, out_dir: Path) -> Path:
    """Write one parquet file per table plus manifest.json."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in (*ENTITY_TABLES, *EVENT_TABLES):
        world.tables[name].to_parquet(out_dir / f"{name}.parquet", index=False)
    manifest = {
        "seed": world.config.seed,
        "config_fingerprint": config_fingerprint(world.config, world.patterns),
        "window": [str(world.config.calendar.start), str(world.config.calendar.end)],
        "p2p_qr_enabled": world.config.scenario.p2p_qr_enabled,
        "rows": {name: len(world.tables[name]) for name in (*ENTITY_TABLES, *EVENT_TABLES)},
    }
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path


def read_world_tables(out_dir: Path) -> dict[str, pd.DataFrame]:
    return {
        name: pd.read_parquet(out_dir / f"{name}.parquet")
        for name in (*ENTITY_TABLES, *EVENT_TABLES)
    }
