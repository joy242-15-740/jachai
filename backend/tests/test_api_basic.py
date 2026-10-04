"""Health, metrics and CORS."""

import json

from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


def client(tmp_path, **kw):
    s = Settings(
        model_dir=tmp_path / "models",
        world_dir=tmp_path / "world",
        reports_dir=tmp_path / "reports",
        audit_db_path=tmp_path / "audit.sqlite3",
        allowed_origins=["http://localhost:3000"],
        **kw,
    )
    return TestClient(create_app(s))


def test_health(tmp_path):
    r = client(tmp_path).get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["model_dir_exists"] is False


def test_metrics_serves_existing_reports_and_lists_missing(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "ablation.json").write_text(json.dumps({"seeds": [42]}), encoding="utf-8")
    (reports / "baselines.md").write_text("# Baselines", encoding="utf-8")
    body = client(tmp_path).get("/metrics").json()
    assert body["reports"]["ablation.json"] == {"seeds": [42]}
    assert body["reports"]["baselines.md"].startswith("# Baselines")
    assert "simulator/results.json" in body["missing"]


def test_cors_allows_only_configured_origins(tmp_path):
    c = client(tmp_path)
    ok = c.get("/health", headers={"Origin": "http://localhost:3000"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    bad = c.get("/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in bad.headers
