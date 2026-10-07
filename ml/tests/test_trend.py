"""Peer percentile and the fixed rising rule. No world and no hidden label."""

import pandas as pd
import pytest

from jachai.models.trend import linear_forecast, peer_frame


def _row(shop, turnover, category="tea"):
    return {
        "shop_id": shop,
        "day": pd.Timestamp("2026-10-06"),
        "category": category,
        "area_type": "urban",
        "size_tier": "small",
        "turnover_7d": turnover,
        "round_1000_share_30d": 0.2,
        "far_payer_share_30d": 0.1,
    }


def test_percentile_stays_inside_category_area_and_size():
    frame = pd.DataFrame(
        [_row("a", 10), _row("b", 20), _row("c", 30), _row("other", 5, category="pharmacy")]
    )
    out = peer_frame(frame).set_index("shop_id")
    tea = out.loc[["a", "b", "c"], "turnover_7d_percentile"].to_numpy()
    assert tea == pytest.approx([100 / 3, 200 / 3, 100])
    assert out.loc["other", "peer_shops"] == 1
    assert out.loc["a", "peer_shops"] == 3


def test_a_climbing_line_is_rising_and_a_flat_line_is_not():
    climbing = [0.10 + 0.02 * i for i in range(14)]
    fitted = linear_forecast(climbing)
    assert fitted["rising"] is True
    assert fitted["forecast"][-1] > climbing[-1]

    assert linear_forecast([0.2] * 14)["rising"] is False
    short = linear_forecast([0.1, None, 0.2])
    assert short["rising"] is False
    assert short["slope_per_day"] is None
