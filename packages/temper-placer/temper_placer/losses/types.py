"""Core data types for loss functions to avoid circular imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

import numpy as np

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.io.config_loader import PlacementConstraints
    from temper_placer.core.hypergraph import PhysicsHypergraph


@dataclass(frozen=True)
class LoopConstraint:
    """Defines a critical current loop to minimize."""
    name: str
    pins: tuple[tuple[str, str], ...]
    max_area: float = 100.0
    weight: float = 1.0
    because: str = ""


@dataclass(frozen=True)
class CriticalPathConstraint:
    """Defines a critical signal path requirement between two pins."""
    name: str
    from_pin: tuple[str, str]  # (component_ref, pin_name)
    to_pin: tuple[str, str]
    max_length: float = 50.0
    weight: float = 1.0
    matched_group: str | None = None
    because: str = ""


@dataclass(frozen=True)
class MatchedLengthConstraint:
    """Defines a group of paths that must have matched lengths."""
    name: str
    path_indices: tuple[int, ...]
    tolerance: float = 5.0
    weight: float = 1.0
    because: str = ""


@dataclass(frozen=True)
class NoiseIsolationConstraint:
    """Defines isolation requirement between sensitive components and noise sources."""
    name: str
    sensitive_indices: tuple[int, ...]
    noise_source_indices: tuple[int, ...]
    min_distance: float = 10.0
    weight: float = 1.0
    because: str = ""


@dataclass(frozen=True)
class ThermalConstraint:
    """Defines thermal placement requirements for a component."""
    component_ref: str
    edge: str
    max_distance: float = 5.0
    weight: float = 1.0
    because: str = ""


@dataclass(frozen=True)
class StarGroundConstraint:
    """Defines a star ground topology for a specific net."""
    net_name: str
    max_distance: float = 0.0  # Ideally 0
    weight: float = 1.0
    anchor_position: tuple[float, float] | None = None  # Optional fixed anchor
    because: str = ""


@dataclass(frozen=True)
class ClearanceRule:
    """Defines a minimum clearance between net classes."""
    net_class_a: str
    net_class_b: str
    min_clearance: float
    weight: float = 1.0
    because: str = ""


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
    because: str = ""


@dataclass(frozen=True)
class ComponentSpacingRule:
    """Defines minimum edge-to-edge spacing between specific component pairs."""
    component_a: str  # Component reference (e.g., "D2")
    component_b: str  # Component reference (e.g., "C_BUS1")
    min_separation_mm: float  # Minimum edge-to-edge distance
    weight: float = 1.0
    because: str = ""


@dataclass(frozen=True)
class GeometryContext:
    """Pre-computed geometric data and board bounds."""
    bounds: np.ndarray = field(default_factory=lambda: np.zeros((0, 2)))  # (N, 2)
    fixed_mask: np.ndarray = field(default_factory=lambda: np.zeros((0,), dtype=bool))  # (N,)
    origin: np.ndarray = field(default_factory=lambda: np.zeros((2,)))  # (2,)
    width: float = 0.0
    height: float = 0.0
    board_margin: float = 0.0


@dataclass(frozen=True)
class NetlistContext:
    """Pre-computed netlist and connectivity data."""
    net_pin_indices: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.int32))
    net_pin_offsets: np.ndarray = field(default_factory=lambda: np.zeros((0, 0, 2)))
    net_pin_mask: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=bool))
    net_weights: np.ndarray = field(default_factory=lambda: np.zeros((0,)))
    net_layer_counts: np.ndarray = field(default_factory=lambda: np.zeros((0,), dtype=np.int32))
    centrality: np.ndarray = field(default_factory=lambda: np.zeros((0,)))
    hv_indices: np.ndarray = field(default_factory=lambda: np.zeros((0,), dtype=np.int32))
    lv_indices: np.ndarray = field(default_factory=lambda: np.zeros((0,), dtype=np.int32))
    fiducial_indices: np.ndarray = field(default_factory=lambda: np.zeros((0,), dtype=np.int32))
    max_pins_per_net: int = 0


@dataclass(frozen=True)
class ConstraintContext:
    """Pre-computed constraint data (loops, thermal, stars)."""
    loop_pin_indices: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.int32))
    loop_pin_offsets: np.ndarray = field(default_factory=lambda: np.zeros((0, 0, 2)))
    loop_pin_mask: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=bool))
    loop_max_areas: np.ndarray = field(default_factory=lambda: np.zeros((0,)))
    loop_weights: np.ndarray = field(default_factory=lambda: np.zeros((0,)))
    path_pin_indices: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.int32))
    path_pin_offsets: np.ndarray = field(default_factory=lambda: np.zeros((0, 0, 2)))
    path_max_lengths: np.ndarray = field(default_factory=lambda: np.zeros((0,)))
    path_weights: np.ndarray = field(default_factory=lambda: np.zeros((0,)))
    star_net_indices: np.ndarray = field(default_factory=lambda: np.zeros((0,), dtype=np.int32))
    star_weights: np.ndarray = field(default_factory=lambda: np.zeros((0,)))
    star_anchor_pos: np.ndarray = field(default_factory=lambda: np.zeros((0, 2)))
    star_has_anchor: np.ndarray = field(default_factory=lambda: np.zeros((0,), dtype=bool))
    domain_bounds: np.ndarray = field(default_factory=lambda: np.zeros((0, 4)))
    domain_star_points: np.ndarray = field(default_factory=lambda: np.zeros((0, 2)))
    domain_has_star: np.ndarray = field(default_factory=lambda: np.zeros((0,), dtype=bool))
    is_star_net: np.ndarray = field(default_factory=lambda: np.zeros((0,), dtype=bool))
    spatial_penalties: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))


@dataclass(frozen=True)
class LossContext:
    """Immutable context containing all data needed by loss functions."""
    netlist: Any  # Netlist object
    board: Any    # Board object
    bounds: np.ndarray = field(default_factory=lambda: np.zeros((0, 2)))
    fixed_mask: np.ndarray = field(default_factory=lambda: np.zeros((0,), dtype=bool))
    
    geometry: GeometryContext = field(default_factory=GeometryContext)
    netlist_data: NetlistContext = field(default_factory=NetlistContext)
    constraints_data: ConstraintContext = field(default_factory=ConstraintContext)
    
    hypergraph: Optional["PhysicsHypergraph"] = None
    constraints_config: Optional[Any] = None
    thermal_constraints: list[Any] = field(default_factory=list)
    loop_constraints: list[Any] = field(default_factory=list)
    matched_groups: list[Any] = field(default_factory=list)
    clearance_rules: list[Any] = field(default_factory=list)
    star_ground_constraints: list[Any] = field(default_factory=list)
    component_spacing_rules: list[Any] = field(default_factory=list)
    
    component_type_indices: dict[str, np.ndarray] = field(default_factory=dict)
    net_class_indices: dict[str, np.ndarray] = field(default_factory=dict)
    component_name_to_index: dict[str, int] = field(default_factory=dict)
    port_facing_groups: list[Any] = field(default_factory=list)

    @property
    def origin(self) -> np.ndarray:
        return self.geometry.origin
    
    @property
    def width(self) -> float:
        return self.geometry.width
    
    @property
    def height(self) -> float:
        return self.geometry.height
    
    @property
    def board_margin(self) -> float:
        return self.geometry.board_margin

    @property
    def centrality(self) -> np.ndarray:
        return self.netlist_data.centrality
    
    @property
    def net_pin_indices(self) -> np.ndarray:
        return self.netlist_data.net_pin_indices
    
    @property
    def net_pin_offsets(self) -> np.ndarray:
        return self.netlist_data.net_pin_offsets
    
    @property
    def net_pin_mask(self) -> np.ndarray:
        return self.netlist_data.net_pin_mask
    
    @property
    def net_weights(self) -> np.ndarray:
        return self.netlist_data.net_weights
    
    @property
    def net_layer_counts(self) -> np.ndarray:
        return self.netlist_data.net_layer_counts
    
    @property
    def hv_indices(self) -> np.ndarray:
        return self.netlist_data.hv_indices
    
    @property
    def lv_indices(self) -> np.ndarray:
        return self.netlist_data.lv_indices
    
    @property
    def fiducial_indices(self) -> np.ndarray:
        return self.netlist_data.fiducial_indices

    @property
    def star_net_indices(self) -> np.ndarray:
        return self.constraints_data.star_net_indices
    
    @property
    def star_weights(self) -> np.ndarray:
        return self.constraints_data.star_weights
    
    @property
    def star_anchor_pos(self) -> np.ndarray:
        return self.constraints_data.star_anchor_pos
    
    @property
    def star_has_anchor(self) -> np.ndarray:
        return self.constraints_data.star_has_anchor
    
    @property
    def domain_bounds(self) -> np.ndarray:
        return self.constraints_data.domain_bounds
    
    @property
    def domain_star_points(self) -> np.ndarray:
        return self.constraints_data.domain_star_points
    
    @property
    def domain_has_star(self) -> np.ndarray:
        return self.constraints_data.domain_has_star
    
    @property
    def is_star_net(self) -> np.ndarray:
        return self.constraints_data.is_star_net

    @property
    def spatial_penalties(self) -> np.ndarray:
        return self.constraints_data.spatial_penalties

    @property
    def loop_pin_indices(self) -> np.ndarray:
        return self.constraints_data.loop_pin_indices
    
    @property
    def loop_pin_offsets(self) -> np.ndarray:
        return self.constraints_data.loop_pin_offsets
    
    @property
    def loop_pin_mask(self) -> np.ndarray:
        return self.constraints_data.loop_pin_mask
    
    @property
    def loop_max_areas(self) -> np.ndarray:
        return self.constraints_data.loop_max_areas
    
    @property
    def loop_weights(self) -> np.ndarray:
        return self.constraints_data.loop_weights

    @property
    def path_pin_indices(self) -> np.ndarray:
        return self.constraints_data.path_pin_indices
    
    @property
    def path_pin_offsets(self) -> np.ndarray:
        return self.constraints_data.path_pin_offsets
    
    @property
    def path_max_lengths(self) -> np.ndarray:
        return self.constraints_data.path_max_lengths
    
    @property
    def path_weights(self) -> np.ndarray:
        return self.constraints_data.path_weights


@dataclass
class LossResult:
    """Result from a loss function evaluation."""
    value: float
    breakdown: Optional[dict[str, float]] = field(default_factory=dict)
