"""Random string IDs. IDs carry no meaning and look nothing like phone or NID numbers."""

import numpy as np


def random_ids(rng: np.random.Generator, n: int, prefix: str, n_hex: int = 10) -> np.ndarray:
    """`n` unique IDs like 'SH3f9a0c12be': a letter prefix followed by random hex."""
    space = 16**n_hex
    values = rng.integers(0, space, size=n, dtype=np.int64)
    # Redraw any duplicates until all values are unique (deterministic given rng).
    while True:
        _, first = np.unique(values, return_index=True)
        if len(first) == n:
            break
        dup = np.ones(n, dtype=bool)
        dup[first] = False
        values[dup] = rng.integers(0, space, size=int(dup.sum()), dtype=np.int64)
    return np.array([f"{prefix}{v:0{n_hex}x}" for v in values], dtype=object)
