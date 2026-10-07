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


def _history_frame(
    payment_features: pd.DataFrame, days: pd.DatetimeIndex, shops: pd.Index, window: int
) -> pd.DataFrame:
    """Median hour and one-time-payer share over the previous `window` days."""
    f = payment_features
    day_ord = pd.Series(np.arange(len(days)), index=days)
    work = pd.DataFrame(
        {
            "shop_id": f["shop_id"].to_numpy(),
            "ord": f["ts"].dt.normalize().map(day_ord).to_numpy(),
            "hour": f["hour"].to_numpy(dtype=float),
            "payer_id": f["payer_id"].to_numpy(),
        }
    ).dropna(subset=["ord"])
    shop_pos = {shop: i for i, shop in enumerate(shops)}
    median_hour = np.full((len(days), len(shops)), np.nan)
    one_time = np.full((len(days), len(shops)), np.nan)
    for shop, g in work.groupby("shop_id", sort=False):
        col = shop_pos.get(shop)
        if col is None:
            continue
        g = g.sort_values("ord", kind="stable")
        ords = g["ord"].to_numpy()
        hours = g["hour"].to_numpy()
        payers = g["payer_id"].to_numpy()
        for i in range(len(days)):
            hi = int(np.searchsorted(ords, i, side="left"))
            lo = int(np.searchsorted(ords, i - window, side="left"))
            if hi <= lo:
                continue
            median_hour[i, col] = float(np.median(hours[lo:hi]))
            uniq, counts = np.unique(payers[lo:hi], return_counts=True)
            one_time[i, col] = float((counts == 1).sum() / len(uniq))
    med = pd.DataFrame(median_hour, index=days, columns=shops).stack(future_stack=True)
    once = pd.DataFrame(one_time, index=days, columns=shops).stack(future_stack=True)
    out = pd.DataFrame({"median_hour_30d": med, "one_time_payer_share_30d": once})
    out.index = out.index.set_names(["day", "shop_id"])
    return out.reset_index()


def _owner_p2p_senders(
    tables: dict[str, pd.DataFrame],
    shops: pd.DataFrame,
    days: pd.DatetimeIndex,
    thr: FeatureThresholds,
) -> pd.Series:
    """Distinct-sender days into the owner's personal wallet over the previous
    `short_window_days` days (0 when the P2P table is empty)."""
    p2p = public_view(tables["p2p_transfers"])
    owner_to_shop = pd.Series(shops.index, index=shops["owner_wallet_id"])
    p2p = p2p[p2p["receiver_id"].isin(owner_to_shop.index)]
    daily = (
        p2p.assign(shop_id=p2p["receiver_id"].map(owner_to_shop), day=p2p["ts"].dt.normalize())
        .groupby(["shop_id", "day"])["sender_id"]
        .nunique()
        .astype(float)
    )
    wide = _wide(daily, days, shops.index)
    return (
        _past(wide, thr.short_window_days).stack(future_stack=True).rename_axis(["day", "shop_id"])
    )


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
    long["owner_p2p_senders_7d"] = (
        _owner_p2p_senders(tables, shops, days, thr)
        .reindex(pd.MultiIndex.from_frame(long[["day", "shop_id"]]))
        .to_numpy()
    )
    long["shop_age_days"] = (long["day"] - long["opened_on"]).dt.days
    long["is_open"] = (long["shop_age_days"] >= 0).astype(np.int8)
    long = long.rename(columns={"n_qr_codes": "qr_codes_per_account"})
    extra = _history_frame(f, days, shops.index, lng)
    long = long.merge(extra, on=["day", "shop_id"], how="left", validate="1:1")
    return long.drop(columns=["opened_on"]).sort_values(["day", "shop_id"]).reset_index(drop=True)
