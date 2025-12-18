"""
Base classes and interfaces for loss functions.

This module defines the core abstractions for loss functions in temper-placer:
- LossFunction: Abstract base class for individual loss functions
- LossContext: Immutable context passed to all loss functions
- LossResult: Return type with value and optional breakdown
- CompositeLoss: Aggregates multiple weighted loss functions

All loss functions must be JAX-compatible (work with jit, grad, vmap).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import NamedTuple, cast

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.core.board import Board
from temper_placer.core.netlist import (
    Netlist,
    build_adjacency_matrix,
    compute_eigenvector_centrality,
)


@dataclass(frozen=True)
class LoopConstraint:
    """
    Defines a critical current loop to minimize.

    Attributes:
        name: Loop identifier (e.g., "gate_drive_high").
        pins: List of (component_ref, pin_name) forming the loop in order.
        max_area: Maximum allowed loop area in mm² (soft constraint).
        weight: Importance weight for this loop.
    """

    name: str
    pins: tuple[tuple[str, str], ...]  # Immutable for hashability
    max_area: float = 100.0  # mm²
    weight: float = 1.0


@dataclass(frozen=True)
class ThermalConstraint:
    """
    Defines thermal placement requirements for a component.

    Attributes:
        component_ref: Component reference (e.g., "Q1").
        edge: Board edge for heatsink mounting ("TOP", "BOTTOM", "LEFT", "RIGHT").
        max_distance: Maximum distance from edge in mm.
        weight: Importance weight.
    """

    component_ref: str
    edge: str  # "TOP", "BOTTOM", "LEFT", "RIGHT"
    max_distance: float = 5.0  # mm
    weight: float = 1.0


@dataclass(frozen=True)
class ClearanceRule:
    """
    Defines a minimum clearance between net classes.

    Attributes:
        net_class_a: First net class (e.g., "HighVoltage").
        net_class_b: Second net class (e.g., "Signal").
        min_clearance: Minimum distance in mm.
        weight: Importance weight for violations.
    """

    net_class_a: str
    net_class_b: str
    min_clearance: float  # mm
    weight: float = 1.0


@dataclass(frozen=True)
class MountingRule:
    """
    Defines mechanical placement constraints for a component.

    Attributes:
        component_idx: Index of the component.
        rule_type: Type of rule ("edge", "near_mount", "fixed_position", "accessible").
        edge: Board edge ("TOP", "BOTTOM", "LEFT", "RIGHT") for edge rule.
        max_distance_mm: Max distance for edge/mount rules.
        mount_positions: List of (x, y) tuples for mount points.
        target_position: (x, y) target for fixed position.
        weight: Importance weight.
    """

    component_idx: int
    rule_type: str
    edge: str | None = None
    max_distance_mm: float | None = None
    mount_positions: tuple[tuple[float, float], ...] | None = None  # Tuple for immutability
    target_position: tuple[float, float] | None = None
    weight: float = 1.0


@dataclass
class LossContext:
    """
    Immutable context containing all data needed by loss functions.

    This is passed to all loss functions and contains the netlist, board,
    and constraint definitions. It also includes pre-computed arrays for
    efficient JAX operations.

    Attributes:
        netlist: Complete netlist with components and nets.
        board: Board definition with zones and ground domains.
        bounds: (N, 2) array of component bounds (width, height).
        fixed_mask: (N,) boolean array of fixed components.
        hv_indices: Array of component indices in HighVoltage net class.
        lv_indices: Array of component indices in Signal net class.
        clearance_rules: List of clearance rules to enforce.
        thermal_constraints: List of thermal placement constraints.
        loop_constraints: List of critical loop constraints.
        net_class_map: Dict mapping component ref to net class.

        # Pre-computed arrays for JAX-compatible wirelength computation:
        net_pin_indices: (M, P) padded array of component indices per net pin.
        net_pin_offsets: (M, P, 2) padded array of pin offsets (x, y) per net.
        net_pin_mask: (M, P) boolean mask for valid pins (False = padding).
        net_weights: (M,) array of net weights.
        max_pins_per_net: Maximum pins per net (P dimension).

        # Pre-computed arrays for loop constraints:
        loop_pin_indices: (L, Q) padded array of component indices per loop.
        loop_pin_offsets: (L, Q, 2) padded array of pin offsets per loop.
        loop_pin_mask: (L, Q) boolean mask for valid pins.
        loop_max_areas: (L,) array of maximum allowed areas.
        loop_weights: (L,) array of loop weights.

        # Pre-computed arrays for clearance by net class:
        net_class_indices: Dict mapping net class to array of component indices.
    """

    netlist: Netlist
    board: Board
    bounds: Array  # (N, 2) component bounds
    fixed_mask: Array  # (N,) boolean

    # Pre-computed indices for clearance checking
    hv_indices: Array = field(default_factory=lambda: jnp.array([], dtype=jnp.int32))
    lv_indices: Array = field(default_factory=lambda: jnp.array([], dtype=jnp.int32))

    # Constraint definitions
    clearance_rules: list[ClearanceRule] = field(default_factory=list)
    thermal_constraints: list[ThermalConstraint] = field(default_factory=list)
    loop_constraints: list[LoopConstraint] = field(default_factory=list)
    mounting_rules: list[MountingRule] = field(default_factory=list)

    # Net class mapping
    net_class_map: dict[str, str] = field(default_factory=dict)

    # Pre-computed arrays for JAX-compatible wirelength (filled by from_netlist_and_board)
    net_pin_indices: Array = field(default_factory=lambda: jnp.zeros((0, 0), dtype=jnp.int32))
    net_pin_offsets: Array = field(default_factory=lambda: jnp.zeros((0, 0, 2), dtype=jnp.float32))
    net_pin_mask: Array = field(default_factory=lambda: jnp.zeros((0, 0), dtype=jnp.bool_))
    net_weights: Array = field(default_factory=lambda: jnp.zeros((0,), dtype=jnp.float32))
    max_pins_per_net: int = 0

    # Pre-computed arrays for loop constraints
    loop_pin_indices: Array = field(default_factory=lambda: jnp.zeros((0, 0), dtype=jnp.int32))
    loop_pin_offsets: Array = field(default_factory=lambda: jnp.zeros((0, 0, 2), dtype=jnp.float32))
    loop_pin_mask: Array = field(default_factory=lambda: jnp.zeros((0, 0), dtype=jnp.bool_))
    loop_max_areas: Array = field(default_factory=lambda: jnp.zeros((0,), dtype=jnp.float32))
    loop_weights: Array = field(default_factory=lambda: jnp.zeros((0,), dtype=jnp.float32))

    # Pre-computed net class indices
    net_class_indices: dict[str, Array] = field(default_factory=dict)

    # Centrality weights for each component (N,)
    centrality: Array = field(default_factory=lambda: jnp.array([], dtype=jnp.float32))

    @classmethod
    def from_netlist_and_board(
        cls,
        netlist: Netlist,
        board: Board,
        clearance_rules: list[ClearanceRule] | None = None,
        thermal_constraints: list[ThermalConstraint] | None = None,
        loop_constraints: list[LoopConstraint] | None = None,
        mounting_rules: list[MountingRule] | None = None,
        use_centrality_weighting: bool = False,
    ) -> LossContext:
        """
        Create a LossContext from netlist and board with automatic index computation.

        Args:
            netlist: The netlist to use.
            board: The board definition.
            clearance_rules: Optional list of clearance rules.
            thermal_constraints: Optional list of thermal constraints.
            loop_constraints: Optional list of loop constraints.
            mounting_rules: Optional list of mounting rules.
            use_centrality_weighting: If True, scale weights and step sizes
                by component centrality (hub prioritization).

        Returns:
            A new LossContext with pre-computed arrays.

        Raises:
            ValueError: If constraint references invalid components or pins.
        """
        bounds = netlist.get_bounds_array()
        fixed_mask = netlist.get_fixed_mask()

        # Build net class map from components
        net_class_map = {c.ref: c.net_class for c in netlist.components}

        # Compute HV and LV indices
        hv_indices = []
        lv_indices = []
        net_class_indices_dict: dict[str, list[int]] = {}

        for i, comp in enumerate(netlist.components):
            if comp.net_class == "HighVoltage":
                hv_indices.append(i)
            elif comp.net_class in ("Signal", "LowVoltage"):
                lv_indices.append(i)

            # Build net class -> indices mapping
            if comp.net_class not in net_class_indices_dict:
                net_class_indices_dict[comp.net_class] = []
            net_class_indices_dict[comp.net_class].append(i)

        # Convert net class indices to JAX arrays
        net_class_indices = {
            nc: jnp.array(indices, dtype=jnp.int32)
            for nc, indices in net_class_indices_dict.items()
        }

        # Compute centrality (if enabled or needed for weighting)
        if use_centrality_weighting:
            adjacency = build_adjacency_matrix(netlist)
            centrality = compute_eigenvector_centrality(adjacency)
        else:
            centrality = jnp.ones(netlist.n_components) / max(netlist.n_components, 1)

        # Pre-compute net pin arrays for JAX-compatible wirelength
        net_pin_indices, net_pin_offsets, net_pin_mask, net_weights, max_pins = (
            cls._precompute_net_arrays(netlist, centrality if use_centrality_weighting else None)
        )

        # Pre-compute loop constraint arrays
        loop_constraints = loop_constraints or []
        loop_pin_indices, loop_pin_offsets, loop_pin_mask, loop_max_areas, loop_weights = (
            cls._precompute_loop_arrays(
                netlist, loop_constraints, centrality if use_centrality_weighting else None
            )
        )

        # Validate constraints reference valid components/pins
        validation_errors = cls._validate_constraints(
            netlist, thermal_constraints or [], loop_constraints
        )
        if validation_errors:
            raise ValueError("Invalid constraint references:\n" + "\n".join(validation_errors))

        return cls(
            netlist=netlist,
            board=board,
            bounds=bounds,
            fixed_mask=fixed_mask,
            hv_indices=jnp.array(hv_indices, dtype=jnp.int32),
            lv_indices=jnp.array(lv_indices, dtype=jnp.int32),
            clearance_rules=clearance_rules or [],
            thermal_constraints=thermal_constraints or [],
            loop_constraints=loop_constraints,
            mounting_rules=mounting_rules or [],
            net_class_map=net_class_map,
            net_pin_indices=net_pin_indices,
            net_pin_offsets=net_pin_offsets,
            net_pin_mask=net_pin_mask,
            net_weights=net_weights,
            max_pins_per_net=max_pins,
            loop_pin_indices=loop_pin_indices,
            loop_pin_offsets=loop_pin_offsets,
            loop_pin_mask=loop_pin_mask,
            loop_max_areas=loop_max_areas,
            loop_weights=loop_weights,
            net_class_indices=net_class_indices,
            centrality=centrality if use_centrality_weighting else jnp.array([]),
        )

    @staticmethod
    def _precompute_net_arrays(
        netlist: Netlist,
        centrality: Array | None = None,
    ) -> tuple[Array, Array, Array, Array, int]:
        """
        Pre-compute padded arrays for net pin positions.

        Returns:
            net_pin_indices: (M, P) component indices per net pin
            net_pin_offsets: (M, P, 2) pin offsets per net
            net_pin_mask: (M, P) valid pin mask
            net_weights: (M,) net weights
            max_pins: Maximum pins per net (P)
        """
        # Filter to nets with 2+ pins (required for HPWL)
        valid_nets = [n for n in netlist.nets if len(n.pins) >= 2]

        if not valid_nets:
            return (
                jnp.zeros((0, 0), dtype=jnp.int32),
                jnp.zeros((0, 0, 2), dtype=jnp.float32),
                jnp.zeros((0, 0), dtype=jnp.bool_),
                jnp.zeros((0,), dtype=jnp.float32),
                0,
            )

        max_pins = max(len(n.pins) for n in valid_nets)
        len(valid_nets)
        n_components = netlist.n_components

        # Initialize arrays
        indices = []
        offsets = []
        masks = []
        weights = []

        for net in valid_nets:
            net_indices = []
            net_offsets = []
            net_mask = []

            # For centrality weighting
            net_comp_indices = []

            for comp_ref, pin_name in net.pins:
                comp_idx = netlist.get_component_index(comp_ref)
                comp = netlist.get_component(comp_ref)
                pin = comp.get_pin(pin_name)

                net_indices.append(comp_idx)
                net_comp_indices.append(comp_idx)
                if pin is not None:
                    net_offsets.append(list(pin.position))
                else:
                    net_offsets.append([0.0, 0.0])  # Default to center
                net_mask.append(True)

            # Pad to max_pins
            while len(net_indices) < max_pins:
                net_indices.append(0)  # Dummy index
                net_offsets.append([0.0, 0.0])
                net_mask.append(False)

            indices.append(net_indices)
            offsets.append(net_offsets)
            masks.append(net_mask)

            # Compute effective net weight
            weight = net.weight
            if centrality is not None and centrality.shape[0] > 0:
                # Boost net weight by max centrality of connected components
                # Scale by N to keep average weight consistent (avg centrality is 1/N)
                max_c = jnp.max(centrality[jnp.array(net_comp_indices)])
                weight = weight * (max_c * n_components)

            weights.append(weight)

        return (
            jnp.array(indices, dtype=jnp.int32),
            jnp.array(offsets, dtype=jnp.float32),
            jnp.array(masks, dtype=jnp.bool_),
            jnp.array(weights, dtype=jnp.float32),
            max_pins,
        )

    @staticmethod
    def _precompute_loop_arrays(
        netlist: Netlist,
        loop_constraints: list[LoopConstraint],
        centrality: Array | None = None,
    ) -> tuple[Array, Array, Array, Array, Array]:
        """
        Pre-compute padded arrays for loop constraint pin positions.

        Returns:
            loop_pin_indices: (L, Q) component indices per loop
            loop_pin_offsets: (L, Q, 2) pin offsets per loop
            loop_pin_mask: (L, Q) valid pin mask
            loop_max_areas: (L,) max areas per loop
            loop_weights: (L,) weights per loop
        """
        if not loop_constraints:
            return (
                jnp.zeros((0, 0), dtype=jnp.int32),
                jnp.zeros((0, 0, 2), dtype=jnp.float32),
                jnp.zeros((0, 0), dtype=jnp.bool_),
                jnp.zeros((0,), dtype=jnp.float32),
                jnp.zeros((0,), dtype=jnp.float32),
            )

        max_pins = max(len(lc.pins) for lc in loop_constraints)
        n_components = netlist.n_components

        indices = []
        offsets = []
        masks = []
        max_areas = []
        weights = []

        for loop in loop_constraints:
            loop_indices = []
            loop_offsets = []
            loop_mask = []

            # For centrality weighting
            loop_comp_indices = []

            for comp_ref, pin_name in loop.pins:
                try:
                    comp_idx = netlist.get_component_index(comp_ref)
                    comp = netlist.get_component(comp_ref)
                    pin = comp.get_pin(pin_name)

                    loop_indices.append(comp_idx)
                    loop_comp_indices.append(comp_idx)
                    if pin is not None:
                        loop_offsets.append(list(pin.position))
                    else:
                        loop_offsets.append([0.0, 0.0])
                    loop_mask.append(True)
                except KeyError:
                    # Component not found - will be caught in validation
                    loop_indices.append(0)
                    loop_offsets.append([0.0, 0.0])
                    loop_mask.append(False)

            # Pad to max_pins
            while len(loop_indices) < max_pins:
                loop_indices.append(0)
                loop_offsets.append([0.0, 0.0])
                loop_mask.append(False)

            indices.append(loop_indices)
            offsets.append(loop_offsets)
            masks.append(loop_mask)
            max_areas.append(loop.max_area)

            # Compute effective loop weight
            weight = loop.weight
            if centrality is not None and centrality.shape[0] > 0 and loop_comp_indices:
                # Boost loop weight by max centrality of involved components
                max_c = jnp.max(centrality[jnp.array(loop_comp_indices)])
                weight = weight * (max_c * n_components)

            weights.append(weight)

        return (
            jnp.array(indices, dtype=jnp.int32),
            jnp.array(offsets, dtype=jnp.float32),
            jnp.array(masks, dtype=jnp.bool_),
            jnp.array(max_areas, dtype=jnp.float32),
            jnp.array(weights, dtype=jnp.float32),
        )

    @staticmethod
    def _validate_constraints(
        netlist: Netlist,
        thermal_constraints: list[ThermalConstraint],
        loop_constraints: list[LoopConstraint],
    ) -> list[str]:
        """
        Validate that all constraint references are valid.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors = []
        valid_refs = {c.ref for c in netlist.components}

        # Validate thermal constraints
        for tc in thermal_constraints:
            if tc.component_ref not in valid_refs:
                errors.append(f"ThermalConstraint references unknown component: {tc.component_ref}")

        # Validate loop constraints
        for lc in loop_constraints:
            for comp_ref, pin_name in lc.pins:
                if comp_ref not in valid_refs:
                    errors.append(
                        f"LoopConstraint '{lc.name}' references unknown component: {comp_ref}"
                    )
                else:
                    comp = netlist.get_component(comp_ref)
                    pin = comp.get_pin(pin_name)
                    if pin is None:
                        # Warn but don't fail - will use component center
                        pass  # Could log warning here

        return errors

    def get_component_index(self, ref: str) -> int:
        """Get array index for a component by reference."""
        return self.netlist.get_component_index(ref)


