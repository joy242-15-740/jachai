"""Peer and trend for one shop. A cue for the analyst, not a new decision score.

The payment, shop and network scores are unchanged. A rising flag does not block
the shop and does not move it into a band by itself.
"""

from __future__ import annotations

from fastapi import HTTPException, Request

from jachai.models.trend import panel_for_shop


def peer_trend_payload(store, shop_id: str) -> dict:
    """Works for the in-memory store. The cached demo has no score series."""
    if not hasattr(store, "scored"):
        return {
            "available": False,
            "shop_id": shop_id,
            "reason_en": (
                "The cached demo has no per-shop score series. "
                "Open the live API for peer and trend."
            ),
            "reason_bn": ("ক্যাশ ডেমোতে দোকানভিত্তিক স্কোরের ধারা নেই। সহপাঠী ও ধারার জন্য লাইভ API খুলুন।"),
        }
    return panel_for_shop(
        shop_id=shop_id,
        shop_day=store.shop_day_features,
        payments=store.scored.data.payments,
        proba=store.scored.payment_proba,
        as_of=store.as_of,
        threshold=float(store.system.payment.threshold),
        shop_row=store.shops.loc[shop_id],
    )


def register_peer_trend(app) -> None:
    @app.get("/shops/{shop_id}/peer-trend")
    def peer_trend(shop_id: str, request: Request) -> dict:
        store = request.app.state.store
        if store is None:
            raise HTTPException(503, "no trained system loaded: run `make demo-data` first")
        if not store.has_shop(shop_id):
            raise HTTPException(404, f"unknown shop {shop_id}")
        return peer_trend_payload(store, shop_id)
