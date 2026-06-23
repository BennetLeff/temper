"""Core data types for loss functions to avoid circular imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, NamedTuple, Optional

import jax
import jax.numpy as jnp
from jax import Array

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


@jax.tree_util.register_pytree_node_class
@dataclass(frozen=True)
class GeometryContext:
    """Pre-computed geometric data and board bounds."""
    bounds: Array = None  # (N, 2) component bounds
    fixed_mask: Array = None  # (N,) boolean mask
    origin: Array = None  # (2,) board origin (ox, oy)
    width: float = 0.0
    height: float = 0.0
    board_margin: float = 0.0

    def tree_flatten(self):
        children = (self.bounds, self.fixed_mask, self.origin)
        aux_data = (self.width, self.height, self.board_margin)
        return (children, aux_data)

    @classmethod
    def tree_unflatten(cls, aux_data, children):
        return cls(*children, *aux_data)


@jax.tree_util.register_pytree_node_class
@dataclass(frozen=True)
class NetlistContext:
    """Pre-computed netlist and connectivity data."""
    net_pin_indices: Array = None  # (M, P) indices of components in pins
    net_pin_offsets: Array = None  # (M, P, 2) pin offsets from center
    net_pin_mask: Array = None  # (M, P) valid pin mask
    net_weights: Array = None  # (M,) net priority weights
    net_layer_counts: Array = None  # (M,) required layers
    centrality: Array = None  # (N,) node centrality
    hv_indices: Array = None  # Indices of high-voltage components
    lv_indices: Array = None  # Indices of low-voltage components
    fiducial_indices: Array = None  # Indices of fiducials
    max_pins_per_net: int = 0

    def tree_flatten(self):
        children = (
            self.net_pin_indices,
            self.net_pin_offsets,
            self.net_pin_mask,
            self.net_weights,
            self.net_layer_counts,
            self.centrality,
            self.hv_indices,
            self.lv_indices,
            self.fiducial_indices,
        )
        aux_data = (self.max_pins_per_net,)
        return (children, aux_data)

    @classmethod
    def tree_unflatten(cls, aux_data, children):
        return cls(*children, *aux_data)


@jax.tree_util.register_pytree_node_class
@dataclass(frozen=True)
class ConstraintContext:
    """Pre-computed constraint data (loops, thermal, stars)."""
    # Loop constraints
    loop_pin_indices: Array = None  # (L, P)
    loop_pin_offsets: Array = None  # (L, P, 2)
    loop_pin_mask: Array = None  # (L, P)
    loop_max_areas: Array = None  # (L,)
    loop_weights: Array = None  # (L,)

    # Critical Paths
    path_pin_indices: Array = None  # (K, 2)
    path_pin_offsets: Array = None  # (K, 2, 2)
    path_max_lengths: Array = None  # (K,)
    path_weights: Array = None  # (K,)

    # Star Grounds
    star_net_indices: Array = None  # (S,)
    star_weights: Array = None  # (S,)
    star_anchor_pos: Array = None  # (S, 2)
    star_has_anchor: Array = None  # (S,)
    
    # Ground Domains
    domain_bounds: Array = None  # (D, 4)
    domain_star_points: Array = None  # (D, 2)
    domain_has_star: Array = None  # (D,)
    is_star_net: Array = None  # (M,)
    
    # Spatial Feedback (from routing failures)
    spatial_penalties: Array = None  # (K, 3) -> [x, y, magnitude]

    def tree_flatten(self):
        children = (
            self.loop_pin_indices,
            self.loop_pin_offsets,
            self.loop_pin_mask,
            self.loop_max_areas,
            self.loop_weights,
            self.path_pin_indices,
            self.path_pin_offsets,
            self.path_max_lengths,
            self.path_weights,
            self.star_net_indices,
            self.star_weights,
            self.star_anchor_pos,
            self.star_has_anchor,
            self.domain_bounds,
            self.domain_star_points,
            self.domain_has_star,
            self.is_star_net,
            self.spatial_penalties,
        )
        aux_data = None
        return (children, aux_data)

    @classmethod
    def tree_unflatten(cls, aux_data, children):
        return cls(*children)


@jax.tree_util.register_pytree_node_class
@dataclass(frozen=True)
class LossContext:
    """
    Immutable context containing all data needed by loss functions.
    This monolith is being decomposed into the sub-contexts above.
    """
    # Original references (Keep at top for positional constructor compatibility).
    # netlist and board default to None for loss functions that don't need them
    # (e.g., self-contained tests on position arrays).
    netlist: Any = None  # Netlist object
    board: Any = None    # Board object
    bounds: Array = None  # (N, 2) component bounds
    fixed_mask: Array = None  # (N,) boolean mask
    
    # New sub-contexts (Always populated)
    geometry: GeometryContext = field(default_factory=GeometryContext)
    netlist_data: NetlistContext = field(default_factory=NetlistContext)
    constraints_data: ConstraintContext = field(default_factory=ConstraintContext)
    
    # Hypergraph (Optional for backward compatibility, but preferred for new losses)
    hypergraph: Optional["PhysicsHypergraph"] = None

    constraints_config: Optional[Any] = None  # PlacementConstraints (aux_data)
    thermal_constraints: list[Any] = field(default_factory=list)
    loop_constraints: list[Any] = field(default_factory=list)
    matched_groups: list[Any] = field(default_factory=list)
    clearance_rules: list[Any] = field(default_factory=list)
    star_ground_constraints: list[Any] = field(default_factory=list)
    component_spacing_rules: list[Any] = field(default_factory=list)  # ComponentSpacingRule list
    
    # Missing auxiliary data for aesthetic and other losses
    component_type_indices: dict[str, Array] = field(default_factory=dict)
    net_class_indices: dict[str, Array] = field(default_factory=dict)
    component_name_to_index: dict[str, int] = field(default_factory=dict)  # ref -> index mapping
    port_facing_groups: list[Any] = field(default_factory=list)

    # --- Delegated Properties for Backward Compatibility ---
    
    # Geometry related
    @property
    def origin(self) -> Array:
        return self.geometry.origin if self.geometry.origin is not None else jnp.zeros((2,))
    
    @property
    def width(self) -> float:
        return self.geometry.width
    
    @property
    def height(self) -> float:
        return self.geometry.height
    
    @property
    def board_margin(self) -> float:
        return self.geometry.board_margin

    # Netlist related
    @property
    def centrality(self) -> Array:
        return self.netlist_data.centrality if self.netlist_data.centrality is not None else jnp.ones((0,))
    
    @property
    def net_pin_indices(self) -> Array:
        return self.netlist_data.net_pin_indices if self.netlist_data.net_pin_indices is not None else jnp.zeros((0, 0), dtype=jnp.int32)
    
    @property
    def net_pin_offsets(self) -> Array:
        return self.netlist_data.net_pin_offsets if self.netlist_data.net_pin_offsets is not None else jnp.zeros((0, 0, 2))
    
    @property
    def net_pin_mask(self) -> Array:
        return self.netlist_data.net_pin_mask if self.netlist_data.net_pin_mask is not None else jnp.zeros((0, 0), dtype=jnp.bool_)
    
    @property
    def net_weights(self) -> Array:
        return self.netlist_data.net_weights if self.netlist_data.net_weights is not None else jnp.ones((0,))
    
    @property
    def net_layer_counts(self) -> Array:
        return self.netlist_data.net_layer_counts if self.netlist_data.net_layer_counts is not None else jnp.ones((0,), dtype=jnp.int32)
    
    @property
    def hv_indices(self) -> Array:
        return self.netlist_data.hv_indices if self.netlist_data.hv_indices is not None else jnp.zeros((0,), dtype=jnp.int32)
    
    @property
    def lv_indices(self) -> Array:
        return self.netlist_data.lv_indices if self.netlist_data.lv_indices is not None else jnp.zeros((0,), dtype=jnp.int32)
    
    @property
    def fiducial_indices(self) -> Array:
        return self.netlist_data.fiducial_indices if self.netlist_data.fiducial_indices is not None else jnp.zeros((0,), dtype=jnp.int32)

    # Constraints related
    @property
    def star_net_indices(self) -> Array:
        return self.constraints_data.star_net_indices if self.constraints_data.star_net_indices is not None else jnp.zeros((0,), dtype=jnp.int32)
    
    @property
    def star_weights(self) -> Array:
        return self.constraints_data.star_weights if self.constraints_data.star_weights is not None else jnp.zeros((0,))
    
    @property
    def star_anchor_pos(self) -> Array:
        return self.constraints_data.star_anchor_pos if self.constraints_data.star_anchor_pos is not None else jnp.zeros((0, 2))
    
    @property
    def star_has_anchor(self) -> Array:
        return self.constraints_data.star_has_anchor if self.constraints_data.star_has_anchor is not None else jnp.zeros((0,), dtype=jnp.bool_)
    
    @property
    def domain_bounds(self) -> Array:
        return self.constraints_data.domain_bounds if self.constraints_data.domain_bounds is not None else jnp.zeros((0, 4))
    
    @property
    def domain_star_points(self) -> Array:
        return self.constraints_data.domain_star_points if self.constraints_data.domain_star_points is not None else jnp.zeros((0, 2))
    
    @property
    def domain_has_star(self) -> Array:
        return self.constraints_data.domain_has_star if self.constraints_data.domain_has_star is not None else jnp.zeros((0,), dtype=jnp.bool_)
    
    @property
    def is_star_net(self) -> Array:
        return self.constraints_data.is_star_net if self.constraints_data.is_star_net is not None else jnp.zeros((0,), dtype=jnp.bool_)

    @property
    def spatial_penalties(self) -> Array:
        return self.constraints_data.spatial_penalties if self.constraints_data.spatial_penalties is not None else jnp.zeros((0, 3))

    @property
    def loop_pin_indices(self) -> Array:
        return self.constraints_data.loop_pin_indices if self.constraints_data.loop_pin_indices is not None else jnp.zeros((0, 0), dtype=jnp.int32)
    
    @property
    def loop_pin_offsets(self) -> Array:
        return self.constraints_data.loop_pin_offsets if self.constraints_data.loop_pin_offsets is not None else jnp.zeros((0, 0, 2))
    
    @property
    def loop_pin_mask(self) -> Array:
        return self.constraints_data.loop_pin_mask if self.constraints_data.loop_pin_mask is not None else jnp.zeros((0, 0), dtype=jnp.bool_)
    
    @property
    def loop_max_areas(self) -> Array:
        return self.constraints_data.loop_max_areas if self.constraints_data.loop_max_areas is not None else jnp.zeros((0,))
    
    @property
    def loop_weights(self) -> Array:
        return self.constraints_data.loop_weights if self.constraints_data.loop_weights is not None else jnp.zeros((0,))

    @property
    def path_pin_indices(self) -> Array:
        return self.constraints_data.path_pin_indices if self.constraints_data.path_pin_indices is not None else jnp.zeros((0, 0), dtype=jnp.int32)
    
    @property
    def path_pin_offsets(self) -> Array:
        return self.constraints_data.path_pin_offsets if self.constraints_data.path_pin_offsets is not None else jnp.zeros((0, 0, 2))
    
    @property
    def path_max_lengths(self) -> Array:
        return self.constraints_data.path_max_lengths if self.constraints_data.path_max_lengths is not None else jnp.zeros((0,))
    
    @property
    def path_weights(self) -> Array:
        return self.constraints_data.path_weights if self.constraints_data.path_weights is not None else jnp.zeros((0,))

    def tree_flatten(self):
        children = (self.geometry, self.netlist_data, self.constraints_data, self.hypergraph, self.bounds, self.fixed_mask)
        aux_data = (
            self.netlist,
            self.board,
            self.constraints_config,
            self.thermal_constraints,
            self.loop_constraints,
            self.matched_groups,
            self.clearance_rules,
            self.star_ground_constraints,
            self.component_spacing_rules,
            self.component_type_indices,
            self.net_class_indices,
            self.component_name_to_index,
            self.port_facing_groups,
        )
        return (children, aux_data)

    @classmethod
    def tree_unflatten(cls, aux_data, children):
        geometry, netlist_data, constraints_data, hypergraph, bounds, fixed_mask = children
        (
            netlist, board, config, thermal, loop, matched, clearance, star,
            comp_spacing, comp_types, net_classes, comp_name_map, port_facing
        ) = aux_data
        return cls(
            netlist=netlist,
            board=board,
            bounds=bounds,
            fixed_mask=fixed_mask,
            geometry=geometry,
            netlist_data=netlist_data,
            constraints_data=constraints_data,
            hypergraph=hypergraph,
            constraints_config=config,
            thermal_constraints=thermal,
            loop_constraints=loop,
            matched_groups=matched,
            clearance_rules=clearance,
            star_ground_constraints=star,
            component_spacing_rules=comp_spacing,
            component_type_indices=comp_types,
            net_class_indices=net_classes,
            component_name_to_index=comp_name_map,
            port_facing_groups=port_facing,
        )


@dataclass
class LossResult:
    """Result from a loss function evaluation."""
    value: Array
    breakdown: Optional[dict[str, Array]] = field(default_factory=dict)
