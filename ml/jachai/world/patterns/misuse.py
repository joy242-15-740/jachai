"""The six project misuse patterns. Every row they add has true label 1.

Each injector reads its settings from configs/patterns.yaml; nothing here is a
business rule. Regulatory numbers (Tk 30,000 limit, Tk 2,000 incentive cap,
regime dates) come from configs/world.yaml.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import model_validator

from jachai.world.events import ADD_MONEY_COLUMNS, P2P_COLUMNS, REMITTANCE_COLUMNS, to_ts
from jachai.world.patterns import register
from jachai.world.patterns.common import (
    Params,
    claim_shops,
    day_index,
    distance_km,
    far_customers,
    label_columns,
    mark_customers,
    mark_shops,
    n_from_share,
    qr_frame,
    release_shops,
    shop_hours,
)
from jachai.world.sampling import (
    SECONDS_PER_DAY,
    after_hours_seconds,
    lognormal,
    open_hours_seconds,
    pick_in_group,
    shop_prices,
)
from jachai.world.world import TRUE_PATTERN, World

Range = tuple[float, float]
IntRange = tuple[int, int]


def _local_payers(world: World, rng, shop_pos: np.ndarray) -> np.ndarray:
    """A random customer from each shop's own zone."""
    customers = world.tables["customers"]
    ids = customers["customer_id"].to_numpy()
    zones = world.tables["shops"]["zone_id"].to_numpy()[shop_pos]
    picked = pick_in_group(rng, customers["zone_id"].to_numpy(), ids, zones)
    fallback = ids[rng.integers(0, len(ids), len(shop_pos))]
    return np.where(pd.isna(picked), fallback, picked)


def _split(rng, totals: np.ndarray, parts: np.ndarray, unit: int) -> tuple[np.ndarray, np.ndarray]:
    """Split each total into `parts` uneven pieces rounded to `unit`.
    Returns (owner index per piece, piece amount)."""
    owner = np.repeat(np.arange(len(totals)), parts)
    w = rng.uniform(0.6, 1.4, len(owner))
    w_sum = np.bincount(owner, weights=w)
    piece = totals[owner] * w / w_sum[owner]
    return owner, np.maximum(unit, np.round(piece / unit) * unit).astype(np.int64)


# 1 ---------------------------------------------------------------------------
class CashDeskParams(Params):
    shop_share: float
    categories: list[str]
    daily_cashouts: float
    active_day_share: float
    amounts: list[int]
    amount_weights: list[float]
    after_hours_share: float
    payer_pool_share: float
    far_payer_share: float
    bank_add_money_share: float


