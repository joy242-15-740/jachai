"""The World container and the hidden-column convention.

Columns whose name starts with HIDDEN_PREFIX hold the generator's ground truth
(true label, pattern name, customer segment). They exist only for evaluation.
Feature and model code must read tables through `public_view`, which drops them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from jachai.world.config import PatternsConfig, WorldConfig

HIDDEN_PREFIX = "_true_"
TRUE_LABEL = f"{HIDDEN_PREFIX}is_misuse"
TRUE_PATTERN = f"{HIDDEN_PREFIX}pattern"
NORMAL = "normal"

ENTITY_TABLES = ("zones", "shops", "customers", "agents")
EVENT_TABLES = ("qr_payments", "remittances", "add_money", "p2p_transfers")

# ID prefix for each event table; IDs are assigned once, after all patterns ran.
EVENT_ID = {
    "qr_payments": ("payment_id", "QP"),
    "remittances": ("remittance_id", "RM"),
    "add_money": ("add_money_id", "AM"),
    "p2p_transfers": ("transfer_id", "PP"),
}


def public_view(df: pd.DataFrame) -> pd.DataFrame:
    """The table without ground-truth columns: what upay could actually observe."""
    return df.drop(columns=[c for c in df.columns if c.startswith(HIDDEN_PREFIX)])


@dataclass
class World:
    config: WorldConfig
    patterns: PatternsConfig | None
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    # Each shop's regular customers (see entities.regular_pools); used by patterns
    # that add honest volume.
    pools: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None

    def append(self, table: str, rows: pd.DataFrame) -> None:
        """Add event rows (e.g. from a pattern). Columns must match the table."""
        current = self.tables[table]
        missing = set(current.columns) ^ set(rows.columns)
        if missing:
            raise ValueError(f"{table}: column mismatch {sorted(missing)}")
        if rows.empty:
            return
        self.tables[table] = pd.concat([current, rows[current.columns]], ignore_index=True)
