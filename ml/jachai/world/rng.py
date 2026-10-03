"""Named random streams.

Every part of the generator (shops, payments, each pattern, ...) gets its own
random stream, derived from the master seed and the part's name. So the same
seed always gives the same world, and switching one pattern off does not shift
the random numbers used by any other part.
"""

import zlib

import numpy as np


def stream(seed: int, name: str) -> np.random.Generator:
    """Independent, reproducible generator for `name` under master `seed`."""
    # crc32 is stable across runs and machines, unlike Python's built-in hash().
    return np.random.default_rng([seed, zlib.crc32(name.encode("utf-8"))])
