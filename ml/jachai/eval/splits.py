"""Train / validation / test split, by shop and by time, with one held-out pattern.

  by shop   every shop belongs to exactly one group (stable hash of its ID), so
            the model is always tested on shops it has never seen
  by time   train < validation < test in calendar order; the warm-up days, which
            lack history, are skipped
  held out  every shop running `split.holdout_pattern` goes to test, and that
            pattern's payments are removed from train and validation: the model
            is never trained or tuned on it, so test recall on it shows whether
            Jachai catches a trick it has never seen

Assigning held-out shops to test uses the hidden truth. That is fine: it only
decides where rows go, never what a model sees as input or label.
"""

from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

from jachai.features.config import ThresholdsConfig
from jachai.world.config import WorldConfig
from jachai.world.world import TRUE_PATTERN

GROUPS = ("train", "validation", "test")


def shop_groups(shops: pd.DataFrame, thr: ThresholdsConfig, seed: int) -> pd.Series:
    """shop_id -> 'train' / 'validation' / 'test'."""
    shares = thr.split.shop_shares
    u = shops["shop_id"].map(lambda s: zlib.crc32(f"split:{seed}:{s}".encode()) / 2**32)
    edges = np.cumsum([shares["train"], shares["validation"]])
    group = np.select([u < edges[0], u < edges[1]], ["train", "validation"], "test")
    group = pd.Series(group, index=shops["shop_id"].to_numpy(), name="group")
    holdout = thr.split.holdout_pattern
    if holdout:
        held = shops.loc[shops[TRUE_PATTERN] == holdout, "shop_id"].to_numpy()
        group.loc[held] = "test"
    return group


def time_groups(ts: pd.Series, cfg: WorldConfig, thr: ThresholdsConfig) -> pd.Series:
    """Each timestamp -> its period ('warmup', 'train', 'validation', 'test')."""
    day = ts.dt.normalize()
    start = pd.Timestamp(cfg.calendar.start) + pd.Timedelta(days=thr.eval.warmup_days)
    train_end = pd.Timestamp(thr.split.train_end)
    val_end = pd.Timestamp(thr.split.validation_end)
    period = np.select(
        [day < start, day <= train_end, day <= val_end], ["warmup", "train", "validation"], "test"
    )
    return pd.Series(period, index=ts.index)


def assign_split(
    payments: pd.DataFrame,
    tables: dict[str, pd.DataFrame],
    cfg: WorldConfig,
    thr: ThresholdsConfig,
) -> pd.Series:
    """For each payment row: 'train', 'validation', 'test' or '' (not used).

    A row is used only when its shop's group equals its time period. Held-out
    pattern rows are never in train or validation.
    """
    groups = shop_groups(tables["shops"], thr, cfg.seed)
    shop_group = payments["shop_id"].map(groups).to_numpy()
    period = time_groups(payments["ts"], cfg, thr).to_numpy()
    split = np.where(shop_group == period, shop_group, "")
    holdout = thr.split.holdout_pattern
    if holdout:
        pattern = payments["payment_id"].map(
            tables["qr_payments"].set_index("payment_id")[TRUE_PATTERN]
        )
        split = np.where((pattern.to_numpy() == holdout) & (split != "test"), "", split)
    return pd.Series(split, index=payments.index, name="split")
