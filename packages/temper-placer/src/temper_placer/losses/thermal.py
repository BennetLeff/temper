"""
Thermal placement loss functions.

This module provides comprehensive thermal placement constraints:

1. ThermalLoss - Edge placement for heatsink-mounted components (Q1, Q2)
2. ThermalSpreadLoss - Prevent high-power components from clustering (heat spreading)
3. HeatSensitiveDistanceLoss - Keep sensors/MCU away from heat sources
4. EdgePreferenceLoss - Encourage thermal pad components toward board edges

For the Temper induction cooker:
- Q1, Q2 (IGBTs) must be within 5mm of TOP edge for heatsink mounting
- High-power components (IGBTs, diodes) should be spread to avoid thermal hotspots
- Temperature sensors (MAX31865) must be >20mm from IGBTs for accurate readings
- MCU should be >15mm from power stage
"""

from __future__ import annotations

from dataclasses import dataclass

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import (
    LossContext,
    LossFunction,
    LossResult,
    ThermalConstraint,
)


def compute_edge_distance(
    position: Array,
    board_bounds: Array,
    edge: str,
) -> Array:
    """
    Compute distance from a position to a board edge.

    Args:
        position: (2,) position [x, y] in mm.
        board_bounds: [x_min, y_min, x_max, y_max] board bounds.
        edge: Edge name ("TOP", "BOTTOM", "LEFT", "RIGHT").

    Returns:
        Scalar distance to edge in mm.
    """
    x, y = position[0], position[1]
    x_min, y_min, x_max, y_max = board_bounds

    if edge == "TOP":
        return y_max - y
    elif edge == "BOTTOM":
        return y - y_min
    elif edge == "LEFT":
        return x - x_min
    elif edge == "RIGHT":
        return x_max - x
    else:
        # Unknown edge, return large distance
        return jnp.array(1000.0)


def compute_thermal_penalty(
    positions: Array,
    context: LossContext,
    margin: float = 1.0,
) -> Array:
    """
    Compute thermal placement penalty.

    Penalizes components that are farther from their required board edge
    than the maximum allowed distance.

    Uses softplus for smooth gradients near the constraint boundary:
    - When distance < max_distance: penalty is small (exponentially decaying)
    - When distance > max_distance: penalty grows approximately quadratically
    - The margin parameter controls the transition width

    Args:
        positions: (N, 2) component center positions.
        context: LossContext with thermal_constraints and board.
        margin: Soft margin width (mm). Larger values give smoother gradients
                but less sharp constraint enforcement. Default 1.0mm.

    Returns:
        Total thermal penalty (scalar).
    """
    if not context.thermal_constraints:
        return jnp.array(0.0)

    board_bounds = context.board.get_relative_bounds_array()
    total_penalty = jnp.array(0.0)

    for tc in context.thermal_constraints:
        comp_idx = context.get_component_index(tc.component_ref)
        position = positions[comp_idx]

        # Distance to required edge
        distance = compute_edge_distance(position, board_bounds, tc.edge)

        # Soft penalty using softplus for smooth gradients
        # softplus(x/margin) ≈ 0 when x << 0, ≈ x/margin when x >> 0
        # This gives smooth transition at the boundary
        excess = distance - tc.max_distance
        soft_excess = margin * jax.nn.softplus(excess / margin)

        # Quadratic penalty for violation, scaled by weight
        penalty = tc.weight * soft_excess**2

        total_penalty = total_penalty + penalty

    return total_penalty