class LossResult(NamedTuple):
    """
    Result from a loss function evaluation.

    Attributes:
        value: The scalar loss value (differentiable).
        breakdown: Optional dict with per-component or per-item breakdown.
    """

    value: Array  # Scalar loss value
    breakdown: dict[str, Array] | None = None


class LossFunction(ABC):
    """
    Abstract base class for loss functions.

    All loss functions must inherit from this class and implement:
    - name property: A unique identifier for the loss
    - __call__: Compute the loss given positions, rotations, and context

    Loss functions should be stateless and JAX-compatible. Any configuration
    should be passed in __init__ and stored as instance attributes.

    Example:
        >>> class MyLoss(LossFunction):
        ...     @property
        ...     def name(self) -> str:
        ...         return "my_loss"
        ...
        ...         value = jnp.sum(positions ** 2)
        ...         return LossResult(value=value)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this loss function."""
        ...

    @abstractmethod
    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
    ) -> LossResult:
        """
        Compute the loss value.

        Args:
            positions: (N, 2) array of component center positions in mm.
            rotations: (N, 4) soft one-hot rotation indicators from Gumbel-Softmax.
            context: LossContext with netlist, board, and constraints.

        Returns:
            LossResult with scalar loss value and optional breakdown.
        """
        ...

    def weight_schedule(self, epoch: int, total_epochs: int) -> float:
        """
        Get the weight multiplier for this loss at a given epoch.

        Override this method to implement curriculum learning. The default
        implementation returns 1.0 (constant weight).

        Args:
            epoch: Current training epoch (0-indexed).
            total_epochs: Total number of training epochs.

        Returns:
            Weight multiplier for this loss (typically 0.0 to 1.0).
        """
        return 1.0