@register("round_amount_cash_desk")
def round_amount_cash_desk(world: World, params: dict, rng: np.random.Generator) -> None:
    """Shop hands out cash for QR 'purchases': round amounts, many one-off payers,
    often after hours, often right after a bank top-up."""
    p = CashDeskParams(**params)
    cfg, shops = world.config, world.tables["shops"]
    days = cfg.calendar.days
    pos = claim_shops(
        world,
        rng,
        n_from_share(p.shop_share, len(shops)),
        shops["category"].isin(p.categories).to_numpy(),
    )

    active = rng.random((len(pos), days)) < p.active_day_share
    counts = rng.poisson(p.daily_cashouts, (len(pos), days)) * active
    cell = np.repeat(np.arange(counts.size), counts.ravel())
    shop_pos, day = pos[cell // days], cell % days
    n = len(cell)

    weights = np.array(p.amount_weights) / sum(p.amount_weights)
    amount = rng.choice(np.array(p.amounts, dtype=np.int64), n, p=weights)
    open_h, close_h = shop_hours(world, shop_pos)
    late = rng.random(n) < p.after_hours_share
    secs = np.where(
        late,
        after_hours_seconds(rng, open_h, close_h),
        open_hours_seconds(rng, open_h, close_h),
    )

    # Payers come from a pool of cash-out users: many different people per shop,
    # some of them visiting several cash desks. Most live outside the shop's zone.
    customers = world.tables["customers"]
    pool = rng.choice(
        len(customers), n_from_share(p.payer_pool_share, len(customers)), replace=False
    )
    pool_ids = customers["customer_id"].to_numpy()[pool]
    payer = pool_ids[rng.integers(0, len(pool), n)]
    local = rng.random(n) >= p.far_payer_share
    picked = pick_in_group(
        rng,
        customers["zone_id"].to_numpy()[pool],
        pool_ids,
        shops["zone_id"].to_numpy()[shop_pos[local]],
    )
    payer[local] = np.where(pd.isna(picked), payer[local], picked)
    shop_ids = shops["shop_id"].to_numpy()[shop_pos]
    world.append("qr_payments", qr_frame(world, day, secs, payer, shop_ids, amount, rng))

    # bank -> wallet -> fake purchase -> cash: a bank top-up 10 min to 6 h before.
    t = day * SECONDS_PER_DAY + secs - rng.integers(600, 6 * 3600, n)
    topup = (rng.random(n) < p.bank_add_money_share) & (t >= 0)
    k = int(topup.sum())
    world.append(
        "add_money",
        pd.DataFrame(
            {
                "ts": to_ts(cfg, np.zeros(k, dtype=np.int64), t[topup]),
                "customer_id": payer[topup],
                "channel": "bank",
                "agent_id": None,
                "amount": amount[topup],
                **label_columns(world, k),
            }
        )[ADD_MONEY_COLUMNS],
    )
    mark_customers(world, payer)


# 2 ---------------------------------------------------------------------------
class DrainParams(Params):
    receiver_share: float
    shop_share: float
    min_distance_km: float
    drain_fraction: Range
    delay_hours: Range
    split_into: IntRange


@register("remittance_drain")
def remittance_drain(world: World, params: dict, rng: np.random.Generator) -> None:
    """A remittance arrives; within hours almost all of it is 'spent' at a distant
    colluding shop; then the account goes quiet."""
    p = DrainParams(**params)
    cfg, shops, customers = world.config, world.tables["shops"], world.tables["customers"]
    days = cfg.calendar.days
    shop_pos = claim_shops(world, rng, n_from_share(p.shop_share, len(shops)))

    eligible = np.flatnonzero(
        (customers["_true_segment"] == "remittance_receiver").to_numpy()
        & (customers[TRUE_PATTERN] == "normal").to_numpy()
    )
    drainers = rng.choice(eligible, n_from_share(p.receiver_share, len(eligible)), replace=False)
    n = len(drainers)
    drainer_ids = customers["customer_id"].to_numpy()[drainers]

    # The remittance itself (labelled as part of the scheme).
    t_rem = rng.integers(0, (days - 3) * SECONDS_PER_DAY, n)
    rem_amount = np.round(lognormal(rng, cfg.remittances.amount, n)).astype(np.int64)
    corridors = cfg.remittances.corridors
    world.append(
        "remittances",
        pd.DataFrame(
            {
                "ts": to_ts(cfg, np.zeros(n, dtype=np.int64), t_rem),
                "customer_id": drainer_ids,
                "amount": rem_amount,
                "corridor": np.array(list(corridors), dtype=object)[
                    rng.choice(len(corridors), n, p=list(corridors.values()))
                ],
                **label_columns(world, n),
            }
        )[REMITTANCE_COLUMNS],
    )

    # Each drainer pays a colluding shop at least min_distance_km away (or the farthest one).
    dist = distance_km(
        customers["x_km"].to_numpy()[drainers][:, None],
        customers["y_km"].to_numpy()[drainers][:, None],
        shops["x_km"].to_numpy()[shop_pos][None, :],
        shops["y_km"].to_numpy()[shop_pos][None, :],
    )
    score = np.where(dist >= p.min_distance_km, 1 + rng.random(dist.shape), dist / dist.max())
    target = shop_pos[score.argmax(axis=1)]

    total = rem_amount * rng.uniform(*p.drain_fraction, n)
    parts = rng.integers(p.split_into[0], p.split_into[1] + 1, n)
    owner, amount = _split(rng, total, parts, unit=10)
    delay = (rng.uniform(*p.delay_hours, len(owner)) * 3600).astype(np.int64)
    t_pay = np.minimum(t_rem[owner] + delay, days * SECONDS_PER_DAY - 1)
    world.append(
        "qr_payments",
        qr_frame(
            world,
            t_pay // SECONDS_PER_DAY,
            t_pay % SECONDS_PER_DAY,
            drainer_ids[owner],
            shops["shop_id"].to_numpy()[target[owner]],
            amount,
            rng,
        ),
    )

    # Dormant afterwards: drop the drainer's own honest activity after the last drain.
    last = pd.Series(t_pay).groupby(owner).max().to_numpy()
    cutoff = pd.Series(to_ts(cfg, np.zeros(n, dtype=np.int64), last), index=drainer_ids)
    for table, who in (
        ("qr_payments", "payer_id"),
        ("add_money", "customer_id"),
        ("remittances", "customer_id"),
        ("p2p_transfers", "sender_id"),
    ):
        df = world.tables[table]
        limit = df[who].map(cutoff)
        drop = limit.notna() & (df["ts"] > limit) & (df[TRUE_PATTERN] == "normal")
        world.tables[table] = df[~drop].reset_index(drop=True)

    # Claimed shops that no drainer ended up using go back to normal.
    release_shops(world, np.setdiff1d(shop_pos, target))
    mark_customers(world, drainer_ids)


# 3 ---------------------------------------------------------------------------
class BurstParams(Params):
    shop_share: float
    size_tiers: list[str]
    burst_days: IntRange
    burst_total: Range
    ticket: Range
    min_distance_km: float


@register("turnover_burst")
def turnover_burst(world: World, params: dict, rng: np.random.Generator) -> None:
    """A small shop suddenly takes Tk 3-7 lakh in a day, from payers far away."""
    p = BurstParams(**params)
    cfg, shops = world.config, world.tables["shops"]
    days = cfg.calendar.days
    pos = claim_shops(
        world,
        rng,
        n_from_share(p.shop_share, len(shops)),
        shops["size_tier"].isin(p.size_tiers).to_numpy(),
    )

    cell_shop, cell_day = [], []
    for s in pos:
        k = min(int(rng.integers(p.burst_days[0], p.burst_days[1] + 1)), days)
        cell_shop.append(np.full(k, s))
        cell_day.append(rng.choice(days, k, replace=False))
    cell_shop, cell_day = np.concatenate(cell_shop), np.concatenate(cell_day)

    totals = rng.uniform(*p.burst_total, len(cell_shop))
    parts = np.ceil(totals / np.mean(p.ticket)).astype(np.int64)
    owner, amount = _split(rng, totals, parts, unit=100)
    shop_pos = cell_shop[owner]
    open_h, close_h = shop_hours(world, shop_pos)
    payer = far_customers(
        world,
        rng,
        shops["x_km"].to_numpy()[shop_pos],
        shops["y_km"].to_numpy()[shop_pos],
        p.min_distance_km,
    )
    world.append(
        "qr_payments",
        qr_frame(
            world,
            cell_day[owner],
            open_hours_seconds(rng, open_h, close_h),
            payer,
            shops["shop_id"].to_numpy()[shop_pos],
            amount,
            rng,
        ),
    )
    mark_customers(world, payer)


# 4 ---------------------------------------------------------------------------
class BypassParams(Params):
    rings_per_1000_shops: float
    ring_size: IntRange
    customers_per_ring: IntRange
    active_days: IntRange
    daily_total: Range


@register("limit_bypass")
def limit_bypass(world: World, params: dict, rng: np.random.Generator) -> None:
    """Customers move more than the daily cash-out limit by splitting it across a
    ring of nearby complicit shops on the same day."""
    p = BypassParams(**params)
    cfg, shops, customers = world.config, world.tables["shops"], world.tables["customers"]
    limit = cfg.regulation.cash_out_limit_daily
    if p.daily_total[0] <= limit:
        raise ValueError(f"limit_bypass daily_total must start above the limit (Tk {limit:,.0f})")
    days = cfg.calendar.days
    sx, sy = shops["x_km"].to_numpy(), shops["y_km"].to_numpy()
    cust_ids = customers["customer_id"].to_numpy()

    payers, shop_ids, day_list, secs_list, amounts = [], [], [], [], []
    for _ in range(n_from_share(p.rings_per_1000_shops / 1000, len(shops))):
        seed = claim_shops(world, rng, 1)
        if len(seed) == 0:
            break
        # The ring: the seed shop plus its nearest shops that have no pattern yet.
        free = np.flatnonzero((shops[TRUE_PATTERN] == "normal").to_numpy())
        size = int(rng.integers(p.ring_size[0], p.ring_size[1] + 1))
        near = free[np.argsort(distance_km(sx[free], sy[free], sx[seed[0]], sy[seed[0]]))]
        ring = np.concatenate([seed, near[: size - 1]])
        mark_shops(world, ring)

        zone = shops["zone_id"].iat[seed[0]]
        local = np.flatnonzero((customers["zone_id"] == zone).to_numpy())
        k = min(int(rng.integers(p.customers_per_ring[0], p.customers_per_ring[1] + 1)), len(local))
        members = cust_ids[rng.choice(local, k, replace=False)]
        mark_customers(world, members)

        for who in members:
            n_days = min(int(rng.integers(p.active_days[0], p.active_days[1] + 1)), days)
            for day in rng.choice(days, n_days, replace=False):
                m = int(rng.integers(min(3, len(ring)), len(ring) + 1))
                hit = rng.choice(ring, m, replace=False)
                _, part = _split(rng, np.array([rng.uniform(*p.daily_total)]), np.array([m]), 500)
                # Visits a few shops within a few hours.
                start = int(rng.integers(10 * 3600, 18 * 3600))
                payers += [who] * m
                shop_ids += list(shops["shop_id"].to_numpy()[hit])
                day_list += [day] * m
                secs_list += list(start + np.cumsum(rng.integers(600, 5400, m)))
                amounts += list(part)

    world.append(
        "qr_payments",
        qr_frame(
            world,
            np.array(day_list, dtype=np.int64),
            np.array(secs_list, dtype=np.int64),
            np.array(payers, dtype=object),
            np.array(shop_ids, dtype=object),
            np.array(amounts, dtype=np.int64),
            rng,
        ),
    )


# 5 ---------------------------------------------------------------------------
class SplittingParams(Params):
    shop_share: float
    categories: list[str]
    payers_per_shop: IntRange
    payments_per_day: IntRange
    below_cap: IntRange
    active_day_share: float


@register("incentive_splitting")
def incentive_splitting(world: World, params: dict, rng: np.random.Generator) -> None:
    """After the regime change, the same few payers make many payments just under
    the incentive cap at one shop, to farm the per-payment incentive."""
    p = SplittingParams(**params)
    cfg, shops = world.config, world.tables["shops"]
    days = cfg.calendar.days
    first = max(0, day_index(world, cfg.calendar.regime_change))
    if first >= days:
        return  # regime change is outside the window: nothing to farm
    pos = claim_shops(
        world,
        rng,
        n_from_share(p.shop_share, len(shops)),
        shops["category"].isin(p.categories).to_numpy(),
    )

    # A fixed small group of colluding payers per shop.
    group_size = rng.integers(p.payers_per_shop[0], p.payers_per_shop[1] + 1, len(pos))
    group_payers = _local_payers(world, rng, np.repeat(pos, group_size))
    group_start = np.concatenate([[0], np.cumsum(group_size)[:-1]])

    n_after = days - first
    active = rng.random((len(pos), n_after)) < p.active_day_share
    counts = rng.integers(p.payments_per_day[0], p.payments_per_day[1] + 1, active.shape) * active
    cell = np.repeat(np.arange(counts.size), counts.ravel())
    shop_i, day = cell // n_after, first + cell % n_after
    n = len(cell)

    pick = group_start[shop_i] + (rng.random(n) * group_size[shop_i]).astype(np.int64)
    cap = int(cfg.regulation.qr_incentive_cap)
    amount = cap - rng.integers(p.below_cap[0], p.below_cap[1] + 1, n)

    # Payments come in a run: a start time in opening hours, then 1-20 minutes apart.
    open_h, close_h = shop_hours(world, pos[shop_i])
    start = open_hours_seconds(rng, open_h, close_h)
    gaps = pd.Series(rng.integers(60, 1200, n)).groupby(cell).cumsum().to_numpy()
    first_of_cell = np.r_[True, cell[1:] != cell[:-1]]
    run_start = np.maximum.accumulate(np.where(first_of_cell, np.arange(n), 0))
    secs = start[run_start] + gaps

    world.append(
        "qr_payments",
        qr_frame(
            world,
            day,
            secs,
            group_payers[pick],
            shops["shop_id"].to_numpy()[pos[shop_i]],
            amount,
            rng,
        ),
    )
    mark_customers(world, group_payers)


# 6 ---------------------------------------------------------------------------
class P2pDisguiseParams(Params):
    shop_share: float
    daily_transfers: IntRange
    qr_shift_share: float

    @model_validator(mode="after")
    def _share(self) -> P2pDisguiseParams:
        if not 0 <= self.qr_shift_share <= 1:
            raise ValueError("qr_shift_share must be in [0, 1]")
        return self


@register("p2p_disguise")
def p2p_disguise(world: World, params: dict, rng: np.random.Generator) -> None:
    """Once P2P QR exists, a shop asks customers to pay the owner's personal wallet
    instead of the merchant QR: business income disguised as personal transfers.
    Does nothing unless scenario.p2p_qr_enabled is true."""
    p = P2pDisguiseParams(**params)
    cfg, shops = world.config, world.tables["shops"]
    if not cfg.scenario.p2p_qr_enabled:
        return
    days = cfg.calendar.days
    first = max(0, day_index(world, cfg.scenario.p2p_qr_start))
    if first >= days:
        return
    pos = claim_shops(world, rng, n_from_share(p.shop_share, len(shops)))

    n_after = days - first
    counts = rng.integers(p.daily_transfers[0], p.daily_transfers[1] + 1, (len(pos), n_after))
    cell = np.repeat(np.arange(counts.size), counts.ravel())
    shop_pos, day = pos[cell // n_after], first + cell % n_after
    n = len(cell)

    # Ordinary purchases: category ticket sizes, paid by the shop's regulars.
    cats = shops["category"].to_numpy()[shop_pos]
    amount = np.zeros(n, dtype=np.int64)
    for name, c in cfg.categories.items():
        m = cats == name
        if m.any():
            raw = lognormal(rng, c.ticket, int(m.sum()))
            amount[m] = shop_prices(rng, raw, c.round_unit, c.round_share)
    pool, pool_start, pool_size = world.pools
    offset = (rng.random(n) * pool_size[shop_pos]).astype(np.int64)
    sender = world.tables["customers"]["customer_id"].to_numpy()[
        pool[pool_start[shop_pos] + offset]
    ]
    open_h, close_h = shop_hours(world, shop_pos)
    world.append(
        "p2p_transfers",
        pd.DataFrame(
            {
                "ts": to_ts(cfg, day, open_hours_seconds(rng, open_h, close_h)),
                "sender_id": sender,
                "receiver_id": shops["owner_wallet_id"].to_numpy()[shop_pos],
                "amount": amount,
                "via_qr": True,
                **label_columns(world, n),
            }
        )[P2P_COLUMNS],
    )

    # Those sales no longer go through the merchant QR.
    qr = world.tables["qr_payments"]
    start = np.datetime64(cfg.scenario.p2p_qr_start, "s")
    moved = (
        qr["shop_id"].isin(shops["shop_id"].to_numpy()[pos])
        & (qr["ts"] >= start)
        & (qr[TRUE_PATTERN] == "normal")
    ).to_numpy()
    moved = moved & (rng.random(len(qr)) < p.qr_shift_share)
    world.tables["qr_payments"] = qr[~moved].reset_index(drop=True)