@dataclass
class ThermalLoss(LossFunction):
    """
    Loss function penalizing components far from required board edges.

    For heat-generating components like IGBTs, this loss ensures they are
    placed near board edges where heatsinks can be mounted.

    Uses softplus for smooth gradients near the constraint boundary:
    penalty = weight * softplus(excess/margin)²

    where excess = distance - max_distance.

    Attributes:
        margin: Soft margin width for penalty transition (mm).
                Larger values give smoother gradients but less sharp
                constraint enforcement. Default 1.0mm is good for PCB scale.
    """

    margin: float = 1.0

    @property
    def name(self) -> str:
        return "thermal"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
    ) -> LossResult:
        """
        Compute thermal placement loss.

        Args:
            positions: (N, 2) component positions.
            rotations: (N, 4) soft one-hot rotations (unused for thermal).
            context: LossContext with thermal_constraints.

        Returns:
            LossResult with total thermal penalty.
        """
        penalty = compute_thermal_penalty(positions, context, self.margin)
        return LossResult(value=penalty)

    def trace(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
    ) -> tuple[Array, Trace]:
        """Generate a natural language trace for thermal constraints."""
        from temper_placer.explainability.trace import Trace

        board_bounds = context.board.get_relative_bounds_array()
        total_penalty = jnp.array(0.0)
        trace = Trace.empty()

        for tc in context.thermal_constraints:
            comp_idx = context.get_component_index(tc.component_ref)
            position = positions[comp_idx]

            # Distance to required edge
            distance = compute_edge_distance(position, board_bounds, tc.edge)

            # Penalty calculation (simplified for trace significant check)
            excess = distance - tc.max_distance
            penalty = float(tc.weight * jnp.maximum(0, excess)**2)

            total_penalty = total_penalty + penalty
            if penalty > 1e-3:
                trace = trace.add(
                    tc.component_ref,
                    penalty,
                    tc.because or f"Must be within {tc.max_distance}mm of {tc.edge} edge for cooling"
                )

        return total_penalty, trace


def create_temper_thermal_constraints() -> list[ThermalConstraint]:
    """
    Create default thermal constraints for Temper board.

    The IGBTs (Q1, Q2) must be within 5mm of the TOP edge for heatsink mounting.

    Returns:
        List of ThermalConstraint for Temper board.
    """
    return [
        ThermalConstraint(
            component_ref="Q1",
            edge="TOP",
            max_distance=5.0,
            weight=10.0,  # High weight - critical for thermal management
        ),
        ThermalConstraint(
            component_ref="Q2",
            edge="TOP",
            max_distance=5.0,
            weight=10.0,
        ),
    ]


# ============================================================================
# Thermal Spreading Loss
# ============================================================================


@dataclass(frozen=True)
class ThermalComponentConfig:
    """Configuration for a thermal component.

    Attributes:
        component_ref: Component reference (e.g., "Q1").
        power_dissipation_w: Power dissipation in Watts (for weighting).
    """

    component_ref: str
    power_dissipation_w: float = 1.0


@dataclass
class ThermalSpreadLoss(LossFunction):
    """
    Penalize high-power components being too close together.

    This loss prevents thermal hot spots by spreading heat-generating components.
    The penalty is weighted by the product of power dissipations - two 50W
    components close together is worse than a 50W and 5W component.

    Uses softplus for smooth gradients near the constraint boundary.

    Attributes:
        high_power_indices: Array of component indices for high-power components.
        min_separation_mm: Minimum separation between high-power components.
        power_weights: Power dissipation weights (higher = more important to separate).
        margin: Soft margin for smooth transition (mm).
    """

    high_power_indices: Array
    min_separation_mm: float = 15.0
    power_weights: Array | None = None
    margin: float = 2.0

    @property
    def name(self) -> str:
        return "thermal_spread"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
    ) -> LossResult:
        """
        Compute thermal spreading penalty.

        Args:
            positions: (N, 2) component positions.
            rotations: (N, 4) rotation indicators (unused).
            context: LossContext.

        Returns:
            LossResult with total spreading penalty.
        """
        n_hp = self.high_power_indices.shape[0]
        if n_hp < 2:
            return LossResult(value=jnp.array(0.0))

        # Get positions of high-power components
        hp_positions = positions[self.high_power_indices]  # (K, 2)

        # Default weights if not provided
        weights = self.power_weights
        if weights is None:
            weights = jnp.ones(n_hp, dtype=jnp.float32)

        # Compute all pairwise distances
        # hp_positions[:, None, :] is (K, 1, 2)
        # hp_positions[None, :, :] is (1, K, 2)
        diff = hp_positions[:, None, :] - hp_positions[None, :, :]  # (K, K, 2)
        distances = jnp.sqrt(jnp.sum(diff**2, axis=-1) + 1e-12)  # (K, K)

        # Compute weight matrix (product of power dissipations)
        weight_matrix = weights[:, None] * weights[None, :]  # (K, K)

        # Only consider upper triangle (avoid double-counting)
        # Create upper triangle mask (excluding diagonal)
        upper_mask = jnp.triu(jnp.ones((n_hp, n_hp), dtype=jnp.bool_), k=1)

        # Compute penalty for each pair using softplus for smooth gradients
        excess = self.min_separation_mm - distances
        soft_excess = self.margin * jax.nn.softplus(excess / self.margin)
        penalties = weight_matrix * soft_excess**2

        # Sum only upper triangle
        total_penalty = jnp.sum(jnp.where(upper_mask, penalties, 0.0))

        return LossResult(
            value=total_penalty,
            breakdown={
                "thermal_spread_min_distance": jnp.min(jnp.where(upper_mask, distances, jnp.inf)),
                "thermal_spread_violations": jnp.sum(
                    jnp.where(upper_mask & (distances < self.min_separation_mm), 1, 0)
                ),
            },
        )


