"""Payer-day features: what each payer did on *earlier* days.

Only (payer, day) pairs where the payer makes a QR payment get a row; that is
all the payment table needs. Windows are time-based and closed on the left, so
the row for day D covers days D-7 .. D-1.
"""

from __future__ import annotations

import pandas as pd

from jachai.features.config import FeatureThresholds
from jachai.world.world import public_view


def _past_rolling(daily: pd.DataFrame, key: str, window_days: int) -> pd.DataFrame:
    """Sum of each column over the `window_days` days before each row's day."""
    daily = daily.sort_values([key, "day"])
    rolled = (
        daily.set_index("day")
        .groupby(key)
        .rolling(f"{window_days}D", closed="left")
        .sum()
        .fillna(0.0)
    )
    return rolled.reset_index()


def build_payer_day_features(
    payment_features: pd.DataFrame, tables: dict[str, pd.DataFrame], thr: FeatureThresholds
) -> pd.DataFrame:
    f = payment_features
    top_unit = max(thr.round_units)
    pay = pd.DataFrame(
        {
            "payer_id": f["payer_id"],
            "day": f["ts"].dt.normalize(),
            "amount": f["amount"].astype(float),
            "payments": 1.0,
            "round": f[f"is_round_{top_unit}"].astype(float),
            "first_visits": f["first_visit"].astype(float),
        }
    )
    pay["shop_id"] = f["shop_id"]
    grouped = pay.groupby(["payer_id", "day"])
    daily = grouped[["amount", "payments", "round", "first_visits"]].sum()
    # Distinct shops per day, summed over the window (a shop visited on two days counts twice).
    daily["shop_days"] = grouped["shop_id"].nunique().astype(float)
    daily = daily.reset_index()

    inflow = pd.concat(
        [
            public_view(tables["add_money"]).assign(bank=lambda d: (d["channel"] == "bank") * 1.0),
            public_view(tables["remittances"]).assign(bank=0.0),
        ]
    )
    inflow = (
        inflow.assign(payer_id=inflow["customer_id"], day=inflow["ts"].dt.normalize())
        .groupby(["payer_id", "day"])
        .agg(inflow=("amount", "sum"), bank_topups=("bank", "sum"))
        .reset_index()
    )
    # Inflow days without payments still count towards later payment days.
    both = daily.merge(inflow, on=["payer_id", "day"], how="outer").fillna(0.0)
    rolled = _past_rolling(both, "payer_id", thr.short_window_days)

    out = pd.DataFrame(
        {
            "payer_id": rolled["payer_id"],
            "day": rolled["day"],
            "payer_payments_7d": rolled["payments"],
            "payer_amount_7d": rolled["amount"],
            "payer_shop_days_7d": rolled["shop_days"],
            "payer_round_share_7d": rolled["round"]
            / rolled["payments"].where(rolled["payments"] > 0),
            "payer_first_visit_share_7d": rolled["first_visits"]
            / rolled["payments"].where(rolled["payments"] > 0),
            "payer_inflow_7d": rolled["inflow"],
            "payer_bank_topups_7d": rolled["bank_topups"],
        }
    )
    # Keep only days with a payment: that is where the features are used.
    return out.merge(daily[["payer_id", "day"]], on=["payer_id", "day"], how="inner")
