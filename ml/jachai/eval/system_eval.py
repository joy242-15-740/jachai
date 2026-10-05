"""Full-system evaluation on VALIDATION, over several seeds. Never uses the test set.

    python -m jachai.eval.system_eval    (what `make validate` runs)

For each seed in thresholds.yaml `eval.ablation_seeds`:
  1. generate the world, train the full system (payment + shop + network + fusion)
  2. shop level, validation shops on the last validation day: fused risk, every
     component, and both baselines at shop level
  3. fusion ablation: risk with only some component groups switched on
  4. payment feature-group ablation: retrain the payment model without one group
  5. evasion: regenerate the same world with no round misuse amounts, and score
     it with the system trained on the normal world (nothing refitted)

Budgets: `k` = analyst shop capacity scaled to the validation share of shops;
`bands` = as many shops as the fused system puts in review + high.
Results as mean ± std over seeds. Writes reports/validation_evaluation.{json,md}.

Limit: the held-out pattern's shops are all in TEST, so its recall can only be
measured in the single final test evaluation.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from jachai.eval import metrics as m
from jachai.explain.reasons import feature_to_code, load_reason_codes
from jachai.features import build_features
from jachai.features.config import ThresholdsConfig, load_thresholds
from jachai.labels.config import RulesConfig, load_rules
from jachai.models.config import ModelsConfig, load_models_config
from jachai.models.fusion import payment_components
from jachai.models.payment import train_payment_model
from jachai.system import Scored, score_system, train_system
from jachai.world.config import EvasionCfg, load_patterns_config, load_world_config
from jachai.world.generate import generate_world
from jachai.world.summary import default_report_path, md_table
from jachai.world.world import TRUE_LABEL, TRUE_PATTERN

MISUSE_PATTERNS = (
    "round_amount_cash_desk",
    "remittance_drain",
    "turnover_burst",
    "limit_bypass",
    "incentive_splitting",
    "p2p_disguise",
)


# --- shop-level scoring ------------------------------------------------------------


def eval_frame(scored: Scored, tables: dict, thr: ThresholdsConfig) -> pd.DataFrame:
    """Validation shops on the last validation day, with truth and baseline scores."""
    s = scored.shop_day
    day = pd.Timestamp(thr.split.validation_end)
    v = s[(s["split"] == "validation") & (s["day"] == day)].copy()
    shops = tables["shops"].set_index("shop_id")
    v["truth"] = v["shop_id"].map(shops[TRUE_LABEL]).to_numpy()
    v["pattern"] = v["shop_id"].map(shops[TRUE_PATTERN]).to_numpy()

    pay = scored.data.payments
    in_val = (scored.data.split == "validation").to_numpy()
    q = tables["qr_payments"].set_index("payment_id").loc[pay.loc[in_val, "payment_id"]]
    misuse_taka = q.loc[q[TRUE_LABEL] == 1].groupby("shop_id")["amount"].sum()
    v["misuse_taka"] = v["shop_id"].map(misuse_taka).fillna(0).to_numpy()

    # Baselines at shop level, from the last 30 days (earlier days only).
    recent = (pay["ts"] >= day - pd.Timedelta(days=30)).to_numpy() & (pay["ts"] < day).to_numpy()
    flagged = (
        pd.Series(scored.data.weak_label == 1)[recent]
        .groupby(pay.loc[recent, "shop_id"].to_numpy())
        .sum()
    )
    v["rules_only"] = v["shop_id"].map(flagged).fillna(0).to_numpy()
    daily = (
        pay[recent]
        .groupby([pay.loc[recent, "shop_id"], pay.loc[recent, "ts"].dt.normalize()])["amount"]
        .sum()
    )
    v["blanket_limit"] = v["shop_id"].map(daily.groupby(level=0).max()).fillna(0).to_numpy()
    return v.reset_index(drop=True)


def shop_metrics(v: pd.DataFrame, score: np.ndarray, k: int, n_band: int) -> dict:
    t, taka = v["truth"].to_numpy(), v["misuse_taka"].to_numpy()
    score = np.nan_to_num(score, nan=-np.inf)
    order = np.argsort(-score, kind="stable")
    out = {"pr_auc": m.pr_auc(t, np.where(np.isinf(score), 0, score))}
    for label, n in (("k", k), ("bands", n_band)):
        top = np.zeros(len(t), dtype=bool)
        top[order[:n]] = True
        out[f"{label}_n"] = n
        out[f"{label}_precision"] = m.precision(t, top)
        out[f"{label}_recall"] = m.recall(t, top)
        out[f"{label}_value_recall"] = float(taka[top].sum() / taka.sum()) if taka.sum() else np.nan
        out[f"{label}_honest_shops"] = int((top & (t == 0)).sum())
        honest_lookalike = v["pattern"].str.startswith("hn_").to_numpy()
        out[f"{label}_honest_lookalikes"] = int((top & honest_lookalike).sum())
        if label == "bands":
            for p in MISUSE_PATTERNS:
                mask = v["pattern"].to_numpy() == p
                if mask.any():
                    out[f"recall_{p}"] = float(top[mask].mean())
    return out


def risk_with(
    system, frame: pd.DataFrame, models: ModelsConfig, group_names: list[str]
) -> np.ndarray:
    """Fused risk using only the components of the given fusion groups (same fixed weights)."""
    cols = [c for g in group_names for c in models.ablation.fusion_groups[g]]
    ranks = system.fusion.ranks(frame)[cols]
    w = pd.Series(models.fusion.weights)[cols]
    return (ranks * w).sum(axis=1).to_numpy() / w.sum()


def budgets(v: pd.DataFrame, thr: ThresholdsConfig) -> tuple[int, int]:
    k = round(thr.eval.analyst_capacity_shops * thr.split.shop_shares["validation"])
    n_band = int(v["band"].isin(["review", "high"]).sum())
    return k, n_band


# --- one seed ------------------------------------------------------------------------


def evaluate_seed(seed: int, thr, rules: RulesConfig, models: ModelsConfig) -> dict:
    base, patterns = load_world_config(), load_patterns_config()
    cfg = base.model_copy(update={"seed": seed})
    world = generate_world(cfg, patterns)
    shop_day = build_features(world.tables, cfg, thr.features)["shop_day"]
    system, scored = train_system(world.tables, shop_day, cfg, thr, rules, models)
    v = eval_frame(scored, world.tables, thr)
    k, n_band = budgets(v, thr)

    rows = []

    def add(group: str, name: str, score: np.ndarray, frame: pd.DataFrame = v) -> None:
        rows.append(
            {"seed": seed, "group": group, "variant": name, **shop_metrics(frame, score, k, n_band)}
        )

    # 2) system, components, baselines
    add("system", "fused_risk", v["risk"].to_numpy())
    for c in models.fusion.weights:
        add("component", c, v[c].to_numpy(dtype=float))
    add("baseline", "rules_only", v["rules_only"].to_numpy(dtype=float))
    add("baseline", "blanket_limit", v["blanket_limit"].to_numpy(dtype=float))

    # 3) fusion groups
    groups = models.ablation.fusion_groups
    for g in groups:
        add("fusion_only", f"only {g}", risk_with(system, v, models, [g]))
        add(
            "fusion_only",
            f"all but {g}",
            risk_with(system, v, models, [x for x in groups if x != g]),
        )

    # 4) payment feature groups (retrain the payment model without each)
    codes = feature_to_code(load_reason_codes())
    target = scored.data.targets(rules.training_target)
    va = (scored.data.split == "validation").to_numpy()
    q = world.tables["qr_payments"].set_index("payment_id").loc[scored.data.payments["payment_id"]]
    pay_truth = q[TRUE_LABEL].to_numpy()
    payment_rows = [
        {
            "seed": seed,
            "dropped": "(none)",
            "payment_pr_auc": m.pr_auc(pay_truth[va], scored.payment_proba[va]),
        }
    ]
    for group, group_codes in models.ablation.payment_feature_groups.items():
        drop = [f for f, c in codes.items() if c in group_codes and f in scored.data.payments]
        pm = train_payment_model(
            scored.data.payments.drop(columns=drop),
            scored.data.split,
            target,
            models.payment_model,
            cfg.seed,
        )
        proba = pm.predict_proba(scored.data.payments)
        comp = payment_components(
            scored.data.payments,
            proba,
            pm.threshold,
            v[["shop_id", "day"]],
            models.fusion.payment_window_days,
        )
        v2 = v.copy()
        v2[["payment_top3_7d", "payment_flag_share_7d"]] = comp.to_numpy()
        payment_rows.append(
            {
                "seed": seed,
                "dropped": group,
                "payment_pr_auc": m.pr_auc(pay_truth[va], proba[va]),
                **{
                    f"fused_{key}": val
                    for key, val in shop_metrics(v2, system.fusion.risk(v2), k, n_band).items()
                    if key in ("pr_auc", "k_precision", "bands_recall", "bands_value_recall")
                },
            }
        )

    # 5) evasion: same seed, no round misuse amounts; scored by the trained system
    evaded_patterns = patterns.model_copy(update={"evasion": EvasionCfg(remove_round_amounts=True)})
    evaded = generate_world(cfg, evaded_patterns)
    e_shop_day = build_features(evaded.tables, cfg, thr.features)["shop_day"]
    e_scored = score_system(system, evaded.tables, e_shop_day, cfg, thr, rules, models)
    e = eval_frame(e_scored, evaded.tables, thr)
    rows.append(
        {
            "seed": seed,
            "group": "evasion",
            "variant": "fused_risk",
            **shop_metrics(e, e["risk"].to_numpy(), k, n_band),
        }
    )
    rows.append(
        {
            "seed": seed,
            "group": "evasion",
            "variant": "rules_only",
            **shop_metrics(e, e["rules_only"].to_numpy(dtype=float), k, n_band),
        }
    )
    no_rules = [g for g in models.ablation.fusion_groups if g != "rules"]
    rows.append(
        {
            "seed": seed,
            "group": "evasion",
            "variant": "all but rules",
            **shop_metrics(e, risk_with(system, e, models, no_rules), k, n_band),
        }
    )
    ev_va = (e_scored.data.split == "validation").to_numpy()
    eq = (
        evaded.tables["qr_payments"]
        .set_index("payment_id")
        .loc[e_scored.data.payments["payment_id"]]
    )
    payment_rows.append(
        {
            "seed": seed,
            "dropped": "(evasion world: no round misuse amounts)",
            "payment_pr_auc": m.pr_auc(
                eq[TRUE_LABEL].to_numpy()[ev_va], e_scored.payment_proba[ev_va]
            ),
        }
    )
    return {
        "seed": seed,
        "validation_shops": len(v),
        "validation_misuse_shops": int(v["truth"].sum()),
        "k": k,
        "band_budget": n_band,
        "band_counts": pd.crosstab(v["band"], v["truth"]).to_dict(),
        "shop_rows": rows,
        "payment_rows": payment_rows,
    }


# --- summary and report ----------------------------------------------------------------


def mean_std(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    num = df.drop(columns=["seed"]).select_dtypes("number").columns
    g = df.groupby(keys, sort=False)[list(num)]
    mean, std = g.mean(), g.std(ddof=0)
    return mean.combine(
        std, lambda a, b: a.combine(b, lambda x, y: f"{x:.3f} ± {y:.3f}" if pd.notna(x) else "n/a")
    )


def run() -> dict:
    thr, rules, models = load_thresholds(), load_rules(), load_models_config()
    per_seed = []
    for seed in thr.eval.ablation_seeds:
        per_seed.append(evaluate_seed(seed, thr, rules, models))
        print(f"seed {seed} done", flush=True)
    return {
        "evaluated_on": "validation shops, last validation day; hidden truth",
        "test_set_touched": False,
        "seeds": thr.eval.ablation_seeds,
        "per_seed": per_seed,
    }


HEADLINE = {  # name -> (normal-world (group, variant), evasion-world (group, variant))
    "rules only": (("baseline", "rules_only"), ("evasion", "rules_only")),
    "Jachai without rules": (("fusion_only", "all but rules"), ("evasion", "all but rules")),
    "Jachai with rules": (("system", "fused_risk"), ("evasion", "fused_risk")),
}
HEADLINE_METRICS = [
    "pr_auc",
    "bands_precision",
    "bands_recall",
    "bands_value_recall",
    "recall_limit_bypass",
]

CIRCULARITY = (
    "**Circularity note.** The synthetic world and the rules (labeling functions) were "
    "both written from the same reported misuse typologies. The rules therefore match "
    "the injected patterns almost exactly and look much stronger on the normal world "
    "than they would on real data, where misuse is messier and adapts. The fairer tests "
    "of whether Jachai generalises are: the evasion test (misusers stop using round "
    "amounts), ring detection (limit-bypass rings found through the payer-shop network), "
    "and the held-out pattern, which the models never see and which is measured once, "
    "in the final test evaluation."
)


def headline(shop: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(mean ± std text table, numeric means) for the three-way comparison."""
    text, means = {}, {}
    for name, ((ng, nv), (eg, ev)) in HEADLINE.items():
        row_t, row_m = {}, {}
        for setting, (g, var) in (("normal", (ng, nv)), ("evasion", (eg, ev))):
            sub = shop[(shop["group"] == g) & (shop["variant"] == var)]
            for metric in HEADLINE_METRICS:
                col = f"{setting}: {'ring recall' if metric == 'recall_limit_bypass' else metric}"
                row_m[col] = sub[metric].mean()
                row_t[col] = f"{sub[metric].mean():.3f} ± {sub[metric].std(ddof=0):.3f}"
        text[name], means[name] = row_t, row_m
    return pd.DataFrame(text).T.rename_axis("system"), pd.DataFrame(means).T


