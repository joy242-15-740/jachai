"""Safe case briefs made only from structured, public evidence.

The optional LLM may reword the English analyst note. It never receives or
writes merchant-facing text, never chooses a score or action, and its output is
accepted only when every numeric token already appears in the evidence and no
configured accusation or promise is present. Any error or rejection returns the
deterministic template.
"""

from __future__ import annotations

import json
import re
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from jachai.world.config import DEFAULT_CONFIG_DIR

NUMBER = re.compile(r"(?<![\w])(?:Tk\s*)?[-+]?\d[\d,]*(?:\.\d+)?%?(?![\w])", re.IGNORECASE)
NUMBER_WORD = re.compile(
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)\b",
    re.IGNORECASE,
)


def load_brief_config(path: Path | None = None) -> dict[str, Any]:
    with (path or DEFAULT_CONFIG_DIR / "brief.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _normal_number(token: str) -> str:
    return re.sub(r"^(?:tk\s*)", "", token.strip().lower()).replace(",", "")


def _text_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [text for child in value.values() for text in _text_values(child)]
    if isinstance(value, list):
        return [text for child in value for text in _text_values(child)]
    return [str(value)] if value is not None else []


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: tuple[str, ...]


def validate_analyst_note(
    note: str, evidence: dict[str, Any], config: dict[str, Any] | None = None
) -> ValidationResult:
    """Reject invented numbers, accusations and promises.

    Numeric spelling is deliberately strict: an LLM must copy evidence numbers
    verbatim instead of converting, rounding or estimating them.
    """
    cfg = (config or load_brief_config())["analyst_note"]
    lower = note.casefold()
    errors: list[str] = []
    for term in cfg["forbidden_terms"]:
        if re.search(rf"\b{re.escape(term.casefold())}\b", lower):
            errors.append(f"accusation term: {term}")
    for phrase in cfg["forbidden_promises"]:
        if phrase.casefold() in lower:
            errors.append(f"promise: {phrase}")

    evidence_text = " ".join(_text_values(evidence))
    allowed = {_normal_number(x) for x in NUMBER.findall(evidence_text)}
    invented = sorted({_normal_number(x) for x in NUMBER.findall(note)} - allowed)
    if invented:
        errors.append(f"numbers absent from evidence: {', '.join(invented)}")

    allowed_words = {x.casefold() for x in NUMBER_WORD.findall(evidence_text)}
    invented_words = sorted({x.casefold() for x in NUMBER_WORD.findall(note)} - allowed_words)
    if invented_words:
        errors.append(f"number words absent from evidence: {', '.join(invented_words)}")
    if not note.strip():
        errors.append("empty note")
    return ValidationResult(not errors, tuple(errors))


def analyst_template(evidence: dict[str, Any]) -> str:
    scores = evidence["scores"]
    reasons = evidence.get("reasons", [])
    lines = [
        f"Shop {evidence['case_id']} needs human review. Its fused risk score is "
        f"{scores['risk']:.4f} and its current band is {scores['band']}.",
    ]
    if reasons:
        lines.append("Evidence: " + " ".join(reason["en"] for reason in reasons))
    lines.append(
        "This is model-generated evidence from synthetic data, not a finding. "
        "An analyst should check the timeline, linked shops and merchant explanation "
        "before deciding."
    )
    return "\n\n".join(lines)


def merchant_template(evidence: dict[str, Any]) -> str:
    reasons = evidence.get("reasons", [])
    bullets = "\n".join(f"• {reason['bn']}" for reason in reasons)
    noticed = f"\n\nআমরা যা লক্ষ্য করেছি:\n{bullets}" if bullets else ""
    return (
        "প্রিয় দোকান মালিক,\n\n"
        "আপনার দোকানের সাম্প্রতিক কিছু QR লেনদেন আমাদের নিয়মিত পর্যালোচনার অংশ হিসেবে "
        "দেখা হচ্ছে। এটি কোনো অভিযোগ নয়, এবং এখনো কোনো সিদ্ধান্ত নেওয়া হয়নি।"
        f"{noticed}\n\n"
        "এর কোনো স্বাভাবিক কারণ থাকলে, যেমন পাইকারি বিক্রি, উৎসবের ভিড় বা নতুন দোকান, অনুগ্রহ করে আপনার "
        "ব্যাখ্যা জানান। একজন বিশ্লেষক তা মনোযোগ দিয়ে দেখবেন।\n\n"
        "আপনার সহযোগিতার জন্য ধন্যবাদ।\n\nupay মার্চেন্ট সাপোর্ট"
    )


def analyst_evidence(case_detail: dict[str, Any]) -> dict[str, Any]:
    """The strict allow-list sent to the LLM; no Bangla or merchant-facing copy."""
    scores = case_detail["scores"]
    neighbourhood = case_detail.get("neighbourhood", {})
    return {
        "case_id": case_detail["case_id"],
        "scores": {
            "risk": scores["risk"],
            "band": scores["band"],
            "components": scores.get("components", {}),
        },
        "reasons": [
            {"code": reason["code"], "evidence": reason["en"]}
            for reason in case_detail.get("reasons", [])
        ],
        "network": {
            "community_size": neighbourhood.get("community_size"),
            "ring_flag": neighbourhood.get("ring_flag"),
            "linking_payers": neighbourhood.get("linking_payers"),
        },
    }


def openai_reworder(api_key: str, model: str, timeout: float = 8.0) -> Callable[[dict], str]:
    """Small stdlib adapter; no external SDK and no merchant text in the request."""

    def reword(evidence: dict) -> str:
        prompt = (
            "Write a concise English analyst case note using only this JSON evidence. "
            "Copy any number exactly; do not calculate, round, accuse, promise an outcome, "
            "or recommend automatic action. Say that a human must decide. Evidence:\n"
            + json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))
        )
        body = json.dumps({"model": model, "input": prompt}).encode()
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            data = json.load(response)
        if data.get("output_text"):
            return str(data["output_text"])
        return "".join(
            item.get("text", "")
            for output in data.get("output", [])
            for item in output.get("content", [])
            if item.get("type") == "output_text"
        )

    return reword


def build_brief(
    evidence: dict[str, Any],
    llm: Callable[[dict[str, Any]], str] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fallback = analyst_template(evidence)
    note, source, rejected = fallback, "template", None
    if llm is not None:
        safe_evidence = analyst_evidence(evidence)
        try:
            candidate = llm(safe_evidence)
            result = validate_analyst_note(candidate, safe_evidence, config)
            if result.valid:
                note, source = candidate.strip(), "llm"
            else:
                rejected = list(result.errors)
        except Exception as error:  # noqa: BLE001 - optional service must never break case access
            rejected = [f"LLM unavailable: {type(error).__name__}"]
    return {
        "analyst_note": note,
        "analyst_note_source": source,
        "merchant_notice_bn": merchant_template(evidence),
        "merchant_notice_source": "template",
        "llm_output_rejected": rejected,
    }
