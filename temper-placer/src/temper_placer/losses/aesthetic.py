"""
Aesthetic loss functions for professional PCB layouts.

This module implements losses that improve the visual quality and
manufacturability of the placement by:
- Encouraging row/column alignment of similar components
- Promoting consistent component orientations
- Snapping components to a global manufacturing grid
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import LossContext, LossFunction, LossResult

if TYPE_CHECKING:
    from temper_placer.core.netlist import Netlist
    from temper_placer.io.config_loader import AestheticConstraints
    from temper_placer.losses.base import WeightedLoss


@dataclass
class AlignmentLoss(LossFunction):
    """
    Encourages row/column alignment for similar components (e.g., all resistors).

    Attributes:
        prefix_groups: (G, M) array of component indices sharing the same prefix,
            padded with -1. G is number of groups, M is max group size.
    """

    prefix_groups: Array  # (G, M) array of indices, padded with -1

    @property
    def name(self) -> str:
        return "alignment"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
    ) -> LossResult:
        """
        Compute alignment penalty for each prefix group.

        For each group, we penalize the variance in either X or Y (whichever is smaller),
        encouraging components to form either a horizontal row or a vertical column.
        """

        def compute_group_loss(group_indices):
            # Mask for valid indices (not -1)
            mask = group_indices != -1
            group_pos = positions[group_indices]  # (M, 2)

            # Count valid components in this group
            n_valid = jnp.sum(mask)

            # Compute mean position of valid components
            # Use jnp.where to handle empty groups safely
            sum_pos = jnp.sum(group_pos * mask[:, None], axis=0)
            mean_pos = sum_pos / jnp.maximum(n_valid, 1.0)

            # Compute variance in x and y
            diff_sq = (group_pos - mean_pos) ** 2 * mask[:, None]
            var = jnp.sum(diff_sq, axis=0) / jnp.maximum(n_valid, 1.0)  # (2,)

            # Penalty is min of x-variance and y-variance
            # (encourages alignment to either axis)
            # Only apply if group has at least 2 components
            penalty = jnp.minimum(var[0], var[1])
            return jnp.where(n_valid < 2, 0.0, penalty)

        # Vectorize over all prefix groups
        if self.prefix_groups.shape[0] == 0:
            return LossResult(value=jnp.array(0.0))

        group_losses = jax.vmap(compute_group_loss)(self.prefix_groups)
        total = jnp.sum(group_losses)

        return LossResult(
            value=total,
            breakdown={
                "per_group": group_losses,
            },
        )


@dataclass
class RotationConsistencyLoss(LossFunction):
    """
    Encourages a consistent orientation for components across the board.

    Professional layouts often avoid having a "jumble" of orientations.
    This loss penalizes the entropy of the global orientation distribution,
    pushing the design toward a single dominant orientation (or two).
    """

    @property
    def name(self) -> str:
        return "rotation_consistency"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
    ) -> LossResult:
        """
        Compute entropy of the global rotation distribution.
        """
        # rotations is (N, 4) soft one-hot
        # Compute the mean rotation distribution across all components
        global_dist = jnp.mean(rotations, axis=0)  # (4,)

        # Normalize to ensure valid probability distribution
        probs = global_dist / (jnp.sum(global_dist) + 1e-8)

        # Compute entropy (high entropy = mixed rotations, low = consistent)
        entropy = -jnp.sum(probs * jnp.log(probs + 1e-8))

        return LossResult(value=entropy)


def get_prefix_groups(netlist: Netlist, exceptions: list[str] | None = None) -> Array:
    """
    Groups components by their reference designator prefix (e.g., 'R', 'C').

    Args:
        netlist: The netlist to analyze.
        exceptions: List of component refs to exclude from alignment.

    Returns:
        (G, M) array of component indices, padded with -1.
    """
    import re

    from temper_placer.core.netlist import Netlist

    groups_dict = {}
    exceptions = exceptions or []

    for i, comp in enumerate(netlist.components):
        if comp.ref in exceptions:
            continue

        # Extract prefix (all letters at start)
        match = re.match(r"^([a-zA-Z]+)", comp.ref)
        if not match:
            continue
        prefix = match.group(1)

        # Ignore common single-instance prefixes or very large ones?
        # For now, just group everything by prefix
        if prefix not in groups_dict:
            groups_dict[prefix] = []
        groups_dict[prefix].append(i)

    # Filter for groups with at least 2 members
    valid_groups = [g for g in groups_dict.values() if len(g) > 1]
    if not valid_groups:
        return jnp.zeros((0, 0), dtype=jnp.int32)

    # Convert to padded array (G, M)
    max_len = max(len(g) for g in valid_groups)
    padded = [g + [-1] * (max_len - len(g)) for g in valid_groups]
    return jnp.array(padded, dtype=jnp.int32)


def create_aesthetic_losses(
    netlist: Netlist,
    constraints: AestheticConstraints,
) -> list[WeightedLoss]:
    """
    Create aesthetic losses based on constraints.

    Args:
        netlist: Component netlist.
        constraints: Aesthetic constraints from YAML.

    Returns:
        List of WeightedLoss instances.
    """
    from temper_placer.losses.base import WeightedLoss
    from temper_placer.losses.grid import GridAlignmentLoss

    losses = []

    # 1. Grid alignment
    if constraints.grid_weight > 0:
        losses.append(
            WeightedLoss(
                GridAlignmentLoss(grid_size=constraints.grid_size_mm),
                weight=constraints.grid_weight,
            )
        )

    # 2. Row/Column alignment by prefix
    if constraints.alignment_weight > 0 and constraints.align_by_prefix:
        prefix_groups = get_prefix_groups(netlist, exceptions=constraints.prefix_exceptions)
        if prefix_groups.shape[0] > 0:
            losses.append(
                WeightedLoss(
                    AlignmentLoss(prefix_groups=prefix_groups),
                    weight=constraints.alignment_weight,
                )
            )

    # 3. Rotation consistency
    if constraints.rotation_consistency_weight > 0:
        losses.append(
            WeightedLoss(
                RotationConsistencyLoss(),
                weight=constraints.rotation_consistency_weight,
            )
        )

    return losses