def smooth_step(x: Array, edge0: float = 0.0, edge1: float = 1.0) -> Array:
    """
    Smooth step function (Hermite interpolation) for curriculum learning.

    Returns 0 for x <= edge0, 1 for x >= edge1, and smoothly interpolates
    between using 3x² - 2x³.

    Args:
        x: Input value (typically epoch / total_epochs).
        edge0: Lower edge (returns 0).
        edge1: Upper edge (returns 1).

    Returns:
        Smoothly interpolated value in [0, 1].
    """
    t = jnp.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


@dataclass
class WeightedLoss:
    """
    A loss function with its base weight, optional schedule, and normalization.

    Attributes:
        loss_fn: The loss function instance.
        weight: Base weight multiplier.
        schedule_start: Epoch fraction when this loss starts ramping up (0.0-1.0).
        schedule_end: Epoch fraction when this loss reaches full weight.
        normalize_by: Normalization mode:
            - None: No normalization (raw loss value)
            - "components": Divide by number of components
            - "pairs": Divide by number of component pairs (N*(N-1)/2)
            - "board_area": Divide by board area (mm²)
            - "nets": Divide by number of nets (for wirelength)
            - float: Divide by a custom constant
    """

    loss_fn: LossFunction
    weight: float = 1.0
    schedule_start: float = 0.0  # Start at epoch 0
    schedule_end: float = 0.0  # Full weight from epoch 0
    normalize_by: str | float | None = None

    def get_weight(self, epoch: int, total_epochs: int) -> float:
        """Get effective weight at given epoch."""
        # Apply schedule from loss function
        fn_weight = self.loss_fn.weight_schedule(epoch, total_epochs)

        # Apply curriculum schedule
        if self.schedule_end > self.schedule_start:
            progress = jnp.array(epoch / max(total_epochs, 1))
            curriculum = float(smooth_step(progress, self.schedule_start, self.schedule_end))
        else:
            curriculum = 1.0

        return self.weight * fn_weight * curriculum

    def get_normalizer(self, context: LossContext) -> float:
        """
        Get the normalization factor for this loss.

        Args:
            context: LossContext with component/board info.

        Returns:
            Normalization divisor (1.0 if no normalization).
        """
        if self.normalize_by is None:
            return 1.0

        if isinstance(self.normalize_by, (int, float)):
            return float(self.normalize_by)

        n = context.netlist.n_components

        if self.normalize_by == "components":
            return max(n, 1.0)
        elif self.normalize_by == "pairs":
            return max(n * (n - 1) / 2, 1.0)
        elif self.normalize_by == "board_area":
            return max(context.board.width * context.board.height, 1.0)
        elif self.normalize_by == "nets":
            return max(context.netlist.n_nets, 1.0)
        else:
            return 1.0  # Unknown mode, no normalization


