"""Generate the synthetic world: `python -m jachai.world` (what `make world` runs).

    python -m jachai.world [--out data/world] [--p2p] [--seed N]

Reads configs/world.yaml and configs/patterns.yaml, writes one parquet file per
table plus manifest.json, then prints and saves the summary report.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from jachai.world.config import load_patterns_config, load_world_config
from jachai.world.generate import generate_world, write_world
from jachai.world.summary import default_report_path, default_world_dir
from jachai.world.summary import main as summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate the synthetic Jachai world.")
    parser.add_argument("--out", type=Path, default=default_world_dir())
    parser.add_argument("--p2p", action="store_true", help="turn on the P2P QR what-if scenario")
    parser.add_argument("--seed", type=int, help="override the seed (else JACHAI_SEED or config)")
    args = parser.parse_args(argv)

    cfg = load_world_config()
    updates = {}
    if args.seed is not None:
        updates["seed"] = args.seed
    if args.p2p:
        updates["scenario"] = cfg.scenario.model_copy(update={"p2p_qr_enabled": True})
    cfg = cfg.model_copy(update=updates)

    start = time.perf_counter()
    world = generate_world(cfg, load_patterns_config())
    write_world(world, args.out)
    print(f"World written to {args.out} in {time.perf_counter() - start:.1f}s\n")
    summary([str(args.out), "--out", str(default_report_path())])


if __name__ == "__main__":
    main()
