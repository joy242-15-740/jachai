"""Dashboard overview: totals agree with the queue and the per-shop timelines."""

import pandas as pd


def test_overview_matches_queue_and_timelines(api):
    client, store, _ = api
    body = client.get("/overview").json()
    assert body["as_of"] == store.as_of.date().isoformat()
    assert body["window_days"] == 7
    assert len(body["daily"]) == 14
    assert body["daily"][-1]["day"] == body["as_of"]

    # Shop counts are the same shops the queue serves.
    cases = client.get("/cases", params={"limit": 1000}).json()
    shops = body["shops"]
    assert shops["alerts"] == cases["count"] == shops["high"] + shops["review"]
    assert shops["monitored"] == shops["high"] + shops["review"] + shops["low"]
    assert 0 <= shops["ring_linked"] <= shops["monitored"]

    # Seven-day totals are the sum of the last seven daily rows.
    last7 = body["daily"][-7:]
    assert body["volume"]["turnover_7d"] == sum(d["turnover"] for d in last7)
    assert body["volume"]["payments_7d"] == sum(d["payments"] for d in last7)
    assert body["volume"]["flagged_7d"] == sum(d["flagged"] for d in last7)
    assert all(d["flagged_turnover"] <= d["turnover"] for d in body["daily"])

    # Portfolio turnover on a day equals the sum over shops' own timelines.
    pay = store.scored.data.payments
    day = pd.Timestamp(body["daily"][-1]["day"])
    same_day = pay[pay["ts"].dt.normalize() == day]
    assert body["daily"][-1]["turnover"] == float(same_day["amount"].sum())

    # Recent flagged payments: above threshold, at alert-band shops, newest first.
    recent = body["recent_flagged_payments"]
    assert len(recent) <= 6
    assert all(p["score"] >= body["model"]["payment_threshold"] for p in recent)
    assert all(p["band"] in {"review", "high"} for p in recent)
    stamps = [p["ts"] for p in recent]
    assert stamps == sorted(stamps, reverse=True)
    assert body["model"]["payment_model_fingerprint"] == store.system.payment.fingerprint()
    assert "Synthetic" in body["note"]


def test_overview_without_store_is_503(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.settings import Settings

    settings = Settings(
        model_dir=tmp_path / "models",
        world_dir=tmp_path / "world",
        reports_dir=tmp_path / "reports",
        audit_db_path=tmp_path / "audit.sqlite3",
        allowed_origins=["http://localhost:3000"],
    )
    assert TestClient(create_app(settings)).get("/overview").status_code == 503
