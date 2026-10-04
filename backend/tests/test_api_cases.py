"""Scoring, shops and cases endpoints."""

import json

from jachai.world.world import TRUE_LABEL


def test_cases_sorted_by_risk_and_filtered_by_band(api):
    client, _, _ = api
    body = client.get("/cases").json()
    assert body["count"] == len(body["cases"]) > 0
    risks = [c["risk"] for c in body["cases"]]
    assert risks == sorted(risks, reverse=True)
    assert {c["band"] for c in body["cases"]} <= {"review", "high"}
    high = client.get("/cases", params={"band": "high"}).json()["cases"]
    assert all(c["band"] == "high" for c in high)
    assert client.get("/cases", params={"band": "low"}).status_code == 422


def test_case_detail_has_every_part(api):
    client, _, _ = api
    case_id = client.get("/cases").json()["cases"][0]["case_id"]
    d = client.get(f"/cases/{case_id}").json()
    assert set(d) >= {"scores", "reasons", "riskiest_payments", "neighbourhood", "timeline"}
    assert 1 <= len(d["reasons"]) <= 3
    assert all(r["en"] and r["bn"] for r in d["reasons"])
    assert d["scores"]["status"].startswith("needs review")
    assert len(d["timeline"]) > 0
    assert client.get("/cases/NOPE").status_code == 404


def test_shop_endpoint(api):
    client, store, _ = api
    shop_id = store.shops.index[0]
    body = client.get(f"/shops/{shop_id}").json()
    assert body["shop_id"] == shop_id
    assert body["scores"]["band"] in ("low", "review", "high")
    assert client.get("/shops/NOPE").status_code == 404


def test_no_hidden_truth_or_harsh_words_in_responses(api):
    client, _, _ = api
    case_id = client.get("/cases").json()["cases"][0]["case_id"]
    text = json.dumps(client.get(f"/cases/{case_id}").json()) + json.dumps(
        client.get("/cases").json()
    )
    assert "_true_" not in text and TRUE_LABEL not in text
    for word in ("criminal", "fraudster", "guilty"):
        assert word not in text.lower()


def test_score_transaction(api):
    client, store, world = api
    shop_id = store.shops.index[0]
    payer_id = store.customers.index[0]
    r = client.post(
        "/score/transaction",
        json={
            "shop_id": shop_id,
            "payer_id": payer_id,
            "amount": 20000,
            "ts": "2026-10-20T22:30:00",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert 0 <= body["score"] <= 1
    assert body["status"] in ("needs review", "no action")
    assert "analyst decides" in body["note"]
    bad = client.post(
        "/score/transaction",
        json={"shop_id": "NOPE", "payer_id": payer_id, "amount": 1, "ts": "2026-10-20T10:00:00"},
    )
    assert bad.status_code == 404
    invalid = client.post(
        "/score/transaction",
        json={"shop_id": shop_id, "payer_id": payer_id, "amount": -5, "ts": "2026-10-20T10:00:00"},
    )
    assert invalid.status_code == 422


def test_without_artifacts_the_api_says_so(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.settings import Settings

    s = Settings(
        model_dir=tmp_path / "none",
        world_dir=tmp_path / "none",
        reports_dir=tmp_path,
        audit_db_path=tmp_path / "a.db",
        allowed_origins=[],
    )
    with TestClient(create_app(s)) as c:
        assert c.get("/cases").status_code == 503
        assert "demo-data" in c.get("/cases").json()["detail"]
