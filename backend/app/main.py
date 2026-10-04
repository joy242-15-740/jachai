"""Jachai API (FastAPI). Run: `make api` (http://127.0.0.1:8000, docs at /docs).

The API only reads trained artifacts and existing reports; it never retrains,
never re-runs evaluations, and never blocks a shop by itself: every action is a
recommendation that a human analyst records as a decision.
"""

from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.settings import Settings

# Reports GET /metrics may serve (all produced by code: make eval / validate-full / sim).
METRIC_REPORTS = (
    "baselines.md",
    "leakage_check.md",
    "ablation.json",
    "validation_evaluation.json",
    "system_training.json",
    "simulator/results.json",
)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="Jachai API", version=__version__)
    app.state.settings = settings
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

    return app


app = create_app()
