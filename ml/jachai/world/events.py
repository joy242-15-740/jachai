"""Honest background activity: QR payments, remittances, add-money and P2P transfers.

Misuse and hard negatives are added on top of this by the pattern injectors.
Event IDs are assigned later, in generate.finalize, after all patterns ran.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from jachai.world.config import WorldConfig
from jachai.world.rng import stream
from jachai.world.sampling import (
    SECONDS_PER_DAY,
    after_hours_seconds,
    lognormal,
    open_hours_seconds,
    pick_in_group,
    shop_prices,
)
from jachai.world.world import NORMAL, TRUE_LABEL, TRUE_PATTERN

QR_COLUMNS = ["ts", "payer_id", "shop_id", "amount", "on_us", TRUE_LABEL, TRUE_PATTERN]
REMITTANCE_COLUMNS = ["ts", "customer_id", "amount", "corridor", TRUE_LABEL, TRUE_PATTERN]
ADD_MONEY_COLUMNS = ["ts", "customer_id", "channel", "agent_id", "amount", TRUE_LABEL, TRUE_PATTERN]
P2P_COLUMNS = ["ts", "sender_id", "receiver_id", "amount", "via_qr", TRUE_LABEL, TRUE_PATTERN]


def calendar_dates(cfg: WorldConfig) -> pd.DatetimeIndex:
    return pd.date_range(cfg.calendar.start, periods=cfg.calendar.days, freq="D")


def to_ts(cfg: WorldConfig, day_idx: np.ndarray, seconds: np.ndarray) -> np.ndarray:
    """Day index within the window + seconds after midnight -> datetime64[s]."""
    start = np.datetime64(cfg.calendar.start, "s")
    return start + (day_idx * SECONDS_PER_DAY + seconds).astype("timedelta64[s]")


def day_multipliers(cfg: WorldConfig) -> np.ndarray:
    """Weekly and salary-day effects on volume, one value per day."""
    dates = calendar_dates(cfg)
    mult = np.ones(len(dates))
    mult[dates.weekday == 4] *= cfg.weekly.friday_mult
    mult[dates.day <= cfg.weekly.month_start_days] *= cfg.weekly.month_start_mult
    return mult


def honest_label(n: int) -> dict[str, object]:
    return {TRUE_LABEL: np.zeros(n, dtype=np.int8), TRUE_PATTERN: NORMAL}


def shop_daily_rate(cfg: WorldConfig, shops: pd.DataFrame) -> np.ndarray:
    """Expected honest QR payments per day for each shop."""
    cat = shops["category"].map({k: c.daily_qr_payments for k, c in cfg.categories.items()})
    size = shops["size_tier"].map({k: t.volume_mult for k, t in cfg.size_tiers.items()})
    area = shops["area_type"].map({k: a.volume_mult for k, a in cfg.areas.items()})
    return (cat * size * area).to_numpy(dtype=float)


def honest_qr_rows(
    cfg: WorldConfig,
    rng: np.random.Generator,
    shops: pd.DataFrame,
    customers: pd.DataFrame,
    pools: tuple[np.ndarray, np.ndarray, np.ndarray],
    shop_idx: np.ndarray,
    day_idx: np.ndarray,
) -> pd.DataFrame:
    """Honest QR payments for the given (shop row, day) pairs, one payment per pair.

    Used for the base world and by hard-negative patterns that add honest volume.
    """
    n = len(shop_idx)
    cats = shops["category"].to_numpy()[shop_idx]

    amount = np.zeros(n, dtype=np.int64)
    open_h = np.zeros(n, dtype=np.int64)
    close_h = np.zeros(n, dtype=np.int64)
    for name, c in cfg.categories.items():
        m = cats == name
        k = int(m.sum())
        if not k:
            continue
        amount[m] = shop_prices(rng, lognormal(rng, c.ticket, k), c.round_unit, c.round_share)
        open_h[m], close_h[m] = c.open_hours

    late = rng.random(n) < cfg.payers.honest_after_hours_share
    seconds = np.where(
        late,
        after_hours_seconds(rng, open_h, close_h),
        open_hours_seconds(rng, open_h, close_h),
    )

    # Who pays: a regular of this shop, someone from the same zone, or anyone.
    pool, pool_start, pool_size = pools
    cust_ids = customers["customer_id"].to_numpy()
    u = rng.random(n)
    p = cfg.payers
    regular = (u < p.regular_share) & (pool_size[shop_idx] > 0)
    same_zone = ~regular & (u < p.regular_share + p.same_zone_share)
    payer = cust_ids[rng.integers(0, len(cust_ids), n)]  # default: anyone
    offset = (rng.random(n) * pool_size[shop_idx]).astype(np.int64)
    payer[regular] = cust_ids[pool[pool_start[shop_idx] + offset][regular]]
    local = pick_in_group(
        rng,
        customers["zone_id"].to_numpy(),
        cust_ids,
        shops["zone_id"].to_numpy()[shop_idx][same_zone],
    )
    payer[same_zone] = np.where(pd.isna(local), payer[same_zone], local)

    return pd.DataFrame(
        {
            "ts": to_ts(cfg, day_idx, seconds),
            "payer_id": payer,
            "shop_id": shops["shop_id"].to_numpy()[shop_idx],
            "amount": amount,
            "on_us": rng.random(n) < cfg.qr.on_us_share,
            **honest_label(n),
        }
    )[QR_COLUMNS]


def make_qr_payments(
    cfg: WorldConfig,
    shops: pd.DataFrame,
    customers: pd.DataFrame,
    pools: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> pd.DataFrame:
    rng = stream(cfg.seed, "qr_payments")
    n_days = cfg.calendar.days
    lam = shop_daily_rate(cfg, shops)[:, None] * day_multipliers(cfg)[None, :]
    counts = rng.poisson(lam)  # shape (shops, days)
    cell = np.repeat(np.arange(counts.size), counts.ravel())
    return honest_qr_rows(cfg, rng, shops, customers, pools, cell // n_days, cell % n_days)


def make_remittances(cfg: WorldConfig, customers: pd.DataFrame) -> pd.DataFrame:
    rng = stream(cfg.seed, "remittances")
    days = cfg.calendar.days
    receivers = customers.loc[
        customers["_true_segment"] == "remittance_receiver", "customer_id"
    ].to_numpy()
    counts = rng.poisson(cfg.remittances.per_30_days * days / 30, len(receivers))
    who = np.repeat(receivers, counts)
    n = len(who)
    corridors = cfg.remittances.corridors
    return pd.DataFrame(
        {
            "ts": to_ts(cfg, rng.integers(0, days, n), rng.integers(0, SECONDS_PER_DAY, n)),
            "customer_id": who,
            "amount": lognormal(rng, cfg.remittances.amount, n).round().astype(np.int64),
            "corridor": np.array(list(corridors), dtype=object)[
                rng.choice(len(corridors), n, p=list(corridors.values()))
            ],
            **honest_label(n),
        }
    )[REMITTANCE_COLUMNS]


def make_add_money(cfg: WorldConfig, customers: pd.DataFrame, agents: pd.DataFrame) -> pd.DataFrame:
    rng = stream(cfg.seed, "add_money")
    days = cfg.calendar.days
    counts = rng.poisson(cfg.add_money.per_30_days * days / 30, len(customers))
    pos = np.repeat(np.arange(len(customers)), counts)
    n = len(pos)
    channels = cfg.add_money.channels
    channel = np.array(list(channels), dtype=object)[
        rng.choice(len(channels), n, p=list(channels.values()))
    ]
    # Cash-in happens at an agent in the customer's own zone.
    agent = pick_in_group(
        rng,
        agents["zone_id"].to_numpy(),
        agents["agent_id"].to_numpy(),
        customers["zone_id"].to_numpy()[pos],
    )
    agent = np.where(channel == "agent_cash_in", agent, None)
    amount = np.round(lognormal(rng, cfg.add_money.amount, n) / 10) * 10
    return pd.DataFrame(
        {
            "ts": to_ts(cfg, rng.integers(0, days, n), rng.integers(8 * 3600, 22 * 3600, n)),
            "customer_id": customers["customer_id"].to_numpy()[pos],
            "channel": channel,
            "agent_id": agent,
            "amount": np.maximum(10, amount).astype(np.int64),
            **honest_label(n),
        }
    )[ADD_MONEY_COLUMNS]


def empty_p2p() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts": pd.Series(dtype="datetime64[s]"),
            "sender_id": pd.Series(dtype=object),
            "receiver_id": pd.Series(dtype=object),
            "amount": pd.Series(dtype=np.int64),
            "via_qr": pd.Series(dtype=bool),
            TRUE_LABEL: pd.Series(dtype=np.int8),
            TRUE_PATTERN: pd.Series(dtype=object),
        }
    )


def make_p2p_transfers(cfg: WorldConfig, customers: pd.DataFrame) -> pd.DataFrame:
    """Personal transfers between customers. Empty unless the P2P scenario is on."""
    if not cfg.scenario.p2p_qr_enabled:
        return empty_p2p()
    rng = stream(cfg.seed, "p2p_transfers")
    days = cfg.calendar.days
    ids = customers["customer_id"].to_numpy()
    counts = rng.poisson(cfg.p2p.per_30_days * days / 30, len(customers))
    pos = np.repeat(np.arange(len(customers)), counts)
    n = len(pos)
    receiver = ids[rng.integers(0, len(ids), n)]
    local = rng.random(n) < cfg.p2p.same_zone_share
    picked = pick_in_group(
        rng, customers["zone_id"].to_numpy(), ids, customers["zone_id"].to_numpy()[pos[local]]
    )
    receiver[local] = picked
    sender = ids[pos]
    keep = receiver != sender
    ts = to_ts(cfg, rng.integers(0, days, n), rng.integers(7 * 3600, 23 * 3600, n))
    df = pd.DataFrame(
        {
            "ts": ts,
            "sender_id": sender,
            "receiver_id": receiver,
            "amount": shop_prices(rng, lognormal(rng, cfg.p2p.amount, n), 100, 0.6),
            "via_qr": ts >= np.datetime64(cfg.scenario.p2p_qr_start, "s"),
            **honest_label(n),
        }
    )[P2P_COLUMNS]
    return df[keep].reset_index(drop=True)
