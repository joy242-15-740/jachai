"""Portfolio overview for the dashboard home: `GET /overview`.

Everything here is aggregated from the scored store that the queue and case pages
already use (same payments, same frozen model, same bands). Nothing is recomputed
or refitted, and no number is typed by hand. Synthetic data only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from fastapi import HTTPException, Request

from app.common import ALERT_BANDS, STATUS, _clean

WINDOW_DAYS = 7
HISTORY_DAYS = 14
RECENT_PAYMENTS = 6


def _daily(store, start: pd.Timestamp) -> pd.DataFrame:
    """One row per day from `start` to as_of: payments, turnover, flagged (count)."""
    pay = store.scored.data.payments
    mask = (pay["ts"] >= start).to_numpy() & (pay["ts"] < store.as_of + pd.Timedelta(days=1))
    flagged = store.scored.payment_proba >= store.system.payment.threshold
    amount = pay.loc[mask, "amount"].to_numpy()
    p = pd.DataFrame(
        {
            "day": pay.loc[mask, "ts"].dt.normalize().to_numpy(),
            "amount": amount,
            "flagged": flagged[mask],
            "flagged_amount": np.where(flagged[mask], amount, 0),
        }
    )
    daily = p.groupby("day").agg(
        payments=("amount", "size"),
        turnover=("amount", "sum"),
        flagged=("flagged", "sum"),
        flagged_turnover=("flagged_amount", "sum"),
    )
    days = pd.date_range(start, store.as_of, freq="D")
    return daily.reindex(days, fill_value=0).rename_axis("day")


def _recent_flagged(store, start: pd.Timestamp) -> list[dict]:
    """Most recent payments above the payment threshold at shops that are in an
    alert band today. The shop's band is shown, never a verdict on the payment."""
    pay = store.scored.data.payments
    alert_shops = store.latest.index[store.latest["band"].isin(ALERT_BANDS)]
    flagged = store.scored.payment_proba >= store.system.payment.threshold
    mask = flagged & (pay["ts"] >= start).to_numpy() & pay["shop_id"].isin(alert_shops).to_numpy()
    if not mask.any():
        return []
    idx = np.flatnonzero(mask)
    newest_first = np.argsort(pay["ts"].to_numpy()[idx], kind="stable")[::-1]
    idx = idx[newest_first[:RECENT_PAYMENTS]]
    rows = pay.iloc[idx]
    return [
        {
            "payment_id": r["payment_id"],
            "shop_id": r["shop_id"],
            "category": store.shops.at[r["shop_id"], "category"],
            "ts": r["ts"].isoformat(),
            "amount": int(r["amount"]),
            "score": round(float(store.scored.payment_proba[i]), 4),
            "band": store.latest.at[r["shop_id"], "band"],
            "status": STATUS[store.latest.at[r["shop_id"], "band"]],
        }
        for i, (_, r) in zip(idx, rows.iterrows(), strict=True)
    ]


def overview_payload(store) -> dict:
    as_of = store.as_of
    window_start = as_of - pd.Timedelta(days=WINDOW_DAYS - 1)
    prev_start = window_start - pd.Timedelta(days=WINDOW_DAYS)
    history_start = as_of - pd.Timedelta(days=HISTORY_DAYS - 1)
    daily = _daily(store, min(prev_start, history_start))

    current = daily.loc[window_start:as_of]
    previous = daily.loc[prev_start : window_start - pd.Timedelta(days=1)]
    turnover_7d = float(current["turnover"].sum())
    turnover_prev = float(previous["turnover"].sum())
    delta = (turnover_7d - turnover_prev) / turnover_prev if turnover_prev else None

    latest = store.latest
    bands = latest["band"].value_counts()
    ring = latest["ring_flag"].fillna(False).astype(bool)
    linking = latest["linking_payers"].fillna(0)
    history = daily.loc[history_start:as_of].reset_index()
    history["day"] = history["day"].dt.date.astype(str)

    return {
        "as_of": as_of.date().isoformat(),
        "window_days": WINDOW_DAYS,
        "window": {
            "start": window_start.date().isoformat(),
            "end": as_of.date().isoformat(),
            "previous_start": prev_start.date().isoformat(),
        },
        "volume": {
            "turnover_7d": turnover_7d,
            "turnover_previous_7d": turnover_prev,
            "delta_vs_previous": None if delta is None else round(delta, 4),
            "payments_7d": int(current["payments"].sum()),
            "flagged_7d": int(current["flagged"].sum()),
            "flagged_turnover_7d": float(current["flagged_turnover"].sum()),
        },
        "daily": [
            {
                "day": r["day"],
                "payments": int(r["payments"]),
                "turnover": float(r["turnover"]),
                "flagged": int(r["flagged"]),
                "flagged_turnover": float(r["flagged_turnover"]),
            }
            for r in history.to_dict(orient="records")
        ],
        "shops": {
            "monitored": int(len(latest)),
            "high": int(bands.get("high", 0)),
            "review": int(bands.get("review", 0)),
            "low": int(bands.get("low", 0)),
            "alerts": int(bands.get("high", 0) + bands.get("review", 0)),
            "ring_linked": int(ring.sum()),
            "ring_linked_alerts": int((ring & latest["band"].isin(ALERT_BANDS)).sum()),
            "with_linking_payers": int((linking > 0).sum()),
            "mean_risk": round(float(latest["risk"].mean()), 4),
        },
        "recent_flagged_payments": _recent_flagged(store, window_start),
        "model": {
            "payment_model_fingerprint": store.system.payment.fingerprint(),
            "payment_threshold": round(float(store.system.payment.threshold), 4),
            "fusion_weights": {k: _clean(v) for k, v in store.cfg.models.fusion.weights.items()},
            "evidence_timestamp": as_of.isoformat(),
        },
        "note": (
            "Synthetic demo data. Bands request a human review; nothing is blocked automatically."
        ),
    }


def register_overview(app) -> None:
    @app.get("/overview")
    def overview(request: Request) -> dict:
        store = request.app.state.store
        if store is None:
            raise HTTPException(503, "no trained system loaded: run `make demo-data` first")
        if hasattr(store, "overview"):
            return store.overview()
        return overview_payload(store)