# ============================================================================
# Heat Sensitive Distance Loss
# ============================================================================


@dataclass
class HeatSensitiveDistanceLoss(LossFunction):
    """
    Penalize heat-sensitive components being too close to heat sources.

    This loss protects temperature-sensitive components (MCU, sensors) from
    thermal damage or drift by enforcing minimum distance from heat sources.

    Uses softplus for smooth gradients.

    Attributes:
        sensitive_indices: Array of component indices for heat-sensitive components.
        heat_source_indices: Array of component indices for heat sources.
        min_distance_mm: Minimum distance from heat sources.
        heat_source_powers: Optional power dissipation weights for heat sources.
        margin: Soft margin for smooth transition (mm).
    """

    sensitive_indices: Array
    heat_source_indices: Array
    min_distance_mm: float = 20.0
    heat_source_powers: Array | None = None
    margin: float = 2.0

    @property
    def name(self) -> str:
        return "heat_sensitive_distance"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
    ) -> LossResult:
        """
        Compute heat-sensitive distance penalty.

        Args:
            positions: (N, 2) component positions.
            rotations: (N, 4) rotation indicators (unused).
            context: LossContext.

        Returns:
            LossResult with total distance penalty.
        """
        n_sensitive = self.sensitive_indices.shape[0]
        n_sources = self.heat_source_indices.shape[0]

        if n_sensitive == 0 or n_sources == 0:
            return LossResult(value=jnp.array(0.0))

        # Get positions
        sens_positions = positions[self.sensitive_indices]  # (S, 2)
        source_positions = positions[self.heat_source_indices]  # (H, 2)

        # Default power weights
        powers = self.heat_source_powers
        if powers is None:
            powers = jnp.ones(n_sources, dtype=jnp.float32)

        # Compute all pairwise distances between sensitive and sources
        # sens_positions[:, None, :] is (S, 1, 2)
        # source_positions[None, :, :] is (1, H, 2)
        diff = sens_positions[:, None, :] - source_positions[None, :, :]  # (S, H, 2)
        distances = jnp.sqrt(jnp.sum(diff**2, axis=-1) + 1e-12)  # (S, H)

        # Compute penalty for each pair using softplus
        excess = self.min_distance_mm - distances
        soft_excess = self.margin * jax.nn.softplus(excess / self.margin)

        # Weight by heat source power
        penalties = powers[None, :] * soft_excess**2  # (S, H)

        # Sum all penalties
        total_penalty = jnp.sum(penalties)

        # Track minimum distance for diagnostics
        min_distance = jnp.min(distances)

        return LossResult(
            value=total_penalty,
            breakdown={
                "heat_sensitive_min_distance": min_distance,
                "heat_sensitive_violations": jnp.sum(
                    jnp.where(distances < self.min_distance_mm, 1, 0)
                ),
            },
        )


# ============================================================================
# Edge Preference Loss
# ============================================================================


