"""Observable, imperfect case labels.

`case_label` stands for what past analyst cases recorded. It is the true label
with some misuse missed (miss_rate) and some honest rows wrongly flagged
(false_flag_rate), drawn independently per row. The true label stays hidden in
`_true_is_misuse` for evaluation only.
"""

import numpy as np

from jachai.world.rng import stream
from jachai.world.world import TRUE_LABEL, World

CASE_LABEL = "case_label"
# table -> which noise rates apply
NOISY_TABLES = {"shops": "shops", "qr_payments": "payments", "p2p_transfers": "payments"}


def apply_label_noise(world: World) -> None:
    if world.patterns is None:
        return
    rng = stream(world.config.seed, "label_noise")
    for table, level in NOISY_TABLES.items():
        noise = getattr(world.patterns.label_noise, level)
        df = world.tables[table]
        truth = df[TRUE_LABEL].to_numpy()
        u = rng.random(len(df))
        case = np.where(truth == 1, u >= noise.miss_rate, u < noise.false_flag_rate)
        df[CASE_LABEL] = case.astype(np.int8)
