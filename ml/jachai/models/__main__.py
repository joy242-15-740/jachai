"""`python -m jachai.models` (what `make train` runs).

Trains the payment model on rules' votes + past cases, saves it to models/ (gitignored) and
writes reports/payment_model_training.json. Does not touch the test set.
"""

from __future__ import annotations

import json

from jachai.features.config import load_thresholds
from jachai.labels.config import load_rules
from jachai.models.config import load_models_config
from jachai.models.train import prepare_payment_data, train_from_data, validation_report
from jachai.world.config import REPO_ROOT, load_world_config
from jachai.world.generate import read_world_tables
from jachai.world.summary import default_report_path, default_world_dir

MODELS_DIR = REPO_ROOT / "models"


def main() -> None:
    cfg, thr, rules, models = (
        load_world_config(),
        load_thresholds(),
        load_rules(),
        load_models_config(),
    )
    data = prepare_payment_data(read_world_tables(default_world_dir()), cfg, thr, rules)
    model = train_from_data(data, models, rules.training_target, cfg.seed)
    model.save(MODELS_DIR)
    report = {
        "model": "payment",
        "fingerprint": model.fingerprint(),
        **model.meta,
        "holdout_pattern": thr.split.holdout_pattern,
        "validation": validation_report(model, data, rules.training_target),
    }
    path = default_report_path().parent / "payment_model_training.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Model saved to {MODELS_DIR}; report {path}")


if __name__ == "__main__":
    main()
