"""Point-in-time features for payments, payers and shops.

`build_features` returns:
  payments  one row per QR payment: payment features + that payer's and that
            shop's history (earlier days only)
  shop_day  one row per (shop, day): used for shop-level scoring
"""

from __future__ import annotations

import pandas as pd

from jachai.features.config import FeatureThresholds
from jachai.features.payer import build_payer_day_features
from jachai.features.payment import build_payment_features
from jachai.features.shop import PEER_KEYS, build_shop_day_features
from jachai.world.config import WorldConfig

ID_COLUMNS = ["payment_id", "ts", "payer_id", "shop_id", "day"]


def build_features(
    tables: dict[str, pd.DataFrame], cfg: WorldConfig, thr: FeatureThresholds
) -> dict[str, pd.DataFrame]:
    pay = build_payment_features(tables, cfg, thr)
    shop_day = build_shop_day_features(pay, tables, cfg, thr)
    payer_day = build_payer_day_features(pay, tables, thr)

    joined = pay.assign(day=pay["ts"].dt.normalize())
    joined = joined.merge(payer_day, on=["payer_id", "day"], how="left", validate="m:1")
    shop_cols = [c for c in shop_day.columns if c not in PEER_KEYS]
    joined = joined.merge(shop_day[shop_cols], on=["shop_id", "day"], how="left", validate="m:1")
    return {"payments": joined, "shop_day": shop_day}


def feature_columns(df: pd.DataFrame) -> list[str]:
    """Numeric model inputs: everything except IDs, timestamps and peer-group labels."""
    skip = set(ID_COLUMNS) | set(PEER_KEYS)
    return [c for c in df.columns if c not in skip and pd.api.types.is_numeric_dtype(df[c])]
