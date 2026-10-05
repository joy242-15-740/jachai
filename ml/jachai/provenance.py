"""Provenance stamp for every training and evaluation report.

Each JSON report records:
  config_hash        sha256 (first 16 hex) of every config that training and
                     evaluation read, after the active profile is applied. The
                     API-only `recommendation` section of rules.yaml is left out
                     on purpose: it never affects a model or a result.
  config_hashes      the same, per config file
  git_commit         the commit the code ran at, plus whether the tree had
                     uncommitted changes ("dirty")
  model_fingerprint  the trained payment model's fingerprint, when there is one

Two reports with the same config_hash and model_fingerprint describe the same
system. Without this, a stale report cannot be told apart from a current one.
"""

from __future__ import annotations

import hashlib
import json
import subprocess

from jachai.features.config import load_thresholds
from jachai.labels.config import load_rules
from jachai.models.config import load_models_config
from jachai.world.config import REPO_ROOT, load_patterns_config, load_world_config

# rules.yaml sections that only the API reads (never training or evaluation).
API_ONLY_RULES = {"recommendation"}


def _hash(obj) -> str:
    text = json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def config_hashes() -> dict[str, str]:
    rules = load_rules().model_dump(exclude=API_ONLY_RULES)
    return {
        "world": _hash(load_world_config().model_dump()),
        "patterns": _hash(load_patterns_config().model_dump()),
        "thresholds": _hash(load_thresholds().model_dump()),
        "models": _hash(load_models_config().model_dump()),
        "rules": _hash(rules),
    }


def git_commit() -> dict[str, object]:
    def run(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()

    try:
        return {
            "commit": run("rev-parse", "--short", "HEAD"),
            "dirty": bool(run("status", "--porcelain")),
        }
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}  # e.g. a deployment without .git


def provenance(model_fingerprint: str | None = None) -> dict[str, object]:
    hashes = config_hashes()
    return {
        "config_hash": _hash(hashes),
        "config_hashes": hashes,
        "git": git_commit(),
        "model_fingerprint": model_fingerprint,
    }
