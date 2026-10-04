"""Load configs/simulator.yaml; per-run overrides are validated the same way."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from jachai.world.config import DEFAULT_CONFIG_DIR, _read_yaml, _Strict, apply_profile


class Replay(_Strict):
    seed: int
    days: int = Field(gt=0)


class SimParams(_Strict):
    misuse_scale: float = Field(gt=0, le=1)
    fee_rate: float | None = Field(default=None, gt=0, lt=1)
    analyst_capacity_per_day: int = Field(ge=0)
    limit_level: float = Field(gt=0)
    analyst_recall: float = Field(ge=0, le=1)
    analyst_false_confirm: float = Field(ge=0, le=1)
    rules_min_flags: int = Field(gt=0)
    jachai_bands: list[str] = Field(min_length=1)
    convert_min_monthly_taka: float = Field(ge=0)
    offer_acceptance: float = Field(ge=0, le=1)
    displaced_to_agents_share: float = Field(ge=0, le=1)
    seed: int

    def with_overrides(self, overrides: dict[str, Any] | None) -> SimParams:
        """A validated copy with some values changed (e.g. from UI sliders)."""
        return SimParams.model_validate({**self.model_dump(), **(overrides or {})})


class SimulatorConfig(_Strict):
    replay: Replay
    params: SimParams


def load_simulator_config(path: Path | None = None) -> SimulatorConfig:
    data = _read_yaml(path or DEFAULT_CONFIG_DIR / "simulator.yaml")
    return SimulatorConfig.model_validate(apply_profile("simulator", data))
