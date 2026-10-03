"""Load configs/rules.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from jachai.world.config import DEFAULT_CONFIG_DIR, _read_yaml, _Strict


class LFSpec(_Strict):
    weight: float = Field(gt=0)
    # Thresholds; each labeling function checks the names it needs.
    model_config = _Strict.model_config | {"extra": "allow"}

    def param(self, name: str) -> Any:
        extra = self.model_extra or {}
        if name not in extra:
            raise KeyError(f"missing labeling-function setting {name!r} in configs/rules.yaml")
        return extra[name]


class AggregatorSpec(_Strict):
    kind: Literal["weighted_vote"]
    threshold: float = Field(gt=0, lt=1)


class RulesConfig(_Strict):
    labeling_functions: dict[str, LFSpec]
    aggregator: AggregatorSpec


def load_rules(path: Path | None = None) -> RulesConfig:
    return RulesConfig.model_validate(_read_yaml(path or DEFAULT_CONFIG_DIR / "rules.yaml"))
