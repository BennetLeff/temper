"""
Router V6 Stage DRC Validators.

Per-stage Design Rule Check (DRC) validators that run after each
channel analysis micro-stage. Each validator is a standalone function
decorated with @register_validator(name) for auto-discovery.

Part of feat/decompose-stage2: U0 BoardState Extension.
"""

from __future__ import annotations

from temper_placer.router_v6.astar_core import (
    RoutePath,
    RouteNode3D,
    RoutePath3D,
    _astar_search,
    _heuristic,
    _line_of_sight,
    _astar_search_lazy_theta_star,
    _astar_search_theta_star,
    _astar_search_3d,
    _route_segment_3d,
)

from temper_placer.router_v6.astar_grid import (
    _build_tht_pad_locations,
    _extract_pad_centers_per_net,
    _find_access_node,
    _identify_blocking_nets,
    _is_at_tht_pad,
    _mark_route_blocked,
    _restore_net_pads,
    _unblock_net_pads,
    _unmark_route_blocked,
)

from dataclasses import dataclass, field
from typing import Any, Callable

# Global registry: validator_name -> callable
VALIDATOR_REGISTRY: dict[str, list[Callable]] = {}


@dataclass
class StageDRCFailure:
    """A design rule violation detected by a stage validator."""

    field: str
    value: Any
    reason: str
    stage: str = ""

    def __str__(self) -> str:
        return f"[{self.stage}] {self.field}: {self.reason} (value={self.value!r})"


def register_validator(name: str):
    """Decorator to register a validator function for a specific stage."""

    def decorator(func: Callable):
        if name not in VALIDATOR_REGISTRY:
            VALIDATOR_REGISTRY[name] = []
        VALIDATOR_REGISTRY[name].append(func)
        return func

    return decorator


def run_validators(stage_name: str, state) -> list[StageDRCFailure]:
    """Run all registered validators for a stage."""
    failures: list[StageDRCFailure] = []
    for validator in VALIDATOR_REGISTRY.get(stage_name, []):
        result = validator(state)
        if isinstance(result, list):
            failures.extend(result)
        elif result is not None:
            failures.append(result)
    return failures


def get_registered_stages() -> list[str]:
    """Return list of stage names that have validators registered."""
    return sorted(VALIDATOR_REGISTRY.keys())


def clear_validators():
    """Clear all registered validators (useful for testing)."""
    VALIDATOR_REGISTRY.clear()
