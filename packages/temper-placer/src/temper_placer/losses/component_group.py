"""
Component Group Loss Function.

Enforces that groups of related components stay clustered within a maximum spread.
This is useful for:
- MCU decoupling capacitors (keep near MCU)
- LDO input/output capacitors (keep near regulator)
- SPI chain components (keep clustered for short traces)
- Functional blocks that should be grouped
"""

from __future__ import annotations

import jax.numpy as jnp
from jax import Array

from temper_placer.io.config_loader import ComponentGroup
from temper_placer.losses.base import LossContext, LossFunction, LossResult


class ComponentGroupLoss(LossFunction):
    """
    Penalize component groups that spread beyond their max_spread_mm limit.

    For each group:
    1. Compute bounding box of all component centers
    2. Measure diagonal of bounding box (max spread)
    3. If spread > max_spread_mm, apply quadratic penalty

    The penalty is: weight * (violation)^2 where violation = max(0, spread - max_spread_mm)

    Attributes:
        groups: List of ComponentGroup configurations from constraints
        weight: Global weight for group penalties (default: 1.0)
    """

    def __init__(self, groups: list[ComponentGroup], weight: float = 1.0):
        """
        Initialize ComponentGroupLoss.

        Args:
            groups: List of component groups to enforce
            weight: Global penalty weight
        """
        self.groups = groups
        self.weight = weight

    @property
    def name(self) -> str:
        return "component_group"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
    ) -> LossResult:
        """
        Compute total penalty for component groups exceeding max_spread_mm.

        Args:
            positions: (N, 2) component center positions
            rotations: (N, 4) soft one-hot rotation indicators (unused here)
            context: LossContext with netlist
            epoch: Current epoch (unused)
            total_epochs: Total epochs (unused)
            net_virtual_nodes: Virtual nodes (unused)

        Returns:
            LossResult with total group spread penalty
        """
        total_penalty = 0.0

        for group in self.groups:
            # Get indices of components in this group
            indices = []
            for ref in group.components:
                try:
                    idx = context.netlist.get_component_index(ref)
                    indices.append(idx)
                except (ValueError, KeyError):
                    # Component not in netlist - skip
                    continue

            if len(indices) < 2:
                # Need at least 2 components to measure spread
                continue

            # Get positions of group members: (n_group, 2)
            group_indices_array = jnp.array(indices, dtype=jnp.int32)
            group_positions = positions[group_indices_array]

            # Compute bounding box
            min_pos = jnp.min(group_positions, axis=0)  # (2,)
            max_pos = jnp.max(group_positions, axis=0)  # (2,)

            # Bounding box size
            bbox_size = max_pos - min_pos  # (2,) = (width, height)

            # Diagonal = sqrt(width^2 + height^2) - maximum possible spread
            spread = jnp.sqrt(jnp.sum(bbox_size**2))

            # Violation: how much we exceed the limit
            violation = jnp.maximum(0.0, spread - group.max_spread_mm)

            # Quadratic penalty
            penalty = violation**2

            total_penalty += penalty

        return LossResult(value=total_penalty * self.weight)

    def weight_schedule(self, epoch: int, total_epochs: int) -> float:
        """
        Component grouping is active from the start.

        Returns constant 1.0 - curriculum scheduling happens in CompositeLoss.
        """
        return 1.0
