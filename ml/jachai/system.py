"""The full Jachai scoring system: payment model + shop score + network + fusion.

Fitting rules (all observable data; the hidden truth is never used here):
  payment model   train shops x train dates (rules' votes + past cases)
  shop score      train shops x train dates (no labels)
  network         no fitting; weekly snapshots of earlier payments only
  fusion ranks    train shops x train dates
  fusion bands    validation shops x validation dates, frozen as fixed cut-offs
Test shops and dates are never used for any fitting or choice.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from jachai.eval.splits import shop_groups, time_groups
from jachai.features.config import ThresholdsConfig
from jachai.labels.config import RulesConfig
from jachai.models.config import ModelsConfig
from jachai.models.fusion import Fusion, payment_components
from jachai.models.network import build_network_features, network_as_of
from jachai.models.payment import PaymentModel
from jachai.models.shop import ShopModel
from jachai.models.train import PaymentData, prepare_payment_data, train_from_data
from jachai.world.config import WorldConfig


@dataclass
class System:
    payment: PaymentModel
    shop: ShopModel
    fusion: Fusion


@dataclass
class Scored:
    data: PaymentData  # payment features, split, weak labels, case verdicts
    payment_proba: np.ndarray  # per payment
    shop_day: pd.DataFrame  # one row per shop-day: components, risk, band, split


def shop_day_split(
    shop_day: pd.DataFrame, tables: dict, cfg: WorldConfig, thr: ThresholdsConfig
) -> np.ndarray:
    """'train' / 'validation' / 'test' when shop group and day period match, else ''."""
    group = shop_day["shop_id"].map(shop_groups(tables["shops"], thr, cfg.seed)).to_numpy()
    period = time_groups(shop_day["day"], cfg, thr).to_numpy()
    return np.where(group == period, group, "")


def build_components(
    tables: dict,
    data: PaymentData,
    payment: PaymentModel,
    cfg: WorldConfig,
    thr: ThresholdsConfig,
    rules: RulesConfig,
    models: ModelsConfig,
    shop_day: pd.DataFrame,
) -> tuple[np.ndarray, pd.DataFrame]:
    proba = payment.predict_proba(data.payments)
    comp = payment_components(
        data.payments, proba, payment.threshold, shop_day, models.fusion.payment_window_days
    )
    network = build_network_features(
        tables,
        pd.Timestamp(cfg.calendar.start),
        cfg.calendar.days,
        models.network,
        rules.ring_flag,
        thr.features.far_payer_km,
        cfg.regulation.cash_out_limit_daily,
        cfg.seed,
    )
    comp = comp.join(network_as_of(network, shop_day))
    return proba, comp


def train_system(
    tables: dict,
    shop_day: pd.DataFrame,
    cfg: WorldConfig,
    thr: ThresholdsConfig,
    rules: RulesConfig,
    models: ModelsConfig,
) -> tuple[System, Scored]:
    data = prepare_payment_data(tables, cfg, thr, rules)
    payment = train_from_data(data, models, rules.training_target, cfg.seed)

    split = shop_day_split(shop_day, tables, cfg, thr)
    shop = ShopModel(models.shop_model, cfg.seed).fit(shop_day, split == "train")
    shop_scores = shop.score(shop_day)

    proba, comp = build_components(tables, data, payment, cfg, thr, rules, models, shop_day)
    comp = comp.join(shop_scores[["turnover_z", "peer_anomaly", "expected_daily_turnover"]])

    fusion = Fusion(models.fusion).fit_ranks(comp, split == "train")
    risk = fusion.risk(comp)
    fusion.freeze_bands(risk[split == "validation"], thr.bands)

    # Keep the shop features that reason texts quote (e.g. actual turnover).
    quoted = [
        "turnover_7d",
        "turnover_vs_peers_7d",
        "round_1000_share_30d",
        "after_hours_share_30d",
        "first_visit_share_30d",
    ]
    scored = (
        shop_day[["shop_id", "day", *quoted]]
        .join(comp)
        .assign(risk=risk, band=fusion.band(risk), split=split)
    )
    return System(payment, shop, fusion), Scored(data, proba, scored)
