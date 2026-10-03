"""Labeling functions: one per misuse typology, plus two that vote "honest".

Each function looks at feature rows and returns, per row:
     1  looks like misuse
     0  looks honest
    -1  ABSTAIN (no opinion)
They are deliberately simple, readable rules over point-in-time features. They
never read the hidden truth. Their thresholds live in configs/rules.yaml.

`level` says which table a function votes on: "payment" (one row per QR payment)
or "shop_day" (one row per shop and day).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from jachai.labels.config import LFSpec
from jachai.world.config import WorldConfig

ABSTAIN, HONEST, MISUSE = -1, 0, 1


@dataclass(frozen=True)
class LabelingFunction:
    name: str
    level: str  # "payment" or "shop_day"
    vote: int  # the label it gives when it fires: MISUSE or HONEST
    fires: Callable[[pd.DataFrame, LFSpec, WorldConfig], pd.Series]

    def __call__(self, df: pd.DataFrame, spec: LFSpec, cfg: WorldConfig) -> np.ndarray:
        hit = self.fires(df, spec, cfg).fillna(False).to_numpy(dtype=bool)
        return np.where(hit, self.vote, ABSTAIN).astype(np.int8)


REGISTRY: dict[str, LabelingFunction] = {}


def labeling_function(level: str, vote: int):
    def wrap(fn: Callable[[pd.DataFrame, LFSpec, WorldConfig], pd.Series]):
        REGISTRY[fn.__name__] = LabelingFunction(fn.__name__, level, vote, fn)
        return fn

    return wrap


# --- Misuse votes on payments -------------------------------------------------


@labeling_function("payment", MISUSE)
def lf_cash_desk(df, s, cfg):
    stranger = df["first_visit"] == 1
    night_or_far = (df["after_hours"] == 1) | (df["payer_shop_distance_km"] >= s.param("far_km"))
    return (
        (df["is_round_1000"] == 1)
        & (df["amount"] >= s.param("min_amount"))
        & stranger
        & night_or_far
    )


@labeling_function("payment", MISUSE)
def lf_remittance_drain(df, s, cfg):
    return (df["paid_share_of_recent_remittance"] >= s.param("min_paid_share")) & (
        df["payer_shop_distance_km"] >= s.param("min_distance_km")
    )


@labeling_function("payment", MISUSE)
def lf_turnover_burst(df, s, cfg):
    return (
        (df["first_visit"] == 1)
        & (df["amount_vs_category_median"] >= s.param("min_amount_vs_median"))
        & (df["payer_shop_distance_km"] >= s.param("min_distance_km"))
    )


@labeling_function("payment", MISUSE)
def lf_limit_bypass(df, s, cfg):
    over = df["payer_day_total"] > cfg.regulation.cash_out_limit_daily
    round_piece = df["amount"] % s.param("round_unit") == 0
    return over & round_piece & (df["payer_day_shops"] >= s.param("min_shops_today"))


@labeling_function("payment", MISUSE)
def lf_incentive_splitting(df, s, cfg):
    return (
        (df["just_under_cap"] == 1)
        & (df["after_regime_change"] == 1)
        & (df["payer_day_payments_here"] >= s.param("min_payments_here_today"))
    )


# --- Honest votes on payments ---------------------------------------------------


@labeling_function("payment", HONEST)
def lf_honest_small_ticket(df, s, cfg):
    return (
        (df["amount_vs_category_median"] <= s.param("max_amount_vs_median"))
        & (df["just_under_cap"] == 0)
        & (df["near_limit"] == 0)
    )


@labeling_function("payment", HONEST)
def lf_honest_regular_customer(df, s, cfg):
    return (
        (df["first_visit"] == 0)
        & (df["payer_shop_distance_km"] <= s.param("max_distance_km"))
        & (df["is_round_1000"] == 0)
    )


# --- Misuse votes on shop-days --------------------------------------------------


@labeling_function("shop_day", MISUSE)
def lf_p2p_disguise(df, s, cfg):
    return df["owner_p2p_senders_7d"] >= s.param("min_p2p_senders_7d")


def apply_lfs(df: pd.DataFrame, level: str, rules, cfg: WorldConfig) -> pd.DataFrame:
    """Vote matrix: one column per labeling function of this level, values -1/0/1.

    Every function in configs/rules.yaml must be registered, and every registered
    function must be configured, so the two can never drift apart."""
    configured = set(rules.labeling_functions)
    missing = configured - set(REGISTRY)
    unconfigured = set(REGISTRY) - configured
    if missing or unconfigured:
        raise KeyError(
            f"rules.yaml vs code mismatch: unknown {sorted(missing)}, "
            f"unconfigured {sorted(unconfigured)}"
        )
    return pd.DataFrame(
        {
            name: lf(df, rules.labeling_functions[name], cfg)
            for name, lf in REGISTRY.items()
            if lf.level == level
        },
        index=df.index,
    )
