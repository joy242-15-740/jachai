"""Peer comparison and a simple risk trend. Not a fourth decision score.

Peer percentile: where this shop sits, on one day, among shops of the same
category, area type and size. The inputs are already point-in-time (they use
earlier days only).

Risk trend: the last 14 days of this shop's mean payment-model score, then a
straight line over those days, extended 7 days. The line is a forecast in the
everyday sense, not a new model and not a reason to block the shop.

Rising flag, fixed before looking at results: slope > 0 and the day-7 forecast
is at least 0.02 above today's score. Early warning is that flag on a day when
today's score is still under the payment model's validation threshold.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from jachai.features.shop import PEER_KEYS

HISTORY_DAYS = 14
HORIZON_DAYS = 7
MIN_POINTS = 3
# Pre-set margin. A slope alone flags flat noise; 0.02 is two percentage points
# of payment score. Not tuned on the hidden label.
RISING_MARGIN = 0.02

METRICS = (
    ("turnover_7d", "Turnover, last 7 days", "গত ৭ দিনের লেনদেন"),
    ("round_1000_share_30d", "Round Tk 1,000 share, last 30 days", "গত ৩০ দিনে ৳১,০০০ রাউন্ড অংশ"),
    ("far_payer_share_30d", "Distant-payer share, last 30 days", "গত ৩০ দিনে দূরের গ্রাহকের অংশ"),
)


def peer_frame(shop_day: pd.DataFrame) -> pd.DataFrame:
    """Percentile in [0, 100] within category x area x size, on the same day.

    A one-shop group gets 100. The caller should show the group size beside it.
    """
    out = shop_day[["shop_id", "day", *PEER_KEYS, *[m[0] for m in METRICS]]].copy()
    grouped = out.groupby(["day", *PEER_KEYS], sort=False)
    out["peer_shops"] = grouped["shop_id"].transform("size")
    for column, _en, _bn in METRICS:
        out[f"{column}_percentile"] = grouped[column].rank(method="average", pct=True) * 100.0
    return out


def daily_mean_score(payments: pd.DataFrame, proba: np.ndarray, shop_id: str) -> pd.Series:
    """Mean calibrated payment score per day. Days with no payments are absent."""
    mask = payments["shop_id"].to_numpy() == shop_id
    if not mask.any():
        return pd.Series(dtype=float)
    days = payments.loc[mask, "ts"].dt.normalize()
    scores = pd.Series(np.asarray(proba)[mask], index=days.index)
    return scores.groupby(days).mean()


def linear_forecast(history: list[float | None]) -> dict:
    """Fit score = intercept + slope * day_index on the days that have a score.

    `history` is oldest first and should already be length HISTORY_DAYS.
    Forecast values are clipped to [0, 1] for display; the slope is unclipped.
    """
    xs, ys = [], []
    for i, value in enumerate(history):
        if value is not None and not (isinstance(value, float) and np.isnan(value)):
            xs.append(float(i))
            ys.append(float(value))
    blank = {
        "slope_per_day": None,
        "forecast": [None] * HORIZON_DAYS,
        "rising": False,
        "reason": f"fewer than {MIN_POINTS} days with payments in the last {HISTORY_DAYS}",
    }
    if len(xs) < MIN_POINTS:
        return blank
    slope, intercept = (float(v) for v in np.polyfit(xs, ys, 1))
    last = len(history) - 1
    raw = [intercept + slope * (last + step) for step in range(1, HORIZON_DAYS + 1)]
    forecast = [float(np.clip(v, 0.0, 1.0)) for v in raw]
    today = history[-1]
    today_ok = today is not None and not (isinstance(today, float) and np.isnan(today))
    rising = bool(today_ok and slope > 0 and raw[-1] >= float(today) + RISING_MARGIN)
    return {
        "slope_per_day": slope,
        "forecast": forecast,
        "rising": rising,
        "reason": (
            "slope > 0 and the day-7 line is at least 0.02 above today"
            if rising
            else "slope is not up, or the day-7 line stays within 0.02 of today"
        ),
    }


def history_and_forecast(
    daily: pd.Series, as_of: pd.Timestamp
) -> tuple[list[dict], list[dict], dict]:
    """14 days ending at as_of, then 7 forecast days. Missing days stay null."""
    as_of = pd.Timestamp(as_of).normalize()
    days = pd.date_range(as_of - pd.Timedelta(days=HISTORY_DAYS - 1), as_of, freq="D")
    values: list[float | None] = []
    history = []
    for day in days:
        value = daily.get(day, np.nan)
        if value is None or (isinstance(value, float) and np.isnan(value)):
            values.append(None)
            history.append({"day": day.date().isoformat(), "score": None})
        else:
            number = float(value)
            values.append(number)
            history.append({"day": day.date().isoformat(), "score": round(number, 4)})
    fitted = linear_forecast(values)
    future = []
    for step, score in enumerate(fitted["forecast"], start=1):
        day = as_of + pd.Timedelta(days=step)
        future.append(
            {
                "day": day.date().isoformat(),
                "score": None if score is None else round(float(score), 4),
            }
        )
    return history, future, fitted


def panel_for_shop(
    shop_id: str,
    shop_day: pd.DataFrame,
    payments: pd.DataFrame,
    proba: np.ndarray,
    as_of: pd.Timestamp,
    threshold: float,
    shop_row: pd.Series,
) -> dict:
    """JSON-ready panel. Scores are the payment model only. Nothing is blocked."""
    as_of = pd.Timestamp(as_of).normalize()
    peers = peer_frame(shop_day)
    row = peers[(peers["shop_id"] == shop_id) & (peers["day"] == as_of)]
    percentiles = []
    peer_shops = None
    if not row.empty:
        one = row.iloc[0]
        peer_shops = int(one["peer_shops"])
        for column, en, bn in METRICS:
            value = one[column]
            pct = one[f"{column}_percentile"]
            percentiles.append(
                {
                    "metric": column,
                    "en": en,
                    "bn": bn,
                    "value": None if pd.isna(value) else round(float(value), 4),
                    "percentile": None if pd.isna(pct) else round(float(pct), 1),
                }
            )
    daily = daily_mean_score(payments, proba, shop_id)
    history, forecast, fitted = history_and_forecast(daily, as_of)
    today = history[-1]["score"] if history else None
    below = today is not None and today < threshold
    return {
        "available": True,
        "shop_id": shop_id,
        "as_of": as_of.date().isoformat(),
        "peer_group": {
            "category": None if shop_row is None else shop_row.get("category"),
            "area_type": None if shop_row is None else shop_row.get("area_type"),
            "size_tier": None if shop_row is None else shop_row.get("size_tier"),
            "shops": peer_shops,
        },
        "percentiles": percentiles,
        "history": history,
        "forecast": forecast,
        "rising": bool(fitted["rising"]),
        "early_warning": bool(fitted["rising"] and below),
        "slope_per_day": (
            None if fitted["slope_per_day"] is None else round(float(fitted["slope_per_day"]), 4)
        ),
        "payment_threshold": round(float(threshold), 4),
        "today_score": today,
        "reason_en": fitted["reason"],
        "note_en": (
            "Peer and trend is an early look, before a shop crosses the payment threshold. "
            "It does not change the payment, shop or network score, "
            "and it does not block the shop. "
            "An analyst decides."
        ),
        "note_bn": (
            "সহপাঠী ও ধারা একটি আগাম ইঙ্গিত, পেমেন্ট সীমা পার হওয়ার আগে। "
            "এটি পেমেন্ট, দোকান বা নেটওয়ার্ক স্কোর বদলায় না এবং দোকান বন্ধ করে না। "
            "সিদ্ধান্ত বিশ্লেষকের।"
        ),
    }


def rising_on_day(daily: pd.Series, day: pd.Timestamp, threshold: float) -> dict:
    """Rising and early-warning flags for one shop on one day, using only scores up to that day."""
    _history, _forecast, fitted = history_and_forecast(daily, day)
    today = daily.get(pd.Timestamp(day).normalize(), np.nan)
    today_f = None if pd.isna(today) else float(today)
    below = today_f is not None and today_f < threshold
    return {
        "rising": bool(fitted["rising"]),
        "early_warning": bool(fitted["rising"] and below),
        "today": today_f,
    }
