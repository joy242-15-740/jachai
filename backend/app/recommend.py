"""Recommended next step for a case, from configs/rules.yaml `recommendation`.

Works on the case-detail dict both stores return (live and cached), so the
public demo and the full API recommend the same way. It only recommends: the
analyst decides and records the decision; nothing happens automatically.

Estimated cash-out demand (30 days) = sum over the timeline's days of
turnover x (flagged payments / payments). It is an estimate from observable
data only, shown as "about Tk ...".
"""

from __future__ import annotations

from jachai.labels.config import Recommendation

BANGLA_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")


def cash_out_demand(timeline: list[dict]) -> float:
    total = 0.0
    for day in timeline:
        payments = day.get("payments") or 0
        if payments:
            total += (day.get("turnover") or 0) * (day.get("flagged") or 0) / payments
    return total


def recommend(detail: dict, cfg: Recommendation) -> dict:
    band = detail["scores"]["band"]
    net = detail.get("neighbourhood") or {}
    demand = cash_out_demand(detail.get("timeline") or [])
    facts = {
        "ring": bool(net.get("ring_flag")),
        "high_and_demand": band == "high" and demand >= cfg.convert_min_monthly_demand,
        "high": band == "high",
        "review": band == "review",
        "low": band == "low",
    }
    rule = next(r for r in cfg.rules if facts[r.when])
    values = {
        "demand": f"{round(demand):,}",
        "linking_payers": int(net.get("linking_payers") or 0),
        "community_size": int(net.get("community_size") or 0),
    }
    return {
        "action": rule.action,
        "en": rule.en.format(**values),
        "bn": rule.bn.format(**values).translate(BANGLA_DIGITS),
        "estimated_cash_out_demand_30d": round(demand),
        "convert_eligible": demand >= cfg.convert_min_monthly_demand,
        "note": "Recommendation only: the analyst decides.",
    }
