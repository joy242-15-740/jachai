"""Small sampling helpers shared by the base world and the pattern injectors."""

import numpy as np

from jachai.world.config import Lognormal

SECONDS_PER_DAY = 86_400


def lognormal(rng: np.random.Generator, spec: Lognormal, size: int) -> np.ndarray:
    """Lognormal amounts with the given median and sigma, clipped to [min, max]."""
    x = rng.lognormal(mean=np.log(spec.median), sigma=spec.sigma, size=size)
    return np.clip(x, spec.min, spec.max)


def shop_prices(
    rng: np.random.Generator, amounts: np.ndarray, round_unit: int, round_share: float
) -> np.ndarray:
    """Turn raw amounts into shop prices in whole Tk.

    A `round_share` of tickets at or above `round_unit` are rounded to that unit
    (e.g. Tk 6,500 for a phone); everything else is rounded to Tk 5.
    """
    to_unit = (rng.random(len(amounts)) < round_share) & (amounts >= round_unit)
    rounded_5 = np.maximum(5, np.round(amounts / 5) * 5)
    rounded_unit = np.round(amounts / round_unit) * round_unit
    return np.where(to_unit, rounded_unit, rounded_5).astype(np.int64)


def open_hours_seconds(
    rng: np.random.Generator, open_h: np.ndarray, close_h: np.ndarray
) -> np.ndarray:
    """Seconds after midnight inside opening hours, busiest mid-day (Beta(2,2) shape)."""
    span = (close_h - open_h) * 3600
    return (open_h * 3600 + rng.beta(2, 2, size=len(open_h)) * span).astype(np.int64)


def after_hours_seconds(
    rng: np.random.Generator, open_h: np.ndarray, close_h: np.ndarray
) -> np.ndarray:
    """Seconds after midnight outside opening hours, uniform over the closed period."""
    closed = (24 - (close_h - open_h)) * 3600
    t = close_h * 3600 + rng.random(len(open_h)) * closed
    return (t % SECONDS_PER_DAY).astype(np.int64)


def pick_in_group(
    rng: np.random.Generator,
    member_keys: np.ndarray,
    member_values: np.ndarray,
    query_keys: np.ndarray,
) -> np.ndarray:
    """For each query key, a random member value with the same key (e.g. a random
    customer living in the shop's zone). Returns None where the group is empty."""
    order = np.argsort(member_keys, kind="stable")
    keys_sorted = member_keys[order]
    uniq, start, count = np.unique(keys_sorted, return_index=True, return_counts=True)
    g = np.searchsorted(uniq, query_keys)
    g_safe = np.minimum(g, len(uniq) - 1)
    found = uniq[g_safe] == query_keys
    offset = (rng.random(len(query_keys)) * count[g_safe]).astype(np.int64)
    picked = member_values[order][start[g_safe] + offset]
    return np.where(found, picked, None)
