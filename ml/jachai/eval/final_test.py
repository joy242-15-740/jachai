"""Single-use final evaluation of the frozen full system.

This command trains and freezes the system on train/validation only, then reads
hidden truth for test rows exactly once. It refuses to overwrite an existing
result so an accidental rerun cannot silently replace the submitted evidence.
"""

from __future__ import annotations

import json

import pandas as pd

from jachai.eval.system_eval import MISUSE_PATTERNS, shop_metrics
from jachai.features import build_features
from jachai.features.config import load_thresholds
from jachai.labels.config import load_rules
from jachai.models.config import load_models_config
from jachai.provenance import provenance
from jachai.system import train_system
from jachai.world.config import load_patterns_config, load_world_config
from jachai.world.generate import generate_world
from jachai.world.summary import default_report_path, md_table
from jachai.world.world import TRUE_LABEL, TRUE_PATTERN


def final_frame(scored, tables: dict, cfg, thr) -> pd.DataFrame:
    """One row per test shop on the final generated day, with hidden truth."""
    day = pd.Timestamp(cfg.calendar.start) + pd.Timedelta(days=cfg.calendar.days - 1)
    frame = scored.shop_day[
        (scored.shop_day["split"] == "test") & (scored.shop_day["day"] == day)
    ].copy()
    shops = tables["shops"].set_index("shop_id")
    frame["truth"] = frame["shop_id"].map(shops[TRUE_LABEL]).to_numpy()
    frame["pattern"] = frame["shop_id"].map(shops[TRUE_PATTERN]).to_numpy()

    payments = scored.data.payments
    in_test = (scored.data.split == "test").to_numpy()
    truth = tables["qr_payments"].set_index("payment_id").loc[payments.loc[in_test, "payment_id"]]
    misuse_taka = truth.loc[truth[TRUE_LABEL] == 1].groupby("shop_id")["amount"].sum()
    frame["misuse_taka"] = frame["shop_id"].map(misuse_taka).fillna(0).to_numpy()

    recent = (payments["ts"] >= day - pd.Timedelta(days=30)).to_numpy() & (
        payments["ts"] < day
    ).to_numpy()
    rule_flags = (
        pd.Series(scored.data.weak_label == 1)[recent]
        .groupby(payments.loc[recent, "shop_id"].to_numpy())
        .sum()
    )
    frame["rules_only"] = frame["shop_id"].map(rule_flags).fillna(0).to_numpy()
    daily = (
        payments[recent]
        .groupby([payments.loc[recent, "shop_id"], payments.loc[recent, "ts"].dt.normalize()])[
            "amount"
        ]
        .sum()
    )
    frame["blanket_limit"] = frame["shop_id"].map(daily.groupby(level=0).max()).fillna(0)
    return frame.reset_index(drop=True)


def evaluate(frame: pd.DataFrame, thr) -> dict:
    """Compare frozen fusion and baselines at identical test budgets."""
    k = min(
        len(frame),
        max(1, round(thr.eval.analyst_capacity_shops * thr.split.shop_shares["test"])),
    )
    n_band = int(frame["band"].isin(["review", "high"]).sum())
    rows = {}
    for name, score in {
        "Jachai with rules": frame["risk"].to_numpy(dtype=float),
        "Rules only": frame["rules_only"].to_numpy(dtype=float),
        "Blanket limit": frame["blanket_limit"].to_numpy(dtype=float),
    }.items():
        rows[name] = shop_metrics(frame, score, k, n_band)
    return {
        "test_shops": len(frame),
        "test_misuse_shops": int(frame["truth"].sum()),
        "analyst_capacity_k": k,
        "band_budget": n_band,
        "held_out_pattern": thr.split.holdout_pattern,
        "metrics": rows,
    }


def render(result: dict) -> str:
    metrics = pd.DataFrame(result["metrics"]).T.rename_axis("method")
    cols = [
        "pr_auc",
        "k_precision",
        "k_recall",
        "k_value_recall",
        "k_honest_shops",
        "bands_precision",
        "bands_recall",
        "bands_value_recall",
        "bands_honest_shops",
    ]
    pattern_cols = [f"recall_{p}" for p in MISUSE_PATTERNS if f"recall_{p}" in metrics]
    return (
        "\n\n".join(
            [
                "# Final frozen-system test evaluation",
                "**FINAL TEST — single access.** Synthetic data only. The current full system "
                "was trained on train rows, thresholds were frozen on validation, and hidden "
                "test truth was read only for this report. No tuning may follow these results.",
                f"Test shops: {result['test_shops']}; misuse shops: "
                f"{result['test_misuse_shops']}; analyst-capacity k: "
                f"{result['analyst_capacity_k']}; matched band budget: "
                f"{result['band_budget']}; held-out pattern: "
                f"`{result['held_out_pattern']}`.",
                "## System and baselines at matched budgets",
                md_table(metrics[cols]),
                "## Recall by pattern at the matched band budget",
                md_table(metrics[pattern_cols]),
                "These results describe a synthetic test partition, not real-world accuracy or "
                "financial impact.",
            ]
        )
        + "\n"
    )


def main() -> None:
    reports = default_report_path().parent
    json_path = reports / "final_test.json"
    md_path = reports / "final_test.md"
    if json_path.exists() or md_path.exists():
        raise SystemExit("final test already exists; refusing to access or overwrite it")

    cfg = load_world_config()
    patterns = load_patterns_config()
    thr, rules, models = load_thresholds(), load_rules(), load_models_config()
    world = generate_world(cfg, patterns)
    shop_day = build_features(world.tables, cfg, thr.features)["shop_day"]
    system, scored = train_system(world.tables, shop_day, cfg, thr, rules, models)
    result = {
        "provenance": provenance(system.payment.fingerprint()),
        "evaluated_on": "frozen full system; test shops on final generated day",
        "test_set_touched": True,
        "seed": cfg.seed,
        **evaluate(final_frame(scored, world.tables, cfg, thr), thr),
    }
    json_path.write_text(json.dumps(result, indent=2, default=float) + "\n", encoding="utf-8")
    report = render(result)
    md_path.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
