"""Reason codes: exact SHAP maths, full coverage, numbers taken from the data."""

import re

import numpy as np
import pytest

from jachai.explain.reasons import (
    feature_to_code,
    load_reason_codes,
    payment_reasons,
    payment_shap,
    placeholder_values,
    render,
    shop_contributions,
    shop_reasons,
)
from jachai.features import feature_columns


@pytest.fixture(scope="module")
def codes():
    return load_reason_codes()


def test_shap_values_add_up_to_the_raw_score(small_system):
    _, system, scored = small_system
    sample = scored.data.payments.head(300)
    shap = payment_shap(system.payment, sample)
    raw = system.payment.booster.predict(
        sample[system.payment.features],
        num_iteration=system.payment.booster.best_iteration,
        raw_score=True,
    )
    np.testing.assert_allclose(shap.sum(axis=1), raw, rtol=1e-6, atol=1e-6)


def test_every_model_feature_and_component_has_a_code(small_system, codes):
    _, system, scored = small_system
    assert set(feature_columns(scored.data.payments)) <= set(feature_to_code(codes))
    assert set(system.fusion.cfg.weights) == set(codes["shop_components"])
    used = set(codes["payment_features"]) | set(codes["shop_components"].values())
    assert used <= set(codes["templates"])
    for code, t in codes["templates"].items():
        assert t["en"] and t["bn"], code


def test_every_template_renders_with_bangla_digits_only(small_system, codes):
    world, _, scored = small_system
    row = scored.data.payments.iloc[0].combine_first(scored.shop_day.iloc[0])
    values = placeholder_values(row, world.config)
    for code in codes["templates"]:
        en, bn = render(code, values, codes)
        assert "{" not in en and "{" not in bn, code
        assert not re.search(r"[0-9]", bn), f"{code}: ASCII digits in Bangla text"


def test_payment_reason_numbers_come_from_the_payment(small_system, codes):
    world, system, scored = small_system
    pay = scored.data.payments
    top = pay.iloc[np.argsort(-scored.payment_proba)[:20]]
    for (_, row), reasons in zip(
        top.iterrows(), payment_reasons(system.payment, top, world.config, codes), strict=True
    ):
        assert 1 <= len(reasons) <= 3
        assert all(r.contribution > 0 for r in reasons)
        for r in reasons:
            if r.code in ("ROUND_AMOUNT", "LARGE_FOR_CATEGORY", "JUST_UNDER_CAP"):
                assert f"{round(row['amount']):,}" in r.en


def test_shop_contributions_add_up_to_the_fused_risk(small_system):
    _, system, scored = small_system
    s = scored.shop_day
    np.testing.assert_allclose(shop_contributions(system.fusion, s).sum(axis=1), s["risk"])


def test_shop_reasons_for_high_band_shops(small_system, codes):
    world, system, scored = small_system
    high = scored.shop_day[scored.shop_day["band"] == "high"].head(10)
    assert len(high)
    for reasons in shop_reasons(system.fusion, high, world.config, codes):
        assert 1 <= len(reasons) <= 3
        assert len({r.code for r in reasons}) == len(reasons)


def test_shop_turnover_reason_quotes_the_real_turnover(small_system, codes):
    world, system, scored = small_system
    s = scored.shop_day
    rows = s[s["turnover_7d"] > 0].head(5)
    for (_, row), _reasons in zip(
        rows.iterrows(), shop_reasons(system.fusion, rows, world.config, codes), strict=True
    ):
        en, _ = render("TURNOVER_IMPLAUSIBLE", placeholder_values(row, world.config), codes)
        assert f"Tk {round(row['turnover_7d'] / 7):,}/day" in en
        assert "Tk 0/day" not in en


def test_missing_column_is_an_error_not_a_zero(small_system, codes):
    from jachai.explain.reasons import MissingData

    world, _, scored = small_system
    row = scored.shop_day.iloc[0].drop("turnover_7d")
    with pytest.raises(MissingData, match="turnover_7d"):
        render("TURNOVER_IMPLAUSIBLE", placeholder_values(row, world.config), codes)
