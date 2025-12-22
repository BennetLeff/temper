"""Core data types for loss functions to avoid circular imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, NamedTuple

import jax.numpy as jnp
from jax import Array

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.io.config_loader import PlacementConstraints


@dataclass(frozen=True)
class LoopConstraint:
    """Defines a critical current loop to minimize."""
    name: str
    pins: tuple[tuple[str, str], ...]
    max_area: float = 100.0
    weight: float = 1.0


@dataclass(frozen=True)
class CriticalPathConstraint:
    """Defines a critical signal path requirement between two pins."""
    name: str
    from_pin: tuple[str, str]  # (component_ref, pin_name)
    to_pin: tuple[str, str]
    max_length: float = 50.0
    weight: float = 1.0
    matched_group: str | None = None


@dataclass(frozen=True)
class MatchedLengthConstraint:
    """Defines a group of paths that must have matched lengths."""
    name: str
    path_indices: tuple[int, ...]
    tolerance: float = 5.0
    weight: float = 1.0


@dataclass(frozen=True)
class NoiseIsolationConstraint:
    """Defines isolation requirement between sensitive components and noise sources."""
    name: str
    sensitive_indices: tuple[int, ...]
    noise_source_indices: tuple[int, ...]
    min_distance: float = 10.0
    weight: float = 1.0


@dataclass(frozen=True)
class ThermalConstraint:
    """Defines thermal placement requirements for a component."""
    component_ref: str
    edge: str
    max_distance: float = 5.0
    weight: float = 1.0


@dataclass(frozen=True)
class ClearanceRule:
    """Defines a minimum clearance between net classes."""
    net_class_a: str
    net_class_b: str
    min_clearance: float
    weight: float = 1.0


@dataclass(frozen=True)
class MountingRule:
    """Defines mechanical placement constraints for a component."""
    component_idx: int
    rule_type: str
    edge: str | None = None
    max_distance_mm: float | None = None
    mount_positions: tuple[tuple[float, float], ...] | None = None
    target_position: tuple[float, float] | None = None
    weight: float = 1.0


@dataclass
class LossContext:
    """Immutable context containing all data needed by loss functions."""
    netlist: Netlist
    board: Board
    bounds: Array
    fixed_mask: Array
    constraints: PlacementConstraints | None = None

    hv_indices: Array = field(default_factory=lambda: jnp.array([], dtype=jnp.int32))
    lv_indices: Array = field(default_factory=lambda: jnp.array([], dtype=jnp.int32))
    clearance_rules: list[ClearanceRule] = field(default_factory=list)
    thermal_constraints: list[ThermalConstraint] = field(default_factory=list)
    loop_constraints: list[LoopConstraint] = field(default_factory=list)
    mounting_rules: list[MountingRule] = field(default_factory=list)
    net_class_map: dict[str, str] = field(default_factory=dict)
    net_pin_indices: Array = field(default_factory=lambda: jnp.zeros((0, 0), dtype=jnp.int32))
    net_pin_offsets: Array = field(default_factory=lambda: jnp.zeros((0, 0, 2), dtype=jnp.float32))
    net_pin_mask: Array = field(default_factory=lambda: jnp.zeros((0, 0), dtype=jnp.bool_))
    net_weights: Array = field(default_factory=lambda: jnp.zeros((0,), dtype=jnp.float32))
    max_pins_per_net: int = 0
    loop_pin_indices: Array = field(default_factory=lambda: jnp.zeros((0, 0), dtype=jnp.int32))
    loop_pin_offsets: Array = field(default_factory=lambda: jnp.zeros((0, 0, 2), dtype=jnp.float32))
    loop_pin_mask: Array = field(default_factory=lambda: jnp.zeros((0, 0), dtype=jnp.bool_))
    loop_max_areas: Array = field(default_factory=lambda: jnp.zeros((0,), dtype=jnp.float32))
    loop_weights: Array = field(default_factory=lambda: jnp.zeros((0,), dtype=jnp.float32))

    # Critical Paths
    path_pin_indices: Array = field(default_factory=lambda: jnp.zeros((0, 2), dtype=jnp.int32))
    path_pin_offsets: Array = field(default_factory=lambda: jnp.zeros((0, 2, 2), dtype=jnp.float32))
    path_max_lengths: Array = field(default_factory=lambda: jnp.zeros((0,), dtype=jnp.float32))
    path_weights: Array = field(default_factory=lambda: jnp.zeros((0,), dtype=jnp.float32))

    # Matched Length Groups
    # (Since groups have varying sizes, we use padding or a different structure)
    # For now, let's just store the indices
    matched_groups: list[MatchedLengthConstraint] = field(default_factory=list)

    # Noise Isolation
    noise_isolation_constraints: list[NoiseIsolationConstraint] = field(default_factory=list)

    net_class_indices: dict[str, Array] = field(default_factory=dict)
    centrality: Array = field(default_factory=lambda: jnp.array([], dtype=jnp.float32))

    # Ground Domains
    domain_bounds: Array = field(default_factory=lambda: jnp.zeros((0, 4), dtype=jnp.float32))
    domain_star_points: Array = field(default_factory=lambda: jnp.zeros((0, 2), dtype=jnp.float32))
    domain_has_star: Array = field(default_factory=lambda: jnp.zeros((0,), dtype=jnp.bool_))


class LossResult(NamedTuple):
    """Result from a loss function evaluation."""
    value: Array
    breakdown: dict[str, Array] | None = None
