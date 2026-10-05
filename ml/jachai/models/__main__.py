"""`python -m jachai.models` (what `make train` runs).

Trains the full system (payment model, shop score, fusion ranks; bands frozen on
validation), saves it to models/ (gitignored) and writes
reports/system_training.json. Does not touch the test set.
"""

from __future__ import annotations

import json

import joblib

from jachai.features import build_features
from jachai.features.config import load_thresholds
from jachai.labels.config import load_rules
from jachai.models.config import load_models_config
from jachai.models.train import validation_report
from jachai.provenance import provenance
from jachai.system import train_system
from jachai.world.config import load_world_config
from jachai.world.generate import read_world_tables
from jachai.world.summary import default_model_dir, default_report_path, default_world_dir


def main() -> None:
    cfg, thr, rules, models = (
        load_world_config(),
        load_thresholds(),
        load_rules(),
        load_models_config(),
    )
    tables = read_world_tables(default_world_dir())
    shop_day = build_features(tables, cfg, thr.features)["shop_day"]
    system, scored = train_system(tables, shop_day, cfg, thr, rules, models)

    model_dir = default_model_dir()
    system.payment.save(model_dir)
    joblib.dump(system.shop, model_dir / "shop_model.joblib")
    system.fusion.save(model_dir / "fusion.json")

    val = scored.shop_day[scored.shop_day["split"] == "validation"]
    report = {
        "system": "payment + shop + network + fusion",
        "provenance": provenance(system.payment.fingerprint()),
        "test_set_touched": False,
        "payment_model": {
            "fingerprint": system.payment.fingerprint(),
            **system.payment.meta,
            "validation_vs_targets": validation_report(
                system.payment, scored.data, rules.training_target
            ),
        },
        "shop_model": {
            "peer_forests": len(system.shop.forests),
            "turnover_residual_median": system.shop.residual_median,
            "turnover_residual_scale": system.shop.residual_scale,
        },
        "fusion": {
            "weights": models.fusion.weights,
            "band_cutoffs_frozen_on_validation": system.fusion.cutoffs,
            "validation_shop_days_per_band": val["band"].value_counts().to_dict(),
        },
    }
    path = default_report_path().parent / "system_training.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=float) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, default=float))
    print(f"System saved to {model_dir}; report {path}")


if __name__ == "__main__":
    main()