@dataclass
class EdgePreferenceLoss(LossFunction):
    """
    Encourage thermal pad components toward board edges.

    Components with thermal pads (IGBTs, power MOSFETs, regulators) dissipate
    heat better when placed near board edges where:
    - Heatsinks can be attached
    - Airflow is better
    - Less heat transfer to other components

    Penalizes components that are farther from the nearest edge than the
    preferred margin.

    Attributes:
        thermal_pad_indices: Array of component indices with thermal pads.
        board_width: Board width in mm.
        board_height: Board height in mm.
        preferred_margin_mm: Preferred distance from edge (default 10mm).
        weight: Penalty weight.
    """

    thermal_pad_indices: Array
    board_width: float
    board_height: float
    preferred_margin_mm: float = 10.0
    weight: float = 1.0

    @property
    def name(self) -> str:
        return "edge_preference"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
    ) -> LossResult:
        """
        Compute edge preference penalty.

        Args:
            positions: (N, 2) component positions.
            rotations: (N, 4) rotation indicators (unused).
            context: LossContext.

        Returns:
            LossResult with total edge preference penalty.
        """
        if self.thermal_pad_indices.shape[0] == 0:
            return LossResult(value=jnp.array(0.0))

        # Get positions of thermal pad components
        tp_positions = positions[self.thermal_pad_indices]  # (T, 2)

        # Compute distance to nearest edge for each component
        # Distance to left edge
        dist_left = tp_positions[:, 0]
        # Distance to right edge
        dist_right = self.board_width - tp_positions[:, 0]
        # Distance to bottom edge
        dist_bottom = tp_positions[:, 1]
        # Distance to top edge
        dist_top = self.board_height - tp_positions[:, 1]

        # Minimum distance to any edge
        dist_to_edge = jnp.minimum(
            jnp.minimum(dist_left, dist_right),
            jnp.minimum(dist_bottom, dist_top),
        )

        # Penalize if too far from edge
        excess = jax.nn.relu(dist_to_edge - self.preferred_margin_mm)
        penalties = self.weight * excess**2

        total_penalty = jnp.sum(penalties)

        return LossResult(
            value=total_penalty,
            breakdown={
                "edge_preference_avg_distance": jnp.mean(dist_to_edge),
                "edge_preference_max_distance": jnp.max(dist_to_edge),
            },
        )


# ============================================================================
# Factory Functions
# ============================================================================


def create_thermal_spread_loss(
    component_configs: list[ThermalComponentConfig],
    netlist,
    min_separation_mm: float = 15.0,
) -> ThermalSpreadLoss | None:
    """
    Create a ThermalSpreadLoss from component configurations.

    Args:
        component_configs: List of ThermalComponentConfig for high-power components.
        netlist: Netlist for resolving component refs to indices.
        min_separation_mm: Minimum separation between high-power components.

    Returns:
        ThermalSpreadLoss or None if no valid components found.
    """
    indices = []
    powers = []

    for config in component_configs:
        try:
            idx = netlist.get_component_index(config.component_ref)
            indices.append(idx)
            powers.append(config.power_dissipation_w)
        except KeyError:
            # Component not in netlist, skip
            pass

    if len(indices) < 2:
        return None

    return ThermalSpreadLoss(
        high_power_indices=jnp.array(indices, dtype=jnp.int32),
        min_separation_mm=min_separation_mm,
        power_weights=jnp.array(powers, dtype=jnp.float32),
    )


def create_heat_sensitive_distance_loss(
    sensitive_refs: list[str],
    heat_source_configs: list[ThermalComponentConfig],
    netlist,
    min_distance_mm: float = 20.0,
) -> HeatSensitiveDistanceLoss | None:
    """
    Create a HeatSensitiveDistanceLoss from component references.

    Args:
        sensitive_refs: Component refs for heat-sensitive components.
        heat_source_configs: ThermalComponentConfig for heat sources.
        netlist: Netlist for resolving refs to indices.
        min_distance_mm: Minimum distance from heat sources.

    Returns:
        HeatSensitiveDistanceLoss or None if no valid components found.
    """
    sensitive_indices = []
    source_indices = []
    source_powers = []

    for ref in sensitive_refs:
        try:
            idx = netlist.get_component_index(ref)
            sensitive_indices.append(idx)
        except KeyError:
            pass

    for config in heat_source_configs:
        try:
            idx = netlist.get_component_index(config.component_ref)
            source_indices.append(idx)
            source_powers.append(config.power_dissipation_w)
        except KeyError:
            pass

    if len(sensitive_indices) == 0 or len(source_indices) == 0:
        return None

    return HeatSensitiveDistanceLoss(
        sensitive_indices=jnp.array(sensitive_indices, dtype=jnp.int32),
        heat_source_indices=jnp.array(source_indices, dtype=jnp.int32),
        min_distance_mm=min_distance_mm,
        heat_source_powers=jnp.array(source_powers, dtype=jnp.float32),
    )


