"""Payment-level features, computed point-in-time.

Rule: a payment's features may use the payment itself and events at or before
its timestamp, never anything later. Concretely:
  - running totals use cumulative sums in time order (this payment included),
  - look-back windows use merge_asof (latest value at or before a time),
  - daily references (category median basket) use only *earlier* days.
ml/tests/test_features_leakage.py proves it: features built from data cut off
at time T equal the features built from all data, for every payment before T.

Inputs are read through `public_view`, so hidden `_true_*` columns never reach
a feature.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from jachai.features.config import FeatureThresholds
from jachai.world.config import WorldConfig
from jachai.world.world import public_view

KEYS = ["payment_id", "ts", "payer_id", "shop_id"]


def _minutes_since_last(events: pd.DataFrame, who: str, at: pd.DataFrame, name: str) -> pd.Series:
    """Minutes from the latest event at or before each row. NaN when there is none.

    `at` may use the event itself when it is in `events`. Nothing after `at.ts` is used.
    """
    if events.empty:
        return pd.Series(np.nan, index=at.index, name=name)
    ev = events[[who, "ts"]].astype({"ts": "datetime64[ns]"})
    ev = ev.sort_values("ts", kind="stable").rename(columns={"ts": "ts_event"})
    query = at[[who, "ts"]].astype({"ts": "datetime64[ns]"}).reset_index(names="_row")
    merged = pd.merge_asof(
        query.sort_values("ts"),
        ev,
        left_on="ts",
        right_on="ts_event",
        by=who,
        direction="backward",
        allow_exact_matches=True,
    )
    minutes = (merged["ts"] - merged["ts_event"]).dt.total_seconds() / 60.0
    return minutes.set_axis(merged["_row"]).reindex(at.index).rename(name)


def _window_sum(
    events: pd.DataFrame, who: str, at: pd.DataFrame, window: pd.Timedelta, name: str
) -> pd.Series:
    """For each row in `at` (columns: who, ts), the sum of `events.amount` for the
    same person with event ts in (at.ts - window, at.ts]."""
    # Tables may store ts at different precisions; merge_asof needs one unit.
    ev = events[[who, "ts", "amount"]].astype({"ts": "datetime64[ns]"})
    ev = ev.sort_values("ts", kind="stable")
    ev = ev.assign(cum=ev.groupby(who)["amount"].cumsum())[[who, "ts", "cum"]]
    query = at[[who, "ts"]].astype({"ts": "datetime64[ns]"}).reset_index(names="_row")
    now = pd.merge_asof(query.sort_values("ts"), ev, on="ts", by=who, allow_exact_matches=True)
    before = pd.merge_asof(
        query.assign(ts=query["ts"] - window).sort_values("ts"),
        ev,
        on="ts",
        by=who,
        allow_exact_matches=True,
    )
    now = now.set_index("_row")["cum"].fillna(0)
    before = before.set_index("_row")["cum"].fillna(0)
    return (now - before).reindex(at.index).rename(name)


def category_median_basket(
    qr: pd.DataFrame, shops: pd.DataFrame, lookback_days: int
) -> pd.DataFrame:
    """Reference basket per (category, day): median of daily median tickets over the
    previous `lookback_days` days. The current day is excluded (shift by one day)."""
    cat = qr["shop_id"].map(shops.set_index("shop_id")["category"])
    daily = qr.assign(category=cat, day=qr["ts"].dt.normalize())
    daily = daily.groupby(["day", "category"])["amount"].median().unstack("category")
    days = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    daily = daily.reindex(days)
    ref = daily.rolling(lookback_days, min_periods=1).median().shift(1)
    return ref.rename_axis("day").stack().rename("category_median").reset_index()


def build_payment_features(
    tables: dict[str, pd.DataFrame], cfg: WorldConfig, thr: FeatureThresholds
) -> pd.DataFrame:
    """One row per QR payment, in time order, with KEYS plus feature columns."""
    qr = public_view(tables["qr_payments"]).sort_values("ts", kind="stable")
    qr = qr.reset_index(drop=True)
    shops = public_view(tables["shops"]).set_index("shop_id")
    customers = public_view(tables["customers"]).set_index("customer_id")
    f = qr[KEYS + ["amount", "on_us"]].copy()
    day = qr["ts"].dt.normalize()

    # --- The amount itself ------------------------------------------------------
    for unit in thr.round_units:
        f[f"is_round_{unit}"] = (qr["amount"] % unit == 0).astype(np.int8)
    cap = cfg.regulation.qr_incentive_cap
    f["just_under_cap"] = (
        (qr["amount"] >= cap - thr.just_under_cap_band) & (qr["amount"] < cap)
    ).astype(np.int8)
    f["after_regime_change"] = (qr["ts"] >= pd.Timestamp(cfg.calendar.regime_change)).astype(
        np.int8
    )

    # Amount compared with the category's usual basket (earlier days only).
    category = qr["shop_id"].map(shops["category"])
    ref = category_median_basket(qr, shops.reset_index(), thr.category_median_lookback_days)
    ref = ref.set_index(["day", "category"])["category_median"]
    median = pd.Series(ref.reindex(pd.MultiIndex.from_arrays([day, category])).to_numpy())
    f["amount_vs_category_median"] = qr["amount"] / median  # NaN on the very first day

    # --- When -------------------------------------------------------------------
    hour = qr["ts"].dt.hour
    hours = {k: c.open_hours for k, c in cfg.categories.items()}
    open_h = category.map(lambda c: hours[c][0])
    close_h = category.map(lambda c: hours[c][1])
    f["hour"] = hour.astype(np.int8)
    f["is_friday"] = (qr["ts"].dt.weekday == 4).astype(np.int8)
    f["after_hours"] = ((hour < open_h) | (hour >= close_h)).astype(np.int8)

    # --- Payer's day so far (this payment included) -------------------------------
    by_payer_day = qr.groupby([qr["payer_id"], day])
    f["payer_day_total"] = by_payer_day["amount"].cumsum()
    first_shop_today = ~qr.assign(day=day).duplicated(["payer_id", "day", "shop_id"])
    f["payer_day_shops"] = first_shop_today.groupby([qr["payer_id"], day]).cumsum()
    limit = cfg.regulation.cash_out_limit_daily
    f["payer_day_total_vs_limit"] = f["payer_day_total"] / limit
    f["near_limit"] = (f["payer_day_total"] >= thr.near_limit_share * limit).astype(np.int8)
    f["payer_day_payments_here"] = qr.groupby([qr["payer_id"], qr["shop_id"], day]).cumcount() + 1

    # --- Money paid soon after money came in ------------------------------------
    inflows = pd.concat(
        [
            public_view(tables["add_money"])[["customer_id", "ts", "amount"]],
            public_view(tables["remittances"])[["customer_id", "ts", "amount"]],
        ]
    ).rename(columns={"customer_id": "payer_id"})
    window = pd.Timedelta(minutes=thr.inflow_window_minutes)
    inflow = _window_sum(inflows, "payer_id", qr, window, "inflow_recent")
    f["inflow_recent"] = inflow
    f["paid_share_of_recent_inflow"] = np.where(
        inflow > 0, np.minimum(qr["amount"] / inflow.where(inflow > 0), 2.0), 0.0
    )

    remits = public_view(tables["remittances"]).rename(columns={"customer_id": "payer_id"})
    rwin = pd.Timedelta(hours=thr.remittance_window_hours)
    remit = _window_sum(remits, "payer_id", qr, rwin, "remittance_recent")
    outflow = _window_sum(qr, "payer_id", qr, rwin, "outflow_recent")  # includes this payment
    f["remittance_recent"] = remit
    f["paid_share_of_recent_remittance"] = np.where(
        remit > 0, np.minimum(outflow / remit.where(remit > 0), 2.0), 0.0
    )
    # Lag from the latest add-money or remittance at or before this payment.
    # Distinct from the windowed sums above: those say how much arrived, this says how soon.
    f["minutes_since_inflow"] = _minutes_since_last(inflows, "payer_id", qr, "minutes_since_inflow")

    # --- Who and where ------------------------------------------------------------
    px = qr["payer_id"].map(customers["x_km"])
    py = qr["payer_id"].map(customers["y_km"])
    sx = qr["shop_id"].map(shops["x_km"])
    sy = qr["shop_id"].map(shops["y_km"])
    f["payer_shop_distance_km"] = np.hypot(px - sx, py - sy).round(2)
    f["first_visit"] = (qr.groupby(["payer_id", "shop_id"]).cumcount() == 0).astype(np.int8)
    # Share of this payer's earlier payments that were already at this shop.
    # 0 on the payer's first ever payment. Uses only rows before this one (cumcount).
    prior_here = qr.groupby(["payer_id", "shop_id"], sort=False).cumcount().to_numpy()
    prior_any = qr.groupby("payer_id", sort=False).cumcount().to_numpy()
    repeat = np.zeros(len(qr), dtype=float)
    np.divide(prior_here, prior_any, out=repeat, where=prior_any > 0)
    f["payer_repeat_rate"] = repeat
    opened = qr["payer_id"].map(customers["account_opened_on"])
    f["payer_account_age_days"] = (qr["ts"] - opened).dt.days
    return f
