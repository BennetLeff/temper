"""
Functional grouping loss functions.

These losses encourage components to be placed according to their functional
role in the circuit:

- GroupClusterLoss: Penalize groups exceeding their maximum diameter
- ProximityLoss: Penalize component pairs that are too far apart
- GroupSeparationLoss: Penalize groups that are too close together

Functional grouping encodes expert PCB design knowledge:
- Keep gate drivers close to their MOSFETs/IGBTs
- Keep decoupling capacitors close to their ICs
- Keep power stage separate from MCU/control section
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import LossContext, LossFunction, LossResult


@dataclass
class ProximityRule:
    """Rule specifying maximum distance between two components."""

    idx_a: int  # Component index A
    idx_b: int  # Component index B
    max_distance_mm: float  # Maximum allowed distance
    weight: float = 1.0  # Importance weight


@dataclass
class GroupConfig:
    """Configuration for a functional group."""

    name: str
    component_indices: Array  # JAX array of component indices
    max_diameter_mm: float  # Maximum spread (diameter of bounding circle)
    weight: float = 1.0


class GroupClusterLoss(LossFunction):
    """
    Penalize functional groups that exceed their maximum diameter.

    For each group, computes the maximum pairwise distance between any two
    components (diameter). If this exceeds max_diameter_mm, applies a
    squared penalty.

    This encourages related components (e.g., gate driver + IGBT + bootstrap cap)
    to be placed close together for better performance.
    """

    def __init__(
        self,
        groups: List[GroupConfig],
    ):
        """
        Initialize GroupClusterLoss.

        Args:
            groups: List of GroupConfig defining groups and their max diameters.
        """
        self.groups = groups

    @property
    def name(self) -> str:
        return "group_cluster"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
    ) -> LossResult:
        """
        Compute total group cluster penalty.

        Args:
            positions: (N, 2) component positions.
            rotations: (N, 4) rotation indicators (unused).
            context: LossContext with netlist info.

        Returns:
            LossResult with sum of squared diameter excesses.
        """
        total_penalty = jnp.array(0.0)
        breakdown: Dict[str, Array] = {}

        for group in self.groups:
            # Get positions of components in this group
            group_positions = positions[group.component_indices]
            n_in_group = group_positions.shape[0]

            if n_in_group < 2:
                # Single component has diameter 0
                group_diameter = jnp.array(0.0)
            else:
                # Compute maximum pairwise distance (diameter)
                group_diameter = _compute_group_diameter(group_positions)

            # Penalty for exceeding max diameter
            excess = jax.nn.relu(group_diameter - group.max_diameter_mm)
            penalty = group.weight * excess**2

            total_penalty = total_penalty + penalty
            breakdown[f"group_{group.name}_diameter"] = group_diameter
            breakdown[f"group_{group.name}_penalty"] = penalty

        return LossResult(value=total_penalty, breakdown=breakdown)


def _compute_group_diameter(positions: Array) -> Array:
    """
    Compute the diameter (max pairwise distance) of a set of points.

    Args:
        positions: (M, 2) positions of M components.

    Returns:
        Scalar maximum pairwise distance.
    """
    # Compute all pairwise distances
    # positions[:, None, :] is (M, 1, 2)
    # positions[None, :, :] is (1, M, 2)
    # diff is (M, M, 2)
    diff = positions[:, None, :] - positions[None, :, :]

    # Euclidean distances (M, M)
    # Add small epsilon for numerical stability at zero distance
    distances = jnp.sqrt(jnp.sum(diff**2, axis=-1) + 1e-12)

    # Maximum distance is the diameter
    return jnp.max(distances)


class ProximityLoss(LossFunction):
    """
    Penalize component pairs that exceed their maximum allowed distance.

    This is used for constraints like:
    - Decoupling capacitor must be within 3mm of IC
    - Gate driver must be within 10mm of MOSFET

    A squared penalty is applied when distance exceeds the maximum.
    """

    def __init__(
        self,
        proximity_rules: List[ProximityRule],
    ):
        """
        Initialize ProximityLoss.

        Args:
            proximity_rules: List of ProximityRule defining pairs and max distances.
        """
        self.rules = proximity_rules

        # Pre-convert to JAX arrays for efficiency
        if proximity_rules:
            self._idx_a = jnp.array([r.idx_a for r in proximity_rules], dtype=jnp.int32)
            self._idx_b = jnp.array([r.idx_b for r in proximity_rules], dtype=jnp.int32)
            self._max_dist = jnp.array(
                [r.max_distance_mm for r in proximity_rules], dtype=jnp.float32
            )
            self._weights = jnp.array([r.weight for r in proximity_rules], dtype=jnp.float32)
        else:
            self._idx_a = jnp.array([], dtype=jnp.int32)
            self._idx_b = jnp.array([], dtype=jnp.int32)
            self._max_dist = jnp.array([], dtype=jnp.float32)
            self._weights = jnp.array([], dtype=jnp.float32)

    @property
    def name(self) -> str:
        return "proximity"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
    ) -> LossResult:
        """
        Compute total proximity penalty.

        Args:
            positions: (N, 2) component positions.
            rotations: (N, 4) rotation indicators (unused).
            context: LossContext.

        Returns:
            LossResult with sum of squared distance excesses.
        """
        if len(self.rules) == 0:
            return LossResult(value=jnp.array(0.0))

        # Get positions for each pair
        pos_a = positions[self._idx_a]  # (R, 2)
        pos_b = positions[self._idx_b]  # (R, 2)

        # Compute distances
        diff = pos_a - pos_b
        distances = jnp.sqrt(jnp.sum(diff**2, axis=-1) + 1e-12)  # (R,)

        # Penalty for exceeding max distance
        excesses = jax.nn.relu(distances - self._max_dist)  # (R,)
        penalties = self._weights * excesses**2  # (R,)

        total_penalty = jnp.sum(penalties)

        return LossResult(
            value=total_penalty,
            breakdown={
                "proximity_distances": distances,
                "proximity_penalties": penalties,
            },
        )


class GroupSeparationLoss(LossFunction):
    """
    Penalize groups that are too close together.

    This ensures that different functional blocks maintain adequate separation,
    e.g., keeping the power stage away from the MCU.

    Uses centroid-to-centroid distance between groups.
    """

    def __init__(
        self,
        separations: List[Tuple[GroupConfig, GroupConfig, float]],
    ):
        """
        Initialize GroupSeparationLoss.

        Args:
            separations: List of (group_a, group_b, min_distance_mm) tuples.
        """
        self.separations = separations

    @property
    def name(self) -> str:
        return "group_separation"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
    ) -> LossResult:
        """
        Compute total group separation penalty.

        Args:
            positions: (N, 2) component positions.
            rotations: (N, 4) rotation indicators (unused).
            context: LossContext.

        Returns:
            LossResult with sum of squared distance deficits.
        """
        if len(self.separations) == 0:
            return LossResult(value=jnp.array(0.0))

        total_penalty = jnp.array(0.0)
        breakdown: Dict[str, Array] = {}

        for i, (group_a, group_b, min_dist) in enumerate(self.separations):
            # Compute centroids of each group
            centroid_a = jnp.mean(positions[group_a.component_indices], axis=0)
            centroid_b = jnp.mean(positions[group_b.component_indices], axis=0)

            # Distance between centroids
            diff = centroid_a - centroid_b
            distance = jnp.sqrt(jnp.sum(diff**2) + 1e-12)

            # Penalty for being too close
            deficit = jax.nn.relu(min_dist - distance)
            penalty = deficit**2

            total_penalty = total_penalty + penalty
            breakdown[f"sep_{group_a.name}_{group_b.name}_dist"] = distance
            breakdown[f"sep_{group_a.name}_{group_b.name}_penalty"] = penalty

        return LossResult(value=total_penalty, breakdown=breakdown)


def create_grouping_losses_from_constraints(
    constraints,  # PlacementConstraints
    netlist,  # Netlist
) -> Tuple[Optional[GroupClusterLoss], Optional[ProximityLoss], Optional[GroupSeparationLoss]]:
    """
    Create grouping loss functions from PlacementConstraints.

    Args:
        constraints: PlacementConstraints with component_groups and group_separations.
        netlist: Netlist for resolving component refs to indices.

    Returns:
        Tuple of (GroupClusterLoss, ProximityLoss, GroupSeparationLoss).
        Any may be None if no constraints of that type exist.
    """
    # Build group configs
    group_configs: Dict[str, GroupConfig] = {}
    all_proximity_rules: List[ProximityRule] = []

    for group in constraints.component_groups:
        # Resolve component refs to indices
        indices = []
        for ref in group.components:
            try:
                idx = netlist.get_component_index(ref)
                indices.append(idx)
            except KeyError:
                # Component not in netlist, skip
                pass

        if indices:
            config = GroupConfig(
                name=group.name,
                component_indices=jnp.array(indices, dtype=jnp.int32),
                max_diameter_mm=group.max_spread_mm,
                weight=1.0,
            )
            group_configs[group.name] = config

            # Add proximity rules from within the group
            for rule in group.proximity_rules:
                try:
                    idx_a = netlist.get_component_index(rule.component_a)
                    idx_b = netlist.get_component_index(rule.component_b)
                    all_proximity_rules.append(
                        ProximityRule(
                            idx_a=idx_a,
                            idx_b=idx_b,
                            max_distance_mm=rule.max_distance_mm,
                            weight=1.0,
                        )
                    )
                except KeyError:
                    # Component not found, skip
                    pass

    # Create GroupClusterLoss if we have groups
    cluster_loss = None
    if group_configs:
        cluster_loss = GroupClusterLoss(list(group_configs.values()))

    # Create ProximityLoss if we have rules
    proximity_loss = None
    if all_proximity_rules:
        proximity_loss = ProximityLoss(all_proximity_rules)

    # Build group separation loss
    separation_loss = None
    separations: List[Tuple[GroupConfig, GroupConfig, float]] = []

    for sep in constraints.group_separations:
        if sep.group_a in group_configs and sep.group_b in group_configs:
            separations.append(
                (
                    group_configs[sep.group_a],
                    group_configs[sep.group_b],
                    sep.min_distance_mm,
                )
            )

    if separations:
        separation_loss = GroupSeparationLoss(separations)

    return cluster_loss, proximity_loss, separation_loss
