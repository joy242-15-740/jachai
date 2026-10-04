"""Backend settings, read from environment variables (placeholders in .env.example).

MODEL_DIR        trained system (make train / make demo-data); default: the active
                 profile's model dir, else models/
JACHAI_DATA_DIR  generated world; default: the profile's data dir, else data/
REPORTS_DIR      existing reports served by GET /metrics; default: reports/
AUDIT_DB_PATH    SQLite file for the append-only decision log
ALLOWED_ORIGINS  comma-separated origins allowed by CORS (the dashboard URL)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from jachai.world.config import REPO_ROOT
from jachai.world.summary import default_model_dir, default_world_dir


def _origins(raw: str) -> list[str]:
    return [o.strip() for o in raw.split(",") if o.strip()]


@dataclass(frozen=True)
class Settings:
    model_dir: Path = field(default_factory=default_model_dir)
    world_dir: Path = field(default_factory=default_world_dir)
    reports_dir: Path = field(
        default_factory=lambda: REPO_ROOT / os.environ.get("REPORTS_DIR", "reports")
    )
    audit_db_path: Path = field(
        default_factory=lambda: REPO_ROOT / os.environ.get("AUDIT_DB_PATH", "data/audit.sqlite3")
    )
    allowed_origins: list[str] = field(
        default_factory=lambda: _origins(os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000"))
    )
