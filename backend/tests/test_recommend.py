"""Recommended next step: config-driven, ordered, never an automatic action."""

import re

from app.recommend import cash_out_demand, recommend
from jachai.labels.config import load_rules

CFG = load_rules().recommendation


def detail(band, ring=False, timeline=None):
    return {
        "scores": {"band": band},
        "neighbourhood": {"ring_flag": ring, "linking_payers": 4, "community_size": 3},
        "timeline": timeline or [],
    }


BIG = [{"payments": 10, "turnover": 400_000, "flagged": 5}]  # ~Tk 200,000 flagged
SMALL = [{"payments": 10, "turnover": 20_000, "flagged": 2}]  # ~Tk 4,000 flagged


def test_demand_is_turnover_times_flagged_share():
    assert cash_out_demand(BIG + SMALL) == 200_000 + 4_000
    assert cash_out_demand([{"payments": 0, "turnover": 5, "flagged": 0}]) == 0


def test_rules_apply_in_order():
    assert recommend(detail("high", ring=True, timeline=BIG), CFG)["action"] == "escalate"
    assert recommend(detail("high", timeline=BIG), CFG)["action"] == "convert"
    assert recommend(detail("high", timeline=SMALL), CFG)["action"] == "educate"
    assert recommend(detail("review", timeline=BIG), CFG)["action"] == "monitor"
    assert recommend(detail("low"), CFG)["action"] == "clear"


def test_text_has_the_evidence_number_in_both_languages():
    r = recommend(detail("high", timeline=BIG), CFG)
    assert "Tk 200,000" in r["en"]
    assert "২০০,০০০" in r["bn"] and not re.search(r"[0-9]", r["bn"])
    assert r["convert_eligible"] is True
    assert "analyst decides" in r["note"]


def test_case_detail_includes_a_recommendation(api):
    client, _, _ = api
    case_id = client.get("/cases").json()["cases"][0]["case_id"]
    rec = client.get(f"/cases/{case_id}").json()["recommendation"]
    assert rec["action"] in {"clear", "monitor", "educate", "convert", "escalate"}
    assert rec["en"] and rec["bn"]


def test_convert_is_never_offered_to_a_ring_or_escalated_case():
    ring = recommend(detail("high", ring=True, timeline=BIG), CFG)
    assert ring["action"] == "escalate" and ring["convert_offer"] == "none"
    review_ring = recommend(detail("review", ring=True, timeline=BIG), CFG)
    assert review_ring["convert_offer"] == "none"


def test_convert_offer_levels():
    assert recommend(detail("high", timeline=BIG), CFG)["convert_offer"] == "recommended"
    assert recommend(detail("review", timeline=BIG), CFG)["convert_offer"] == "secondary"
    assert recommend(detail("high", timeline=SMALL), CFG)["convert_offer"] == "none"
    assert recommend(detail("low"), CFG)["convert_offer"] == "none"


def test_no_agent_lead_for_a_shop_we_clear():
    cleared = recommend(detail("low", timeline=BIG), CFG)
    assert cleared["action"] == "clear" and cleared["convert_offer"] == "none"
