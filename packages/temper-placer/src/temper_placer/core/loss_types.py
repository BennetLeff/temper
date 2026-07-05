"""DEPRECATED: Loss types stubs — JAX retirement.

LossContext and related types were deleted with the JAX losses/ package.
These stubs exist for backwards compatibility during the transition.
All real loss computation now happens via CP-SAT.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LossResult:
    """DEPRECATED: Loss result stub."""
    value: float = 0.0
    breakdown: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class LoopConstraint:
    """DEPRECATED: Loop constraint stub."""
    name: str = ""
    pins: tuple = ()
    max_area: float = 100.0
    weight: float = 1.0
    because: str = ""


@dataclass(frozen=True)
class ThermalConstraint:
    """DEPRECATED: Thermal constraint stub."""
    component_ref: str = ""
    edge: str = ""
    max_distance: float = 5.0
    weight: float = 1.0
    because: str = ""


@dataclass(frozen=True)
class ClearanceRule:
    """DEPRECATED: Clearance rule stub."""
    source: str = ""
    target: str = ""
    min_clearance: float = 0.0
    weight: float = 1.0


@dataclass(frozen=True)
class StarGroundConstraint:
    """DEPRECATED: Star ground constraint stub."""
    net_name: str = ""
    max_distance: float = 0.0
    weight: float = 1.0
    anchor_position: tuple | None = None
    because: str = ""


@dataclass(frozen=True)
class CriticalPathConstraint:
    """DEPRECATED: Critical path constraint stub."""
    name: str = ""
    from_pin: tuple = ()
    to_pin: tuple = ()
    max_length: float = 50.0
    weight: float = 1.0
    matched_group: str | None = None
    because: str = ""


@dataclass(frozen=True)
class MatchedLengthConstraint:
    """DEPRECATED: Matched length constraint stub."""
    name: str = ""
    path_indices: tuple = ()
    tolerance: float = 5.0
    weight: float = 1.0
    because: str = ""


@dataclass(frozen=True)
class NoiseIsolationConstraint:
    """DEPRECATED: Noise isolation constraint stub."""
    name: str = ""
    sensitive_indices: tuple = ()
    noise_source_indices: tuple = ()
    min_distance: float = 10.0
    weight: float = 1.0
    because: str = ""


@dataclass(frozen=True)
class MountingRule:
    """DEPRECATED: Mounting rule stub."""
    component_ref: str = ""
    edge: str = ""
    offset: float = 0.0
    weight: float = 1.0


@dataclass
class LossContext:
    """DEPRECATED: Loss context stub (JAX retirement)."""

    netlist: Any = None
    board: Any = None
    constraints: Any = None

    @classmethod
    def from_netlist_and_board(cls, netlist, board, **kwargs):
        """DEPRECATED: Always raises NotImplementedError."""
        raise NotImplementedError(
            "LossContext.from_netlist_and_board removed (JAX retirement). "
            "Use temper_placer.placer.deterministic.PlacementResult instead."
        )


@dataclass
class CompositeLoss:
    """DEPRECATED: Composite loss stub."""
    losses: list = field(default_factory=list)

    def __call__(self, *args, **kwargs):
        raise NotImplementedError("CompositeLoss removed (JAX retirement).")


@dataclass
class WeightedLoss:
    """DEPRECATED: Weighted loss stub."""
    loss: Any = None
    weight: float = 1.0

    def __call__(self, *args, **kwargs):
        raise NotImplementedError("WeightedLoss removed (JAX retirement).")


class LossFunction:
    """DEPRECATED: Loss function stub."""
    pass


class ConstraintContext:
    """DEPRECATED: Constraint context stub."""
    pass


class GeometryContext:
    """DEPRECATED: Geometry context stub."""
    pass


class NetlistContext:
    """DEPRECATED: Netlist context stub."""
    pass


# Provide a bare fallback so callers that imported from losses.types
# or losses.base don't get AttributeError on cold import
