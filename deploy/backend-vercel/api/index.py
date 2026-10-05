"""Vercel ASGI entrypoint for the synthetic fast-profile demo API."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "ml"))

os.environ.setdefault("JACHAI_PROFILE", "fast")
os.environ.setdefault("MODEL_DIR", "models/fast")
os.environ.setdefault("REPORTS_DIR", "reports/fast")
os.environ.setdefault("AUDIT_DB_PATH", "/tmp/jachai-audit.sqlite3")
os.environ.setdefault("JACHAI_CACHED_STORE", "1")
os.environ.setdefault("DEMO_DATA_DIR", "frontend/public/demo")
os.environ.setdefault("SIMULATOR_GRID_PATH", "frontend/public/demo/simulate-grid.json")
os.environ.setdefault(
    "ALLOWED_ORIGINS",
    "https://jachai-eta.vercel.app,http://localhost:3000",
)

from app.main import app as fastapi_app  # noqa: E402


class StripFunctionPrefix:
    """Restore the public path after Vercel's internal function rewrite."""

    def __init__(self, application):
        self.application = application

    async def __call__(self, scope, receive, send):
        if scope["type"] in {"http", "websocket"}:
            scope = dict(scope)
            prefix = "/api/index.py"
            path = scope.get("path", "")
            if path.startswith(prefix):
                scope["root_path"] = prefix
                scope["path"] = path.removeprefix(prefix) or "/"
        await self.application(scope, receive, send)


app = StripFunctionPrefix(fastapi_app)
