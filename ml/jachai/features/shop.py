"""Shop-day features: how each shop behaved on *earlier* days.

The row for (shop, day D) only uses payments from days before D (a one-day
shift after every rolling window). Every shop has a row for every day, including
days with no payments, so "quiet before, busy now" is visible.

Peers are shops of the same category, area type and size tier: a small rural
tea stall is compared with other small rural tea stalls, not with Dhaka
wholesalers.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from jachai.features.config import FeatureThresholds
from jachai.world.config import WorldConfig
from jachai.world.world import public_view

PEER_KEYS = ["category", "area_type", "size_tier"]


def _wide(daily: pd.Series, days: pd.DatetimeIndex, shops: pd.Index) -> pd.DataFrame:
    """(shop, day) series -> days x shops table, zeros where nothing happened."""
    return daily.unstack("shop_id").reindex(index=days, columns=shops).fillna(0.0)


def _past(wide: pd.DataFrame, window: int, how: str = "sum") -> pd.DataFrame:
    """Rolling window over earlier days only (shifted by one day)."""
    roll = wide.rolling(window, min_periods=1)
    return getattr(roll, how)().shift(1)


def build_shop_day_features(
    payment_features: pd.DataFrame,
    tables: dict[str, pd.DataFrame],
    cfg: WorldConfig,
    thr: FeatureThresholds,
) -> pd.DataFrame:
    """One row per (shop_id, day) for every shop and every day in the window."""
    shops = public_view(tables["shops"]).set_index("shop_id")
    days = pd.date_range(cfg.calendar.start, periods=cfg.calendar.days, freq="D")
    f = payment_features
    by = [f["shop_id"], f["ts"].dt.normalize().rename("day")]
    top_unit = max(thr.round_units)

    def wide(values: pd.Series, how: str = "sum") -> pd.DataFrame:
        return _wide(values.groupby(by).agg(how).swaplevel(), days, shops.index)

    one = pd.Series(1.0, index=f.index)
    turnover = wide(f["amount"].astype(float))
    count = wide(one)
    payers = wide(f["payer_id"], "nunique")
    rnd = wide(f[f"is_round_{top_unit}"].astype(float))
    late = wide(f["after_hours"].astype(float))
    first = wide(f["first_visit"].astype(float))
    far = wide((f["payer_shop_distance_km"] >= thr.far_payer_km).astype(float))

    s, lng = thr.short_window_days, thr.long_window_days
    count_long = _past(count, lng)

    def share(num: pd.DataFrame) -> pd.DataFrame:
        return _past(num, lng) / count_long.where(count_long > 0)

    turnover_short = _past(turnover, s)
    median_day_long = _past(turnover, lng, "median")
    out = {
        "turnover_7d": turnover_short,
        "payments_7d": _past(count, s),
        "unique_payers_per_day_7d": _past(payers, s, "mean"),
        f"round_{top_unit}_share_30d": share(rnd),
        "after_hours_share_30d": share(late),
        "first_visit_share_30d": share(first),
        "far_payer_share_30d": share(far),
        # Yesterday's turnover against the shop's own typical day: a burst detector.
        "last_day_vs_own_median_30d": (turnover.shift(1) + 1) / (median_day_long + 1),
    }
    long = pd.concat(
        {name: wide_df.stack(future_stack=True) for name, wide_df in out.items()}, axis=1
    )
    long.index = long.index.set_names(["day", "shop_id"])
    long = long.reset_index()

    # Turnover against peers on the same day (+1 smoothing for quiet peer groups).
    static = shops[PEER_KEYS + ["n_qr_codes", "opened_on"]]
    long = long.join(static, on="shop_id")
    peer_median = long.groupby(["day", *PEER_KEYS])["turnover_7d"].transform("median")
    long["turnover_vs_peers_7d"] = (long["turnover_7d"] + 1) / (peer_median + 1)
    long["shop_age_days"] = (long["day"] - long["opened_on"]).dt.days
    long["is_open"] = (long["shop_age_days"] >= 0).astype(np.int8)
    long = long.rename(columns={"n_qr_codes": "qr_codes_per_account"})
    return long.drop(columns=["opened_on"]).sort_values(["day", "shop_id"]).reset_index(drop=True)
