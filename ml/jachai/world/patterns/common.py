"""Helpers shared by pattern injectors."""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict

from jachai.world.events import QR_COLUMNS, to_ts
from jachai.world.sampling import SECONDS_PER_DAY
from jachai.world.world import TRUE_LABEL, TRUE_PATTERN, World


class Params(BaseModel):
    """Base for each injector's params: unknown keys are an error."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def pattern_name(world: World) -> str:
    return world.current_pattern.name


def is_misuse(world: World) -> int:
    return int(world.current_pattern.kind == "misuse")


def label_columns(world: World, n: int) -> dict[str, object]:
    return {
        TRUE_LABEL: np.full(n, is_misuse(world), dtype=np.int8),
        TRUE_PATTERN: pattern_name(world),
    }


def n_from_share(share: float, total: int) -> int:
    return max(1, round(share * total))


def claim_shops(world: World, rng: np.random.Generator, n: int, mask: np.ndarray | None = None):
    """Pick up to `n` random shops (row positions) that match `mask` and have no
    pattern yet, and reserve them for the current pattern."""
    shops = world.tables["shops"]
    ok = shops[TRUE_PATTERN].to_numpy() == "normal"
    if mask is not None:
        ok &= mask
    candidates = np.flatnonzero(ok)
    chosen = rng.choice(candidates, size=min(n, len(candidates)), replace=False)
    mark_shops(world, chosen)
    return np.sort(chosen)


def mark_shops(world: World, positions: np.ndarray) -> None:
    shops = world.tables["shops"]
    shops.loc[shops.index[positions], TRUE_PATTERN] = pattern_name(world)
    shops.loc[shops.index[positions], TRUE_LABEL] = is_misuse(world)


def release_shops(world: World, positions: np.ndarray) -> None:
    """Undo a claim: the shops become normal again."""
    shops = world.tables["shops"]
    shops.loc[shops.index[positions], TRUE_PATTERN] = "normal"
    shops.loc[shops.index[positions], TRUE_LABEL] = 0


def mark_customers(world: World, customer_ids: np.ndarray) -> None:
    customers = world.tables["customers"]
    hit = customers["customer_id"].isin(customer_ids) & (customers[TRUE_PATTERN] == "normal")
    customers.loc[hit, TRUE_PATTERN] = pattern_name(world)


def shop_hours(world: World, shop_pos: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Opening and closing hour for each shop position."""
    cats = world.tables["shops"]["category"].to_numpy()[shop_pos]
    hours = {k: c.open_hours for k, c in world.config.categories.items()}
    open_h = np.array([hours[c][0] for c in cats], dtype=np.int64)
    close_h = np.array([hours[c][1] for c in cats], dtype=np.int64)
    return open_h, close_h


def distance_km(x1, y1, x2, y2) -> np.ndarray:
    return np.hypot(np.asarray(x1) - np.asarray(x2), np.asarray(y1) - np.asarray(y2))


def far_customers(
    world: World, rng: np.random.Generator, x: np.ndarray, y: np.ndarray, min_km: float
) -> np.ndarray:
    """For each point, a random customer living at least `min_km` away.

    Rejection sampling; after a few tries we accept the farthest draw so it always ends.
    """
    customers = world.tables["customers"]
    cx, cy = customers["x_km"].to_numpy(), customers["y_km"].to_numpy()
    n = len(x)
    pick = rng.integers(0, len(customers), n)
    for _ in range(10):
        too_close = distance_km(cx[pick], cy[pick], x, y) < min_km
        if not too_close.any():
            break
        pick[too_close] = rng.integers(0, len(customers), int(too_close.sum()))
    return customers["customer_id"].to_numpy()[pick]


def qr_frame(
    world: World,
    day_idx: np.ndarray,
    seconds: np.ndarray,
    payer: np.ndarray,
    shop_id: np.ndarray,
    amount: np.ndarray,
    rng: np.random.Generator,
) -> pd.DataFrame:
    n = len(day_idx)
    return pd.DataFrame(
        {
            # Runs that spill past midnight are kept on their own day, at 23:59:59.
            "ts": to_ts(world.config, day_idx, np.minimum(seconds, SECONDS_PER_DAY - 1)),
            "payer_id": payer,
            "shop_id": shop_id,
            "amount": np.asarray(amount, dtype=np.int64),
            "on_us": rng.random(n) < world.config.qr.on_us_share,
            **label_columns(world, n),
        }
    )[QR_COLUMNS]


def day_index(world: World, date) -> int:
    """Day index of `date` within the window (may be < 0 or >= days)."""
    return (pd.Timestamp(date) - pd.Timestamp(world.config.calendar.start)).days
