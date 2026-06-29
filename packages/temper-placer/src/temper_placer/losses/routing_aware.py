"""
Routing Channel Loss Functions.

This module provides losses that penalize placements creating narrow routing corridors.
These losses implement the principle: "Routing failures are placement failures."

Key Functions:
- RoutingChannelLoss: Penalizes narrow corridors between components
- MCUClusteringLoss: Keeps MCU peripherals within clustering radius
- BusAlignmentLoss: Encourages collinear placement of bus-connected components
"""

from __future__ import annotations

from typing import Any

import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import (
    LossContext,
    LossFunction,
    LossResult,
)


def _estimate_crossing_nets(
    comp_i: int,
    comp_j: int,
    netlist: Any,
) -> int:
    """Estimate how many nets must cross between two components.

    A net "crosses" if it connects to components on opposite sides
    of the line between comp_i and comp_j.

    For simplicity, we count nets that connect to both comp_i's neighbors
    and comp_j's neighbors but not to comp_i or comp_j directly.
    """
    # Simple heuristic: count shared nets between neighbors
    # Full implementation would do geometric analysis
    return 2  # Placeholder - assume 2 nets need to cross


def compute_routing_channel_penalty(
    positions: Array,
    bounds: Array,
    min_channel_width: float = 5.0,
    _net_crossing_estimator: Any = None,
) -> Array:
    """Compute penalty for narrow routing corridors.

    For each pair of adjacent components, computes the "channel width" -
    the gap between their bounding boxes. If this is below min_channel_width
    and nets must cross through, applies a penalty.

    Args:
        positions: (N, 2) component center positions
        bounds: (N, 4) component bounds [width, height, offset_x, offset_y]
        min_channel_width: Minimum acceptable corridor width in mm
        _net_crossing_estimator: Optional callable(i, j) -> int for net count

    Returns:
        Scalar penalty value
    """
    n = positions.shape[0]
    total_penalty = 0.0

    # Extract half-widths and half-heights
    half_widths = bounds[:, 0] / 2
    half_heights = bounds[:, 1] / 2

    # For each pair of components
    for i in range(n):
        for j in range(i + 1, n):
            # Compute axis-aligned gap
            dx = jnp.abs(positions[i, 0] - positions[j, 0])
            dy = jnp.abs(positions[i, 1] - positions[j, 1])

            # Gap in X direction
            gap_x = dx - half_widths[i] - half_widths[j]
            # Gap in Y direction
            gap_y = dy - half_heights[i] - half_heights[j]

            # If overlapping in one axis, the other axis is the corridor
            # If gap_y < 0 (overlapping in Y), then X-gap is the corridor width
            # If gap_x < 0 (overlapping in X), then Y-gap is the corridor width

            # Corridor exists if one gap is negative (overlap) and other is positive
            x_corridor = (gap_y < 0) & (gap_x > 0)
            y_corridor = (gap_x < 0) & (gap_y > 0)

            corridor_width = jnp.where(
                x_corridor, gap_x,
                jnp.where(y_corridor, gap_y, min_channel_width + 1)  # No penalty if no corridor
            )

            # Penalty when corridor is too narrow
            shortfall = min_channel_width - corridor_width
            penalty = jnp.maximum(0.0, shortfall) ** 2

            # Scale by estimated net crossings (more nets = worse)
            # For now use constant estimate
            net_factor = 2.0  # Assume 2 nets typically cross

            total_penalty = total_penalty + penalty * net_factor

    return total_penalty


class RoutingChannelLoss(LossFunction):
    """Loss function penalizing narrow routing corridors.

    When components are placed close together with a narrow gap,
    routing multiple nets through that gap becomes impossible.
    This loss encourages wider corridors where nets need to cross.

    Attributes:
        weight: Loss weight multiplier
        min_channel_width: Minimum corridor width in mm (default 5.0)

    Example:
        >>> loss = RoutingChannelLoss(weight=10.0, min_channel_width=5.0)
        >>> result = loss(positions, rotations, context)
    """

    def __init__(
        self,
        weight: float = 10.0,
        min_channel_width: float = 5.0,
    ):
        self.weight = weight
        self.min_channel_width = min_channel_width

    @property
    def name(self) -> str:
        return "routing_channel"

    def __call__(
        self,
        positions: Array,
        _rotations: Array,
        context: LossContext,
        _epoch: int = 0,
        _total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
        **_kwargs: Any,
    ) -> LossResult:
        """Compute routing channel penalty.

        Args:
            positions: (N, 2) component positions
            rotations: (N, 4) soft one-hot rotations (unused)
            context: LossContext with component bounds

        Returns:
            LossResult with corridor width penalty
        """
        penalty = compute_routing_channel_penalty(
            positions,
            context.bounds,
            self.min_channel_width,
        )

        return LossResult(
            value=self.weight * penalty,
            breakdown={"routing_channel": self.weight * penalty},
        )


