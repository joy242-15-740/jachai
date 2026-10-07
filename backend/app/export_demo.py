"""Write the dashboard's demo-mode JSON: `make demo-json` (after `make demo-data`).

Calls the real API (in-process test client) on the fast-profile artifacts and saves
the responses into frontend/public/demo/, so demo mode shows exactly what the live
API would return, never a hand-written mock. Synthetic data only.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings
from jachai.world.config import REPO_ROOT

OUT = REPO_ROOT / "frontend" / "public" / "demo"
TOP_CASES = 25
GRID = {
    "misuse_scale": [0.25, 0.5, 0.75, 1.0],
    "analyst_capacity_per_day": [5, 10, 20, 40],
    "limit_level": [50000, 100000, 200000],
}


def save(name: str, data) -> None:
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    # A throwaway audit log: demo files never contain real decisions.
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["AUDIT_DB_PATH"] = str(Path(tmp) / "demo_audit.sqlite3")
        with TestClient(create_app(Settings())) as client:
            health = client.get("/health").json()
            if client.get("/cases").status_code != 200:
                raise SystemExit("no trained system: run `make demo-data` first")
            save("health.json", {**health, "demo": True})
            save("overview.json", client.get("/overview").json())
            cases = client.get("/cases", params={"limit": 200}).json()
            save("cases.json", cases)
            for c in cases["cases"][:TOP_CASES]:
                save(f"case-{c['case_id']}.json", client.get(f"/cases/{c['case_id']}").json())
            save("fairness.json", client.get("/fairness").json())
            # Simulator grid for demo-mode sliders (real API runs; the page picks the
            # nearest point and recomputes fees exactly for any fee rate).
            grid = []
            for misuse in GRID["misuse_scale"]:
                for capacity in GRID["analyst_capacity_per_day"]:
                    for limit in GRID["limit_level"]:
                        params = {
                            "misuse_scale": misuse,
                            "analyst_capacity_per_day": capacity,
                            "limit_level": limit,
                        }
                        grid.append(client.post("/simulate", json=params).json())
            save("simulate-grid.json", {"axes": GRID, "runs": grid})
            save("metrics.json", client.get("/metrics").json())
    print(f"Demo JSON written to {OUT}")


if __name__ == "__main__":
    main()
