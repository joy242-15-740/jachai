"""Shop score parts: turnover plausibility and odd behaviour among peers.

Both work on shop-day rows (features from earlier days only) and are fitted on
TRAIN shops in the TRAIN period only. They use no labels at all, so they can
flag tricks no rule describes.

1) Turnover plausibility
   A gradient-boosted regression predicts a shop's usual daily QR turnover
   (log scale) from what the shop IS: category, area type, size tier. The
   residual (actual minus expected) is turned into a robust z-score with the
   median and the median absolute deviation (MAD) of the training residuals, so
   a few misuse shops cannot distort "normal".
   turnover_z > 0: busier than a shop like this should be.

2) Peer anomaly
   An Isolation Forest per peer group (category x area type) scores how unusual
   a shop's behaviour is among similar shops: round receipts, after-hours share,
   strangers, far-away payers, payers per day, turnover vs peers, burstiness.
   Groups with too few shops fall back to the category alone.
   peer_anomaly: higher = more unusual.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, IsolationForest

from jachai.models.config import ShopModelConfig

MAD_TO_STD = 1.4826  # scales a MAD to a standard deviation for normal data


def _daily_turnover(shop_day: pd.DataFrame) -> pd.Series:
    """Average daily turnover over the previous 7 days, log scale."""
    return np.log1p(shop_day["turnover_7d"] / 7)


def _behaviour(shop_day: pd.DataFrame, cfg: ShopModelConfig) -> pd.DataFrame:
    x = shop_day[cfg.isolation_forest.features].astype(float).copy()
    for col in cfg.isolation_forest.log_features:
        x[col] = np.log1p(x[col].clip(lower=0))
    return x.fillna(0.0)


@dataclass
class ShopModel:
    cfg: ShopModelConfig
    seed: int
    turnover_model: HistGradientBoostingRegressor | None = None
    residual_median: float = 0.0
    residual_scale: float = 1.0
    forests: dict[str, IsolationForest] = field(default_factory=dict)

    # --- peer groups ---------------------------------------------------------------
    def _group_key(self, shop_day: pd.DataFrame) -> pd.Series:
        cols = self.cfg.isolation_forest.peer_group
        return shop_day[cols].astype(str).agg("|".join, axis=1)

    def _assign_groups(self, shop_day: pd.DataFrame) -> pd.Series:
        """Peer group per row; groups not fitted (too small) fall back to category."""
        full = self._group_key(shop_day)
        return full.where(full.isin(self.forests), shop_day["category"].astype(str))

    # --- fit -----------------------------------------------------------------------
    def fit(self, shop_day: pd.DataFrame, train_mask: np.ndarray) -> ShopModel:
        t = self.cfg.turnover
        rows = shop_day[train_mask & shop_day["turnover_7d"].notna().to_numpy()]
        rows = rows[rows["is_open"] == 1]
        x = rows[t.inputs].astype("category")
        self.turnover_model = HistGradientBoostingRegressor(
            loss=t.loss,
            max_iter=t.max_iter,
            learning_rate=t.learning_rate,
            categorical_features="from_dtype",
            random_state=self.seed,
        ).fit(x, _daily_turnover(rows))
        self._categories = {c: x[c].cat.categories for c in t.inputs}
        resid = _daily_turnover(rows) - self.turnover_model.predict(x)
        self.residual_median = float(np.median(resid))
        mad = float(np.median(np.abs(resid - self.residual_median)))
        self.residual_scale = max(mad * MAD_TO_STD, 1e-6)

        f = self.cfg.isolation_forest
        days = (rows["day"] - rows["day"].min()).dt.days
        snap = rows[days % f.snapshot_every_days == 0]
        x_beh = _behaviour(snap, self.cfg)
        full = self._group_key(snap)
        shops_per_group = snap.groupby(full)["shop_id"].nunique()
        groups = {g: full == g for g in shops_per_group.index[shops_per_group >= f.min_peer_shops]}
        # Category-level fallback forests for rows in small groups.
        for cat in snap["category"].astype(str).unique():
            groups.setdefault(cat, snap["category"].astype(str) == cat)
        for key, mask in groups.items():
            self.forests[key] = IsolationForest(
                n_estimators=f.n_estimators, random_state=self.seed
            ).fit(x_beh[mask.to_numpy()])
        return self

    # --- score ---------------------------------------------------------------------
    def score(self, shop_day: pd.DataFrame) -> pd.DataFrame:
        t = self.cfg.turnover
        x = pd.DataFrame(
            {
                c: pd.Categorical(shop_day[c].astype(str), categories=self._categories[c])
                for c in t.inputs
            },
            index=shop_day.index,
        )
        expected = self.turnover_model.predict(x)
        resid = _daily_turnover(shop_day) - expected
        z = (resid - self.residual_median) / self.residual_scale

        x_beh = _behaviour(shop_day, self.cfg)
        group = self._assign_groups(shop_day)
        anomaly = pd.Series(np.nan, index=shop_day.index)
        for key, idx in group.groupby(group).groups.items():
            forest = self.forests.get(key)
            if forest is not None:
                # score_samples: lower = more abnormal; flip so higher = odder.
                anomaly.loc[idx] = -forest.score_samples(x_beh.loc[idx])
        return pd.DataFrame(
            {
                "shop_id": shop_day["shop_id"].to_numpy(),
                "day": shop_day["day"].to_numpy(),
                "expected_daily_turnover": np.expm1(expected).round(0),
                "turnover_z": z.to_numpy(),
                "peer_anomaly": anomaly.to_numpy(),
                "peer_group": group.to_numpy(),
            },
            index=shop_day.index,
        )
