"""Hard negatives: honest activity that looks like misuse. True label 0.

Without these, a model could learn shortcuts such as "round amounts = cash-out" or
"sudden spike = fraud" and then wrongly flag honest electronics shops, festival
sellers, haat-day traders and new shops.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from jachai.world.entities import WEEKDAYS
from jachai.world.events import calendar_dates, honest_qr_rows, shop_daily_rate
from jachai.world.patterns import register
from jachai.world.patterns.common import (
    Params,
    claim_shops,
    day_index,
    n_from_share,
    pattern_name,
    qr_frame,
    shop_hours,
)
from jachai.world.sampling import open_hours_seconds
from jachai.world.world import TRUE_LABEL, TRUE_PATTERN, World


def _extra_honest_volume(world: World, rng: np.random.Generator, extra: np.ndarray) -> pd.DataFrame:
    """Honest QR payments for an (shops x days) array of expected extra counts,
    tagged with the current hard-negative pattern name."""
    days = world.config.calendar.days
    counts = rng.poisson(extra)
    cell = np.repeat(np.arange(counts.size), counts.ravel())
    rows = honest_qr_rows(
        world.config,
        rng,
        world.tables["shops"],
        world.tables["customers"],
        world.pools,
        cell // days,
        cell % days,
    )
    rows[TRUE_PATTERN] = pattern_name(world)
    return rows


def _honest_shops(world: World) -> np.ndarray:
    return (world.tables["shops"][TRUE_LABEL] == 0).to_numpy()


class BigTicketParams(Params):
    categories: list[str]
    shop_share: float
    daily_sales: float
    amounts: tuple[float, float]
    round_unit: int


@register("hn_big_ticket_retail")
def hn_big_ticket_retail(world: World, params: dict, rng: np.random.Generator) -> None:
    """Electronics shops and wholesalers with genuine large, round tickets
    (a TV for Tk 45,000, a sack order for Tk 20,000), paid by their regular buyers
    during opening hours."""
    p = BigTicketParams(**params)
    cfg, shops = world.config, world.tables["shops"]
    days = cfg.calendar.days
    in_cat = shops["category"].isin(p.categories).to_numpy()
    pos = claim_shops(world, rng, n_from_share(p.shop_share, int(in_cat.sum())), in_cat)

    counts = rng.poisson(p.daily_sales, (len(pos), days))
    cell = np.repeat(np.arange(counts.size), counts.ravel())
    shop_pos, day = pos[cell // days], cell % days
    n = len(cell)

    raw = rng.uniform(*p.amounts, n)
    amount = np.maximum(p.round_unit, np.round(raw / p.round_unit) * p.round_unit)
    pool, pool_start, pool_size = world.pools
    offset = (rng.random(n) * pool_size[shop_pos]).astype(np.int64)
    payer = world.tables["customers"]["customer_id"].to_numpy()[pool[pool_start[shop_pos] + offset]]
    open_h, close_h = shop_hours(world, shop_pos)
    world.append(
        "qr_payments",
        qr_frame(
            world,
            day,
            open_hours_seconds(rng, open_h, close_h),
            payer,
            shops["shop_id"].to_numpy()[shop_pos],
            amount,
            rng,
        ),
    )


class FestivalParams(Params):
    festival: str
    start: dt.date
    end: dt.date
    volume_mult: dict[str, float]


@register("hn_festival_spike")
def hn_festival_spike(world: World, params: dict, rng: np.random.Generator) -> None:
    """Honest shops sell more around a festival (clothing most of all)."""
    p = FestivalParams(**params)
    cfg, shops = world.config, world.tables["shops"]
    first = max(0, day_index(world, p.start))
    last = min(cfg.calendar.days - 1, day_index(world, p.end))
    if first > last:
        return  # festival is outside the window

    default = p.volume_mult.get("default", 1.0)
    mult = shops["category"].map(lambda c: p.volume_mult.get(c, default)).to_numpy(dtype=float)
    extra = np.zeros((len(shops), cfg.calendar.days))
    extra[:, first : last + 1] = (shop_daily_rate(cfg, shops) * (mult - 1))[:, None]
    extra[~_honest_shops(world)] = 0
    world.append("qr_payments", _extra_honest_volume(world, rng, extra))


class HaatParams(Params):
    volume_mult: float


@register("hn_haat_day_spike")
def hn_haat_day_spike(world: World, params: dict, rng: np.random.Generator) -> None:
    """Rural haat shops get busier on their zone's weekly market days."""
    p = HaatParams(**params)
    cfg, shops, zones = world.config, world.tables["shops"], world.tables["zones"]
    weekday = np.array([WEEKDAYS[d] for d in calendar_dates(cfg).weekday])
    haat_days = zones.set_index("zone_id")["haat_days"].reindex(shops["zone_id"]).fillna("")
    is_haat = np.array([[d in h.split("|") for d in weekday] for h in haat_days], dtype=bool)

    extra = shop_daily_rate(cfg, shops)[:, None] * (p.volume_mult - 1) * is_haat
    extra[~_honest_shops(world)] = 0
    world.append("qr_payments", _extra_honest_volume(world, rng, extra))


class RampParams(Params):
    shop_share: float
    ramp_days: int


@register("hn_new_shop_ramp")
def hn_new_shop_ramp(world: World, params: dict, rng: np.random.Generator) -> None:
    """Some honest shops open during the window and grow over their first weeks,
    so their volume jumps from nothing, which can look like a burst."""
    p = RampParams(**params)
    cfg, shops = world.config, world.tables["shops"]
    days = cfg.calendar.days
    pos = claim_shops(world, rng, n_from_share(p.shop_share, len(shops)))
    # Open somewhere between 20% and 70% into the window, so the ramp is visible.
    open_day = rng.integers(int(days * 0.2), max(int(days * 0.7), int(days * 0.2) + 1), len(pos))
    opened = pd.Timestamp(cfg.calendar.start) + pd.to_timedelta(open_day, unit="D")
    shops.loc[shops.index[pos], "opened_on"] = opened

    qr = world.tables["qr_payments"]
    open_ts = pd.Series(opened, index=shops["shop_id"].to_numpy()[pos])
    shop_open = qr["shop_id"].map(open_ts)
    ours = shop_open.notna().to_numpy()
    age_days = ((qr["ts"] - shop_open).dt.total_seconds() / 86400).to_numpy()
    # Keep a payment with probability rising linearly from 0 to 1 over ramp_days.
    keep_p = np.clip(np.nan_to_num(age_days, nan=0.0) / p.ramp_days, 0, 1)
    drop = ours & (rng.random(len(qr)) >= keep_p)
    qr = qr[~drop].reset_index(drop=True)
    tag = qr["shop_id"].isin(open_ts.index) & (qr[TRUE_PATTERN] == "normal")
    qr.loc[tag, TRUE_PATTERN] = pattern_name(world)
    world.tables["qr_payments"] = qr
