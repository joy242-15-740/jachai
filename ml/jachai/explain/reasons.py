"""Reason codes: top-3 drivers per payment and per shop, in English and Bangla.

Payments
    SHAP values come from LightGBM itself (`pred_contrib=True`, exact TreeSHAP;
    no extra library). They are in the model's raw score (log-odds) and, with
    the bias term, add up exactly to the raw score. Features are grouped into
    reason codes (configs/reason_codes.yaml); a code's contribution is the sum of
    its features' SHAP values. The 3 codes pushing most towards misuse are shown.

Shops
    The fused risk is a weighted average of component ranks, so each component's
    exact share is weight x rank / total weight (for a linear score that is its
    Shapley value against an all-zero baseline). The 3 largest are shown.

Every number in a reason text is computed from the row's own data here. Nothing
is typed by hand, and an LLM never adds numbers (project safety rule).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from jachai.world.config import DEFAULT_CONFIG_DIR, WorldConfig

BANGLA_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
TOP_K = 3


def load_reason_codes(path: Path | None = None) -> dict[str, Any]:
    with (path or DEFAULT_CONFIG_DIR / "reason_codes.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def feature_to_code(codes: dict[str, Any]) -> dict[str, str]:
    return {f: code for code, feats in codes["payment_features"].items() for f in feats}


# --- number formatting ----------------------------------------------------------


def _taka(x: float) -> str:
    return f"{round(float(x)):,}"


def _pct(x: float) -> str:
    return f"{round(100 * float(x))}"


def _ratio(x: float) -> str:
    return f"{float(x):.1f}"


def to_bangla(text: str) -> str:
    return text.translate(BANGLA_DIGITS)


class MissingData(KeyError):
    """A reason needs a column the row does not have. Never fill in a made-up 0."""


def _get(row: pd.Series, col: str, default: float | None = None) -> float:
    """The row's value. A missing COLUMN is an error; a missing VALUE (NaN, e.g. no
    history yet) uses `default`, which must then be given explicitly."""
    if col not in row.index:
        raise MissingData(f"reason text needs column {col!r}, which this row does not have")
    v = row[col]
    if v is None or (isinstance(v, float) and np.isnan(v)):
        if default is None:
            raise MissingData(f"reason text needs a value for {col!r}, but it is missing")
        return default
    return float(v)


def _placeholders(row: pd.Series, cfg: WorldConfig) -> dict:
    """Placeholder -> function computing it from the row (only run when a template uses it)."""
    limit = cfg.regulation.cash_out_limit_daily
    return {
        "amount": lambda: _taka(_get(row, "amount")),
        "basket_ratio": lambda: _ratio(_get(row, "amount_vs_category_median", 1.0)),
        "hour": lambda: f"{int(_get(row, 'hour'))}",
        "payer_day_total": lambda: _taka(_get(row, "payer_day_total")),
        "payer_day_shops": lambda: f"{int(_get(row, 'payer_day_shops'))}",
        "limit_pct": lambda: _pct(_get(row, "payer_day_total") / limit),
        "limit": lambda: _taka(limit),
        "cap": lambda: _taka(cfg.regulation.qr_incentive_cap),
        "payments_here": lambda: f"{int(_get(row, 'payer_day_payments_here'))}",
        "inflow_pct": lambda: _pct(
            max(
                _get(row, "paid_share_of_recent_inflow", 0.0),
                _get(row, "paid_share_of_recent_remittance", 0.0),
            )
        ),
        "distance_km": lambda: f"{round(_get(row, 'payer_shop_distance_km'))}",
        "payer_payments_7d": lambda: f"{int(_get(row, 'payer_payments_7d', 0.0))}",
        "peer_ratio": lambda: _ratio(_get(row, "turnover_vs_peers_7d", 1.0)),
        "round_pct": lambda: _pct(_get(row, "round_1000_share_30d", 0.0)),
        "night_pct": lambda: _pct(_get(row, "after_hours_share_30d", 0.0)),
        "stranger_pct": lambda: _pct(_get(row, "first_visit_share_30d", 0.0)),
        "qr_codes": lambda: f"{int(_get(row, 'qr_codes_per_account'))}",
        "shop_age_days": lambda: f"{int(_get(row, 'shop_age_days'))}",
        # Shop components
        "top3": lambda: f"{_get(row, 'payment_top3_7d', 0.0):.2f}",
        "flag_pct": lambda: _pct(_get(row, "payment_flag_share_7d", 0.0)),
        "rules_flags": lambda: f"{int(_get(row, 'rules_flags_30d', 0.0))}",
        "actual_daily": lambda: _taka(_get(row, "turnover_7d", 0.0) / 7),
        "expected_daily": lambda: _taka(_get(row, "expected_daily_turnover")),
        "linking_payers": lambda: f"{int(_get(row, 'linking_payers', 0.0))}",
        "community_size": lambda: f"{int(_get(row, 'community_size', 1.0))}",
        "distant_pct": lambda: _pct(_get(row, "distant_payer_share", 0.0)),
    }


class Values(dict):
    """Computes a placeholder only when a template asks for it."""

    def __init__(self, row: pd.Series, cfg: WorldConfig):
        super().__init__()
        self._fns = _placeholders(row, cfg)

    def __missing__(self, key: str) -> str:
        value = self._fns[key]()
        self[key] = value
        return value


def placeholder_values(row: pd.Series, cfg: WorldConfig) -> Values:
    return Values(row, cfg)


@dataclass
class Reason:
    code: str
    contribution: float
    en: str
    bn: str


def render(code: str, values: Values, codes: dict[str, Any]) -> tuple[str, str]:
    t = codes["templates"][code]
    return t["en"].format_map(values), to_bangla(t["bn"].format_map(values))


def top_codes(contrib: pd.Series, k: int = TOP_K) -> list[tuple[str, float]]:
    """The k codes with the largest positive contribution (towards misuse)."""
    pos = contrib[contrib > 0].sort_values(ascending=False)
    return list(pos.head(k).items())


# --- payments -----------------------------------------------------------------------


def payment_shap(model, payments: pd.DataFrame) -> pd.DataFrame:
    """Per-feature SHAP values (raw score) plus the bias column `_bias`."""
    contrib = model.booster.predict(
        payments[model.features], num_iteration=model.booster.best_iteration, pred_contrib=True
    )
    return pd.DataFrame(contrib, columns=[*model.features, "_bias"], index=payments.index)


def payment_reasons(
    model, payments: pd.DataFrame, cfg: WorldConfig, codes: dict[str, Any], k: int = TOP_K
) -> list[list[Reason]]:
    shap = payment_shap(model, payments).drop(columns="_bias")
    by_code = shap.T.groupby(shap.columns.map(feature_to_code(codes))).sum().T
    out = []
    for i, (_, row) in enumerate(payments.iterrows()):
        values = placeholder_values(row, cfg)
        reasons = []
        for code, c in top_codes(by_code.iloc[i], k):
            en, bn = render(code, values, codes)
            reasons.append(Reason(code, float(c), en, bn))
        out.append(reasons)
    return out


# --- shops --------------------------------------------------------------------------


def shop_contributions(fusion, components: pd.DataFrame) -> pd.DataFrame:
    """Each component's exact share of the fused risk: weight * rank / total weight."""
    ranks = fusion.ranks(components)
    w = pd.Series(fusion.cfg.weights)[ranks.columns]
    return ranks * w / w.sum()


def shop_reasons(
    fusion, scored: pd.DataFrame, cfg: WorldConfig, codes: dict[str, Any], k: int = TOP_K
) -> list[list[Reason]]:
    contrib = shop_contributions(fusion, scored).rename(columns=codes["shop_components"])
    out = []
    for i, (_, row) in enumerate(scored.iterrows()):
        values = placeholder_values(row, cfg)
        reasons = []
        for code, c in top_codes(contrib.iloc[i], k):
            en, bn = render(code, values, codes)
            reasons.append(Reason(code, float(c), en, bn))
        out.append(reasons)
    return out
