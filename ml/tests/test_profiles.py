"""The fast development profile overrides sizes and dates, nothing else."""

import pytest

from jachai.features.config import load_thresholds
from jachai.models.config import load_models_config
from jachai.world.config import load_patterns_config, load_world_config
from jachai.world.summary import default_model_dir, default_world_dir


def test_no_profile_means_reference_configs(monkeypatch):
    monkeypatch.delenv("JACHAI_PROFILE", raising=False)
    assert load_world_config().population.n_shops == 3000
    assert default_world_dir().parts[-2:] == ("data", "world")


def test_fast_profile_shrinks_the_world_but_keeps_patterns(monkeypatch):
    monkeypatch.setenv("JACHAI_PROFILE", "fast")
    cfg = load_world_config()
    assert cfg.population.n_shops == 300
    assert cfg.calendar.days == 30
    assert cfg.calendar.start <= cfg.calendar.regime_change <= cfg.calendar.end  # 1 Oct inside
    thr = load_thresholds()
    assert thr.eval.ablation_seeds == [42]
    assert cfg.calendar.start < thr.split.train_end < thr.split.validation_end < cfg.calendar.end
    assert load_models_config().network.window_days == 14
    # Same patterns and hard negatives as the reference world.
    monkeypatch.delenv("JACHAI_PROFILE")
    reference = [p.name for p in load_patterns_config().patterns]
    monkeypatch.setenv("JACHAI_PROFILE", "fast")
    assert [p.name for p in load_patterns_config().patterns] == reference


def test_fast_profile_uses_its_own_folders(monkeypatch):
    monkeypatch.setenv("JACHAI_PROFILE", "fast")
    monkeypatch.delenv("MODEL_DIR", raising=False)
    monkeypatch.delenv("JACHAI_DATA_DIR", raising=False)
    assert default_world_dir().parts[-3:] == ("data", "fast", "world")
    assert default_model_dir().parts[-2:] == ("models", "fast")


def test_unknown_profile_fails_loudly(monkeypatch):
    monkeypatch.setenv("JACHAI_PROFILE", "nope")
    with pytest.raises(FileNotFoundError, match="nope"):
        load_world_config()
