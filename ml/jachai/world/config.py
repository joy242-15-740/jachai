"""Load and validate configs/world.yaml and configs/patterns.yaml.

Pydantic models check every field when the YAML is loaded. Unknown keys are
rejected (extra="forbid"), so a typo fails loudly instead of being ignored.
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

# ml/jachai/world/config.py -> repo root is three levels above the package.
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_DIR = REPO_ROOT / "configs"

SHARE_TOLERANCE = 1e-6


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _check_sums_to_one(shares: dict[str, float], what: str) -> None:
    total = sum(shares.values())
    if abs(total - 1.0) > SHARE_TOLERANCE:
        raise ValueError(f"{what} must sum to 1, got {total:.6f}")


def _check_range(pair: list[float] | tuple[float, ...], what: str) -> None:
    if len(pair) != 2 or pair[0] > pair[1]:
        raise ValueError(f"{what} must be [low, high] with low <= high, got {pair}")


class Lognormal(_Strict):
    median: float = Field(gt=0)
    sigma: float = Field(gt=0)
    min: float = Field(ge=0)
    max: float = Field(gt=0)

    @model_validator(mode="after")
    def _min_below_max(self) -> Lognormal:
        if not self.min <= self.median <= self.max:
            raise ValueError("need min <= median <= max")
        return self


class Calendar(_Strict):
    start: dt.date
    days: int = Field(gt=0)
    regime_change: dt.date

    @property
    def end(self) -> dt.date:
        """Last day in the window (inclusive)."""
        return self.start + dt.timedelta(days=self.days - 1)


class Regulation(_Strict):
    cash_out_limit_daily: float = Field(gt=0)
    qr_incentive_cap: float = Field(gt=0)


class Scenario(_Strict):
    p2p_qr_enabled: bool
    p2p_qr_start: dt.date


class Population(_Strict):
    n_shops: int = Field(gt=0)
    n_customers: int = Field(gt=0)
    n_agents: int = Field(gt=0)


class MapCfg(_Strict):
    size_km: float = Field(gt=0)
    dhaka_center_km: tuple[float, float]
    dhaka_radius_km: float = Field(gt=0)
    rural_spread_km: float = Field(gt=0)


class Area(_Strict):
    shop_share: float = Field(ge=0, le=1)
    customer_share: float = Field(ge=0, le=1)
    n_zones: int = Field(gt=0)
    volume_mult: float = Field(gt=0)
    haat_days_per_week: int = Field(default=0, ge=0, le=7)


class SizeTier(_Strict):
    share: float = Field(ge=0, le=1)
    volume_mult: float = Field(gt=0)
    regulars: tuple[int, int]

    @model_validator(mode="after")
    def _range(self) -> SizeTier:
        _check_range(self.regulars, "regulars")
        return self


class Category(_Strict):
    shop_share: float = Field(ge=0, le=1)
    daily_qr_payments: float = Field(gt=0)
    ticket: Lognormal
    round_unit: int = Field(gt=0)
    round_share: float = Field(ge=0, le=1)
    open_hours: tuple[int, int]

    @model_validator(mode="after")
    def _hours(self) -> Category:
        open_h, close_h = self.open_hours
        if not 0 <= open_h < close_h <= 24:
            raise ValueError(f"open_hours must be 0 <= open < close <= 24, got {self.open_hours}")
        return self


class Customers(_Strict):
    account_age_mean_days: float = Field(gt=0)


class Payers(_Strict):
    regular_share: float = Field(ge=0, le=1)
    same_zone_share: float = Field(ge=0, le=1)
    honest_after_hours_share: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _shares(self) -> Payers:
        if self.regular_share + self.same_zone_share > 1:
            raise ValueError("regular_share + same_zone_share must be <= 1")
        return self


class Qr(_Strict):
    codes_per_shop: tuple[int, int]
    on_us_share: float = Field(ge=0, le=1)


class Weekly(_Strict):
    friday_mult: float = Field(gt=0)
    month_start_days: int = Field(ge=0, le=28)
    month_start_mult: float = Field(gt=0)


class Remittances(_Strict):
    receiver_share: float = Field(ge=0, le=1)
    per_30_days: float = Field(ge=0)
    amount: Lognormal
    corridors: dict[str, float]

    @model_validator(mode="after")
    def _shares(self) -> Remittances:
        _check_sums_to_one(self.corridors, "remittances.corridors")
        return self


class AddMoney(_Strict):
    per_30_days: float = Field(ge=0)
    amount: Lognormal
    channels: dict[str, float]

    @model_validator(mode="after")
    def _shares(self) -> AddMoney:
        _check_sums_to_one(self.channels, "add_money.channels")
        return self


class P2p(_Strict):
    per_30_days: float = Field(ge=0)
    amount: Lognormal
    same_zone_share: float = Field(ge=0, le=1)


AREA_TYPES = ("dhaka_urban", "district_town", "rural_haat")


class WorldConfig(_Strict):
    seed: int
    calendar: Calendar
    regulation: Regulation
    scenario: Scenario
    population: Population
    map: MapCfg
    areas: dict[str, Area]
    size_tiers: dict[str, SizeTier]
    categories: dict[str, Category]
    customers: Customers
    payers: Payers
    qr: Qr
    weekly: Weekly
    remittances: Remittances
    add_money: AddMoney
    p2p: P2p

    @model_validator(mode="after")
    def _cross_checks(self) -> WorldConfig:
        if set(self.areas) != set(AREA_TYPES):
            raise ValueError(f"areas must be exactly {AREA_TYPES}, got {sorted(self.areas)}")
        _check_sums_to_one({k: a.shop_share for k, a in self.areas.items()}, "areas.shop_share")
        _check_sums_to_one(
            {k: a.customer_share for k, a in self.areas.items()}, "areas.customer_share"
        )
        _check_sums_to_one({k: t.share for k, t in self.size_tiers.items()}, "size_tiers.share")
        _check_sums_to_one(
            {k: c.shop_share for k, c in self.categories.items()}, "categories.shop_share"
        )
        _check_range(self.qr.codes_per_shop, "qr.codes_per_shop")
        return self


class CasesCfg(_Strict):
    coverage: float = Field(ge=0, le=1)
    audit_share: float = Field(ge=0, le=1)
    flag_weight: dict[Literal["misuse", "hard_negative", "normal"], float]
    misuse_cleared: float = Field(ge=0, le=1)
    honest_convicted: float = Field(ge=0, le=1)
    duration_days: tuple[int, int]

    @model_validator(mode="after")
    def _check(self) -> CasesCfg:
        if self.audit_share > self.coverage:
            raise ValueError("cases.audit_share cannot exceed cases.coverage")
        if set(self.flag_weight) != {"misuse", "hard_negative", "normal"}:
            raise ValueError("cases.flag_weight needs misuse, hard_negative and normal")
        _check_range(self.duration_days, "cases.duration_days")
        return self


class PatternSpec(_Strict):
    name: str
    fn: str
    kind: Literal["misuse", "hard_negative"]
    enabled: bool = True
    # Free-form: each injector validates its own params.
    params: dict[str, Any] = Field(default_factory=dict)


class PatternsConfig(_Strict):
    cases: CasesCfg
    patterns: list[PatternSpec]

    @model_validator(mode="after")
    def _unique_names(self) -> PatternsConfig:
        names = [p.name for p in self.patterns]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ValueError(f"duplicate pattern names: {sorted(dupes)}")
        return self


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} is empty or not a mapping")
    return data


def load_world_config(path: Path | None = None) -> WorldConfig:
    """Load world.yaml. The JACHAI_SEED env var, if set, overrides `seed`."""
    data = _read_yaml(path or DEFAULT_CONFIG_DIR / "world.yaml")
    env_seed = os.environ.get("JACHAI_SEED")
    if env_seed:
        data["seed"] = int(env_seed)
    return WorldConfig.model_validate(data)


def load_patterns_config(path: Path | None = None) -> PatternsConfig:
    """Load patterns.yaml."""
    return PatternsConfig.model_validate(_read_yaml(path or DEFAULT_CONFIG_DIR / "patterns.yaml"))
