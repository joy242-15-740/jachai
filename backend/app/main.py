"""Jachai API (FastAPI). Run: `make api` (http://127.0.0.1:8000, docs at /docs).

The API only reads trained artifacts and existing reports; it never retrains,
never re-runs evaluations, and never blocks a shop by itself: every action is a
recommendation that a human analyst records as a decision.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from app import __version__
from app.settings import Settings
from app.store import Store


class TransactionIn(BaseModel):
    """One QR payment to score. IDs must exist in the loaded (synthetic) world."""

    model_config = ConfigDict(extra="forbid")
    shop_id: str
    payer_id: str
    amount: int = Field(gt=0, le=10_000_000)
    ts: datetime


def get_store(request: Request) -> Store:
    store = request.app.state.store
    if store is None:
        raise HTTPException(503, "no trained system loaded: run `make demo-data` first")
    return store


# Reports GET /metrics may serve (all produced by code: make eval / validate-full / sim).
METRIC_REPORTS = (
    "baselines.md",
    "leakage_check.md",
    "ablation.json",
    "validation_evaluation.json",
    "system_training.json",
    "simulator/results.json",
)


def create_app(settings: Settings | None = None, store: Store | None = None) -> FastAPI:
    """`store` lets tests pass a ready store; otherwise it is built at startup from
    MODEL_DIR and the data dir (skipped, with 503s, if artifacts are missing)."""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.store is None and settings.model_dir.exists() and settings.world_dir.exists():
            app.state.store = Store(settings.model_dir, settings.world_dir)
        yield

    app = FastAPI(title="Jachai API", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.store = store
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health")
    def health() -> dict:
        s = app.state.settings
        return {
            "status": "ok",
            "version": __version__,
            "model_dir_exists": s.model_dir.exists(),
            "world_dir_exists": s.world_dir.exists(),
        }

    @app.get("/metrics")
    def metrics() -> dict:
        """Existing reports, read from disk as they are. Nothing is recomputed."""
        out, missing = {}, []
        for name in METRIC_REPORTS:
            path = app.state.settings.reports_dir / name
            if not path.exists():
                missing.append(name)
            elif path.suffix == ".json":
                out[name] = json.loads(path.read_text(encoding="utf-8"))
            else:
                out[name] = path.read_text(encoding="utf-8")
        return {"reports": out, "missing": missing, "note": "synthetic data; see reports/"}

    @app.post("/score/transaction")
    def score_transaction(tx: TransactionIn, request: Request) -> dict:
        store = get_store(request)
        if not store.has_shop(tx.shop_id):
            raise HTTPException(404, f"unknown shop {tx.shop_id}")
        if tx.payer_id not in store.customers.index:
            raise HTTPException(404, f"unknown payer {tx.payer_id}")
        ts = pd.Timestamp(tx.ts).tz_localize(None)
        return store.score_transaction(tx.shop_id, tx.payer_id, tx.amount, ts)

    @app.get("/shops/{shop_id}")
    def shop(shop_id: str, request: Request) -> dict:
        store = get_store(request)
        if not store.has_shop(shop_id):
            raise HTTPException(404, f"unknown shop {shop_id}")
        return {
            **store.shop_profile(shop_id),
            "scores": store.shop_scores(shop_id),
            "reasons": store.shop_reasons([shop_id])[0],
        }

    @app.get("/cases")
    def cases(
        request: Request,
        band: Literal["review", "high"] | None = None,
        limit: int = Query(100, ge=1, le=1000),
    ) -> dict:
        store = get_store(request)
        items = store.cases(band, limit)
        return {"as_of": store.as_of.date().isoformat(), "count": len(items), "cases": items}

    @app.get("/cases/{case_id}")
    def case(case_id: str, request: Request) -> dict:
        store = get_store(request)
        if not store.has_shop(case_id):
            raise HTTPException(404, f"unknown case {case_id}")
        return store.case_detail(case_id)

    return app


app = create_app()
