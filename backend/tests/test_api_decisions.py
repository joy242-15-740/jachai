"""Decisions (append-only audit log), simulator and fairness endpoints."""

import sqlite3

import pytest

from app.audit import AuditLog


def first_case(client):
    return client.get("/cases").json()["cases"][0]["case_id"]


def test_decision_is_recorded_and_shown_in_case_history(api):
    client, _, _ = api
    case_id = first_case(client)
    body = {
        "decision": "monitor",
        "reason": "Large round amounts at night; watch 2 weeks.",
        "analyst": "A-01",
    }
    r = client.post(f"/cases/{case_id}/decision", json=body)
    assert r.status_code == 201
    row = r.json()
    assert row["decision"] == "monitor" and row["case_id"] == case_id
    assert "No automatic action" in row["note"]
    history = client.get(f"/cases/{case_id}").json()["decisions"]
    assert history[-1]["reason"] == body["reason"]


def test_decision_validation(api):
    client, _, _ = api
    case_id = first_case(client)
    ok = {"decision": "clear", "reason": "Genuine wholesale orders.", "analyst": "A-02"}
    assert (
        client.post(f"/cases/{case_id}/decision", json={**ok, "decision": "ban"}).status_code == 422
    )
    assert client.post(f"/cases/{case_id}/decision", json={**ok, "reason": "ok"}).status_code == 422
    assert client.post(f"/cases/{case_id}/decision", json={**ok, "analyst": ""}).status_code == 422
    assert client.post("/cases/NOPE/decision", json=ok).status_code == 404


def test_every_decision_type_is_accepted(api):
    client, _, _ = api
    case_id = first_case(client)
    for d in ("clear", "monitor", "educate", "convert", "restrict", "escalate"):
        r = client.post(
            f"/cases/{case_id}/decision",
            json={"decision": d, "reason": f"Testing the {d} decision path.", "analyst": "A-03"},
        )
        assert r.status_code == 201, d


def test_audit_log_refuses_updates_and_deletes(tmp_path):
    log = AuditLog(tmp_path / "audit.sqlite3")
    log.append("SH1", "monitor", "first decision here", "A-1", 0.9, "high")
    log.append("SH1", "clear", "second decision here", "A-2", 0.9, "high")
    db = sqlite3.connect(tmp_path / "audit.sqlite3")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute("UPDATE decisions SET decision = 'clear' WHERE id = 1")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.execute("DELETE FROM decisions WHERE id = 1")
    assert log.verify()
    assert not hasattr(log, "update") and not hasattr(log, "delete")


def test_tampering_behind_the_api_is_detected(tmp_path):
    path = tmp_path / "audit.sqlite3"
    log = AuditLog(path)
    log.append("SH1", "monitor", "first decision here", "A-1", 0.9, "high")
    log.append("SH1", "clear", "second decision here", "A-2", 0.9, "high")
    db = sqlite3.connect(path)
    db.executescript(
        "DROP TRIGGER decisions_no_update;"
        "UPDATE decisions SET reason = 'edited later' WHERE id = 1;"
    )
    db.commit()
    assert not log.verify()


def test_simulate_defaults_and_sliders(api):
    client, _, _ = api
    body = client.post("/simulate", json={}).json()
    assert [r["policy"] for r in body["results"]] == ["A", "B", "C", "D", "E"]
    for r in body["results"]:
        total = (
            r["misuse_taka_stopped"] + r["misuse_taka_rerouted"] + r["misuse_taka_still_flowing"]
        )
        assert total == pytest.approx(r["misuse_taka_total"])
    no_analysts = client.post("/simulate", json={"analyst_capacity_per_day": 0}).json()
    for r in no_analysts["results"]:
        if r["policy"] in ("C", "D", "E"):
            assert r["misuse_taka_stopped"] == r["misuse_taka_rerouted"] == 0
    assert no_analysts["params"]["analyst_capacity_per_day"] == 0


def test_simulate_rejects_bad_values(api):
    client, _, _ = api
    assert client.post("/simulate", json={"analyst_recall": 2.0}).status_code == 422
    assert client.post("/simulate", json={"unknown_slider": 1}).status_code == 422


def test_fairness(api):
    client, store, _ = api
    body = client.get("/fairness").json()
    assert "test set not used" in body["evaluated_on"]
    for key in ("by_area_type", "by_size_tier", "by_category"):
        for g in body[key]:
            assert g["false_alarm_rate"] is None or 0 <= g["false_alarm_rate"] <= 1
            assert g["false_alarms"] <= g["honest_shops"]
    assert {g["group"] for g in body["by_area_type"]} <= {
        "dhaka_urban",
        "district_town",
        "rural_haat",
    }
    text = str(body)
    assert not any(shop in text for shop in store.shops.index[:50])  # group totals only
