"""Constants and JSON helpers shared by the live store, the cached store and the
route modules.

Kept free of ML imports on purpose: the serverless demo (JACHAI_CACHED_STORE=1)
installs only FastAPI, pydantic, numpy, pandas and PyYAML, so anything imported
at module level by a route must not pull in LightGBM, scikit-learn or networkx.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

ALERT_BANDS = ("review", "high")
STATUS = {"high": "needs review (high priority)", "review": "needs review", "low": "no action"}


def _clean(value):
    """JSON-safe scalar (NaN -> None, numpy -> python, timestamps -> ISO)."""
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and np.isnan(value):
        return None
    return value


def records(df: pd.DataFrame) -> list[dict]:
    return [{k: _clean(v) for k, v in row.items()} for row in df.to_dict(orient="records")]
