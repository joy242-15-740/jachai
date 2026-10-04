"""Policy simulator: every policy runs and the numbers add up."""

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from jachai.simulate.config import load_simulator_config
from jachai.simulate.policies import POLICIES, SimInputs, run_all, run_policy

DAYS = pd.date_range("2026-10-01", periods=4, freq="D")


def month() -> SimInputs:
    """M1, M2 misuse; H1 honest big seller (passes the cap); H2 honest small shop."""
    rows = []
    for d in DAYS:
        rows += [
            ("M1", d, 20000, 1),
            ("M1", d, 300, 0),
            ("M2", d, 6000, 1),
            ("H1", d, 90000, 0),
            ("H1", d, 30000, 0),
            ("H2", d, 500, 0),
        ]
    pay = pd.DataFrame(rows, columns=["shop_id", "day", "amount", "misuse"])
    pay["ts"] = pay["day"] + pd.to_timedelta(np.arange(len(pay)) % 6, unit="h")
    risk = {"M1": 0.95, "M2": 0.70, "H1": 0.80, "H2": 0.10}
    flags = {"M1": 9, "M2": 1, "H1": 0, "H2": 0}
    sd = pd.DataFrame(
        [
            (
                s,
                d,
                risk[s],
                "high" if risk[s] > 0.9 else ("review" if risk[s] > 0.6 else "low"),
                flags[s],
            )
            for d in DAYS
            for s in risk
        ],
        columns=["shop_id", "day", "risk", "band", "rules_flags_30d"],
    )
    return SimInputs(pay, sd, default_fee_rate=0.0185)


@pytest.fixture
def params():
    return load_simulator_config().params.with_overrides(
        {
            "analyst_recall": 1.0,
            "analyst_false_confirm": 0.0,
            "analyst_capacity_per_day": 1,
            "limit_level": 100000,
            "convert_min_monthly_taka": 0,
            "offer_acceptance": 1.0,
        }
    )


def test_every_policy_runs_and_numbers_add_up(params):
    results = run_all(month(), params)
    assert [r["policy"] for r in results] == list(POLICIES)
    for r in results:
        total = (
            r["misuse_taka_stopped"] + r["misuse_taka_rerouted"] + r["misuse_taka_still_flowing"]
        )
        assert total == pytest.approx(r["misuse_taka_total"]), r["policy"]
        assert r["fees_recaptured"] == pytest.approx(
            r["fee_rate"]
            * (
                r["misuse_taka_rerouted"]
                + params.displaced_to_agents_share * r["misuse_taka_stopped"]
            )
        )
        assert r["analyst_alerts_per_day"] <= params.analyst_capacity_per_day
        assert 0 <= r["genuine_commerce_share"] <= 1
        assert r["agents_signed"] <= r["agent_leads"]


def test_do_nothing_changes_nothing(params):
    a = run_policy("A", month(), params)
    assert a["misuse_taka_stopped"] == a["misuse_taka_rerouted"] == 0
    assert a["honest_shops_restricted"] == 0 and a["blocked_genuine_sales"] == 0
    assert a["fees_recaptured"] == 0 and a["analyst_alerts_per_day"] == 0


def test_blanket_limit_hurts_the_honest_big_seller(params):
    b = run_policy("B", month(), params)
    assert b["honest_shops_restricted"] == 1  # H1 passes Tk 100,000 every day
    assert b["blocked_genuine_sales"] == 4 * 30000
    assert b["misuse_taka_stopped"] == 0  # misuse shops stay under the cap


def test_targeted_review_stops_the_riskiest_shop_from_the_next_day(params):
    d = run_policy("D", month(), params)
    # Day 1 reviews M1 (highest risk) -> stopped from day 2: 3 days x Tk 20,000.
    # Day 2 reviews H1 (risk 0.80, cleared), day 3 reviews M2 -> stopped day 4: Tk 6,000.
    assert d["misuse_taka_stopped"] == 3 * 20000 + 6000
    assert d["honest_shops_restricted"] == 0
    assert d["blocked_sales_at_misuse_shops"] == 3 * 300  # M1's own small sales stop too


def test_rules_only_reviews_only_flagged_shops(params):
    c = run_policy("C", month(), params)
    assert c["misuse_taka_stopped"] == 3 * 20000  # only M1 has >= 3 rule flags
    assert c["analyst_alerts_per_day"] == 1 / 4


def test_convert_reroutes_instead_of_stopping(params):
    e = run_policy("E", month(), params)
    assert e["misuse_taka_stopped"] == 0
    assert e["misuse_taka_rerouted"] == 3 * 20000 + 6000
    assert e["agent_leads"] == e["agents_signed"] == 2
    assert e["fees_recaptured"] == pytest.approx(0.0185 * (3 * 20000 + 6000))


def test_zero_capacity_means_no_reviews(params):
    no_analysts = params.with_overrides({"analyst_capacity_per_day": 0})
    for p in ("C", "D", "E"):
        r = run_policy(p, month(), no_analysts)
        assert r["misuse_taka_stopped"] == r["misuse_taka_rerouted"] == 0


def test_misuse_scale_drops_misuse_shops(params):
    half = run_policy("A", month(), params.with_overrides({"misuse_scale": 0.5}))
    full = run_policy("A", month(), params)
    assert half["misuse_taka_total"] in (4 * 20000, 4 * 6000)
    assert half["misuse_taka_total"] < full["misuse_taka_total"]


def test_fee_rate_slider_and_default(params):
    assert run_policy("E", month(), params)["fee_rate"] == 0.0185  # world.yaml default
    assert run_policy("E", month(), params.with_overrides({"fee_rate": 0.013}))["fee_rate"] == 0.013


def test_bad_override_is_rejected(params):
    with pytest.raises(ValidationError):
        params.with_overrides({"analyst_recall": 2.0})