class CompositeLoss:
    """
    Aggregates multiple weighted loss functions.

    This is the main loss function used during optimization. It combines
    multiple individual loss functions with weights and supports curriculum
    learning through weight scheduling.

    Supports optional normalization to make loss values more comparable
    across different board sizes and component counts. Use the `normalize_by`
    parameter in WeightedLoss for per-loss normalization.

    Example:
        >>> composite = CompositeLoss([
        ...     WeightedLoss(OverlapLoss(), weight=100.0, normalize_by="pairs"),
        ...     WeightedLoss(WirelengthLoss(), weight=1.0, normalize_by="nets"),
        ...     WeightedLoss(ClearanceLoss(), weight=50.0, schedule_start=0.2),
        ... ])
        >>> result = composite(positions, rotations, context, epoch=500, total_epochs=1000)
    """

    def __init__(self, losses: list[WeightedLoss]):
        """
        Initialize with list of weighted losses.

        Args:
            losses: List of WeightedLoss instances to aggregate.
        """
        self.losses = losses

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        weight_overrides: Array | None = None,
    ) -> LossResult:
        """
        Compute total loss as weighted sum of individual losses.

        Args:
            positions: (N, 2) component positions.
            rotations: (N, 4) soft one-hot rotations.
            context: LossContext with all data.
            epoch: Current epoch for weight scheduling.
            total_epochs: Total epochs for weight scheduling.
            weight_overrides: Optional (L,) array of weights to use instead of base weights.

        Returns:
            LossResult with total value and breakdown by loss name.
        """
        total = jnp.array(0.0)
        breakdown: dict[str, Array] = {}

        for i, wloss in enumerate(self.losses):
            if weight_overrides is not None:
                weight = weight_overrides[i]
            else:
                weight = wloss.get_weight(epoch, total_epochs)

            # Note: We always compute the loss even if weight is low.
            result = wloss.loss_fn(positions, rotations, context, epoch, total_epochs)

            # Apply normalization
            normalizer = wloss.get_normalizer(context)
            normalized_value = result.value / normalizer

            weighted_value = weight * normalized_value
            total = total + weighted_value

            # Store both raw and normalized values in breakdown
            breakdown[wloss.loss_fn.name] = result.value
            breakdown[f"{wloss.loss_fn.name}_normalized"] = normalized_value
            breakdown[f"{wloss.loss_fn.name}_weighted"] = weighted_value

            # Merge sub-breakdowns (e.g., per-component metrics)
            if result.breakdown:
                for sub_key, sub_val in result.breakdown.items():
                    breakdown[f"{wloss.loss_fn.name}_{sub_key}"] = sub_val

        return LossResult(value=total, breakdown=breakdown)

    def get_loss_fn(self, name: str) -> LossFunction | None:
        """Get a loss function by name."""
        for wloss in self.losses:
            if wloss.loss_fn.name == name:
                return wloss.loss_fn
        return None

    @property
    def loss_names(self) -> list[str]:
        """Get names of all loss functions."""
        return [wloss.loss_fn.name for wloss in self.losses]


