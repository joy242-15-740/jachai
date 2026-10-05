"""Bundle a small REFERENCE-world demo set for the judge walkthrough.

    make demo-reference   (after `make world` and `make train`)

Writes frontend/public/demo/reference/: one case file per walkthrough example
(the real API's response on the reference system) and manifest.json saying which
world they come from and how each was chosen.

Choosing illustrative examples needs the hidden pattern labels. To keep the test
set closed, candidates come from VALIDATION shops only (never test shops), and
the labels are used only to pick which existing case to show; no score, model,
threshold or reported result changes. Synthetic data only.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings
from app.store import Store
from jachai.eval.splits import shop_groups
from jachai.world.config import REPO_ROOT

OUT = REPO_ROOT / "frontend" / "public" / "demo" / "reference"


def pick(store: Store, groups: pd.Series) -> dict[str, dict]:
    shops = store.tables["shops"].set_index("shop_id")
    latest = store.latest.join(shops[["_true_pattern", "category"]])
    val = latest[latest.index.map(groups) == "validation"]

    ring = val[(val["_true_pattern"] == "limit_bypass") & (val["ring_flag"] == 1)]
    ring = ring.sort_values("risk", ascending=False)
    honest = val[
        (val["_true_pattern"] == "hn_big_ticket_retail")
        & (val["category"] == "electronics")
        & (val["band"] == "low")
    ].sort_values("turnover_vs_peers_7d", ascending=False)
    desk = val[
        (val["_true_pattern"] == "round_amount_cash_desk")
        & val["band"].isin(["review", "high"])
        & (val["ring_flag"] != 1)  # a plain cash desk, not also ring-linked
        & (val.index != "SH5e9a82d0f1")  # shown separately as the convert lead
    ].sort_values("risk", ascending=False)

    chosen = {
        "ring": (ring, "Validation shop truly in a limit-bypass ring, with the ring flag on."),
        "honest_lookalike": (
            honest,
            "Validation electronics shop that is truly an honest big-ticket seller, stays in "
            "the low band; busiest relative to its peers among such shops.",
        ),
        "cash_desk": (
            desk,
            "Validation shop that truly runs a round-amount cash desk, not ring-linked; in review "
            "or high band.",
        ),
    }
    out = {
        key: {"shop_id": frame.index[0], "why_chosen": why}
        for key, (frame, why) in chosen.items()
        if len(frame)
    }
    # Convert lead: the validation cash desk that the configured rule recommends converting.
    out["convert_lead"] = {
        "shop_id": "SH5e9a82d0f1",
        "why_chosen": "Validation shop that truly runs a cash desk; high band, real cash-out "
        "demand and no ring, so the configured rule recommends an agent contract.",
    }
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    model_dir, world_dir = REPO_ROOT / "models", REPO_ROOT / "data" / "world"
    store = Store(model_dir, world_dir)
    groups = shop_groups(store.tables["shops"], store.cfg.thresholds, store.cfg.world.seed)
    examples = pick(store, groups)
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["AUDIT_DB_PATH"] = str(Path(tmp) / "audit.sqlite3")
        settings = Settings(model_dir=model_dir, world_dir=world_dir)
        with TestClient(create_app(settings, store)) as client:
            for key, ex in examples.items():
                detail = client.get(f"/cases/{ex['shop_id']}").json()
                assert "_true_" not in json.dumps(detail)
                (OUT / f"{key}.json").write_text(
                    json.dumps(detail, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
                )
                ex["band"] = detail["scores"]["band"]
                ex["recommended_action"] = detail["recommendation"]["action"]
    # Licensed agents near each example shop (same zone), from the public agents table.
    agents = store.tables["agents"]
    shops_pub = store.shops
    fee_rate = store.cfg.world.regulation.agent_cash_out_fee_rate
    for ex in examples.values():
        shop = shops_pub.loc[ex["shop_id"]]
        same_zone = agents[agents["zone_id"] == shop["zone_id"]]
        dist = (
            (same_zone["x_km"] - shop["x_km"]) ** 2 + (same_zone["y_km"] - shop["y_km"]) ** 2
        ) ** 0.5
        ex["agents_in_zone"] = int(len(same_zone))
        ex["nearest_agent_km"] = round(float(dist.min()), 1) if len(dist) else None
    manifest = {
        "world": "reference (3,000 shops, seed 42), scored by the trained reference system",
        "agent_cash_out_fee_rate": fee_rate,
        "as_of": store.as_of.date().isoformat(),
        "selection": "validation shops only; hidden labels used only to choose examples",
        "examples": examples,
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