class MCUClusteringLoss(LossFunction):
    """Loss function keeping MCU peripherals within clustering radius.

    MCU peripherals (SPI slaves, I2C devices, ADC inputs) should be placed
    close to the MCU to minimize trace length and routing complexity.

    Attributes:
        weight: Loss weight multiplier
        mcu_index: Index of MCU component in positions array
        peripheral_indices: Indices of peripheral components
        max_distance: Maximum allowed distance from MCU (default 15mm)

    Example:
        >>> loss = MCUClusteringLoss(
        ...     weight=5.0,
        ...     mcu_index=0,
        ...     peripheral_indices=[1, 2, 3],
        ...     max_distance=15.0
        ... )
    """

    def __init__(
        self,
        weight: float = 5.0,
        mcu_index: int = 0,
        peripheral_indices: list[int] | None = None,
        max_distance: float = 15.0,
    ):
        self.weight = weight
        self.mcu_index = mcu_index
        self.peripheral_indices = peripheral_indices or []
        self.max_distance = max_distance

    @property
    def name(self) -> str:
        return "mcu_clustering"

    def __call__(
        self,
        positions: Array,
        _rotations: Array,
        _context: LossContext,
        _epoch: int = 0,
        _total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
        **_kwargs: Any,
    ) -> LossResult:
        """Penalizes peripherals that are too far from the MCU.

        Args:
            positions: (N, 2) component positions

        Returns:
            LossResult with clustering penalty
        """
        mcu_pos = positions[self.mcu_index]
        total_penalty = 0.0

        for idx in self.peripheral_indices:
            dist = jnp.sqrt(
                (positions[idx, 0] - mcu_pos[0]) ** 2 +
                (positions[idx, 1] - mcu_pos[1]) ** 2
            )
            excess = jnp.maximum(0.0, dist - self.max_distance)
            total_penalty = total_penalty + excess ** 2

        return LossResult(
            value=self.weight * total_penalty,
            breakdown={},  # Can't materialize during tracing
        )

    @classmethod
    def from_netlist(
        cls,
        netlist: Any,
        mcu_ref: str = "U_MCU",
        weight: float = 5.0,
        max_distance: float = 15.0,
    ) -> "MCUClusteringLoss":
        """Create MCU clustering loss from netlist.

        Automatically identifies MCU and its direct peripherals
        (components sharing nets with MCU).

        Args:
            netlist: Netlist object with components and nets
            mcu_ref: Reference designator of MCU (default "U_MCU")
            weight: Loss weight
            max_distance: Maximum peripheral distance

        Returns:
            Configured MCUClusteringLoss instance
        """
        # Find MCU index
        mcu_index = None
        for i, comp in enumerate(netlist.components):
            if comp.ref == mcu_ref:
                mcu_index = i
                break

        if mcu_index is None:
            # Fallback: find component with highest fanout
            max_nets = 0
            for i, comp in enumerate(netlist.components):
                comp_nets = sum(1 for net in netlist.nets
                               if any(pin[0] == comp.ref for pin in net.pins))
                if comp_nets > max_nets:
                    max_nets = comp_nets
                    mcu_index = i

        # Find peripherals: components sharing ≥1 net with MCU
        mcu_comp = netlist.components[mcu_index]
        mcu_nets = {net.name for net in netlist.nets
                   if any(pin[0] == mcu_comp.ref for pin in net.pins)}

        peripheral_indices = []
        for i, comp in enumerate(netlist.components):
            if i == mcu_index:
                continue
            comp_nets = {net.name for net in netlist.nets
                        if any(pin[0] == comp.ref for pin in net.pins)}
            shared = mcu_nets & comp_nets
            # Exclude power nets
            shared = {n for n in shared if not any(
                p in n for p in ['GND', 'VCC', 'VDD', '+3V3', '+5V', '+15V']
            )}
            if len(shared) >= 1:
                peripheral_indices.append(i)

        return cls(
            weight=weight,
            mcu_index=mcu_index,
            peripheral_indices=peripheral_indices,
            max_distance=max_distance,
        )