def create_jit_loss_fn(composite: CompositeLoss, context: LossContext):
    """
    Create a JIT-compiled loss function for optimization.

    This returns a function that takes only (positions, rotations, key)
    and is suitable for use with JAX optimizers.

    Args:
        composite: The CompositeLoss to compile.
        context: The LossContext (captured in closure).

    Returns:
        JIT-compiled function: (positions, rotations, epoch, total_epochs, weight_overrides) -> scalar
    """

    @jax.jit
    def loss_fn(
        positions: Array,
        rotations: Array,
        epoch: int,
        total_epochs: int,
        weight_overrides: Array | None = None,
    ) -> Array:
        result = composite(positions, rotations, context, epoch, total_epochs, weight_overrides)
        return result.value

    return loss_fn


def create_value_and_grad_fn(
    composite: CompositeLoss,
    context: LossContext,
    apply_fixed_mask: bool = True,
):
    """
    Create a JIT-compiled function that returns both loss and gradients.

    This is the main function used in the optimization loop.

    Fixed components (connectors, mounting holes, etc.) will have their
    gradients zeroed out if apply_fixed_mask is True.

    Args:
        composite: The CompositeLoss to compile.
        context: The LossContext (captured in closure).
        apply_fixed_mask: If True, zero gradients for fixed components.

    Returns:
        JIT-compiled function: (positions, rotations, epoch, total_epochs, weight_overrides) -> (loss, (grad_pos, grad_rot))
    """
    fixed_mask = context.fixed_mask  # (N,) boolean array

    def loss_fn(
        positions: Array,
        rotations: Array,
        epoch: int,
        total_epochs: int,
        weight_overrides: Array | None = None,
    ) -> Array:
        result = composite(positions, rotations, context, epoch, total_epochs, weight_overrides)
        return result.value

    def value_and_grad_fn(
        positions: Array,
        rotations: Array,
        epoch: int,
        total_epochs: int,
        weight_overrides: Array | None = None,
    ) -> tuple[Array, tuple[Array, Array]]:
        # Compute gradients w.r.t. both positions and rotations
        (loss, (grad_pos, grad_rot)) = jax.value_and_grad(loss_fn, argnums=(0, 1))(
            positions, rotations, epoch, total_epochs, weight_overrides
        )

        # Ensure types for mypy
        loss = jax.lax.stop_gradient(loss)  # Just to ensure it's an Array

        # Zero out gradients for fixed components
        if apply_fixed_mask:
            # fixed_mask is (N,), expand to (N, 2) for positions and (N, 4) for rotations
            grad_pos = jnp.where(fixed_mask[:, None], 0.0, grad_pos)
            grad_rot = jnp.where(fixed_mask[:, None], 0.0, grad_rot)

        return loss, (cast(Array, grad_pos), cast(Array, grad_rot))

    return jax.jit(value_and_grad_fn)


