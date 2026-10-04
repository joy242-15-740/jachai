"""In-memory scoring store, built once when the API starts.

Loads the trained system (MODEL_DIR) and the generated world, scores every
shop-day and payment with the frozen system (nothing is refitted), and answers
API questions from that. Hidden `_true_*` columns are never served: every table
handed out goes through `public_view`.

A "case" is a shop in an alert band (review / high) on the latest scored day.
There is one open case per shop, so the case id is the shop id.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from jachai.explain.reasons import load_reason_codes, payment_reasons, shop_reasons
from jachai.features import build_features
from jachai.features.config import ThresholdsConfig, load_thresholds
from jachai.labels.config import RulesConfig, load_rules
from jachai.models.config import ModelsConfig, load_models_config
from jachai.models.network import heavy_same_day_pairs, shop_links
from jachai.system import load_system, score_system
from jachai.world.config import WorldConfig, load_world_config
from jachai.world.generate import read_world_tables
from jachai.world.world import TRUE_LABEL, TRUE_PATTERN, public_view

ALERT_BANDS = ("review", "high")
TIMELINE_DAYS = 30
STATUS = {"high": "needs review (high priority)", "review": "needs review", "low": "no action"}


@dataclass
class Configs:
    world: WorldConfig
    thresholds: ThresholdsConfig
    rules: RulesConfig
    models: ModelsConfig

    @classmethod
    def load(cls) -> Configs:
        return cls(load_world_config(), load_thresholds(), load_rules(), load_models_config())


def _clean(value):
    """JSON-safe scalar (NaN -> None, numpy -> python, timestamps -> ISO)."""
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and np.isnan(value):
        return None
    return value


def records(df: pd.DataFrame) -> list[dict]:
    return [{k: _clean(v) for k, v in row.items()} for row in df.to_dict(orient="records")]


def _reasons(reasons) -> list[dict]:
    return [
        {"code": r.code, "en": r.en, "bn": r.bn, "weight": round(r.contribution, 4)}
        for r in reasons
    ]


class Store:
    def __init__(self, model_dir, world_dir, configs: Configs | None = None, sim_cache_dir=None):
        self.cfg = configs or Configs.load()
        self.sim_cache_dir = sim_cache_dir or world_dir.parent / "simulator"
        self._sim_inputs = None
        c = self.cfg
        self.tables = read_world_tables(world_dir)
        self.system = load_system(model_dir, c.models)
        self.codes = load_reason_codes()
        self.shop_day_features = build_features(self.tables, c.world, c.thresholds.features)[
            "shop_day"
        ]
        self.scored = score_system(
            self.system,
            self.tables,
            self.shop_day_features,
            c.world,
            c.thresholds,
            c.rules,
            c.models,
        )
        self.as_of = self.scored.shop_day["day"].max()
        latest = self.scored.shop_day[self.scored.shop_day["day"] == self.as_of]
        self.latest = latest.set_index("shop_id")
        self.shops = public_view(self.tables["shops"]).set_index("shop_id")
        self.customers = public_view(self.tables["customers"]).set_index("customer_id")

    # --- shops and cases ------------------------------------------------------------
    def has_shop(self, shop_id: str) -> bool:
        return shop_id in self.shops.index

    def shop_scores(self, shop_id: str) -> dict:
        row = self.latest.loc[shop_id]
        components = {c: _clean(row[c]) for c in self.cfg.models.fusion.weights}
        return {
            "as_of": self.as_of.date().isoformat(),
            "risk": round(float(row["risk"]), 4),
            "band": row["band"],
            "status": STATUS[row["band"]],
            "components": components,
            "expected_daily_turnover": _clean(row["expected_daily_turnover"]),
        }

    def shop_reasons(self, shop_ids: list[str]) -> list[list[dict]]:
        rows = self.latest.loc[shop_ids].reset_index()
        return [
            _reasons(r) for r in shop_reasons(self.system.fusion, rows, self.cfg.world, self.codes)
        ]

    def shop_profile(self, shop_id: str) -> dict:
        s = self.shops.loc[shop_id]
        keep = ["category", "size_tier", "area_type", "zone_id", "n_qr_codes", "opened_on"]
        return {"shop_id": shop_id, **{k: _clean(s[k]) for k in keep}}

    def cases(self, band: str | None = None, limit: int = 100) -> list[dict]:
        bands = [band] if band else list(ALERT_BANDS)
        open_cases = (
            self.latest[self.latest["band"].isin(bands)]
            .sort_values("risk", ascending=False)
            .head(limit)
        )
        ids = open_cases.index.tolist()
        top = self.shop_reasons(ids) if ids else []
        return [
            {
                "case_id": shop,
                **self.shop_profile(shop),
                "risk": round(float(open_cases.at[shop, "risk"]), 4),
                "band": open_cases.at[shop, "band"],
                "status": STATUS[open_cases.at[shop, "band"]],
                "top_reason": reasons[0] if reasons else None,
            }
            for shop, reasons in zip(ids, top, strict=True)
        ]

    # --- case detail ----------------------------------------------------------------
    def timeline(self, shop_id: str) -> list[dict]:
        start = self.as_of - pd.Timedelta(days=TIMELINE_DAYS - 1)
        pay = self.scored.data.payments
        mask = (pay["shop_id"] == shop_id).to_numpy() & (pay["ts"] >= start).to_numpy()
        p = pd.DataFrame(
            {
                "day": pay.loc[mask, "ts"].dt.normalize().to_numpy(),
                "amount": pay.loc[mask, "amount"].to_numpy(),
                "flagged": self.scored.payment_proba[mask] >= self.system.payment.threshold,
            }
        )
        daily = p.groupby("day").agg(
            payments=("amount", "size"), turnover=("amount", "sum"), flagged=("flagged", "sum")
        )
        sd = self.scored.shop_day
        risk = sd[(sd["shop_id"] == shop_id) & (sd["day"] >= start)].set_index("day")[
            ["risk", "band"]
        ]
        out = risk.join(daily, how="left").fillna({"payments": 0, "turnover": 0, "flagged": 0})
        return records(out.reset_index().assign(day=lambda d: d["day"].dt.date.astype(str)))

    def riskiest_payments(self, shop_id: str, n: int = 5) -> list[dict]:
        pay = self.scored.data.payments
        start = self.as_of - pd.Timedelta(days=TIMELINE_DAYS - 1)
        mask = (pay["shop_id"] == shop_id).to_numpy() & (pay["ts"] >= start).to_numpy()
        if not mask.any():
            return []
        idx = np.flatnonzero(mask)[np.argsort(-self.scored.payment_proba[mask])[:n]]
        rows = pay.iloc[idx]
        reasons = payment_reasons(self.system.payment, rows, self.cfg.world, self.codes)
        return [
            {
                "payment_id": r["payment_id"],
                "ts": r["ts"].isoformat(),
                "amount": int(r["amount"]),
                "score": round(float(self.scored.payment_proba[i]), 4),
                "reasons": _reasons(rs),
            }
            for i, (_, r), rs in zip(idx, rows.iterrows(), reasons, strict=True)
        ]

    def neighbourhood(self, shop_id: str) -> dict:
        """Shops linked to this one by payers who paid both on the same heavy day
        (past the daily limit across several shops), over the last 30 days."""
        net = self.cfg.models.network
        qr = public_view(self.tables["qr_payments"])
        window = qr[
            (qr["ts"] < self.as_of) & (qr["ts"] >= self.as_of - pd.Timedelta(days=net.window_days))
        ]
        links = shop_links(
            heavy_same_day_pairs(window, net, self.cfg.world.regulation.cash_out_limit_daily), net
        )
        mine = links[(links["shop_id_a"] == shop_id) | (links["shop_id_b"] == shop_id)]
        other = np.where(mine["shop_id_a"] == shop_id, mine["shop_id_b"], mine["shop_id_a"])
        neighbours = [
            {
                "shop_id": o,
                "shared_payers": int(n),
                "category": self.shops.at[o, "category"],
                "band": self.latest.at[o, "band"],
                "risk": round(float(self.latest.at[o, "risk"]), 4),
            }
            for o, n in sorted(zip(other, mine["shared"], strict=True), key=lambda t: -t[1])
        ]
        row = self.latest.loc[shop_id]
        return {
            "community_size": _clean(row["community_size"]),
            "ring_flag": bool(row["ring_flag"]) if pd.notna(row["ring_flag"]) else False,
            "linking_payers": _clean(row["linking_payers"]),
            "linked_shops": neighbours,
        }

    def case_detail(self, shop_id: str) -> dict:
        return {
            "case_id": shop_id,
            "shop": self.shop_profile(shop_id),
            "scores": self.shop_scores(shop_id),
            "reasons": self.shop_reasons([shop_id])[0],
            "riskiest_payments": self.riskiest_payments(shop_id),
            "neighbourhood": self.neighbourhood(shop_id),
            "timeline": self.timeline(shop_id),
        }

    # --- fairness -------------------------------------------------------------------
    def fairness(self) -> dict:
        """False-alarm rate (honest shops put in an alert band / honest shops) by area
        type, shop size and category. Uses VALIDATION shops on the last validation day
        only (never test shops), and returns group totals only, never per-shop truth."""
        sd = self.scored.shop_day
        day = pd.Timestamp(self.cfg.thresholds.split.validation_end)
        v = sd[(sd["split"] == "validation") & (sd["day"] == day)].copy()
        truth = self.tables["shops"].set_index("shop_id")[TRUE_LABEL]
        v["honest"] = v["shop_id"].map(truth).to_numpy() == 0
        v["alert"] = v["band"].isin(ALERT_BANDS).to_numpy()
        v = v.join(self.shops[["area_type", "size_tier", "category"]], on="shop_id")
        honest = v[v["honest"]]

        def table(by: str | None) -> list[dict]:
            groups = honest.groupby(by) if by else [("all", honest)]
            out = []
            for name, g in groups:
                n = len(g)
                out.append(
                    {
                        "group": name,
                        "honest_shops": n,
                        "false_alarms": int(g["alert"].sum()),
                        "false_alarm_rate": round(float(g["alert"].mean()), 4) if n else None,
                        "small_sample": n < 20,
                    }
                )
            return out

        return {
            "evaluated_on": f"validation shops on {day.date()} (test set not used)",
            "overall": table(None)[0],
            "by_area_type": table("area_type"),
            "by_size_tier": table("size_tier"),
            "by_category": table("category"),
            "note": "Synthetic data. Small groups (small_sample) give unstable rates.",
        }

    # --- policy simulator -----------------------------------------------------------
    def simulate(self, overrides: dict) -> dict:
        from jachai.simulate.config import load_simulator_config
        from jachai.simulate.inputs import build_inputs, cached_inputs
        from jachai.simulate.policies import run_all

        sim = load_simulator_config()
        params = sim.params.with_overrides(overrides)  # raises ValidationError if invalid
        if self._sim_inputs is None:
            c = self.cfg
            key = {
                "system": self.system.payment.fingerprint(),
                "replay_seed": sim.replay.seed,
                "replay_days": sim.replay.days,
                "fee_rate": c.world.regulation.agent_cash_out_fee_rate,
            }
            self._sim_inputs = cached_inputs(
                self.sim_cache_dir,
                key,
                lambda: build_inputs(self.system, c.world, c.thresholds, c.rules, c.models, sim),
            )
        return {
            "params": params.model_dump(),
            "replay": sim.replay.model_dump(),
            "results": run_all(self._sim_inputs, params),
            "note": "Synthetic replay world (not the test set): the method, not real amounts.",
        }

    # --- one new payment ------------------------------------------------------------
    def score_transaction(self, shop_id: str, payer_id: str, amount: int, ts: pd.Timestamp) -> dict:
        """Point-in-time features for one new payment (history strictly before `ts`),
        scored by the frozen payment model. Rebuilds features from the history, which
        takes about a second on the fast world: fine for a demo, not production latency."""
        tables = {k: v.copy() for k, v in self.tables.items()}
        for name in ("qr_payments", "remittances", "add_money", "p2p_transfers"):
            tables[name] = tables[name][tables[name]["ts"] < ts]
        new = tables["qr_payments"].head(0).copy()
        new.loc[0, ["payment_id", "ts", "payer_id", "shop_id", "amount", "on_us"]] = [
            "QP_NEW",
            ts,
            payer_id,
            shop_id,
            amount,
            True,
        ]
        # Hidden truth columns only keep the table's types; never read or served.
        new.loc[0, [TRUE_LABEL, TRUE_PATTERN]] = [0, "unknown"]
        tables["qr_payments"] = pd.concat([tables["qr_payments"], new], ignore_index=True).astype(
            tables["qr_payments"].dtypes.to_dict()
        )
        feats = build_features(tables, self.cfg.world, self.cfg.thresholds.features)["payments"]
        row = feats[feats["payment_id"] == "QP_NEW"]
        proba = float(self.system.payment.predict_proba(row)[0])
        flagged = proba >= self.system.payment.threshold
        reasons = payment_reasons(self.system.payment, row, self.cfg.world, self.codes)[0]
        return {
            "score": round(proba, 4),
            "threshold": round(self.system.payment.threshold, 4),
            "status": "needs review" if flagged else "no action",
            "reasons": _reasons(reasons),
            "note": "Recommendation only: an analyst decides; nothing is blocked automatically.",
        }
