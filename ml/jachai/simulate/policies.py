"""Five policies replayed over the same month.

  A  do_nothing       nothing changes
  B  blanket_limit    every merchant capped at `limit_level` Tk of QR per day;
                      payments past the cap that day are blocked, honest or not
  C  rules_only       shops with >= `rules_min_flags` rule-flagged payments in the
                      last 30 days join an analyst queue (most flags first)
  D  jachai_targeted  shops in the Jachai alert bands join the queue (highest risk first)
  E  jachai_convert   as D; confirmed shops with enough cash-out demand get an agent
                      offer; if accepted, their cash-out continues as licensed agent
                      business (rerouted, earning fees); otherwise they are stopped

Analysts review at most `analyst_capacity_per_day` shops a day, each shop at most
once in the month. A reviewed misuse shop is confirmed with `analyst_recall`; a
reviewed honest shop is wrongly confirmed with `analyst_false_confirm`. Action
starts the day after the review. Each shop's review and offer draws are fixed
once and shared by C, D and E, so the policies differ in WHICH shops they review,
not in luck. Nothing here blocks automatically in Jachai's case: "confirmed"
stands for a human analyst's decision.

Inputs (all for the replayed month):
  payments  shop_id, ts, day, amount, misuse (hidden truth, 0/1)
  shop_day  shop_id, day, risk, band, rules_flags_30d
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from jachai.simulate.config import SimParams

POLICIES = {
    "A": "do_nothing",
    "B": "blanket_limit",
    "C": "rules_only",
    "D": "jachai_targeted",
    "E": "jachai_convert",
}


@dataclass
class SimInputs:
    payments: pd.DataFrame
    shop_day: pd.DataFrame
    default_fee_rate: float


def scale_misuse(inputs: SimInputs, params: SimParams) -> SimInputs:
    """Keep only `misuse_scale` of misuse shops; dropped shops' misuse payments vanish
    (their honest sales stay, so they become honest shops)."""
    if params.misuse_scale >= 1:
        return inputs
    pay = inputs.payments
    misuse_shops = np.sort(pay.loc[pay["misuse"] == 1, "shop_id"].unique())
    rng = np.random.default_rng(params.seed)
    keep = set(rng.permutation(misuse_shops)[: round(params.misuse_scale * len(misuse_shops))])
    drop = (pay["misuse"] == 1) & ~pay["shop_id"].isin(keep)
    return SimInputs(pay[~drop].reset_index(drop=True), inputs.shop_day, inputs.default_fee_rate)


def _draws(shop_ids: np.ndarray, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ids = np.sort(shop_ids)
    return pd.DataFrame(
        {"review": rng.random(len(ids)), "offer": rng.random(len(ids))}, index=pd.Index(ids)
    )


def _review_policy(policy: str, inputs: SimInputs, params: SimParams) -> pd.DataFrame:
    """Per reviewed shop: review day, outcome, action start. Empty for A and B."""
    pay, sd = inputs.payments, inputs.shop_day
    misuse_shop = pay.groupby("shop_id")["misuse"].max()
    draws = _draws(sd["shop_id"].unique(), params.seed)
    if policy == "C":
        alert = sd["rules_flags_30d"].fillna(0) >= params.rules_min_flags
        priority = sd["rules_flags_30d"].fillna(0)
    else:
        alert = sd["band"].isin(params.jachai_bands)
        priority = sd["risk"]
    queue = sd.assign(priority=priority)[alert.to_numpy()]

    misuse_pay = pay[pay["misuse"] == 1]
    reviewed: dict[str, dict] = {}
    for day, today in queue.groupby("day", sort=True):
        today = today[~today["shop_id"].isin(reviewed)]
        today = today.sort_values(["priority", "shop_id"], ascending=[False, True])
        for shop in today["shop_id"].head(params.analyst_capacity_per_day):
            is_misuse = bool(misuse_shop.get(shop, 0))
            u = draws.at[shop, "review"]
            confirmed = u < (params.analyst_recall if is_misuse else params.analyst_false_confirm)
            action = "cleared"
            if confirmed:
                action = "stopped" if is_misuse else "restricted_honest"
                if policy == "E" and is_misuse:
                    recent = misuse_pay[
                        (misuse_pay["shop_id"] == shop)
                        & (misuse_pay["day"] < day)
                        & (misuse_pay["day"] >= day - pd.Timedelta(days=30))
                    ]["amount"].sum()
                    if recent >= params.convert_min_monthly_taka:
                        offered = True
                        accepted = draws.at[shop, "offer"] < params.offer_acceptance
                        action = "converted" if accepted else "stopped"
                        reviewed[shop] = {"offered": offered}
            reviewed.setdefault(shop, {})
            reviewed[shop].update(
                {"review_day": day, "action": action, "from_day": day + pd.Timedelta(days=1)}
            )
    out = pd.DataFrame.from_dict(reviewed, orient="index")
    if out.empty:
        return pd.DataFrame(columns=["review_day", "action", "from_day", "offered"])
    if "offered" not in out:
        out["offered"] = False
    out["offered"] = out["offered"].fillna(False).astype(bool)
    return out


def run_policy(policy: str, inputs: SimInputs, params: SimParams) -> dict:
    inputs = scale_misuse(inputs, params)
    pay = inputs.payments
    fee_rate = params.fee_rate if params.fee_rate is not None else inputs.default_fee_rate
    days = pay["day"].nunique()
    misuse = (pay["misuse"] == 1).to_numpy()
    amount = pay["amount"].to_numpy(dtype=float)
    blocked = np.zeros(len(pay), dtype=bool)  # payment does not happen
    rerouted = np.zeros(len(pay), dtype=bool)  # happens as licensed agent cash-out
    reviews = pd.DataFrame(columns=["review_day", "action", "from_day", "offered"])

    if policy == "B":
        order = pay.sort_values("ts", kind="stable").index
        running = pay.loc[order].groupby(["shop_id", "day"])["amount"].cumsum()
        blocked[running.index[running > params.limit_level]] = True
    elif policy in ("C", "D", "E"):
        reviews = _review_policy(policy, inputs, params)
        act = (
            pay["shop_id"].map(reviews["action"])
            if len(reviews)
            else pd.Series(index=pay.index, dtype=object)
        )
        start = (
            pay["shop_id"].map(reviews["from_day"])
            if len(reviews)
            else pd.Series(index=pay.index, dtype="datetime64[ns]")
        )
        active = (pay["day"] >= start).fillna(False).to_numpy()
        act = act.fillna("").to_numpy()
        blocked = active & np.isin(act, ["stopped", "restricted_honest"])
        rerouted = active & (act == "converted") & misuse
    elif policy != "A":
        raise ValueError(f"unknown policy {policy!r}")

    stopped = blocked & misuse
    honest_blocked = blocked & ~misuse
    misuse_shops = set(pay.loc[misuse, "shop_id"])
    honest_shop_blocked = honest_blocked & ~pay["shop_id"].isin(misuse_shops).to_numpy()
    flowing_misuse = misuse & ~stopped & ~rerouted
    flowing_honest = ~misuse & ~honest_blocked
    t_stopped, t_rerouted = amount[stopped].sum(), amount[rerouted].sum()
    honest_flow, misuse_flow = amount[flowing_honest].sum(), amount[flowing_misuse].sum()
    return {
        "policy": policy,
        "name": POLICIES[policy],
        "days": int(days),
        "misuse_taka_total": float(amount[misuse].sum()),
        "misuse_taka_stopped": float(t_stopped),
        "misuse_taka_rerouted": float(t_rerouted),
        "misuse_taka_still_flowing": float(misuse_flow),
        "fees_recaptured": float(
            fee_rate * (t_rerouted + params.displaced_to_agents_share * t_stopped)
        ),
        "honest_shops_restricted": int(pay.loc[honest_shop_blocked, "shop_id"].nunique()),
        "blocked_genuine_sales": float(amount[honest_shop_blocked].sum()),
        "blocked_sales_at_misuse_shops": float(amount[honest_blocked & ~honest_shop_blocked].sum()),
        "analyst_alerts_per_day": float(len(reviews) / days) if days else 0.0,
        "agent_leads": int(reviews["offered"].sum()) if len(reviews) else 0,
        "agents_signed": int((reviews["action"] == "converted").sum()) if len(reviews) else 0,
        "genuine_commerce_share": float(honest_flow / (honest_flow + misuse_flow))
        if honest_flow + misuse_flow
        else float("nan"),
        "fee_rate": float(fee_rate),
    }


def run_all(inputs: SimInputs, params: SimParams) -> list[dict]:
    return [run_policy(p, inputs, params) for p in POLICIES]
