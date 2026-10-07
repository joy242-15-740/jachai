"""The four mechanism columns stay inside what the shop or payer has already done."""

from jachai.features import build_features
from jachai.features.config import load_thresholds


def test_mechanism_features_match_their_definitions(pattern_world):
    built = build_features(pattern_world.tables, pattern_world.config, load_thresholds().features)
    pay = built["payments"]
    for column in (
        "payer_repeat_rate",
        "one_time_payer_share_30d",
        "hour_vs_shop_median_30d",
        "minutes_since_inflow",
    ):
        assert column in pay.columns

    first = pay.sort_values("ts").groupby("payer_id", sort=False).head(1)
    assert (first["payer_repeat_rate"] == 0).all()
    assert pay["payer_repeat_rate"].between(0, 1).all()

    lag = pay["minutes_since_inflow"].dropna()
    assert (lag >= 0).all()

    gap = pay["hour_vs_shop_median_30d"].dropna()
    assert (gap >= 0).all()
    assert (gap <= 24).all()

    share = pay["one_time_payer_share_30d"].dropna()
    assert share.between(0, 1).all()

    # The first calendar day has no shop history, so both shop-history columns are missing.
    first_day = built["shop_day"]["day"].min()
    opening = built["shop_day"][built["shop_day"]["day"] == first_day]
    assert opening["one_time_payer_share_30d"].isna().all()
    assert opening["median_hour_30d"].isna().all()
    assert "median_hour_30d" not in pay.columns


def test_repeat_rate_is_positive_on_a_return_visit(pattern_world):
    pay = build_features(pattern_world.tables, pattern_world.config, load_thresholds().features)[
        "payments"
    ]
    returns = pay[pay["first_visit"] == 0]
    assert not returns.empty
    assert (returns["payer_repeat_rate"] > 0).all()