def create_value_and_grad_fn_with_breakdown(
    composite: CompositeLoss,
    context: LossContext,
    apply_fixed_mask: bool = True,
):
    """
    Create a JIT-compiled function that returns loss, breakdown, and gradients.

    This version returns the loss breakdown alongside the gradients, avoiding
    the need to recompute the loss for logging purposes.

    Args:
        composite: The CompositeLoss to compile.
        context: The LossContext (captured in closure).
        apply_fixed_mask: If True, zero gradients for fixed components.

    Returns:
        JIT-compiled function: (positions, rotations, epoch, total_epochs, weight_overrides) ->
            ((loss, breakdown_dict), (grad_pos, grad_rot))

        The breakdown_dict maps loss term names to their values.
    """
    fixed_mask = context.fixed_mask  # (N,) boolean array

    def loss_fn_with_aux(
        positions: Array,
        rotations: Array,
        epoch: int,
        total_epochs: int,
        weight_overrides: Array | None = None,
    ) -> tuple[Array, dict[str, Array]]:
        result = composite(positions, rotations, context, epoch, total_epochs, weight_overrides)
        # Convert breakdown to dict of arrays for JIT compatibility
        breakdown = result.breakdown or {}
        return result.value, breakdown

    def value_and_grad_fn(
        positions: Array,
        rotations: Array,
        epoch: int,
        total_epochs: int,
        weight_overrides: Array | None = None,
    ) -> tuple[tuple[Array, dict[str, Array]], tuple[Array, Array]]:
        # Compute gradients w.r.t. both positions and rotations
        # has_aux=True means the function returns (loss, aux) and we differentiate loss only
        ((loss, breakdown), (grad_pos, grad_rot)) = jax.value_and_grad(
            loss_fn_with_aux, argnums=(0, 1), has_aux=True
        )(positions, rotations, epoch, total_epochs, weight_overrides)

        # Zero out gradients for fixed components
        if apply_fixed_mask:
            grad_pos = jnp.where(fixed_mask[:, None], 0.0, grad_pos)
            grad_rot = jnp.where(fixed_mask[:, None], 0.0, grad_rot)

        return (loss, breakdown), (cast(Array, grad_pos), cast(Array, grad_rot))

    return jax.jit(value_and_grad_fn)


def apply_fixed_mask_to_gradients(
    grad_pos: Array,
    grad_rot: Array,
    fixed_mask: Array,
) -> tuple[Array, Array]:
    """
    Zero out gradients for fixed components.

    This utility function can be used when manually computing gradients
    outside of create_value_and_grad_fn.

    Args:
        grad_pos: (N, 2) position gradients.
        grad_rot: (N, 4) rotation gradients.
        fixed_mask: (N,) boolean mask where True = fixed component.

    Returns:
        Tuple of masked (grad_pos, grad_rot) arrays.
    """
    grad_pos = jnp.where(fixed_mask[:, None], 0.0, grad_pos)
    grad_rot = jnp.where(fixed_mask[:, None], 0.0, grad_rot)
    return grad_pos, grad_rot