class BusAlignmentLoss(LossFunction):
    """Loss function encouraging collinear placement of bus-connected components.

    SPI, I2C, and parallel buses consist of multiple parallel signals.
    Components on the same bus should be aligned (horizontally or vertically)
    to allow parallel trace routing.

    Attributes:
        weight: Loss weight multiplier
        bus_groups: List of component index lists, one per bus

    Example:
        >>> # SPI bus connects components 0, 3, 7
        >>> loss = BusAlignmentLoss(weight=5.0, bus_groups=[[0, 3, 7]])
    """

    def __init__(
        self,
        weight: float = 5.0,
        bus_groups: list[list[int]] | None = None,
    ):
        self.weight = weight
        self.bus_groups = bus_groups or []

    @property
    def name(self) -> str:
        return "bus_alignment"

    def __call__(
        self,
        positions: Array,
        _rotations: Array,
        _context: LossContext,
        _epoch: int = 0,
        _total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
        **_kwargs: Any,
    ) -> LossResult:
        """For each bus group, computes deviation from best-fit line
        through component centers.

        Args:
            positions: (N, 2) component positions

        Returns:
            LossResult with alignment penalty
        """
        total_penalty = 0.0

        for group in self.bus_groups:
            if len(group) < 2:
                continue

            # Get positions for this group
            group_pos = positions[jnp.array(group)]

            # Compute best-fit line (PCA-style)
            centroid = jnp.mean(group_pos, axis=0)
            centered = group_pos - centroid

            # Covariance matrix
            cov = jnp.dot(centered.T, centered) / len(group)

            # Eigendecomposition to find principal axis
            # For 2D, we can compute analytically
            a, b, c = cov[0, 0], cov[0, 1], cov[1, 1]
            trace = a + c
            det = a * c - b * b
            lambda1 = trace / 2 + jnp.sqrt((trace / 2) ** 2 - det + 1e-6)
            lambda2 = trace / 2 - jnp.sqrt((trace / 2) ** 2 - det + 1e-6)

            # Penalty is the smaller eigenvalue (variance perpendicular to line)
            # This is the sum of squared distances from best-fit line
            penalty = jnp.minimum(lambda1, lambda2) * len(group)
            total_penalty = total_penalty + penalty

        return LossResult(
            value=self.weight * total_penalty,
            breakdown={},  # Can't materialize during tracing
        )

    @classmethod
    def from_netlist(
        cls,
        netlist: Any,
        bus_patterns: list[str] | None = None,
        weight: float = 5.0,
    ) -> "BusAlignmentLoss":
        """Create bus alignment loss from netlist.

        Automatically identifies buses by net name patterns
        (e.g., SPI_*, I2C_*, USB_*).

        Args:
            netlist: Netlist object with components and nets
            bus_patterns: Net name prefixes to identify buses
            weight: Loss weight

        Returns:
            Configured BusAlignmentLoss instance
        """
        if bus_patterns is None:
            bus_patterns = ["SPI_", "I2C_", "USB_", "UART_"]

        # Build component name -> index map
        comp_to_idx = {c.ref: i for i, c in enumerate(netlist.components)}

        # Find bus nets and their components
        bus_components: dict[str, set[int]] = {}

        for net in netlist.nets:
            for pattern in bus_patterns:
                if net.name.startswith(pattern):
                    bus_name = pattern.rstrip("_")
                    if bus_name not in bus_components:
                        bus_components[bus_name] = set()
                    for comp_ref, _pin in net.pins:
                        if comp_ref in comp_to_idx:
                            bus_components[bus_name].add(comp_to_idx[comp_ref])
                    break

        # Convert to list of lists
        bus_groups = [list(comps) for comps in bus_components.values() if len(comps) >= 2]

        return cls(weight=weight, bus_groups=bus_groups)