def success_checks(means: pd.DataFrame) -> list[str]:
    """The agreed success criteria, checked on the numbers (never hand-written)."""
    r, w, wo = (
        means.loc["rules only"],
        means.loc["Jachai with rules"],
        means.loc["Jachai without rules"],
    )
    ok1 = w["normal: pr_auc"] >= r["normal: pr_auc"] - 0.02
    ok2 = w["evasion: pr_auc"] > r["evasion: pr_auc"]
    ok3 = (
        w["evasion: ring recall"] > r["evasion: ring recall"]
        and w["normal: ring recall"] >= r["normal: ring recall"] - 0.02
    )
    lines = [
        f"Normal world: Jachai with rules PR-AUC {w['normal: pr_auc']:.3f} vs rules "
        f"{r['normal: pr_auc']:.3f} (needs to be within 0.02 or better): "
        f"{'MET' if ok1 else 'NOT MET'}.",
        f"Evasion world: {w['evasion: pr_auc']:.3f} vs rules {r['evasion: pr_auc']:.3f} "
        f"(needs to stay ahead): {'MET' if ok2 else 'NOT MET'}.",
        f"Rings: recall {w['normal: ring recall']:.3f} normal / {w['evasion: ring recall']:.3f} "
        f"evasion vs rules {r['normal: ring recall']:.3f} / {r['evasion: ring recall']:.3f} "
        f"(needs to stay ahead under evasion, not fall behind on normal): "
        f"{'MET' if ok3 else 'NOT MET'}.",
        f"Effect of adding rules: normal PR-AUC {wo['normal: pr_auc']:.3f} -> "
        f"{w['normal: pr_auc']:.3f}; evasion {wo['evasion: pr_auc']:.3f} -> "
        f"{w['evasion: pr_auc']:.3f}.",
        "Overall: "
        + (
            "all criteria met." if ok1 and ok2 and ok3 else "NOT all criteria met: stop and review."
        ),
    ]
    return lines


