"""Feature-group importance on validation. Does not rewrite the model-comparison report.

    JACHAI_PROFILE=fast python -m jachai.eval.feature_justification

Same shop-and-time split and the same LightGBM training as the payment model.
Thresholds are fit on validation targets (rules and past cases), never on the
hidden label. The hidden label is used only to grade. The test split is not
scored.

For each feature group in configs/models.yaml:
  TreeSHAP   mean absolute contribution on validation payments (LightGBM pred_contrib)
  permutation  drop in validation PR-AUC when that group's columns are shuffled
  ablation   retrain without the group; change in validation PR-AUC, F1 and recall

The four mechanism columns are also dropped one at a time.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import numpy as np

from jachai.eval import metrics as m
from jachai.eval.model_comparison import COMPARISON_SEEDS, OUT_DIR, _jsonable
from jachai.explain.reasons import feature_to_code, load_reason_codes, payment_shap
from jachai.features import feature_columns
from jachai.features.config import load_thresholds
from jachai.labels.config import load_rules
from jachai.models.config import load_models_config
from jachai.models.payment import train_payment_model
from jachai.models.train import prepare_payment_data
from jachai.provenance import provenance
from jachai.world.config import load_patterns_config, load_world_config
from jachai.world.generate import generate_world
from jachai.world.world import TRUE_LABEL

PERMUTATIONS = 5
MECHANISM_COLUMNS = (
    "payer_repeat_rate",
    "one_time_payer_share_30d",
    "hour_vs_shop_median_30d",
    "minutes_since_inflow",
)

# Real-world story each group is meant to capture. A hypothesis, not a finding.
# The finding is the measured column next to it.
MECHANISMS = {
    "amount": (
        "Round amounts, a basket far from the category's usual ticket, and payments "
        "just under the incentive cap. Hypothesis: a cash desk and cap-splitting "
        "leave these traces."
    ),
    "timing": (
        "Hour, Friday, and whether the payment is outside opening hours. "
        "Hypothesis: cash-out desks run when the shop would normally be shut."
    ),
    "payer_day": (
        "How much this payer has already paid today, and how that compares with the daily limit. "
        "Hypothesis: limit bypass is a day total pushed across several shops."
    ),
    "money_in_then_out": (
        "Add-money or remittance in a short window before the payment, and the share spent. "
        "Hypothesis: a drain pays out money that has just arrived."
    ),
    "who_and_where": (
        "First visit at this shop, and how far the payer lives from it. "
        "Hypothesis: a cash desk is paid by people who are not its regulars and do not live nearby."
    ),
    "payer_history": (
        "The payer's recent volume, shops, round-amount share and account age. "
        "Hypothesis: a mule account is young and busy."
    ),
    "shop_history": (
        "The shop's recent turnover, round receipts, night share, strangers and peer comparison. "
        "Hypothesis: a misused shop looks unlike its own past and unlike similar shops."
    ),
    "mechanism": (
        "Payer repeat rate, one-time-payer share, time of day versus this shop's own hours, "
        "and minutes from the last top-up or remittance. "
        "Hypothesis: the same stories at a finer grain."
    ),
}


def _groups(columns: list[str]) -> dict[str, list[str]]:
    codes = load_reason_codes()
    mapping = feature_to_code(codes)
    configured = load_models_config().ablation.payment_feature_groups
    groups = {}
    for name, code_list in configured.items():
        wanted = set(code_list)
        groups[name] = [col for col in columns if mapping.get(col) in wanted]
    covered = {col for cols in groups.values() for col in cols}
    missing = [col for col in columns if col not in covered]
    if missing:
        groups["ungrouped"] = missing
    return groups


def _grade(truth: np.ndarray, proba: np.ndarray, flag: np.ndarray, amount: np.ndarray) -> dict:
    return {
        "pr_auc": m.pr_auc(truth, proba),
        "precision": m.precision(truth, flag),
        "recall": m.recall(truth, flag),
        "f1": _f1(m.precision(truth, flag), m.recall(truth, flag)),
        "fpr": m.false_positive_rate(truth, flag),
        "value_recall": m.value_weighted_recall(truth, flag, amount),
    }


def _f1(precision: float, recall: float) -> float:
    if np.isnan(precision) or np.isnan(recall):
        return float("nan")
    if precision + recall == 0:
        return 0.0
    return float(2 * precision * recall / (precision + recall))


def _train(payments, split, targets, models, seed, drop: list[str]):
    frame = payments.drop(columns=drop) if drop else payments
    return train_payment_model(frame, split, targets, models.payment_model, seed)


def _permutation(model, frame, truth, base_auc, columns: list[str], seed: int) -> float:
    if not columns or np.isnan(base_auc):
        return float("nan")
    rng = np.random.default_rng(seed)
    drops = []
    for _ in range(PERMUTATIONS):
        scrambled = frame.copy()
        for col in columns:
            scrambled[col] = rng.permutation(scrambled[col].to_numpy())
        drops.append(base_auc - m.pr_auc(truth, model.predict_proba(scrambled)))
    return float(np.mean(drops))


def run_seed(seed: int) -> dict:
    cfg = load_world_config().model_copy(update={"seed": seed})
    patterns = load_patterns_config()
    thr = load_thresholds()
    rules = load_rules()
    models = load_models_config()
    world = generate_world(cfg, patterns)
    data = prepare_payment_data(world.tables, cfg, thr, rules)
    target_cfg = rules.training_target
    targets = data.targets(target_cfg)
    columns = feature_columns(data.payments)
    groups = _groups(columns)
    model = _train(data.payments, data.split, targets, models, seed, [])

    va = data.split.to_numpy() == "validation"
    truth_all = (
        data.payments["payment_id"]
        .map(world.tables["qr_payments"].set_index("payment_id")[TRUE_LABEL])
        .to_numpy()
    )
    truth = truth_all[va]
    amount = data.payments.loc[va, "amount"].to_numpy()
    val_frame = data.payments.loc[va]
    proba = model.predict_proba(val_frame)
    flag = proba >= model.threshold
    full = _grade(truth, proba, flag, amount)
    n, positives = int(va.sum()), int(truth.sum())

    shap = payment_shap(model, val_frame).drop(columns="_bias")
    mean_abs = shap.abs().mean()
    total_abs = float(mean_abs.sum())

    rows = []
    for name, cols in groups.items():
        reduced = _train(data.payments, data.split, targets, models, seed, cols)
        reduced_va = data.payments.loc[va].drop(columns=cols)
        r_proba = reduced.predict_proba(reduced_va)
        r_flag = r_proba >= reduced.threshold
        graded = _grade(truth, r_proba, r_flag, amount)
        share = float(mean_abs.reindex(cols).sum() / total_abs) if total_abs else float("nan")
        rows.append(
            {
                "group": name,
                "n_features": len(cols),
                "features": cols,
                "shap_mean_abs": float(mean_abs.reindex(cols).sum()),
                "shap_share": share,
                "permutation_pr_auc_drop": _permutation(
                    model, val_frame, truth, full["pr_auc"], cols, seed
                ),
                "pr_auc": graded["pr_auc"],
                "pr_auc_drop": full["pr_auc"] - graded["pr_auc"],
                "f1": graded["f1"],
                "f1_drop": full["f1"] - graded["f1"],
                "recall": graded["recall"],
                "recall_drop": full["recall"] - graded["recall"],
                "value_recall_drop": full["value_recall"] - graded["value_recall"],
            }
        )
    singles = []
    for col in MECHANISM_COLUMNS:
        if col not in columns:
            continue
        reduced = _train(data.payments, data.split, targets, models, seed, [col])
        reduced_va = data.payments.loc[va].drop(columns=[col])
        r_proba = reduced.predict_proba(reduced_va)
        graded = _grade(truth, r_proba, r_proba >= reduced.threshold, amount)
        singles.append(
            {
                "feature": col,
                "shap_mean_abs": float(mean_abs.get(col, np.nan)),
                "pr_auc_drop": full["pr_auc"] - graded["pr_auc"],
                "f1_drop": full["f1"] - graded["f1"],
                "recall_drop": full["recall"] - graded["recall"],
            }
        )
    return {
        "seed": seed,
        "n": n,
        "positives": positives,
        "threshold": model.threshold,
        "full": full,
        "groups": rows,
        "mechanism_features": singles,
        "n_features": len(columns),
    }


def _mean_std(values: list[float]) -> tuple[float, float]:
    arr = np.array(values, dtype=float)
    if len(arr) == 0:
        return float("nan"), float("nan")
    if len(arr) == 1:
        return float(arr[0]), 0.0
    return float(np.mean(arr)), float(np.std(arr, ddof=1))


def _fmt(mean: float, std: float) -> str:
    if np.isnan(mean):
        return "n/a"
    return f"{mean:.3f} ± {std:.3f}"


def summarise(per_seed: list[dict]) -> dict:
    names = [row["group"] for row in per_seed[0]["groups"]]
    groups = []
    for name in names:
        picked = [next(g for g in seed["groups"] if g["group"] == name) for seed in per_seed]
        entry = {
            "group": name,
            "n_features": picked[0]["n_features"],
            "features": picked[0]["features"],
        }
        for key in (
            "shap_mean_abs",
            "shap_share",
            "permutation_pr_auc_drop",
            "pr_auc_drop",
            "f1_drop",
            "recall_drop",
            "value_recall_drop",
        ):
            mean, std = _mean_std([row[key] for row in picked])
            entry[f"{key}_mean"] = mean
            entry[f"{key}_std"] = std
        groups.append(entry)
    singles = []
    for feature in MECHANISM_COLUMNS:
        picked = [
            next(row for row in seed["mechanism_features"] if row["feature"] == feature)
            for seed in per_seed
        ]
        entry = {"feature": feature}
        for key in ("shap_mean_abs", "pr_auc_drop", "f1_drop", "recall_drop"):
            mean, std = _mean_std([row[key] for row in picked])
            entry[f"{key}_mean"] = mean
            entry[f"{key}_std"] = std
        singles.append(entry)
    n_mean, _ = _mean_std([s["n"] for s in per_seed])
    pos_mean, _ = _mean_std([s["positives"] for s in per_seed])
    return {
        "groups": groups,
        "mechanism_features": singles,
        "n_mean": n_mean,
        "positives_mean": pos_mean,
    }


def _cell(mean: float, std: float) -> str:
    return _fmt(mean, std)


def render_md(result: dict) -> str:
    summary = result["summary"]
    seeds = result["seeds"]
    sizes = "; ".join(
        f"seed {row['seed']}: N={row['n']:,}, positives={row['positives']:,}"
        for row in result["per_seed"]
    )
    lines = [
        "# Feature justification (validation)",
        "",
        (
            f"Generated by `python -m jachai.eval.feature_justification` with profile "
            f"`{result['profile']}`. Synthetic data only. LightGBM, same shop-and-time split "
            f"as the payment model, seeds {', '.join(str(s) for s in seeds)}. "
            "Metrics are mean ± sample standard deviation across seeds. "
            f"Validation payments: {sizes}. "
            f"Mean N={summary['n_mean']:.0f}, mean positives={summary['positives_mean']:.0f}. "
            "A drop is full-model score minus the score without that group: positive means "
            "the group was helping. SHAP is the mean absolute TreeSHAP contribution on the "
            "raw score (LightGBM `pred_contrib`), summed inside the group. Permutation shuffles "
            f"the group's columns together, {PERMUTATIONS} times, and records the drop in "
            "validation PR-AUC. Thresholds for F1 and recall are fit on validation targets, "
            "not on the hidden label. The test split is not scored. "
            f"Compute time: {result['compute_seconds']:.1f}s. "
            "This file does not replace reports/onsite/ai/model_comparison.md."
        ),
        "",
        "## Importance and ablation",
        "",
        "| Group | Features | SHAP mean abs | SHAP share | "
        "Permutation PR-AUC drop | PR-AUC drop | F1 drop | Recall drop |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in summary["groups"]:
        lines.append(
            "| {group} | {n} | {shap} | {share} | {perm} | {pr} | {f1} | {rec} |".format(
                group=row["group"],
                n=row["n_features"],
                shap=_cell(row["shap_mean_abs_mean"], row["shap_mean_abs_std"]),
                share=_cell(row["shap_share_mean"], row["shap_share_std"]),
                perm=_cell(row["permutation_pr_auc_drop_mean"], row["permutation_pr_auc_drop_std"]),
                pr=_cell(row["pr_auc_drop_mean"], row["pr_auc_drop_std"]),
                f1=_cell(row["f1_drop_mean"], row["f1_drop_std"]),
                rec=_cell(row["recall_drop_mean"], row["recall_drop_std"]),
            )
        )
    lines += [
        "",
        "## Mechanism features, dropped one at a time",
        "",
        "These four columns are also inside the `mechanism` group above. "
        "The single-column rows show whether one of them, rather than the bundle, moves the score.",
        "",
        "| Feature | SHAP mean abs | PR-AUC drop | F1 drop | Recall drop |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in summary["mechanism_features"]:
        lines.append(
            "| {name} | {shap} | {pr} | {f1} | {rec} |".format(
                name=row["feature"],
                shap=_cell(row["shap_mean_abs_mean"], row["shap_mean_abs_std"]),
                pr=_cell(row["pr_auc_drop_mean"], row["pr_auc_drop_std"]),
                f1=_cell(row["f1_drop_mean"], row["f1_drop_std"]),
                rec=_cell(row["recall_drop_mean"], row["recall_drop_std"]),
            )
        )
    lines += ["", "## What each group is for, and what the run showed", ""]
    lines.append("| Feature group | Real-world mechanism it captures | Evidence |")
    lines.append("| --- | --- | --- |")
    by_name = {row["group"]: row for row in summary["groups"]}
    for name, story in MECHANISMS.items():
        row = by_name.get(name)
        if row is None:
            evidence = "This group was not in the trained columns."
        else:
            evidence = (
                f"SHAP share {_cell(row['shap_share_mean'], row['shap_share_std'])}; "
                f"permutation PR-AUC drop "
                f"{_cell(row['permutation_pr_auc_drop_mean'], row['permutation_pr_auc_drop_std'])}"
                "; "
                f"retrain PR-AUC drop {_cell(row['pr_auc_drop_mean'], row['pr_auc_drop_std'])} "
                f"(N≈{summary['n_mean']:.0f}, positives≈{summary['positives_mean']:.0f})."
            )
        lines.append(f"| {name} | {story} | {evidence} |")
    lines += [
        "",
        "## Chart",
        "",
        "![PR-AUC drop when each group is removed](feature_justification.svg)",
        "",
        "## Caveats",
        "",
        "- Fast-profile validation has few misuse payments, so a drop inside "
        "the seed-to-seed spread is not a stable ranking.",
        "- SHAP is on the raw score. Permutation and ablation are on calibrated "
        "probabilities graded with the hidden label.",
        "- Retraining without a group also refits the threshold, so an F1 drop "
        "is not a pure feature effect.",
        "- The mechanism stories are hypotheses. A small or negative drop means "
        "this run did not show that the group helps.",
        "- The model-comparison report was fit before these four columns existed. "
        "Its numbers are unchanged.",
        "",
        "## Reproduce",
        "",
        "```bash\nJACHAI_PROFILE=fast python -m jachai.eval.feature_justification\n```",
        "",
    ]
    return "\n".join(lines)


def render_svg(summary: dict, profile: str) -> str:
    rows = summary["groups"]
    width, height = 760, 46 + 28 * len(rows)
    max_drop = max((abs(row["pr_auc_drop_mean"]) for row in rows), default=0.1) or 0.1
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="20" y="24" font-family="sans-serif" font-size="15" fill="#1c1917">'
        f"Validation PR-AUC drop when the group is removed ({profile})</text>",
    ]
    for i, row in enumerate(rows):
        y = 44 + i * 28
        drop = row["pr_auc_drop_mean"]
        span = 280 * (drop / max_drop) if max_drop else 0
        color = "#0f766e" if drop >= 0 else "#b45309"
        x = 250
        if span >= 0:
            parts.append(f'<rect x="{x}" y="{y}" width="{span:.1f}" height="16" fill="{color}"/>')
        else:
            parts.append(
                f'<rect x="{x + span:.1f}" y="{y}" width="{abs(span):.1f}" '
                f'height="16" fill="{color}"/>'
            )
        parts.append(
            f'<text x="16" y="{y + 13}" font-family="sans-serif" font-size="12" fill="#1c1917">'
            f"{row['group']}</text>"
        )
        parts.append(
            f'<text x="{x + 290}" y="{y + 13}" font-family="sans-serif" '
            f'font-size="12" fill="#44403c">'
            f"{drop:+.3f}</text>"
        )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def run(seeds: list[int]) -> dict:
    t0 = time.perf_counter()
    per_seed = [run_seed(seed) for seed in seeds]
    summary = summarise(per_seed)
    profile = os.environ.get("JACHAI_PROFILE", "").strip() or "reference"
    return {
        "profile": profile,
        "synthetic_data_only": True,
        "evaluated_on": "validation shops and dates, against the hidden true label",
        "test_set_touched": False,
        "seeds": list(seeds),
        "permutations": PERMUTATIONS,
        "shap": "LightGBM pred_contrib TreeSHAP, mean absolute value on validation payments",
        "ablation": (
            "retrain without the group; drop = full metric minus reduced metric; "
            "positive means the group helped"
        ),
        "threshold_rule": "max F1 against validation targets from rules and past cases",
        "mechanisms": MECHANISMS,
        "per_seed": per_seed,
        "summary": summary,
        "compute_seconds": time.perf_counter() - t0,
        "provenance": provenance(),
    }


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, nargs="*", default=list(COMPARISON_SEEDS))
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--allow-long", action="store_true")
    args = parser.parse_args(argv)
    profile = os.environ.get("JACHAI_PROFILE", "").strip() or "reference"
    if profile != "fast" and not args.allow_long:
        raise SystemExit("Refusing a long run. Use JACHAI_PROFILE=fast, or pass --allow-long.")
    result = run(args.seeds)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "feature_justification.svg").write_text(
        render_svg(result["summary"], result["profile"]), encoding="utf-8"
    )
    text = render_md(result)
    (out / "feature_justification.md").write_text(text, encoding="utf-8")
    (out / "feature_justification.json").write_text(
        json.dumps(_jsonable(result), indent=2) + "\n", encoding="utf-8"
    )
    print(text)
    print(f"Wrote {out / 'feature_justification.md'}")


if __name__ == "__main__":
    main()
