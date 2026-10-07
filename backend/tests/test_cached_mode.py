"""The serverless demo (JACHAI_CACHED_STORE=1) must import and answer without the ML
libraries. Vercel installs only requirements.txt (FastAPI, pydantic, numpy, pandas,
PyYAML), so a route module that imports LightGBM, scikit-learn or networkx at import
time takes the whole public API down with FUNCTION_INVOCATION_FAILED.

Runs in a subprocess so the import guard cannot leak into other tests."""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEMO_DIR = REPO / "frontend" / "public" / "demo"

SCRIPT = textwrap.dedent(
    """
    import builtins, json, sys
    blocked = {"sklearn", "lightgbm", "xgboost", "networkx", "joblib", "pyarrow", "scipy"}
    real_import = builtins.__import__

    def guard(name, *args, **kwargs):
        if name.split(".")[0] in blocked:
            raise ImportError(f"{name} is not installed on the serverless demo")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = guard
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        top = client.get("/cases").json()["cases"][0]["case_id"]
        out = {
            "health": client.get("/health").status_code,
            "cases": client.get("/cases").status_code,
            "case": client.get(f"/cases/{top}").status_code,
            "overview": client.get("/overview").status_code,
            "fairness": client.get("/fairness").status_code,
            "simulate": client.post("/simulate", json={}).status_code,
            "peer_trend": client.get(f"/shops/{top}/peer-trend").json()["available"],
            "metrics": client.get("/metrics").status_code,
        }
    print(json.dumps(out))
    """
)


def test_cached_demo_serves_without_ml_libraries(tmp_path):
    env = {
        **os.environ,
        "JACHAI_CACHED_STORE": "1",
        "JACHAI_PROFILE": "fast",
        "DEMO_DATA_DIR": str(DEMO_DIR),
        "SIMULATOR_GRID_PATH": str(DEMO_DIR / "simulate-grid.json"),
        "AUDIT_DB_PATH": str(tmp_path / "audit.sqlite3"),
        "REPORTS_DIR": str(tmp_path / "reports"),
        "PYTHONPATH": os.pathsep.join([str(REPO / "backend"), str(REPO / "ml")]),
    }
    proc = subprocess.run(
        [sys.executable, "-c", SCRIPT], env=env, capture_output=True, text=True, cwd=REPO
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert out == {
        "health": 200,
        "cases": 200,
        "case": 200,
        "overview": 200,
        "fairness": 200,
        "simulate": 200,
        "peer_trend": False,
        "metrics": 200,
    }
