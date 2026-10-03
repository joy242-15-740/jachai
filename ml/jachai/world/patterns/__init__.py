"""Pluggable pattern injectors.

An injector is a function `fn(world, params, rng)` registered under a name with
@register("<name>"). configs/patterns.yaml lists which ones run, in what order,
and with what params. Each injector:
  - validates its own params (a small Pydantic model),
  - picks shops with `claim_shops` (a shop gets at most one pattern),
  - adds event rows with world.append, labelled with its pattern name,
  - marks the shops / customers it used with `mark_shops` / `mark_customers`.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from jachai.world.rng import stream
from jachai.world.world import World

Injector = Callable[[World, dict, np.random.Generator], None]
REGISTRY: dict[str, Injector] = {}


def register(name: str) -> Callable[[Injector], Injector]:
    def wrap(fn: Injector) -> Injector:
        if name in REGISTRY:
            raise ValueError(f"pattern {name!r} registered twice")
        REGISTRY[name] = fn
        return fn

    return wrap


def run_patterns(world: World) -> None:
    """Run every enabled pattern from patterns.yaml, in order."""
    if world.patterns is None:
        return
    for spec in world.patterns.patterns:
        if not spec.enabled:
            continue
        if spec.fn not in REGISTRY:
            raise KeyError(f"pattern fn {spec.fn!r} is not registered; known: {sorted(REGISTRY)}")
        world.current_pattern = spec
        REGISTRY[spec.fn](world, spec.params, stream(world.config.seed, f"pattern:{spec.name}"))
    world.current_pattern = None


# Importing the modules registers their injectors.
from jachai.world.patterns import misuse  # noqa: E402, F401
