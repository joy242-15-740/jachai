"""Replay inputs: the trained system scores a separate replay world, once.

The replay world has its own seed (configs/simulator.yaml `replay.seed`), so it is
neither the training world nor the reserved test set. The replayed month is its
last `replay.days` days. Scoring is the slow part; the result is cached in
data/<profile>/simulator/ and keyed by the system fingerprint and replay seed, so
policy runs (and UI slider changes) only re-run the fast policy engine.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from jachai.features import build_features
from jachai.simulate.config import SimulatorConfig
from jachai.simulate.policies import SimInputs
from jachai.system import Scored, System, score_system
from jachai.world.config import load_patterns_config
from jachai.world.generate import generate_world
from jachai.world.world import TRUE_LABEL


def inputs_from_scored(scored: Scored, tables: dict, days: int, fee_rate: float) -> SimInputs:
    """The last `days` days of a scored world, with hidden truth for outcomes."""
    pay = scored.data.payments
    q = tables["qr_payments"].set_index("payment_id").loc[pay["payment_id"]]
    end = pay["ts"].max().normalize()
    start = end - pd.Timedelta(days=days - 1)
    payments = pd.DataFrame(
        {
            "shop_id": pay["shop_id"].to_numpy(),
            "ts": pay["ts"].to_numpy(),
            "day": pay["ts"].dt.normalize().to_numpy(),
            "amount": q["amount"].to_numpy(),
            "misuse": q[TRUE_LABEL].to_numpy(),
        }
    )
    payments = payments[payments["day"] >= start].reset_index(drop=True)
    sd = scored.shop_day
    shop_day = sd.loc[sd["day"] >= start, ["shop_id", "day", "risk", "band", "rules_flags_30d"]]
    return SimInputs(payments, shop_day.reset_index(drop=True), default_fee_rate=fee_rate)


def build_inputs(system: System, cfg, thr, rules, models, sim: SimulatorConfig) -> SimInputs:
    replay_cfg = cfg.model_copy(update={"seed": sim.replay.seed})
    world = generate_world(replay_cfg, load_patterns_config())
    shop_day = build_features(world.tables, replay_cfg, thr.features)["shop_day"]
    scored = score_system(system, world.tables, shop_day, replay_cfg, thr, rules, models)
    return inputs_from_scored(
        scored, world.tables, sim.replay.days, cfg.regulation.agent_cash_out_fee_rate
    )


def cached_inputs(cache_dir: Path, key: dict, build) -> SimInputs:
    """Load cached inputs if `key` matches, else build, save and return them."""
    meta_path = cache_dir / "inputs.json"
    if meta_path.exists() and json.loads(meta_path.read_text(encoding="utf-8")) == key:
        return SimInputs(
            pd.read_parquet(cache_dir / "payments.parquet"),
            pd.read_parquet(cache_dir / "shop_day.parquet"),
            key["fee_rate"],
        )
    inputs = build()
    cache_dir.mkdir(parents=True, exist_ok=True)
    inputs.payments.to_parquet(cache_dir / "payments.parquet", index=False)
    inputs.shop_day.to_parquet(cache_dir / "shop_day.parquet", index=False)
    meta_path.write_text(json.dumps(key, indent=2) + "\n", encoding="utf-8")
    return inputs
