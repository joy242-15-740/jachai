"""Read-only fast-profile store for the public serverless demo.

The normal API uses :class:`app.store.Store` and the frozen LightGBM artifacts.
Vercel's managed Python runtime lacks LightGBM's native OpenMP library, so this
adapter serves scores and evidence exported by ``make demo-json``. It performs
no training or evaluation and contains no hidden truth columns.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime
from pathlib import Path


class CachedStore:
    """Store-compatible view of code-generated fast-profile demo artifacts."""

    def __init__(self, model_dir: Path, world_dir: Path):
        del model_dir, world_dir
        root = Path(os.getenv("DEMO_DATA_DIR", "frontend/public/demo"))
        self.demo_dir = root
        self._cases_payload = self._read("cases.json")
        self._cases = {row["case_id"]: row for row in self._cases_payload["cases"]}
        self._details = {
            path.stem.removeprefix("case-"): json.loads(path.read_text(encoding="utf-8"))
            for path in root.glob("case-*.json")
        }
        self.as_of = datetime.fromisoformat(self._cases_payload["as_of"])
        grid_path = Path(os.getenv("SIMULATOR_GRID_PATH", root / "simulate-grid.json"))
        grid = json.loads(grid_path.read_text(encoding="utf-8"))
        self._simulator = next(
            run
            for run in grid["runs"]
            if run["params"]["misuse_scale"] == 1
            and run["params"]["analyst_capacity_per_day"] == 20
            and run["params"]["limit_level"] == 100000
        )

    def _read(self, name: str) -> dict:
        return json.loads((self.demo_dir / name).read_text(encoding="utf-8"))

    def has_shop(self, shop_id: str) -> bool:
        return shop_id in self._cases

    def has_payer(self, payer_id: str) -> bool:
        # The public bundle intentionally contains no customer-level data or IDs.
        return bool(payer_id.strip())

    def shop_profile(self, shop_id: str) -> dict:
        if shop_id in self._details:
            return deepcopy(self._details[shop_id]["shop"])
        if shop_id in self._cases:
            case = self._cases[shop_id]
            return {
                key: deepcopy(case[key])
                for key in (
                    "shop_id",
                    "category",
                    "size_tier",
                    "area_type",
                    "zone_id",
                    "n_qr_codes",
                    "opened_on",
                )
            }
        raise KeyError(shop_id)

    def shop_scores(self, shop_id: str) -> dict:
        if shop_id in self._details:
            return deepcopy(self._details[shop_id]["scores"])
        if shop_id in self._cases:
            case = self._cases[shop_id]
            return {
                "as_of": self.as_of,
                "risk": case["risk"],
                "band": case["band"],
                "status": case["status"],
                "components": {},
                "expected_daily_turnover": None,
            }
        return {
            "as_of": self.as_of,
            "risk": 0.0,
            "band": "low",
            "status": "no action",
            "components": {},
            "expected_daily_turnover": None,
        }

    def shop_reasons(self, shop_ids: list[str]) -> list[list[dict]]:
        return [
            deepcopy(
                self._details.get(shop_id, {}).get("reasons")
                or ([self._cases[shop_id]["top_reason"]] if shop_id in self._cases else [])
            )
            for shop_id in shop_ids
        ]

    def cases(self, band: str | None = None, limit: int = 100) -> list[dict]:
        rows = self._cases_payload["cases"]
        if band:
            rows = [row for row in rows if row["band"] == band]
        return deepcopy(rows[:limit])

    def case_detail(self, shop_id: str) -> dict:
        if shop_id not in self._details:
            return {
                "case_id": shop_id,
                "shop": self.shop_profile(shop_id),
                "scores": self.shop_scores(shop_id),
                "reasons": self.shop_reasons([shop_id])[0],
                "riskiest_payments": [],
                "neighbourhood": {
                    "community_size": 0,
                    "ring_flag": False,
                    "linking_payers": 0,
                    "linked_shops": [],
                },
                "timeline": [],
            }
        detail = deepcopy(self._details[shop_id])
        detail.pop("brief", None)
        detail.pop("decisions", None)
        return detail

    def fairness(self) -> dict:
        return deepcopy(self._read("fairness.json"))

    def simulate(self, overrides: dict) -> dict:
        """Apply transparent slider sensitivity to cached fast-profile outputs."""
        out = deepcopy(self._simulator)
        base = out["params"]
        params = {**base, **overrides}
        misuse_ratio = float(params["misuse_scale"]) / float(base["misuse_scale"])
        fee_rate = params.get("fee_rate") or 0.0185
        capacity_ratio = min(
            1.0,
            float(params["analyst_capacity_per_day"])
            / max(1.0, float(base["analyst_capacity_per_day"])),
        )
        limit_ratio = float(base["limit_level"]) / max(1.0, float(params["limit_level"]))
        for row in out["results"]:
            row["misuse_taka_total"] *= misuse_ratio
            effectiveness = 1.0
            if row["policy"] in {"C", "D", "E"}:
                effectiveness = capacity_ratio
            elif row["policy"] == "B":
                effectiveness = min(1.0, limit_ratio)
            row["misuse_taka_stopped"] *= misuse_ratio * effectiveness
            row["misuse_taka_rerouted"] *= misuse_ratio * effectiveness
            row["misuse_taka_still_flowing"] = max(
                0.0,
                row["misuse_taka_total"] - row["misuse_taka_stopped"] - row["misuse_taka_rerouted"],
            )
            row["fees_recaptured"] = (
                (row["misuse_taka_stopped"] + row["misuse_taka_rerouted"]) * float(fee_rate) * 0.5
            )
            row["fee_rate"] = float(fee_rate)
        out["params"] = params
        out["note"] = (
            "Synthetic fast-profile cached scenario sensitivity; no training, validation, "
            "test access, or claim of real-world impact."
        )
        return out

    def score_transaction(self, shop_id: str, payer_id: str, amount: int, ts) -> dict:
        del payer_id, ts
        shop = self.shop_profile(shop_id)
        round_amount = amount % 500 == 0
        large_for_category = amount >= 10_000 and shop["category"] not in {
            "electronics",
            "wholesaler",
        }
        score = min(
            0.95, 0.12 + (0.28 if round_amount else 0.0) + (0.4 if large_for_category else 0.0)
        )
        reasons = []
        if round_amount:
            reasons.append(
                {
                    "code": "ROUND_AMOUNT",
                    "en": "The amount is a round Tk value.",
                    "bn": "পরিমাণটি পূর্ণ অঙ্কের টাকা।",
                    "weight": 0.28,
                }
            )
        if large_for_category:
            reasons.append(
                {
                    "code": "LARGE_TICKET",
                    "en": "The amount is high for this shop category.",
                    "bn": "এই দোকানের ধরনের তুলনায় পরিমাণটি বেশি।",
                    "weight": 0.4,
                }
            )
        return {
            "score": round(score, 4),
            "threshold": 0.65,
            "status": "needs review" if score >= 0.65 else "no action",
            "reasons": reasons[:3],
            "note": (
                "Fast-profile demo recommendation only; an analyst decides and "
                "nothing is blocked automatically."
            ),
        }
