"""Label-source ablation on VALIDATION, against the hidden truth. Never uses the test set.

    python -m jachai.eval.ablation    (what `make ablation` runs)

For every seed in thresholds.yaml `eval.ablation_seeds`, the world is regenerated
in memory and these are compared on validation shops and dates:
  rules_only             the labeling functions' vote, no model
  model_weak             LightGBM on rules' votes only
  model_weak_and_cases   LightGBM on rules' votes + past cases (the chosen design)
  model_cases            LightGBM on past cases only
plus model_weak_and_cases with past-case coverage of 2%, 5% and 10% of shops.

Two ways of comparing:
  at its own threshold   each variant flags what its frozen threshold says
  at a matched budget    every variant flags the same number of payments: the
                         rules' own flag count, and the analyst capacity k. This
                         is the fair test of "fewer honest flags for the same work".

Results are reported per seed and as mean ± std. Writes reports/ablation.json
and reports/ablation.md. Nothing is tuned on these numbers.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from jachai.eval import metrics as m
from jachai.features.config import ThresholdsConfig, load_thresholds
from jachai.labels.config import RulesConfig, load_rules
from jachai.labels.targets import case_verdict_for_payments
from jachai.models.config import ModelsConfig, load_models_config
from jachai.models.train import PaymentData, case_cutoffs, prepare_payment_data, train_from_data
from jachai.world.cases import make_cases
from jachai.world.config import PatternsConfig, WorldConfig, load_patterns_config, load_world_config
from jachai.world.generate import generate_world
from jachai.world.summary import default_report_path, md_table
from jachai.world.world import TRUE_LABEL, World

COVERAGES = (0.02, 0.05, 0.10)
MAIN = "model_weak_and_cases"


def top_n(score: np.ndarray, n: int) -> np.ndarray:
    """Flag the n highest scores (stable ties: earlier rows first)."""
    flag = np.zeros(len(score), dtype=bool)
    flag[np.argsort(-score, kind="stable")[: min(n, len(score))]] = True
    return flag


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
    honest_shop_flags = data.payments.loc[va, "shop_id"].to_numpy()
    row = {
        "variant": name,
        "pr_auc": m.pr_auc(t, s),
        "precision": m.precision(t, f),
        "recall": m.recall(t, f),
        "value_recall": m.value_weighted_recall(t, f, a),
        "flags": int(f.sum()),
        # Of the payments either one flags, the share both flag (1.0 = identical flags).
        "flag_overlap_with_rules": float((f & r).sum() / max((f | r).sum(), 1)),
    }
    # Matched budgets: same number of flags for every variant.
    budgets = {"rules_budget": int(r.sum()), "k": thr.eval.analyst_capacity_payments}
    for label, n in budgets.items():
        fb = top_n(s, n)
        honest_flagged = fb & (t == 0)
        row[f"{label}_n"] = n
        row[f"{label}_precision"] = m.precision(t, fb)
        row[f"{label}_recall"] = m.recall(t, fb)
        row[f"{label}_value_recall"] = m.value_weighted_recall(t, fb, a)
        row[f"{label}_honest_flags"] = int(honest_flagged.sum())
        row[f"{label}_honest_shops_flagged"] = int(
            len(np.unique(honest_shop_flags[honest_flagged]))
        )
    return row


def _case_counts(d: PaymentData) -> dict:
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


def ablate_world(
    tables: dict[str, pd.DataFrame],
    cfg: WorldConfig,
    thr: ThresholdsConfig,
    rules: RulesConfig,
    models: ModelsConfig,
    patterns: PatternsConfig,
) -> dict:
    data = prepare_payment_data(tables, cfg, thr, rules)
    q = tables["qr_payments"].set_index("payment_id").loc[data.payments["payment_id"]]
    truth, amount = q[TRUE_LABEL].to_numpy(), q["amount"].to_numpy()
    rules_flag = data.weak_label == 1
    rules_score = np.nan_to_num(data.weak_proba)

    def evaluate(name: str, d: PaymentData, mode: str) -> dict:
        target = rules.training_target.model_copy(update={"mode": mode})
        try:
            model = train_from_data(d, models, target, cfg.seed)
        except ValueError as err:  # e.g. no misuse case in validation to tune on
            return {"variant": name, "not_trainable": str(err), **_case_counts(d)}
        p = model.predict_proba(d.payments)
        row = score_on_validation(name, p, p >= model.threshold, d, truth, amount, rules_flag, thr)
        return {**row, "train_rows_with_evidence": model.meta["train_rows"], **_case_counts(d)}

    rows = [
        score_on_validation(
            "rules_only", rules_score, rules_flag, data, truth, amount, rules_flag, thr
        ),
        evaluate("model_weak", data, "weak"),
        evaluate(MAIN, data, "weak_and_cases"),
        evaluate("model_cases", data, "cases"),
    ]
    world = World(config=cfg, patterns=None, tables=tables)
    for cov in COVERAGES:
        audit = min(patterns.cases.audit_share, cov)
        cases_cfg = patterns.cases.model_copy(update={"coverage": cov, "audit_share": audit})
        world.patterns = patterns.model_copy(update={"cases": cases_cfg})
        d = PaymentData(
            data.payments,
            data.split,
            data.weak_proba,
            data.weak_label,
            case_verdict_for_payments(
                data.payments, data.split, make_cases(world), case_cutoffs(thr)
            ),
        )
        rows.append(evaluate(f"{MAIN} @ {cov:.0%} cases", d, "weak_and_cases"))
    va = (data.split == "validation").to_numpy()
    return {
        "seed": cfg.seed,
        "validation_payments": int(va.sum()),
        "validation_misuse_payments": int(truth[va].sum()),
        "variants": rows,
    }


def summarise(per_seed: list[dict]) -> pd.DataFrame:
    """mean and std per variant and metric across seeds (untrainable runs skipped)."""
    df = pd.concat(
        [pd.DataFrame(s["variants"]).assign(seed=s["seed"]) for s in per_seed], ignore_index=True
    )
    numeric = df.drop(columns=["seed"]).select_dtypes("number").columns
    grouped = df.groupby("variant", sort=False)[list(numeric)]
    out = grouped.mean().add_suffix("_mean").join(grouped.std(ddof=0).add_suffix("_std"))
    out["trained_seeds"] = df.groupby("variant", sort=False)["pr_auc"].count()
    return out


def run_ablation() -> dict:
    thr, rules, models = load_thresholds(), load_rules(), load_models_config()
    patterns, base = load_patterns_config(), load_world_config()
    per_seed = []
    for seed in thr.eval.ablation_seeds:
        cfg = base.model_copy(update={"seed": seed})
        world = generate_world(cfg, patterns)
        per_seed.append(ablate_world(world.tables, cfg, thr, rules, models, patterns))
        print(f"seed {seed} done")
    summary = summarise(per_seed)
    return {
        "evaluated_on": "validation shops and dates, against the hidden true label",
        "test_set_touched": False,
        "seeds": thr.eval.ablation_seeds,
        "per_seed": per_seed,
        "summary": summary.reset_index().to_dict(orient="records"),
    }


def _pm(summary: pd.DataFrame, variant: str, metric: str) -> str:
    mean, std = summary.loc[variant, f"{metric}_mean"], summary.loc[variant, f"{metric}_std"]
    return "n/a" if np.isnan(mean) else f"{mean:.3f} ± {std:.3f}"


def _compare(s: pd.DataFrame, metric: str, higher_is_better: bool) -> str:
    """'better' / 'worse' only if the gap beats both stds combined, else 'no clear difference'."""
    model, rules = s.loc[MAIN], s.loc["rules_only"]
    gap = model[f"{metric}_mean"] - rules[f"{metric}_mean"]
    if abs(gap) <= model[f"{metric}_std"] + rules[f"{metric}_std"]:
        return "no clear difference"
    return "model better" if (gap > 0) == higher_is_better else "model worse"


def _verdicts(s: pd.DataFrame, budget: str) -> str:
    return (
        f"Verdict: precision {_compare(s, f'{budget}_precision', True)}; taka caught "
        f"{_compare(s, f'{budget}_value_recall', True)}; honest shops flagged "
        f"{_compare(s, f'{budget}_honest_shops_flagged', False)}."
    )


def findings(summary: pd.DataFrame, per_seed: list[dict]) -> list[str]:
    """Plain-language comparisons, all computed (no hand-typed numbers)."""
    s, r = summary, "rules_only"
    out = [
        f"Ranking (PR-AUC): rules {_pm(s, r, 'pr_auc')}, weak-only model "
        f"{_pm(s, 'model_weak', 'pr_auc')}, weak + cases model {_pm(s, MAIN, 'pr_auc')}.",
    ]
    for budget, what in (
        ("rules_budget", "the rules' own number of flags"),
        ("k", "the analyst capacity k"),
    ):
        out.append(
            f"At {what} (same budget for all): precision rules {_pm(s, r, f'{budget}_precision')} "
            f"vs model {_pm(s, MAIN, f'{budget}_precision')}; misuse taka caught rules "
            f"{_pm(s, r, f'{budget}_value_recall')} vs model "
            f"{_pm(s, MAIN, f'{budget}_value_recall')}; "
            f"honest shops flagged rules {_pm(s, r, f'{budget}_honest_shops_flagged')} vs model "
            f"{_pm(s, MAIN, f'{budget}_honest_shops_flagged')}. " + _verdicts(s, budget)
        )
    wins = sum(
        next(v for v in seed["variants"] if v["variant"] == MAIN).get("pr_auc", np.nan)
        > next(v for v in seed["variants"] if v["variant"] == r)["pr_auc"]
        for seed in per_seed
    )
    out.append(
        f"The weak + cases model ranks better than the rules in {wins} of {len(per_seed)} seeds."
    )
    out.append(
        f"At its own frozen threshold the model has precision {_pm(s, MAIN, 'precision')} vs "
        f"rules {_pm(s, r, 'precision')}: it flags more ({_pm(s, MAIN, 'flags')} vs "
        f"{_pm(s, r, 'flags')} payments), so a fair claim needs the matched budget above."
    )
    cov = [f"{c:.0%}: {_pm(s, f'{MAIN} @ {c:.0%} cases', 'pr_auc')}" for c in COVERAGES]
    # Neighbouring coverages differ "clearly" only if the gap beats both stds combined.
    pairs = []
    for lo, hi in zip(COVERAGES, COVERAGES[1:], strict=False):
        a, b = f"{MAIN} @ {lo:.0%} cases", f"{MAIN} @ {hi:.0%} cases"
        gap = s.loc[b, "pr_auc_mean"] - s.loc[a, "pr_auc_mean"]
        spread = s.loc[a, "pr_auc_std"] + s.loc[b, "pr_auc_std"]
        verdict = "a clear difference" if abs(gap) > spread else "within seed-to-seed noise"
        pairs.append(f"{lo:.0%} to {hi:.0%}: {gap:+.3f} ({verdict})")
    out.append(
        "Case coverage vs PR-AUC: " + "; ".join(cov) + ". Steps: " + "; ".join(pairs) + ". "
        "Do not pick a 'best' coverage from differences that are within noise."
    )
    untrainable = s.index[s["trained_seeds"] < len(per_seed)].tolist()
    if untrainable:
        out.append(
            "Not trainable in some seeds (no misuse example to learn or tune on): "
            + ", ".join(
                f"{v} ({len(per_seed) - int(s.loc[v, 'trained_seeds'])} seeds)" for v in untrainable
            )
            + "."
        )
    return out


def render(result: dict) -> str:
    summary = pd.DataFrame(result["summary"]).set_index("variant")
    per_seed = result["per_seed"]
    main_cols = [
        "pr_auc",
        "precision",
        "recall",
        "value_recall",
        "flags",
        "flag_overlap_with_rules",
    ]

    def table(cols: list[str], variants: list[str]) -> pd.DataFrame:
        return pd.DataFrame(
            {c: [_pm(summary, v, c) for v in variants] for c in cols}, index=variants
        ).rename_axis("variant")

    sources = ["rules_only", "model_weak", MAIN, "model_cases"]
    coverage = [f"{MAIN} @ {c:.0%} cases" for c in COVERAGES]
    budget_cols = [
        f"{b}_{x}"
        for b in ("rules_budget", "k")
        for x in ("n", "precision", "recall", "value_recall", "honest_shops_flagged")
    ]
    seed_table = pd.DataFrame(
        {
            seed["seed"]: {v["variant"]: v.get("pr_auc", np.nan) for v in seed["variants"]}
            for seed in per_seed
        }
    ).round(3)
    sizes = "; ".join(
        f"seed {s['seed']}: {s['validation_payments']:,} payments, "
        f"{s['validation_misuse_payments']:,} misuse"
        for s in per_seed
    )
    return (
        "\n\n".join(
            [
                "# Label-source ablation (validation, several seeds)",
                "Generated by `make ablation` (`python -m jachai.eval.ablation`). Synthetic data "
                "only. Every number is on validation shops and dates, against the hidden true "
                "label, as mean ± std over seeds "
                f"{', '.join(str(x) for x in result['seeds'])}. "
                "This ablation does not use the test set (the single final test is "
                "reported separately: reports/final_test.md, "
                f"reports/test_access_log.md). Validation size: {sizes}.",
                "## Findings (computed)",
                "\n".join(f"- {line}" for line in findings(summary, per_seed)),
                "## Matched budget: every variant flags the same number of payments",
                "`rules_budget`: as many flags as the rules make. `k`: the analyst capacity in "
                "configs/thresholds.yaml. `honest_shops_flagged`: distinct honest shops with at "
                "least one wrongly flagged payment.",
                md_table(table(budget_cols, sources)),
                "## Each variant at its own frozen threshold",
                "`flag_overlap_with_rules`: of the payments either the variant or the rules "
                "flag, the share both flag (1.0 = identical).",
                md_table(table(main_cols, sources)),
                "## Past-case coverage (weak + cases model)",
                md_table(table(["pr_auc", "value_recall", "rules_budget_precision"], coverage)),
                "## PR-AUC per seed",
                md_table(seed_table.rename_axis("variant")),
            ]
        )
        + "\n"
    )


def main() -> None:
    result = run_ablation()
    reports = default_report_path().parent
    (reports / "ablation.json").write_text(
        json.dumps(result, indent=2, default=float) + "\n", encoding="utf-8"
    )
    text = render(result)
    (reports / "ablation.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
