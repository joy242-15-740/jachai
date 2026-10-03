"""Fusion: one risk score and band per shop-day from the three scores.

Inputs per shop-day (all from earlier days only):
  payment   payment_top3_7d, payment_flag_share_7d  (payment model, last 7 days)
  shop      turnover_z, peer_anomaly                (shop score)
  network   linking_payers, ring_flag, distant_payer_share (network score)

1) Each component becomes a rank: the share of TRAIN shop-days with a strictly
   lower value (0..1). Missing means "no evidence" and ranks 0.
2) Risk = weighted average of the ranks (weights in configs/models.yaml fusion).
3) Bands: cut-offs at the review / high quantiles of VALIDATION shop-days
   (configs/thresholds.yaml bands), saved as fixed numbers and never re-fitted.

The fused score is a ranking, not a probability. It answers "how unusual is this
shop compared with ordinary shop-days", combining independent kinds of evidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from jachai.features.config import BandThresholds
from jachai.models.config import FusionConfig

BANDS = ("low", "review", "high")


def payment_components(
    payments: pd.DataFrame,
    proba: np.ndarray,
    threshold: float,
    shop_day: pd.DataFrame,
    window_days: int,
) -> pd.DataFrame:
    """Per shop-day D, from that shop's payments on days D-window .. D-1.

    payment_top3_7d        mean of the 3 highest payment probabilities in the window
    payment_flag_share_7d  share of the window's payments at or above the threshold
    """
    p = pd.DataFrame(
        {
            "shop_id": payments["shop_id"].to_numpy(),
            "day": payments["ts"].dt.normalize().to_numpy(),
            "p": proba,
            "flag": (proba >= threshold).astype(float),
        }
    )
    # Each day keeps only its 3 best scores; the window's top 3 is among those.
    p = p.sort_values(["shop_id", "day", "p"], ascending=[True, True, False])
    top = p.groupby(["shop_id", "day"]).head(3)[["shop_id", "day", "p"]]
    # Spread each kept score to the shop-days it counts for: D = day+1 .. day+window.
    shifted = pd.concat(
        [top.assign(day=top["day"] + pd.Timedelta(days=k)) for k in range(1, window_days + 1)]
    )
    shifted = shifted.sort_values(["shop_id", "day", "p"], ascending=[True, True, False])
    top3 = shifted.groupby(["shop_id", "day"]).head(3).groupby(["shop_id", "day"])["p"].mean()

    counts = p.groupby(["shop_id", "day"]).agg(flags=("flag", "sum"), n=("p", "size"))
    # Every calendar day from the first payment to the last shop-day, so the rolling
    # window counts earlier payment days even when shop_day does not list them.
    days = pd.date_range(min(p["day"].min(), shop_day["day"].min()), shop_day["day"].max())
    shops = pd.Index(shop_day["shop_id"].unique())
    wide = {
        c: counts[c].unstack("shop_id").reindex(index=days, columns=shops).fillna(0.0)
        for c in ("flags", "n")
    }
    roll = {c: w.rolling(window_days, min_periods=1).sum().shift(1) for c, w in wide.items()}
    share = (roll["flags"] / roll["n"].where(roll["n"] > 0)).stack(future_stack=True)
    share.index = share.index.set_names(["day", "shop_id"])

    key = pd.MultiIndex.from_arrays([shop_day["shop_id"], shop_day["day"]])
    key_rev = pd.MultiIndex.from_arrays([shop_day["day"], shop_day["shop_id"]])
    return pd.DataFrame(
        {
            "payment_top3_7d": top3.reindex(key).to_numpy(),
            "payment_flag_share_7d": share.reindex(key_rev).to_numpy(),
        },
        index=shop_day.index,
    )


@dataclass
class Fusion:
    cfg: FusionConfig
    reference: dict[str, np.ndarray] = field(default_factory=dict)  # sorted train values
    cutoffs: dict[str, float] = field(default_factory=dict)

    def fit_ranks(self, components: pd.DataFrame, train_mask: np.ndarray) -> Fusion:
        for c in self.cfg.weights:
            values = components.loc[train_mask, c].to_numpy(dtype=float)
            self.reference[c] = np.sort(values[~np.isnan(values)])
        return self

    def ranks(self, components: pd.DataFrame) -> pd.DataFrame:
        out = {}
        for c, ref in self.reference.items():
            x = components[c].to_numpy(dtype=float)
            r = np.searchsorted(ref, np.nan_to_num(x, nan=-np.inf), side="left") / max(len(ref), 1)
            out[c] = np.where(np.isnan(x), 0.0, r)
        return pd.DataFrame(out, index=components.index)

    def risk(self, components: pd.DataFrame) -> np.ndarray:
        r = self.ranks(components)
        w = np.array([self.cfg.weights[c] for c in r.columns])
        return r.to_numpy() @ w / w.sum()

    def freeze_bands(self, risk: np.ndarray, bands: BandThresholds) -> Fusion:
        self.cutoffs = {
            "review": float(np.quantile(risk, bands.review_quantile)),
            "high": float(np.quantile(risk, bands.high_quantile)),
        }
        return self

    def band(self, risk: np.ndarray) -> np.ndarray:
        return np.select(
            [risk >= self.cutoffs["high"], risk >= self.cutoffs["review"]],
            ["high", "review"],
            "low",
        )

    def save(self, path: Path) -> None:
        payload = {
            "weights": self.cfg.weights,
            "cutoffs": self.cutoffs,
            "reference": {c: v.tolist() for c, v in self.reference.items()},
        }
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path, cfg: FusionConfig) -> Fusion:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            cfg,
            {c: np.array(v) for c, v in payload["reference"].items()},
            payload["cutoffs"],
        )
