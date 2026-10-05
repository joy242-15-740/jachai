"""Provenance stamp: stable, sensitive to training configs, blind to API-only text."""

import jachai.provenance as prov
from jachai.labels.config import load_rules
from jachai.world.config import load_patterns_config


def test_hash_is_stable_and_has_every_config():
    a, b = prov.provenance("fp1"), prov.provenance("fp1")
    assert a["config_hash"] == b["config_hash"]
    assert set(a["config_hashes"]) == {"world", "patterns", "thresholds", "models", "rules"}
    assert a["model_fingerprint"] == "fp1"
    assert "commit" in a["git"] and "dirty" in a["git"]


def test_api_only_recommendation_text_does_not_change_the_hash(monkeypatch):
    before = prov.provenance()["config_hash"]
    rules = load_rules()
    rec = rules.recommendation.model_copy(update={"convert_min_monthly_demand": 1.0})
    monkeypatch.setattr(
        prov, "load_rules", lambda: rules.model_copy(update={"recommendation": rec})
    )
    assert prov.provenance()["config_hash"] == before


def test_a_training_config_change_does_change_the_hash(monkeypatch):
    before = prov.provenance()["config_hash"]
    patterns = load_patterns_config()
    cases = patterns.cases.model_copy(update={"coverage": 0.05})
    monkeypatch.setattr(
        prov, "load_patterns_config", lambda: patterns.model_copy(update={"cases": cases})
    )
    assert prov.provenance()["config_hash"] != before


def test_fast_profile_has_its_own_hash(monkeypatch):
    reference = prov.provenance()["config_hash"]
    monkeypatch.setenv("JACHAI_PROFILE", "fast")
    assert prov.provenance()["config_hash"] != reference
