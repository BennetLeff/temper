from dataclasses import dataclass
from typing import List, Optional, Tuple

import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import (
    LossContext,
    LossFunction,
    LossResult,
    WeightedLoss,
    create_jit_loss_fn,
)


@dataclass(frozen=True)
class CoilRule:
    """
    Configuration for induction coil placement rules.

    Attributes:
        coil_ref: Reference designator for the coil (e.g., "L1").
        target_position: (x, y) target for the coil center in mm.
        keepout_radius: Radius in mm around coil center where sensitive components are forbidden.
        sensitive_refs: List of sensitive component refs (e.g., analog ICs, sensors).
        tank_capacitor_refs: List of resonant tank capacitor refs for symmetry check.
        weight_centering: Weight for centering force.
        weight_keepout: Weight for keep-out violation.
        weight_symmetry: Weight for capacitor symmetry.
    """

    coil_ref: str
    target_position: Tuple[float, float]
    keepout_radius: float = 50.0  # mm
    sensitive_refs: Tuple[str, ...] = tuple()
    tank_capacitor_refs: Tuple[str, ...] = tuple()
    weight_centering: float = 1.0
    weight_keepout: float = 1.0
    weight_symmetry: float = 1.0


class CoilRequirementLoss(LossFunction):
    """
    Enforces placement requirements for the main induction coil.

    1. Centering: Coil center -> Target Position
    2. Keep-out: Sensitive components > Radius from Coil
    3. Symmetry: Tank capacitors symmetric relative to Coil
    """

    def __init__(self, rules: List[CoilRule]):
        self.rules = rules

    @property
    def name(self) -> str:
        return "coil_requirement"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
    ) -> LossResult:
        total_centering_loss = 0.0
        total_keepout_loss = 0.0
        total_symmetry_loss = 0.0

        for rule in self.rules:
            # 1. Centering
            coil_idx = context.netlist.get_component_index(rule.coil_ref)
            coil_pos = positions[coil_idx]
            target = jnp.array(rule.target_position)

            # Squared distance to target
            dist_sq = jnp.sum((coil_pos - target) ** 2)
            total_centering_loss += rule.weight_centering * dist_sq

            # 2. Keep-out
            if rule.sensitive_refs:
                # Gather sensitive component indices
                # Note: In a real JIT context, we need precomputed indices in context.
                # Since we can't easily change Context now, we'll iterate or rely on
                # this being constructed at python time (JAX traces loops).
                # But get_component_index is fast enough for construction.

                sensitive_indices = [
                    context.netlist.get_component_index(ref) for ref in rule.sensitive_refs
                ]
                sensitive_pos = positions[jnp.array(sensitive_indices)]

                # Distance to coil
                # (N, 2) - (2,) -> (N, 2)
                diff = sensitive_pos - coil_pos
                dist_sq_sens = jnp.sum(diff**2, axis=1)
                dist_sens = jnp.sqrt(dist_sq_sens + 1e-6)

                # Penalize if dist < radius
                # violation = ReLU(radius - dist)
                violation = jnp.maximum(0.0, rule.keepout_radius - dist_sens)
                # Square violation for stronger gradient
                total_keepout_loss += rule.weight_keepout * jnp.sum(violation**2)

            # 3. Symmetry (simplified)
            # Center of mass of tank caps should be close to coil center
            if rule.tank_capacitor_refs:
                cap_indices = [
                    context.netlist.get_component_index(ref) for ref in rule.tank_capacitor_refs
                ]
                cap_pos = positions[jnp.array(cap_indices)]

                # Center of mass of caps
                caps_center = jnp.mean(cap_pos, axis=0)

                # Distance between coil center and caps center
                sym_dist_sq = jnp.sum((coil_pos - caps_center) ** 2)
                total_symmetry_loss += rule.weight_symmetry * sym_dist_sq

        total_loss = total_centering_loss + total_keepout_loss + total_symmetry_loss

        return LossResult(
            value=jnp.array(total_loss),
            breakdown={
                "coil_centering": jnp.array(total_centering_loss),
                "coil_keepout": jnp.array(total_keepout_loss),
                "coil_symmetry": jnp.array(total_symmetry_loss),
            },
        )


def create_coil_loss(rules: List[CoilRule], weight: float = 1.0) -> WeightedLoss:
    """Create a weighted CoilRequirementLoss."""
    return WeightedLoss(
        CoilRequirementLoss(rules),
        weight=weight,
        normalize_by=1.0,  # Absolute distance in mm, don't normalize by board area
    )
