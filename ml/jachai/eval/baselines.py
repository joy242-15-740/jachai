"""Two baselines Jachai has to beat (CLAUDE.md "Evaluation protocol").

rules_only     the labeling functions alone, used as a detector: the best a
               hand-written rulebook can do, with no model.
blanket_limit  every merchant gets the same daily QR cap, whatever its size or
               trade: the "limit every shop" policy our pitch argues against.

Both are scored on the evaluation window (after the warm-up days, which lack
history) against the hidden truth, at payment level and shop level.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from jachai.eval import metrics as m
from jachai.features.config import ThresholdsConfig
from jachai.labels import weak_label_table
from jachai.labels.config import RulesConfig
from jachai.world.config import WorldConfig
from jachai.world.world import TRUE_LABEL, TRUE_PATTERN


@dataclass
class BaselineResult:
    name: str
    payment_score: pd.Series  # index: payment_id
    payment_flag: pd.Series
    shop_score: pd.Series  # index: shop_id
    shop_flag: pd.Series


def evaluation_window(payments: pd.DataFrame, cfg: WorldConfig, warmup_days: int) -> pd.Series:
    start = pd.Timestamp(cfg.calendar.start) + pd.Timedelta(days=warmup_days)
    return payments["ts"] >= start


def rules_only(
    feats: dict[str, pd.DataFrame], rules: RulesConfig, cfg: WorldConfig, in_window: pd.Series
) -> BaselineResult:
    pay = feats["payments"][in_window.to_numpy()]
    weak = weak_label_table(pay, "payment", rules, cfg)
    score = pd.Series(np.nan_to_num(weak["weak_proba"].to_numpy()), index=pay["payment_id"])
    flag = pd.Series(weak["weak_label"].to_numpy() == 1, index=pay["payment_id"])

    flagged_per_shop = flag.groupby(pay["shop_id"].to_numpy()).sum()
    shop_day = feats["shop_day"]
    sd = shop_day[shop_day["day"] >= pay["ts"].min().normalize()]
    sd_weak = weak_label_table(sd, "shop_day", rules, cfg)
    shop_day_hit = (
        pd.Series(sd_weak["weak_label"].to_numpy() == 1).groupby(sd["shop_id"].to_numpy()).any()
    )
    shops = shop_day["shop_id"].unique()
    shop_score = flagged_per_shop.reindex(shops, fill_value=0).astype(float)
    shop_score += shop_day_hit.reindex(shops, fill_value=False) * 1000  # rank P2P hits first
    min_flags = rules.baselines.rules_only.min_flagged_payments
    shop_flag = (flagged_per_shop.reindex(shops, fill_value=0) >= min_flags) | shop_day_hit.reindex(
        shops, fill_value=False
    )
    return BaselineResult("rules_only", score, flag, shop_score, shop_flag)


def blanket_limit(
    feats: dict[str, pd.DataFrame], rules: RulesConfig, in_window: pd.Series
) -> BaselineResult:
    pay = feats["payments"][in_window.to_numpy()]
    cap = rules.baselines.blanket_limit.daily_cap
    # Running total the shop has received today, this payment included.
    running = pay.groupby([pay["shop_id"], pay["ts"].dt.normalize()])["amount"].cumsum()
    score = pd.Series((running / cap).to_numpy(), index=pay["payment_id"])
    flag = score > 1.0  # blocked: over the cap
    shops = feats["shop_day"]["shop_id"].unique()
    shop_score = score.groupby(pay["shop_id"].to_numpy()).max().reindex(shops, fill_value=0.0)
    return BaselineResult("blanket_limit", score, flag, shop_score, shop_score > 1.0)


def evaluate(
    result: BaselineResult, tables: dict[str, pd.DataFrame], thr: ThresholdsConfig
) -> dict[str, float]:
    """Payment- and shop-level metrics against the hidden truth."""
    q = tables["qr_payments"].set_index("payment_id").loc[result.payment_score.index]
    truth, amount = q[TRUE_LABEL].to_numpy(), q["amount"].to_numpy()
    s, f = result.payment_score.to_numpy(), result.payment_flag.to_numpy()

    shops = tables["shops"].set_index("shop_id").loc[result.shop_score.index]
    st = shops[TRUE_LABEL].to_numpy()
    honest_lookalike = shops[TRUE_PATTERN].str.startswith("hn_").to_numpy()
    sf = result.shop_flag.to_numpy()
    return {
        "payment_pr_auc": m.pr_auc(truth, s),
        "payment_precision": m.precision(truth, f),
        "payment_recall": m.recall(truth, f),
        "payment_value_recall": m.value_weighted_recall(truth, f, amount),
        f"payment_precision_at_{thr.eval.analyst_capacity_payments}": m.precision_at_k(
            truth, s, thr.eval.analyst_capacity_payments
        ),
        "honest_taka_blocked_share": float(
            amount[f & (truth == 0)].sum() / amount[truth == 0].sum()
        ),
        "shop_pr_auc": m.pr_auc(st, result.shop_score.to_numpy()),
        "shop_precision": m.precision(st, sf),
        "shop_recall": m.recall(st, sf),
        f"shop_precision_at_{thr.eval.analyst_capacity_shops}": m.precision_at_k(
            st, result.shop_score.to_numpy(), thr.eval.analyst_capacity_shops
        ),
        "honest_shop_fpr": m.false_positive_rate(st, sf),
        "honest_lookalike_shop_fpr": float(sf[honest_lookalike].mean())
        if honest_lookalike.any()
        else float("nan"),
    }


def run_baselines(
    tables: dict[str, pd.DataFrame],
    feats: dict[str, pd.DataFrame],
    cfg: WorldConfig,
    thr: ThresholdsConfig,
    rules: RulesConfig,
) -> pd.DataFrame:
    """One row of metrics per baseline."""
    window = evaluation_window(feats["payments"], cfg, thr.eval.warmup_days)
    results = [rules_only(feats, rules, cfg, window), blanket_limit(feats, rules, window)]
    return pd.DataFrame({r.name: evaluate(r, tables, thr) for r in results}).T.rename_axis(
        "baseline"
    )
