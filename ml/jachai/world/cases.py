"""Past investigations ("cases"): sparse, shop-level, dated, biased, imperfect.

Real upay would not have a label for every payment. It would have a few hundred
closed investigations, mostly of shops its existing rules flagged, plus a small
random audit. Some verdicts are wrong. This module creates that `cases` table:

  case_id, shop_id, opened_on, closed_on (NaT while still open), verdict (1 misuse,
  0 honest), source ("rule_flag" or "audit")

Selection bias is approximated: the generator cannot run our rules (they need
features computed from the finished world), so flagged shops are drawn with
weights by kind of shop (misuse / honest look-alike / normal) from patterns.yaml.

Cases are observable data, not hidden truth. Training code must only use cases
closed before its cutoff and only for its own shops.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from jachai.world.ids import random_ids
from jachai.world.rng import stream
from jachai.world.world import TRUE_LABEL, TRUE_PATTERN, World

CASE_COLUMNS = ["case_id", "shop_id", "opened_on", "closed_on", "verdict", "source"]


def empty_cases() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "case_id": pd.Series(dtype=object),
            "shop_id": pd.Series(dtype=object),
            "opened_on": pd.Series(dtype="datetime64[s]"),
            "closed_on": pd.Series(dtype="datetime64[s]"),
            "verdict": pd.Series(dtype=np.int8),
            "source": pd.Series(dtype=object),
        }
    )


def _first_misuse_day(world: World) -> pd.Series:
    """Per shop, the first day with a misuse payment (cases open after it)."""
    frames = [world.tables["qr_payments"], world.tables["p2p_transfers"]]
    frames[1] = frames[1].assign(
        shop_id=frames[1]["receiver_id"].map(
            world.tables["shops"].set_index("owner_wallet_id")["shop_id"]
        )
    )
    hits = pd.concat([f.loc[f[TRUE_LABEL] == 1, ["shop_id", "ts"]] for f in frames])
    return hits.groupby("shop_id")["ts"].min().dt.normalize()


def make_cases(world: World) -> pd.DataFrame:
    if world.patterns is None:
        return empty_cases()
    c = world.patterns.cases
    cfg = world.config
    rng = stream(cfg.seed, "cases")
    shops = world.tables["shops"]
    n = len(shops)
    kinds = {p.name: p.kind for p in world.patterns.patterns}
    kind = shops[TRUE_PATTERN].map(lambda p: kinds.get(p, "normal")).to_numpy()

    # 1) Random audit: every shop equally likely.
    n_audit = round(c.audit_share * n)
    audit = rng.choice(n, size=n_audit, replace=False)
    # 2) Rule-flagged: the rest of the coverage, drawn with selection bias.
    n_flag = max(0, round(c.coverage * n) - n_audit)
    weight = np.array([c.flag_weight[k] for k in kind], dtype=float)
    weight[audit] = 0
    weight /= weight.sum()
    flagged = rng.choice(n, size=min(n_flag, int((weight > 0).sum())), replace=False, p=weight)

    pos = np.concatenate([audit, flagged])
    source = np.array(["audit"] * len(audit) + ["rule_flag"] * len(flagged), dtype=object)
    truth = shops[TRUE_LABEL].to_numpy()[pos]

    # Wrong verdicts.
    u = rng.random(len(pos))
    verdict = np.where(truth == 1, u >= c.misuse_cleared, u < c.honest_convicted).astype(np.int8)

    # Dates: a misuse shop's case opens after its misuse began; others any time.
    start = pd.Timestamp(cfg.calendar.start)
    end = pd.Timestamp(cfg.calendar.end)
    first_bad = shops["shop_id"].iloc[pos].map(_first_misuse_day(world))
    earliest = first_bad.fillna(start).to_numpy(dtype="datetime64[s]")
    span = ((end - pd.Series(earliest)).dt.days.clip(lower=0) + 1).to_numpy()
    opened = earliest + (rng.random(len(pos)) * span).astype("timedelta64[D]")
    lo, hi = c.duration_days
    closed = opened + rng.integers(lo, hi + 1, len(pos)).astype("timedelta64[D]")
    closed = np.where(closed <= np.datetime64(end, "s"), closed, np.datetime64("NaT", "s"))

    cases = pd.DataFrame(
        {
            "case_id": random_ids(rng, len(pos), "CS"),
            "shop_id": shops["shop_id"].to_numpy()[pos],
            "opened_on": opened.astype("datetime64[s]"),
            "closed_on": pd.to_datetime(closed).astype("datetime64[s]"),
            "verdict": verdict,
            "source": source,
        }
    )
    return cases.sort_values(["opened_on", "case_id"]).reset_index(drop=True)[CASE_COLUMNS]
