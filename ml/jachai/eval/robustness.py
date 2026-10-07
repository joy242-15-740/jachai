"""Robustness, peer-trend check, and an adaptive adversary. Validation only.

    JACHAI_PROFILE=fast python -m jachai.eval.robustness

Writes three new reports under reports/onsite/ai/. It does not edit the
model-comparison report, the reference validation report, or the final test.

The hidden label grades slices. It is not used to fit a threshold. Analyst
retraining uses noisy verdicts, not the raw label: the noise rates are the
ones already configured for past cases.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

from jachai.eval import metrics as m
from jachai.eval.model_comparison import OUT_DIR, _jsonable
from jachai.eval.splits import shop_groups
from jachai.explain.brief import analyst_evidence, analyst_template, validate_analyst_note
from jachai.explain.reasons import load_reason_codes, payment_reasons
from jachai.features.config import load_thresholds
from jachai.labels.config import load_rules
from jachai.models.config import load_models_config
from jachai.models.network import build_network_features
from jachai.models.payment import PaymentModel
from jachai.models.train import prepare_payment_data, train_from_data
from jachai.models.trend import HISTORY_DAYS, HORIZON_DAYS, linear_forecast
from jachai.provenance import provenance
from jachai.world.config import load_patterns_config, load_world_config
from jachai.world.generate import generate_world
from jachai.world.world import TRUE_LABEL, TRUE_PATTERN, public_view

# Hypothesis, written with the pattern definitions, not after seeing SHAP.
# Agreement means at least one of these codes is in the top 3 reasons.
EXPECTED_CODES = {
    "round_amount_cash_desk": frozenset(
        {
            "ROUND_AMOUNT",
            "AFTER_HOURS",
            "NEW_PAYER",
            "DISTANT_PAYER",
            "PAYER_REPEAT",
            "ONE_TIME_PAYERS",
        }
    ),
    "remittance_drain": frozenset({"AFTER_INFLOW", "INFLOW_LAG", "DISTANT_PAYER"}),
    "limit_bypass": frozenset({"NEAR_LIMIT"}),
    "incentive_splitting": frozenset({"JUST_UNDER_CAP"}),
    "p2p_disguise": frozenset({"SHOP_PROFILE"}),
    "turnover_burst": frozenset({"SHOP_BUSY", "LARGE_FOR_CATEGORY"}),
}

LOOKALIKES = (
    ("wholesalers", "category", "wholesaler"),
    ("electronics", "category", "electronics"),
    ("festival spikes", "pattern", "hn_festival_spike"),
    ("new shops", "pattern", "hn_new_shop_ramp"),
)

ADVERSARY_ROUNDS = (
    (1, "Drop round amounts"),
    (2, "Drop round amounts, and move about half the misuse payments to other shops"),
    (3, "Also cut misuse amounts in half"),
)


def _f1(precision: float, recall: float) -> float:
    if np.isnan(precision) or np.isnan(recall) or precision + recall == 0:
        return 0.0 if precision == 0 and recall == 0 else float("nan")
    return float(2 * precision * recall / (precision + recall))


def _metrics(truth: np.ndarray, proba: np.ndarray, flag: np.ndarray, amount: np.ndarray) -> dict:
    truth = np.asarray(truth)
    proba = np.asarray(proba)
    flag = np.asarray(flag)
    amount = np.asarray(amount)
    if len(truth) == 0:
        return {
            "n": 0,
            "positives": 0,
            "flagged": 0,
            "pr_auc": float("nan"),
            "precision": float("nan"),
            "recall": float("nan"),
            "f1": float("nan"),
            "fpr": float("nan"),
            "value_recall": float("nan"),
            "mean_score": float("nan"),
        }
    precision, recall = m.precision(truth, flag), m.recall(truth, flag)
    return {
        "n": int(len(truth)),
        "positives": int(np.asarray(truth).sum()),
        "flagged": int(np.asarray(flag).sum()),
        "pr_auc": m.pr_auc(truth, proba),
        "precision": precision,
        "recall": recall,
        "f1": _f1(precision, recall),
        "fpr": m.false_positive_rate(truth, flag),
        "value_recall": m.value_weighted_recall(truth, flag, amount),
        "mean_score": float(np.nanmean(proba)) if len(proba) else float("nan"),
    }


def _prepare(seed: int):
    cfg = load_world_config().model_copy(update={"seed": seed})
    patterns = load_patterns_config()
    thr = load_thresholds()
    rules = load_rules()
    models = load_models_config()
    world = generate_world(cfg, patterns)
    data = prepare_payment_data(world.tables, cfg, thr, rules)
    model = train_from_data(data, models, rules.training_target, seed)
    return world, data, model, cfg, thr, rules, models, patterns


def _labels(data, tables):
    qr = tables["qr_payments"].set_index("payment_id")
    truth = data.payments["payment_id"].map(qr[TRUE_LABEL]).to_numpy()
    pattern = data.payments["payment_id"].map(qr[TRUE_PATTERN]).to_numpy()
    shops = public_view(tables["shops"]).set_index("shop_id")
    category = data.payments["shop_id"].map(shops["category"]).to_numpy()
    return truth, pattern, category, shops


def _slice_metrics(truth, proba, flag, amount, mask) -> dict:
    if not mask.any():
        return _metrics(np.array([]), np.array([]), np.array([]), np.array([]))
    return _metrics(truth[mask], proba[mask], flag[mask], amount[mask])


def pattern_and_lookalikes(truth, pattern, category, proba, flag, amount, va) -> dict:
    patterns = []
    for name in list(EXPECTED_CODES) + sorted(
        {p for p in set(pattern[va]) if str(p).startswith("hn_")}
    ):
        mask = va & (pattern == name)
        row = _slice_metrics(truth, proba, flag, amount, mask)
        row["pattern"] = name
        row["kind"] = "misuse" if name in EXPECTED_CODES else "look_alike_pattern"
        patterns.append(row)
    looks = []
    for label, kind, value in LOOKALIKES:
        if kind == "category":
            mask = va & (category == value) & (truth == 0)
        else:
            mask = va & (pattern == value) & (truth == 0)
        row = _slice_metrics(truth, proba, flag, amount, mask)
        row["slice"] = label
        row["honest_payments"] = int(mask.sum())
        row["false_positives"] = int((mask & flag).sum())
        looks.append(row)
    return {"patterns": patterns, "lookalikes": looks}


def regime_slices(data, truth, proba, flag, amount, regime: pd.Timestamp) -> list[dict]:
    split = data.split.to_numpy()
    ts = data.payments["ts"]
    specs = (
        ("train shops, before 1 Oct", (split == "train") & (ts < regime).to_numpy()),
        ("train shops, on or after 1 Oct", (split == "train") & (ts >= regime).to_numpy()),
        ("validation shops (all after 1 Oct in this profile)", split == "validation"),
    )
    rows = []
    for name, mask in specs:
        row = _slice_metrics(truth, proba, flag, amount, mask)
        row["slice"] = name
        rows.append(row)
    return rows


def calibration(truth: np.ndarray, proba: np.ndarray, bins: int = 10) -> list[dict]:
    edges = np.linspace(0.0, 1.0, bins + 1)
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        mask = (proba >= lo) & (proba < hi if hi < 1 else proba <= hi)
        n = int(mask.sum())
        rows.append(
            {
                "lo": float(lo),
                "hi": float(hi),
                "n": n,
                "mean_predicted": float(proba[mask].mean()) if n else None,
                "observed_misuse_rate": float(truth[mask].mean()) if n else None,
            }
        )
    return rows


def shap_agreement(model, payments, pattern, flag, cfg) -> dict:
    codes = load_reason_codes()
    mask = np.asarray(flag) & np.isin(pattern, list(EXPECTED_CODES))
    frame = payments.iloc[np.flatnonzero(mask)]
    if frame.empty:
        return {
            "n_flagged_misuse": 0,
            "agreed": 0,
            "share": None,
            "top1_share": None,
            "by_pattern": [],
        }
    reasons = payment_reasons(model, frame, cfg, codes)
    used = pattern[mask]
    agreed = 0
    top1 = 0
    by = {name: {"n": 0, "agreed": 0} for name in EXPECTED_CODES}
    for name, found in zip(used, reasons, strict=True):
        got = [item.code for item in found]
        expected = EXPECTED_CODES[name]
        hit = bool(set(got) & expected)
        agreed += int(hit)
        top1 += int(bool(got) and got[0] in expected)
        by[name]["n"] += 1
        by[name]["agreed"] += int(hit)
    n = len(frame)
    return {
        "n_flagged_misuse": n,
        "agreed": agreed,
        "share": agreed / n,
        "top1_share": top1 / n,
        "by_pattern": [
            {
                "pattern": name,
                **counts,
                "share": (counts["agreed"] / counts["n"] if counts["n"] else None),
            }
            for name, counts in by.items()
        ],
        "mapping": {name: sorted(codes_) for name, codes_ in EXPECTED_CODES.items()},
    }


def false_rings(tables, cfg, thr, rules, models, seed: int) -> dict:
    """Honest shops in one zone that share a payer, and how often ring_flag is on.

    ring_flag is the existing rule (small, tight, heavy same-day links). It is not refit.
    Shared-payer here is any payer, including ordinary regulars. Test shops are excluded.
    The snapshot is the latest one on or before validation_end.
    """
    net = build_network_features(
        tables,
        pd.Timestamp(cfg.calendar.start),
        cfg.calendar.days,
        models.network,
        rules.ring_flag,
        thr.features.far_payer_km,
        cfg.regulation.cash_out_limit_daily,
        seed,
    )
    as_of = pd.Timestamp(thr.split.validation_end)
    snaps = net.loc[net["snapshot"] <= as_of, "snapshot"]
    if snaps.empty:
        return {"n_honest_sharing": 0, "false_rings": 0, "false_ring_rate": None}
    snap = snaps.max()
    latest = net[net["snapshot"] == snap].set_index("shop_id")
    shops = tables["shops"].set_index("shop_id")
    groups = shop_groups(tables["shops"], thr, seed)
    eligible = groups[groups != "test"].index
    honest = shops.index[(shops[TRUE_LABEL] == 0) & shops.index.isin(eligible)]
    qr = public_view(tables["qr_payments"])
    window = qr[(qr["ts"] < snap) & (qr["shop_id"].isin(honest))]
    pairs = window[["payer_id", "shop_id"]].drop_duplicates()
    both = pairs.merge(pairs, on="payer_id", suffixes=("_a", "_b"))
    both = both[both["shop_id_a"] != both["shop_id_b"]]
    zone = shops["zone_id"]
    both = both[both["shop_id_a"].map(zone).to_numpy() == both["shop_id_b"].map(zone).to_numpy()]
    sharing = pd.Index(both["shop_id_a"].unique())
    flagged = latest.reindex(sharing)["ring_flag"].fillna(0).to_numpy()
    n = int(len(sharing))
    hits = int((flagged == 1).sum())
    misuse = shops.index[(shops[TRUE_LABEL] == 1) & shops.index.isin(eligible)]
    misuse_rate = latest.reindex(misuse)["ring_flag"].fillna(0)
    return {
        "snapshot": snap.date().isoformat(),
        "n_honest_sharing_zone": n,
        "false_rings": hits,
        "false_ring_rate": (hits / n) if n else None,
        "n_honest_eligible": int(len(honest)),
        "n_misuse_eligible": int(len(misuse)),
        "misuse_ring_rate": float(misuse_rate.mean()) if len(misuse_rate) else None,
        "definition": (
            "Denominator: honest non-test shops that share at least one payer with another "
            "honest shop in the same zone, using payments before the snapshot. "
            "Numerator: those shops whose existing ring_flag is 1."
        ),
    }


def llm_validator() -> dict:
    """Fixed notes through the validator. No live model call, even if a key is set."""
    case = {
        "case_id": "SHexample",
        "scores": {"risk": 0.42, "band": "review", "components": {"payment_top3_7d": 0.42}},
        "reasons": [
            {"code": "AFTER_HOURS", "en": "Paid outside usual hours.", "bn": "সময়ের বাইরে।"}
        ],
        "neighbourhood": {"community_size": 1, "ring_flag": False, "linking_payers": 0},
    }
    evidence = analyst_evidence(case)
    template = analyst_template(case)
    notes = [
        ("template_against_llm_evidence", template),
        (
            "copies_evidence_numbers",
            "Shop SHexample needs human review. Its fused risk score is 0.42 "
            "and its current band is review.",
        ),
        ("empty", "   "),
        ("accusation", "This shop is guilty of fraud."),
        ("promise", "we guarantee this shop will be cleared."),
        ("invented_number", "Its fused risk score is 0.9999 and its band is review."),
        ("number_word", "There are nine linked shops."),
    ]
    rows = []
    for name, note in notes:
        result = validate_analyst_note(note, evidence)
        rows.append({"fixture": name, "valid": result.valid, "errors": list(result.errors)})
    rejected = [row for row in rows if not row["valid"]]
    return {
        "live_llm_called": False,
        "key_present_but_unused": bool(
            os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
        ),
        "n_fixtures": len(rows),
        "n_rejected": len(rejected),
        "reject_rate_on_fixtures": len(rejected) / len(rows),
        "fixtures": rows,
        "note": (
            "These are constructed notes, not a sample of production LLM output. "
            "The API only validates optional LLM rewording; the template is the fallback."
        ),
    }


def peer_trend_check(data, model: PaymentModel, tables, cfg, thr, seed: int) -> dict:
    """Of validation shop-days flagged early-warning, how many cross the threshold within 7 days.

    The horizon stops at validation_end. Test days are not read.
    """
    proba = model.predict_proba(data.payments)
    frame = pd.DataFrame(
        {
            "shop_id": data.payments["shop_id"].to_numpy(),
            "day": data.payments["ts"].dt.normalize().to_numpy(),
            "score": proba,
        }
    )
    # Scores after validation_end are dropped so a lookup cannot see the test period.
    end = pd.Timestamp(thr.split.validation_end)
    frame = frame[frame["day"] <= end]
    mean_s = frame.groupby(["shop_id", "day"])["score"].mean()
    max_s = frame.groupby(["shop_id", "day"])["score"].max()
    mean_map = {(shop, pd.Timestamp(day)): float(score) for (shop, day), score in mean_s.items()}
    max_map = {(shop, pd.Timestamp(day)): float(score) for (shop, day), score in max_s.items()}
    groups = shop_groups(tables["shops"], thr, seed)
    val_shops = groups[groups == "validation"].index
    start = pd.Timestamp(thr.split.train_end) + pd.Timedelta(days=1)
    days = pd.date_range(start, end, freq="D")
    threshold = float(model.threshold)
    shop_truth = tables["shops"].set_index("shop_id")[TRUE_LABEL]
    considered = 0
    rising_n = 0
    early_n = 0
    early_crossed = 0
    early_misuse_shops = 0
    for shop in val_shops:
        for day in days:
            if day >= end:
                continue
            values = []
            for offset in range(HISTORY_DAYS - 1, -1, -1):
                key = (shop, pd.Timestamp(day) - pd.Timedelta(days=offset))
                values.append(mean_map.get(key))
            fitted = linear_forecast(values)
            today = values[-1]
            early = bool(fitted["rising"] and today is not None and today < threshold)
            considered += 1
            rising_n += int(fitted["rising"])
            if not early:
                continue
            early_n += 1
            early_misuse_shops += int(shop_truth.get(shop, 0) == 1)
            horizon_end = min(pd.Timestamp(day) + pd.Timedelta(days=HORIZON_DAYS), end)
            cursor = pd.Timestamp(day) + pd.Timedelta(days=1)
            crossed = False
            while cursor <= horizon_end:
                key = (shop, cursor)
                if max_map.get(key, -1.0) >= threshold:
                    crossed = True
                    break
                cursor += pd.Timedelta(days=1)
            early_crossed += int(crossed)
    return {
        "threshold": threshold,
        "validation_shop_days_with_a_later_validation_day": considered,
        "rising_shop_days": rising_n,
        "early_warning_shop_days": early_n,
        "early_warning_entered_review": early_crossed,
        "early_warning_hit_rate": (early_crossed / early_n) if early_n else None,
        "early_warning_on_misuse_shops": early_misuse_shops,
        "definition": (
            "Early warning: rising flag (slope > 0 and day-7 forecast at least 0.02 above "
            "today's mean payment score) while today's mean score is still under the payment "
            "threshold. Entered review: some later validation day, within 7 days and not past "
            "validation_end, has a payment score at or above that threshold. "
            "Misuse-shop counts use the hidden shop label only as context."
        ),
    }


def _copy_tables(tables: dict) -> dict:
    return {name: frame.copy(deep=True) for name, frame in tables.items()}


def _shave(amount: np.ndarray, misuse: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    out = amount.copy()
    shave = rng.integers(1, 100, int(misuse.sum()))
    out[misuse] = np.maximum(1, out[misuse] - shave)
    still = misuse & (out % 100 == 0)
    out[still] = np.maximum(1, out[still] - 1)
    return out


def _spread(qr: pd.DataFrame, shops: pd.DataFrame, groups: pd.Series, rng: np.random.Generator):
    misuse = (qr[TRUE_LABEL] == 1).to_numpy()
    move = np.flatnonzero(misuse)[rng.random(int(misuse.sum())) < 0.5]
    cat = shops.set_index("shop_id")["category"]
    buckets: dict[tuple, list] = {}
    for shop_id in shops["shop_id"]:
        buckets.setdefault((cat[shop_id], groups[shop_id]), []).append(shop_id)
    new_shop = qr["shop_id"].to_numpy().copy()
    moved = 0
    for i in move:
        shop = new_shop[i]
        options = [s for s in buckets[(cat[shop], groups[shop])] if s != shop]
        if not options:
            continue
        new_shop[i] = options[int(rng.integers(0, len(options)))]
        moved += 1
    out = qr.copy()
    out["shop_id"] = new_shop
    return out, moved


def _lower(amount: np.ndarray, misuse: np.ndarray) -> np.ndarray:
    out = amount.copy()
    out[misuse] = np.maximum(1, np.rint(out[misuse] * 0.5).astype(int))
    still = misuse & (out % 100 == 0)
    out[still] = np.maximum(1, out[still] - 1)
    return out


def _adapt(tables, level: int, cfg, thr, seed: int) -> tuple[dict, dict]:
    copied = _copy_tables(tables)
    qr = copied["qr_payments"]
    misuse = (qr[TRUE_LABEL] == 1).to_numpy()
    rng = np.random.default_rng(seed + 1000 + level)
    amount = qr["amount"].to_numpy().copy()
    moved = 0
    if level >= 1:
        amount = _shave(amount, misuse, rng)
    if level >= 2:
        qr = qr.copy()
        qr["amount"] = amount
        copied["qr_payments"] = qr
        groups = shop_groups(copied["shops"], thr, cfg.seed)
        qr, moved = _spread(qr, copied["shops"], groups, rng)
        amount = qr["amount"].to_numpy().copy()
        misuse = (qr[TRUE_LABEL] == 1).to_numpy()
    if level >= 3:
        amount = _lower(amount, misuse)
    qr = qr.copy()
    qr["amount"] = amount.astype(int)
    copied["qr_payments"] = qr
    return copied, {"misuse_payments": int(misuse.sum()), "payments_moved": int(moved)}


def _analyst_cases(tables, data, model, thr, patterns, rng) -> tuple[pd.DataFrame, dict]:
    """Noisy verdicts for train shops the model just flagged. Validation labels are not added."""
    proba = model.predict_proba(data.payments)
    train = data.split.to_numpy() == "train"
    flagged = train & (proba >= model.threshold)
    info = {"reviewed_shops": 0, "misuse_cleared": 0, "honest_convicted": 0}
    if not flagged.any():
        return tables["cases"], info
    ranked = (
        pd.DataFrame(
            {
                "shop_id": data.payments.loc[flagged, "shop_id"].to_numpy(),
                "score": proba[flagged],
            }
        )
        .groupby("shop_id")["score"]
        .max()
        .sort_values(ascending=False)
    )
    chosen = ranked.head(thr.eval.analyst_capacity_shops).index.tolist()
    qr = tables["qr_payments"].set_index("payment_id")
    truth = data.payments["payment_id"].map(qr[TRUE_LABEL])
    shop_misuse = (
        pd.DataFrame({"shop_id": data.payments["shop_id"].to_numpy(), "y": truth.to_numpy()})
        .groupby("shop_id")["y"]
        .max()
    )
    noise = patterns.cases
    closed = pd.Timestamp(thr.split.train_end)
    rows = []
    for shop in chosen:
        y = int(shop_misuse.get(shop, 0) == 1)
        u = float(rng.random())
        if y == 1:
            verdict = 0 if u < noise.misuse_cleared else 1
            info["misuse_cleared"] += int(verdict == 0)
        else:
            verdict = 1 if u < noise.honest_convicted else 0
            info["honest_convicted"] += int(verdict == 1)
        rows.append(
            {
                "case_id": f"SIM{shop}",
                "shop_id": shop,
                "opened_on": closed - pd.Timedelta(days=1),
                "closed_on": closed,
                "verdict": np.int8(verdict),
                "source": "analyst_sim",
            }
        )
    info["reviewed_shops"] = len(rows)
    extra = pd.DataFrame(rows)
    # First row wins in case_verdict_for_payments, so the new verdict replaces an older case.
    cases = pd.concat([extra, tables["cases"]], ignore_index=True)
    return cases, info


def _detection(data, model, tables) -> dict:
    truth, _pattern, _category, _shops = _labels(data, tables)
    va = data.split.to_numpy() == "validation"
    proba = model.predict_proba(data.payments)
    flag = proba >= model.threshold
    amount = data.payments["amount"].to_numpy()
    payment = _metrics(truth[va], proba[va], flag[va], amount[va])
    frame = pd.DataFrame(
        {
            "shop_id": data.payments.loc[va, "shop_id"].to_numpy(),
            "truth": truth[va],
            "score": proba[va],
            "flag": flag[va],
            "amount": amount[va],
        }
    )
    if frame.empty:
        shop = {"n": 0, "positives": 0, "recall": None, "fpr": None}
    else:
        by = frame.groupby("shop_id").agg(
            truth=("truth", "max"),
            score=("score", "max"),
            flag=("flag", "max"),
            amount=("amount", "sum"),
        )
        shop = _metrics(
            by["truth"].to_numpy(),
            by["score"].to_numpy(),
            by["flag"].to_numpy().astype(bool),
            by["amount"].to_numpy(),
        )
    return {"payment": payment, "shop": shop}


def adversary(world, frozen: PaymentModel, cfg, thr, rules, models, seed: int) -> list[dict]:
    rows = []
    # Round 0 is the unadapted world, so the later drop has a starting point.
    base = _detection(
        prepare_payment_data(world.tables, cfg, thr, rules),
        frozen,
        world.tables,
    )
    rows.append(
        {
            "round": 0,
            "name": "No adaptation",
            "frozen": base,
            "retrained": base,
            "adaptation": {"misuse_payments": None, "payments_moved": 0},
            "analyst": {
                "reviewed_shops": 0,
                "note": "same model as frozen; nothing new to retrain on",
            },
        }
    )
    for level, name in ADVERSARY_ROUNDS:
        tables, info = _adapt(world.tables, level, cfg, thr, seed)
        adapted = prepare_payment_data(tables, cfg, thr, rules)
        frozen_det = _detection(adapted, frozen, tables)
        rng = np.random.default_rng(seed + 5000 + level)
        cases, analyst = _analyst_cases(tables, adapted, frozen, thr, load_patterns_config(), rng)
        retrained_data = prepare_payment_data(tables, cfg, thr, rules, cases=cases)
        retrained = train_from_data(retrained_data, models, rules.training_target, seed + level)
        retrained_det = _detection(retrained_data, retrained, tables)
        rows.append(
            {
                "round": level,
                "name": name,
                "adaptation": info,
                "analyst": analyst,
                "frozen": frozen_det,
                "retrained": retrained_det,
            }
        )
    return rows


def _fmt(value, digits=3) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "n/a"
    if isinstance(value, (int, np.integer)):
        return f"{int(value):,}"
    return f"{float(value):.{digits}f}"


def _md_table(headers: list[str], rows: list[list]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "---|" * len(headers),
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def render_robustness(result: dict) -> str:
    sizes = result["validation"]
    lines = [
        "# Robustness (validation)",
        "",
        (
            f"Generated by `python -m jachai.eval.robustness` with profile `{result['profile']}`, "
            f"seed {result['seed']}. Synthetic data only. LightGBM threshold fit on validation "
            f"targets. Validation payments: N={sizes['n']:,}, positives={sizes['positives']:,}. "
            "The test split is not scored. "
            f"Compute time for this whole command (robustness, peer trend, adversary): "
            f"{result['compute_seconds']:.1f}s."
        ),
        "",
        "## Per-pattern recall",
        "",
        "Recall is flagged misuse payments in that pattern divided by misuse "
        "payments in that pattern. "
        "Look-alike pattern rows are honest by construction; their recall column is the flag rate.",
        "",
    ]
    lines.append(
        _md_table(
            ["Pattern", "Kind", "N", "Positives", "Flagged", "Recall", "FPR"],
            [
                [
                    row["pattern"],
                    row["kind"],
                    _fmt(row["n"], 0),
                    _fmt(row["positives"], 0),
                    _fmt(row["flagged"], 0),
                    _fmt(row["recall"]),
                    _fmt(row["fpr"]),
                ]
                for row in result["patterns"]
            ],
        )
    )
    lines += ["", "## Look-alike false-positive rate", ""]
    lines.append(
        _md_table(
            ["Slice", "Honest payments", "Flagged honest", "FPR"],
            [
                [
                    row["slice"],
                    _fmt(row["honest_payments"], 0),
                    _fmt(row["false_positives"], 0),
                    _fmt(row["fpr"]),
                ]
                for row in result["lookalikes"]
            ],
        )
    )
    lines += [
        "",
        result["festival_note"],
        "",
        "## Before and after 1 Oct",
        "",
        (
            "The fast validation window starts after 1 Oct, so it has no before slice. "
            "The before/after contrast is train shops in the train window, which the model has "
            "already seen. Validation is reported beside it as the holdout, and it is entirely "
            "after the change. This is not a clean test of the regime shift."
        ),
        "",
    ]
    lines.append(
        _md_table(
            ["Slice", "N", "Positives", "Mean score", "Recall", "Precision", "FPR"],
            [
                [
                    row["slice"],
                    _fmt(row["n"], 0),
                    _fmt(row["positives"], 0),
                    _fmt(row["mean_score"]),
                    _fmt(row["recall"]),
                    _fmt(row["precision"]),
                    _fmt(row["fpr"]),
                ]
                for row in result["regime"]
            ],
        )
    )
    lines += [
        "",
        "## Calibration",
        "",
        "Reliability of the calibrated payment score against the hidden label, "
        "validation payments. "
        "The calibrator itself was fit to validation targets, not to this label, "
        "so a gap is expected.",
        "",
    ]
    lines.append(
        _md_table(
            ["Bin", "N", "Mean predicted", "Observed misuse rate"],
            [
                [
                    f"{row['lo']:.1f}–{row['hi']:.1f}",
                    _fmt(row["n"], 0),
                    _fmt(row["mean_predicted"]),
                    _fmt(row["observed_misuse_rate"]),
                ]
                for row in result["calibration"]
            ],
        )
    )
    lines += [
        "",
        "![Calibration on validation](robustness_calibration.svg)",
        "",
        "## SHAP agreement",
        "",
        (
            "Among flagged validation payments whose injected pattern has an expected reason list, "
            "the share whose top 3 reason codes include at least one expected code. "
            "The lists are a hypothesis (see JSON `mapping`)."
        ),
        "",
        (
            f"Flagged misuse payments: {result['shap']['n_flagged_misuse']}. "
            f"Top-3 overlap: {_fmt(result['shap']['share'])}. "
            f"Top-1 is an expected code: {_fmt(result['shap']['top1_share'])}."
        ),
        "",
    ]
    lines.append(
        _md_table(
            ["Pattern", "Flagged", "Top-3 overlap", "Share"],
            [
                [row["pattern"], _fmt(row["n"], 0), _fmt(row["agreed"], 0), _fmt(row["share"])]
                for row in result["shap"]["by_pattern"]
            ],
        )
    )
    ring = result["false_ring"]
    lines += [
        "",
        "## Network score on honest clusters",
        "",
        ring["definition"],
        "",
        (
            f"Snapshot {ring.get('snapshot')}. Honest shops sharing a payer in the same zone: "
            f"{_fmt(ring['n_honest_sharing_zone'], 0)}. "
            f"Of those, ring_flag is on for {_fmt(ring['false_rings'], 0)} "
            f"(rate {_fmt(ring['false_ring_rate'])}). "
            f"Eligible misuse shops with ring_flag: rate {_fmt(ring['misuse_ring_rate'])} "
            f"(N={_fmt(ring['n_misuse_eligible'], 0)})."
        ),
        "",
        "## LLM validator",
        "",
        result["llm"]["note"],
        (
            f" Live call: {result['llm']['live_llm_called']}. "
            f"Fixtures rejected: {result['llm']['n_rejected']} of {result['llm']['n_fixtures']}."
        ),
        "",
    ]
    lines.append(
        _md_table(
            ["Fixture", "Accepted", "Errors"],
            [
                [row["fixture"], "yes" if row["valid"] else "no", "; ".join(row["errors"]) or "—"]
                for row in result["llm"]["fixtures"]
            ],
        )
    )
    lines += [
        "",
        "## Caveats",
        "",
        "- One fast-profile seed. Pattern counts of zero are real for this calendar, "
        "not a skipped check.",
        "- Train-period before/after numbers describe data the model was fit on.",
        "- SHAP overlap uses a hand-written code list. A miss means the top reasons "
        "were something else, which can still be a real signal.",
        "- The validator rates are fixtures. They are not how often a hosted model "
        "is rejected in production.",
        "",
    ]
    return "\n".join(lines)


def render_peer(result: dict) -> str:
    check = result["peer_trend"]
    return "\n".join(
        [
            "# Peer and trend (validation check)",
            "",
            (
                "Peer and trend does not add a fourth blocking score. "
                "The payment, shop and network "
                "scores still decide the queue. This view says where a shop sits "
                "among shops of the "
                "same category, area and size, and whether its recent payment scores are climbing "
                "before they cross the payment threshold."
            ),
            "",
            check["definition"],
            "",
            (
                f"Seed {result['seed']}, profile `{result['profile']}`. "
                f"Payment threshold {_fmt(check['threshold'])}. "
                f"Validation shop-days with a later validation day: "
                f"{_fmt(check['validation_shop_days_with_a_later_validation_day'], 0)}. "
                f"Rising: {_fmt(check['rising_shop_days'], 0)}. "
                f"Early warning (rising and still under the threshold): "
                f"{_fmt(check['early_warning_shop_days'], 0)}. "
                f"Of those, entered review within the observed horizon: "
                f"{_fmt(check['early_warning_entered_review'], 0)} "
                f"(share {_fmt(check['early_warning_hit_rate'])}). "
                f"Early-warning shop-days sitting on a misuse shop: "
                f"{_fmt(check['early_warning_on_misuse_shops'], 0)}."
            ),
            "",
            (
                "The fast validation window is only a few days long, and the 7-day horizon is cut "
                "at validation_end so the test period stays unread. A low hit rate can mean the "
                "flag is early, or that it is noise. Both readings stay open at this sample size."
            ),
            "",
            "The case page reads `GET /shops/{shop_id}/peer-trend`. "
            "The panel is a cue. An analyst decides.",
            "",
        ]
    )


def _retrain_notes(rows: list[dict]) -> str:
    lines = []
    for row in rows:
        if row["round"] == 0:
            continue
        frozen = row["frozen"]["payment"]["recall"]
        retrained = row["retrained"]["payment"]["recall"]
        fpr = row["retrained"]["payment"]["fpr"]
        if retrained is None or frozen is None or np.isnan(retrained) or np.isnan(frozen):
            continue
        if retrained > frozen:
            lines.append(
                f"Round {row['round']}: retrained recall {_fmt(retrained)} against frozen "
                f"{_fmt(frozen)}, with retrained false-positive rate {_fmt(fpr)}."
            )
        else:
            lines.append(
                f"Round {row['round']}: retrained recall {_fmt(retrained)} does not beat frozen "
                f"{_fmt(frozen)}."
            )
    return " ".join(lines)


def render_adversary(result: dict) -> str:
    lines = [
        "# Adaptive adversary (validation)",
        "",
        (
            f"Profile `{result['profile']}`, seed {result['seed']}. Three cumulative changes to "
            "misuse QR payments only, then the frozen LightGBM and a model retrained on simulated "
            "analyst verdicts. Verdicts use the configured case noise "
            f"(misuse cleared {result['noise']['misuse_cleared']}, "
            f"honest convicted {result['noise']['honest_convicted']}). "
            "The model is given the noisy verdict, not the hidden label. "
            "Only train shops are reviewed, capped at the analyst shop capacity, so validation "
            "rows are not training rows. "
            "Spreading keeps a payment inside the same shop split, so it does not leak into test."
        ),
        "",
        _md_table(
            [
                "Round",
                "Change",
                "Moved",
                "Reviewed",
                "Frozen recall",
                "Retrained recall",
                "Frozen FPR",
                "Retrained FPR",
                "N",
                "Positives",
            ],
            [
                [
                    row["round"],
                    row["name"],
                    _fmt(row["adaptation"]["payments_moved"], 0),
                    _fmt(row["analyst"].get("reviewed_shops"), 0),
                    _fmt(row["frozen"]["payment"]["recall"]),
                    _fmt(row["retrained"]["payment"]["recall"]),
                    _fmt(row["frozen"]["payment"]["fpr"]),
                    _fmt(row["retrained"]["payment"]["fpr"]),
                    _fmt(row["frozen"]["payment"]["n"], 0),
                    _fmt(row["frozen"]["payment"]["positives"], 0),
                ]
                for row in result["adversary"]
            ],
        ),
        "",
        "Shop-level recall uses the maximum payment score. A shop is misuse "
        "if any of its validation payments is.",
        "",
        _md_table(
            ["Round", "Frozen shop recall", "Retrained shop recall", "Shops", "Misuse shops"],
            [
                [
                    row["round"],
                    _fmt(row["frozen"]["shop"]["recall"]),
                    _fmt(row["retrained"]["shop"]["recall"]),
                    _fmt(row["frozen"]["shop"]["n"], 0),
                    _fmt(row["frozen"]["shop"]["positives"], 0),
                ]
                for row in result["adversary"]
            ],
        ),
        "",
        "![Detection by round](adversary.svg)",
        "",
        (
            "Round 0 retrained equals frozen, because there is no new analyst verdict yet. "
            "Later rounds retrain after the frozen model flags train shops on that adapted world. "
            "A higher retrained recall is not a free repair: the FPR column is the honest payments "
            "flagged after that retrain. This is one seed."
        ),
        "",
        _retrain_notes(result["adversary"]),
        "",
    ]
    return "\n".join(lines)


def calibration_svg(bins: list[dict]) -> str:
    w, h, pad = 460, 460, 48
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="20" y="28" font-family="sans-serif" font-size="15" fill="#1c1917">'
        "Validation reliability (hidden label)</text>",
        f'<line x1="{pad}" y1="{h - pad}" x2="{w - pad}" y2="{pad}" '
        f'stroke="#d6d3d1" stroke-width="1"/>',
    ]
    span = w - 2 * pad

    def xy(p, rate):
        return pad + p * span, h - pad - rate * span

    for row in bins:
        if not row["n"] or row["mean_predicted"] is None:
            continue
        x, y = xy(row["mean_predicted"], row["observed_misuse_rate"])
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#0f766e"/>')
        parts.append(
            f'<text x="{x + 8:.1f}" y="{y - 6:.1f}" font-family="sans-serif" font-size="11" '
            f'fill="#44403c">n={row["n"]}</text>'
        )
    parts += [
        f'<text x="{pad}" y="{h - 16}" font-family="sans-serif" font-size="12" fill="#44403c">'
        "Mean predicted</text>",
        f'<text x="8" y="{pad}" font-family="sans-serif" font-size="12" fill="#44403c" '
        'transform="rotate(-90 8 48)">Observed misuse</text>',
        "</svg>",
    ]
    return "\n".join(parts) + "\n"


def adversary_svg(rows: list[dict]) -> str:
    shown = [row for row in rows if row["round"] >= 1]
    w, h, pad = 680, 360, 48
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text x="20" y="28" font-family="sans-serif" font-size="15" fill="#1c1917">'
        "Validation payment recall by adaptation round</text>",
        '<rect x="20" y="44" width="14" height="14" fill="#0f766e"/>',
        '<text x="40" y="56" font-family="sans-serif" font-size="12" '
        'fill="#1c1917">Frozen model</text>',
        '<rect x="160" y="44" width="14" height="14" fill="#b45309"/>',
        '<text x="180" y="56" font-family="sans-serif" font-size="12" fill="#1c1917">'
        "Retrained on analyst verdicts</text>",
    ]
    slot = (w - 2 * pad) / max(len(shown), 1)
    base = h - pad
    for i, row in enumerate(shown):
        x = pad + i * slot + 20
        for shift, key, color in ((0, "frozen", "#0f766e"), (36, "retrained", "#b45309")):
            recall = row[key]["payment"]["recall"]
            recall = (
                0.0
                if recall is None or (isinstance(recall, float) and np.isnan(recall))
                else recall
            )
            height = max(0.0, float(recall)) * (h - 2 * pad - 20)
            parts.append(
                f'<rect x="{x + shift:.1f}" y="{base - height:.1f}" width="28" '
                f'height="{height:.1f}" fill="{color}"/>'
            )
            parts.append(
                f'<text x="{x + shift:.1f}" y="{base - height - 6:.1f}" font-family="sans-serif" '
                f'font-size="11" fill="#1c1917">{float(recall):.2f}</text>'
            )
        parts.append(
            f'<text x="{x:.1f}" y="{base + 20}" font-family="sans-serif" font-size="12" '
            f'fill="#1c1917">Round {row["round"]}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def run(seed: int) -> dict:
    t0 = time.perf_counter()
    world, data, model, cfg, thr, rules, models, patterns = _prepare(seed)
    truth, pattern, category, _shops = _labels(data, world.tables)
    proba = model.predict_proba(data.payments)
    flag = proba >= model.threshold
    amount = data.payments["amount"].to_numpy()
    va = data.split.to_numpy() == "validation"
    slices = pattern_and_lookalikes(truth, pattern, category, proba, flag, amount, va)
    fest = next(p for p in patterns.patterns if p.name == "hn_festival_spike")
    festival_note = (
        f"Festival pattern `{fest.name}` is configured for {fest.params.get('start')} to "
        f"{fest.params.get('end')}. This profile's calendar ends {cfg.calendar.end}. "
        "If the festival starts after the calendar, a zero count is the calendar, "
        "not a missing check."
    )
    regime = regime_slices(
        data, truth, proba, flag, amount, pd.Timestamp(cfg.calendar.regime_change)
    )
    cal = calibration(truth[va], proba[va])
    shap = shap_agreement(model, data.payments.loc[va], pattern[va], flag[va], cfg)
    ring = false_rings(world.tables, cfg, thr, rules, models, seed)
    llm = llm_validator()
    peer = peer_trend_check(data, model, world.tables, cfg, thr, seed)
    rounds = adversary(world, model, cfg, thr, rules, models, seed)
    profile = os.environ.get("JACHAI_PROFILE", "").strip() or "reference"
    return {
        "profile": profile,
        "seed": seed,
        "synthetic_data_only": True,
        "test_set_touched": False,
        "validation": {"n": int(va.sum()), "positives": int(truth[va].sum())},
        "patterns": slices["patterns"],
        "lookalikes": slices["lookalikes"],
        "festival_note": festival_note,
        "regime": regime,
        "calibration": cal,
        "shap": shap,
        "false_ring": ring,
        "llm": llm,
        "peer_trend": peer,
        "adversary": rounds,
        "noise": {
            "misuse_cleared": patterns.cases.misuse_cleared,
            "honest_convicted": patterns.cases.honest_convicted,
        },
        "compute_seconds": time.perf_counter() - t0,
        "provenance": provenance(),
    }


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--allow-long", action="store_true")
    args = parser.parse_args(argv)
    profile = os.environ.get("JACHAI_PROFILE", "").strip() or "reference"
    if profile != "fast" and not args.allow_long:
        raise SystemExit("Refusing a long run. Use JACHAI_PROFILE=fast, or pass --allow-long.")
    result = run(args.seed)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "robustness_calibration.svg").write_text(
        calibration_svg(result["calibration"]), encoding="utf-8"
    )
    (out / "adversary.svg").write_text(adversary_svg(result["adversary"]), encoding="utf-8")
    (out / "robustness.md").write_text(render_robustness(result), encoding="utf-8")
    (out / "peer_trend.md").write_text(render_peer(result), encoding="utf-8")
    (out / "adversary.md").write_text(render_adversary(result), encoding="utf-8")
    payload = _jsonable(result)
    (out / "robustness.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (out / "peer_trend.json").write_text(
        json.dumps(
            _jsonable(
                {
                    "profile": result["profile"],
                    "seed": result["seed"],
                    "test_set_touched": False,
                    "peer_trend": result["peer_trend"],
                }
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (out / "adversary.json").write_text(
        json.dumps(
            _jsonable(
                {
                    "profile": result["profile"],
                    "seed": result["seed"],
                    "test_set_touched": False,
                    "noise": result["noise"],
                    "adversary": result["adversary"],
                }
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {out / 'robustness.md'}, {out / 'peer_trend.md'}, {out / 'adversary.md'}")
    print(f"Compute {result['compute_seconds']:.1f}s")


if __name__ == "__main__":
    main()
