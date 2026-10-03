"""Label-source ablation on VALIDATION, against the hidden truth. Test is not touched.

    python -m jachai.eval.ablation    (what `make ablation` runs)

Compares, on validation shops and dates:
  rules_only             the labeling functions' vote, no model
  model_weak             LightGBM on rules' votes only
  model_weak_and_cases   LightGBM on rules' votes + past cases (the chosen design)
  model_cases            LightGBM on past cases only
and repeats model_weak_and_cases with past-case coverage of 2%, 5% and 10% of
shops (cases regenerated with the same seed; everything else unchanged).

Writes reports/ablation.json and reports/ablation.md.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from jachai.eval import metrics as m
from jachai.features.config import ThresholdsConfig, load_thresholds
from jachai.labels.config import load_rules
from jachai.labels.targets import case_verdict_for_payments
from jachai.models.config import load_models_config
from jachai.models.train import PaymentData, case_cutoffs, prepare_payment_data, train_from_data
from jachai.world.cases import make_cases
from jachai.world.config import load_patterns_config, load_world_config
from jachai.world.generate import read_world_tables
from jachai.world.summary import default_report_path, default_world_dir, md_table
from jachai.world.world import TRUE_LABEL, World

COVERAGES = (0.02, 0.05, 0.10)


def score_on_validation(
    name: str,
    score: np.ndarray,
    flag: np.ndarray,
    data: PaymentData,
    truth: np.ndarray,
    amount: np.ndarray,
    rules_flag: np.ndarray,
    thr: ThresholdsConfig,
) -> dict:
    va = data.split.to_numpy() == "validation"
    t, s, f, a, r = truth[va], score[va], flag[va], amount[va], rules_flag[va]
    k = thr.eval.analyst_capacity_payments
    return {
        "variant": name,
        "pr_auc": m.pr_auc(t, s),
        f"precision_at_{k}": m.precision_at_k(t, s, k),
        "precision": m.precision(t, f),
        "recall": m.recall(t, f),
        "value_recall": m.value_weighted_recall(t, f, a),
        "flags": int(f.sum()),
        # Of the payments either one flags, the share both flag (1.0 = identical flags).
        "flag_overlap_with_rules": float((f & r).sum() / max((f | r).sum(), 1)),
    }


def run_ablation() -> dict:
    cfg, thr, rules = load_world_config(), load_thresholds(), load_rules()
    models, patterns = load_models_config(), load_patterns_config()
    tables = read_world_tables(default_world_dir())
    data = prepare_payment_data(tables, cfg, thr, rules)
    q = tables["qr_payments"].set_index("payment_id").loc[data.payments["payment_id"]]
    truth, amount = q[TRUE_LABEL].to_numpy(), q["amount"].to_numpy()
    rules_flag = data.weak_label == 1
    rules_score = np.nan_to_num(data.weak_proba)

    def case_counts(d: PaymentData) -> dict:
        """Shops with usable case evidence, per split and verdict."""
        out = {}
        for split in ("train", "validation"):
            rows = (d.split == split).to_numpy() & ~np.isnan(d.case_verdict)
            shops = pd.DataFrame(
                {"shop": d.payments.loc[rows, "shop_id"], "v": d.case_verdict[rows]}
            ).drop_duplicates("shop")
            out[f"{split}_case_shops_misuse"] = int((shops["v"] == 1).sum())
            out[f"{split}_case_shops_honest"] = int((shops["v"] == 0).sum())
        return out

    def evaluate(name, d: PaymentData, mode: str) -> dict:
        target = rules.training_target.model_copy(update={"mode": mode})
        try:
            model = train_from_data(d, models, target, cfg.seed)
        except ValueError as err:  # e.g. no misuse case in validation to tune on
            return {"variant": name, "not_trainable": str(err), **case_counts(d)}
        p = model.predict_proba(d.payments)
        row = score_on_validation(name, p, p >= model.threshold, d, truth, amount, rules_flag, thr)
        row["train_rows_with_evidence"] = model.meta["train_rows"]
        return {**row, **case_counts(d)}

    rows = [
        score_on_validation(
            "rules_only", rules_score, rules_flag, data, truth, amount, rules_flag, thr
        ),
        evaluate("model_weak", data, "weak"),
        evaluate("model_weak_and_cases", data, "weak_and_cases"),
        evaluate("model_cases", data, "cases"),
    ]

    coverage_rows = []
    world = World(config=cfg, patterns=None, tables=tables)
    for cov in COVERAGES:
        audit = min(patterns.cases.audit_share, cov)
        cases_cfg = patterns.cases.model_copy(update={"coverage": cov, "audit_share": audit})
        world.patterns = patterns.model_copy(update={"cases": cases_cfg})
        cases = make_cases(world)
        d = PaymentData(
            data.payments,
            data.split,
            data.weak_proba,
            data.weak_label,
            case_verdict_for_payments(data.payments, data.split, cases, case_cutoffs(thr)),
        )
        row = evaluate(f"model_weak_and_cases @ {cov:.0%} coverage", d, "weak_and_cases")
        row["cases"] = len(cases)
        row["usable_train_cases"] = int(
            data.payments.loc[
                (data.split == "train").to_numpy() & ~np.isnan(d.case_verdict), "shop_id"
            ].nunique()
        )
        coverage_rows.append(row)

    return {
        "evaluated_on": "validation shops and dates, against the hidden true label",
        "test_set_touched": False,
        "validation_payments": int((data.split == "validation").sum()),
        "validation_misuse_payments": int(truth[(data.split == "validation").to_numpy()].sum()),
        "label_sources": rows,
        "case_coverage": coverage_rows,
    }


def render(result: dict) -> str:
    sources = pd.DataFrame(result["label_sources"]).set_index("variant").round(3)
    coverage = pd.DataFrame(result["case_coverage"]).set_index("variant").round(3)
    return (
        "\n\n".join(
            [
                "# Label-source ablation (validation)",
                "Generated by `make ablation` (`python -m jachai.eval.ablation`). Synthetic data "
                "only. Every number is on validation shops and dates, against the hidden true "
                "label. The test set is not touched. "
                f"Validation: {result['validation_payments']:,} payments, "
                f"{result['validation_misuse_payments']:,} truly misuse.",
                "## Which labels should the model learn from?",
                "`flag_overlap_with_rules`: of the payments either the variant or the rules "
                "flag, the share both flag (1.0 = identical). `not_trainable`: the variant had "
                "no misuse example to learn or tune on. Case counts are shops with a usable "
                "past case (closed before the split's cutoff).",
                md_table(sources),
                "## How much do past cases need to cover?",
                "`model_weak_and_cases` with past cases on 2%, 5% and 10% of shops. "
                "`usable_train_cases`: training shops whose case closed before the training "
                "cutoff.",
                md_table(coverage),
            ]
        )
        + "\n"
    )


def main() -> None:
    result = run_ablation()
    reports = default_report_path().parent
    (reports / "ablation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    text = render(result)
    (reports / "ablation.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