def create_edge_preference_loss(
    thermal_pad_refs: list[str],
    netlist,
    board_width: float,
    board_height: float,
    preferred_margin_mm: float = 10.0,
) -> EdgePreferenceLoss | None:
    """
    Create an EdgePreferenceLoss from component references.

    Args:
        thermal_pad_refs: Component refs with thermal pads.
        netlist: Netlist for resolving refs to indices.
        board_width: Board width in mm.
        board_height: Board height in mm.
        preferred_margin_mm: Preferred distance from edge.

    Returns:
        EdgePreferenceLoss or None if no valid components found.
    """
    indices = []

    for ref in thermal_pad_refs:
        try:
            idx = netlist.get_component_index(ref)
            indices.append(idx)
        except KeyError:
            pass

    if len(indices) == 0:
        return None

    return EdgePreferenceLoss(
        thermal_pad_indices=jnp.array(indices, dtype=jnp.int32),
        board_width=board_width,
        board_height=board_height,
        preferred_margin_mm=preferred_margin_mm,
    )


# ============================================================================
# Temper-Specific Factory
# ============================================================================


def create_temper_thermal_losses(netlist, board_width: float = 100.0, board_height: float = 150.0):
    """
    Create all thermal losses for the Temper induction cooker.

    This creates:
    1. ThermalSpreadLoss - Spread IGBTs, diodes, and current sense resistors
    2. HeatSensitiveDistanceLoss - Keep MCU and temp sensor away from IGBTs
    3. EdgePreferenceLoss - IGBTs near board edges

    Args:
        netlist: Netlist for the Temper board.
        board_width: Board width in mm.
        board_height: Board height in mm.

    Returns:
        Tuple of (ThermalSpreadLoss, HeatSensitiveDistanceLoss, EdgePreferenceLoss).
        Any may be None if components not found.
    """
    # High-power components with power dissipation estimates
    high_power_configs = [
        ThermalComponentConfig("Q1", 50.0),  # IGBT - major heat
        ThermalComponentConfig("Q2", 50.0),  # IGBT - major heat
        ThermalComponentConfig("D1", 10.0),  # Rectifier diode
        ThermalComponentConfig("D2", 10.0),  # Rectifier diode
        ThermalComponentConfig("R_SENSE_HIGH", 5.0),  # Current sense
        ThermalComponentConfig("R_SENSE_LOW", 5.0),  # Current sense
        ThermalComponentConfig("U_BUCK", 3.0),  # Buck converter
    ]

    spread_loss = create_thermal_spread_loss(
        high_power_configs,
        netlist,
        min_separation_mm=15.0,
    )

    # Heat-sensitive components
    sensitive_refs = [
        "U_MCU",  # MCU - accurate timing
        "U_TEMP_SENSE",  # Temperature sensor - accuracy critical
        "MAX31865",  # Alternative temp sensor name
        "Y1",  # Crystal - frequency stability
    ]

    # Heat sources for sensitive distance (IGBTs are the main concern)
    heat_source_configs = [
        ThermalComponentConfig("Q1", 50.0),
        ThermalComponentConfig("Q2", 50.0),
    ]

    distance_loss = create_heat_sensitive_distance_loss(
        sensitive_refs,
        heat_source_configs,
        netlist,
        min_distance_mm=20.0,
    )

    # Thermal pad components for edge preference
    thermal_pad_refs = ["Q1", "Q2", "U_BUCK"]

    edge_loss = create_edge_preference_loss(
        thermal_pad_refs,
        netlist,
        board_width,
        board_height,
        preferred_margin_mm=10.0,
    )

    return spread_loss, distance_loss, edge_loss