def render(result: dict) -> str:
    shop = pd.DataFrame([r for s in result["per_seed"] for r in s["shop_rows"]])
    pay = pd.DataFrame([r for s in result["per_seed"] for r in s["payment_rows"]])
    # The "(none)" row's fused metrics are the full system's own shop metrics.
    system = shop[(shop["group"] == "system")].set_index("seed")
    for key in ("pr_auc", "k_precision", "bands_recall", "bands_value_recall"):
        none = pay["dropped"] == "(none)"
        pay.loc[none, f"fused_{key}"] = pay.loc[none, "seed"].map(system[key]).to_numpy()
    shop_summary = mean_std(shop, ["group", "variant"])
    pay_summary = mean_std(pay, ["dropped"])
    main_cols = [
        "pr_auc",
        "k_precision",
        "k_recall",
        "k_value_recall",
        "k_honest_shops",
        "bands_precision",
        "bands_recall",
        "bands_value_recall",
        "bands_honest_lookalikes",
    ]
    pattern_cols = [c for c in shop_summary.columns if c.startswith("recall_")]

    def block(group: str, cols: list[str]) -> str:
        return md_table(shop_summary.loc[group, cols])

    sizes = "; ".join(
        f"seed {s['seed']}: {s['validation_shops']} shops, {s['validation_misuse_shops']} misuse, "
        f"k={s['k']}, band budget={s['band_budget']}"
        for s in result["per_seed"]
    )
    return (
        "\n\n".join(
            [
                "# Full-system evaluation (validation, several seeds)",
                "Generated by `make validate` (`python -m jachai.eval.system_eval`). "
                "Synthetic data only. Validation shops on the last validation day, against "
                "the hidden true label, mean ± std over seeds "
                f"{', '.join(map(str, result['seeds']))}. "
                "This evaluation does not use the test set (the single final test is "
                "reported separately: reports/final_test.md, "
                f"reports/test_access_log.md). {sizes}.",
                "`k`: analyst capacity scaled to validation shops. `bands`: as many shops as the "
                "fused system puts in review + high (same budget for every row). "
                "`value_recall`: share of validation-period misuse taka at the flagged shops. "
                "The held-out pattern's shops are all in test, so it is not measured here.",
                "## Headline: rules only vs Jachai without rules vs Jachai with rules",
                "Same budget for every row (`bands`: as many shops as Jachai with rules puts in "
                "review + high). `ring recall`: limit-bypass shops found at that budget.",
                md_table(headline(shop)[0]),
                "### Success criteria (computed)",
                "\n".join(f"- {line}" for line in success_checks(headline(shop)[1])),
                CIRCULARITY,
                "## System vs baselines (shop level)",
                block("system", main_cols),
                block("baseline", main_cols),
                "## Each component alone",
                block("component", main_cols),
                "## Fusion with only some groups",
                block("fusion_only", main_cols),
                "## Recall per misuse pattern at the band budget",
                md_table(
                    pd.concat(
                        [
                            shop_summary.loc["system", pattern_cols],
                            shop_summary.loc["baseline", pattern_cols],
                        ]
                    )
                ),
                "## Payment model without one feature group",
                "`payment_pr_auc`: payment level on validation. `fused_*`: the fused shop score "
                "with that payment model.",
                md_table(pay_summary),
                "## Evasion test: misuse amounts made non-round, system NOT retrained",
                md_table(shop_summary.loc["evasion", main_cols + pattern_cols]),
            ]
        )
        + "\n"
    )


def main() -> None:
    result = run()
    reports = default_report_path().parent
    (reports / "validation_evaluation.json").write_text(
        json.dumps(result, indent=2, default=float) + "\n", encoding="utf-8"
    )
    text = render(result)
    (reports / "validation_evaluation.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
