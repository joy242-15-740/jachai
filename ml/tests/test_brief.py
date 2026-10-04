"""Safe analyst-note validation and template fallback."""

from jachai.explain.brief import build_brief, validate_analyst_note


def evidence():
    return {
        "case_id": "SHabc",
        "scores": {"risk": 0.8123, "band": "high", "components": {"payment": 0.74}},
        "reasons": [
            {
                "code": "ROUND_RECEIPTS",
                "en": "82% of recent receipts were round amounts.",
                "bn": "সাম্প্রতিক রসিদের ৮২% ছিল পূর্ণ অঙ্কের।",
                "weight": 0.31,
            }
        ],
        "neighbourhood": {"community_size": 4, "ring_flag": False, "linking_payers": 3},
    }


def test_validator_accepts_only_evidence_numbers():
    valid = validate_analyst_note("Risk is 0.8123; 82% of receipts need human review.", evidence())
    invented = validate_analyst_note("Risk is 0.99; 82% of receipts need human review.", evidence())
    assert valid.valid
    assert not invented.valid
    assert "0.99" in " ".join(invented.errors)


def test_validator_rejects_accusations_and_promises():
    accusation = validate_analyst_note("This shop is guilty.", evidence())
    promise = validate_analyst_note("We guarantee this shop will be cleared.", evidence())
    assert not accusation.valid
    assert any("accusation" in error for error in accusation.errors)
    assert not promise.valid
    assert any("promise" in error for error in promise.errors)


def test_rejected_llm_output_falls_back_to_template():
    brief = build_brief(evidence(), lambda _: "This criminal shop has risk 0.99.")
    assert brief["analyst_note_source"] == "template"
    assert brief["llm_output_rejected"]
    assert "criminal" not in brief["analyst_note"].lower()


def test_llm_sees_only_english_allow_list_and_valid_output_is_used():
    seen = {}

    def llm(payload):
        seen.update(payload)
        return "Risk is 0.8123 and the band is high. A human must decide."

    brief = build_brief(evidence(), llm)
    assert brief["analyst_note_source"] == "llm"
    assert brief["merchant_notice_source"] == "template"
    assert "সাম্প্রতিক" not in str(seen)
    assert "bn" not in str(seen)


def test_llm_error_falls_back_and_merchant_notice_is_polite():
    def unavailable(_):
        raise RuntimeError("offline")

    brief = build_brief(evidence(), unavailable)
    assert brief["analyst_note_source"] == "template"
    assert brief["llm_output_rejected"] == ["LLM unavailable: RuntimeError"]
    assert "এটি কোনো অভিযোগ নয়" in brief["merchant_notice_bn"]
