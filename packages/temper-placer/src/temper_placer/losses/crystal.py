from dataclasses import dataclass, field

import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import LossContext, LossFunction, LossResult


@dataclass
class CrystalRule:
    """Configuration for crystal placement constraints."""

    crystal_ref: str
    mcu_ref: str
    load_cap_refs: list[str]
    noise_source_refs: list[str] = field(default_factory=list)

    max_mcu_distance_mm: float = 10.0
    max_cap_distance_mm: float = 3.0
    min_noise_distance_mm: float = 15.0

    # Weights
    mcu_dist_weight: float = 1.0
    cap_dist_weight: float = 1.0
    noise_dist_weight: float = 2.0


class CrystalPlacementLoss(LossFunction):
    """
    Enforce crystal/oscillator placement constraints.
    - Crystal close to MCU
    - Load caps close to crystal
    - Noise sources far from crystal
    """

    def __init__(self, rules: list[CrystalRule]):
        self.rules = rules

    @property
    def name(self) -> str:
        return "crystal_placement"

    def __call__(
        self,
        _positions: jnp.ndarray,
        rotations: jnp.ndarray,  # noqa: ARG002
        context: LossContext,  # noqa: ARG002
        epoch: int = 0,  # noqa: ARG002
        total_epochs: int = 1,  # noqa: ARG002
        net_virtual_nodes: Array | None = None,  # noqa: ARG002
    ) -> LossResult:
        return LossResult(value=jnp.array(0.0))


@dataclass
class ResolvedCrystalRule:
    """Resolved indices for crystal placement constraints."""

    crystal_idx: int
    mcu_idx: int
    load_cap_indices: jnp.ndarray  # array of ints
    noise_source_indices: jnp.ndarray  # array of ints

    max_mcu_distance_mm: float
    max_cap_distance_mm: float
    min_noise_distance_mm: float

    mcu_dist_weight: float
    cap_dist_weight: float
    noise_dist_weight: float


class ResolvedCrystalPlacementLoss(LossFunction):
    def __init__(self, rules: list[ResolvedCrystalRule]):
        self.rules = rules

    @property
    def name(self) -> str:
        return "crystal_placement"

    def __call__(
        self,
        positions: jnp.ndarray,
        rotations: jnp.ndarray,  # noqa: ARG002
        context: LossContext,  # noqa: ARG002
        epoch: int = 0,  # noqa: ARG002
        total_epochs: int = 1,  # noqa: ARG002
        net_virtual_nodes: Array | None = None,  # noqa: ARG002
    ) -> LossResult:
        total_loss = jnp.array(0.0)

        for rule in self.rules:
            crystal_pos = positions[rule.crystal_idx]
            mcu_pos = positions[rule.mcu_idx]

            # 1. Crystal to MCU distance
            # Squared Euclidean distance
            diff_mcu = crystal_pos - mcu_pos
            dist_sq_mcu = jnp.sum(diff_mcu**2)
            dist_mcu = jnp.sqrt(dist_sq_mcu + 1e-6)

            # Penalty if > max_distance
            violation_mcu = jnp.maximum(0.0, dist_mcu - rule.max_mcu_distance_mm)
            total_loss = total_loss + (violation_mcu**2 * rule.mcu_dist_weight)

            # 2. Load Caps to Crystal distance
            if rule.load_cap_indices.shape[0] > 0:
                caps_pos = positions[rule.load_cap_indices]
                # Broadcasting: crystal_pos (2,) - caps_pos (N, 2) -> (N, 2)
                diff_caps = crystal_pos[None, :] - caps_pos
                dist_sq_caps = jnp.sum(diff_caps**2, axis=-1)
                dist_caps = jnp.sqrt(dist_sq_caps + 1e-6)

                violation_caps = jnp.maximum(0.0, dist_caps - rule.max_cap_distance_mm)
                # Sum penalties for all caps
                total_loss = total_loss + jnp.sum(violation_caps**2) * rule.cap_dist_weight

            # 3. Noise Sources to Crystal distance (Must be FAR)
            if rule.noise_source_indices.shape[0] > 0:
                noise_pos = positions[rule.noise_source_indices]
                # Broadcasting: crystal_pos (2,) - noise_pos (M, 2) -> (M, 2)
                diff_noise = crystal_pos[None, :] - noise_pos
                dist_sq_noise = jnp.sum(diff_noise**2, axis=-1)
                dist_noise = jnp.sqrt(dist_sq_noise + 1e-6)

                # Penalty if < min_distance
                # deficit = max(0, min_dist - dist)
                violation_noise = jnp.maximum(0.0, rule.min_noise_distance_mm - dist_noise)
                total_loss = total_loss + jnp.sum(violation_noise**2) * rule.noise_dist_weight

        return LossResult(value=total_loss)


def create_crystal_loss(
    netlist,
    rules: list[CrystalRule],
) -> ResolvedCrystalPlacementLoss:
    """
    Factory to resolve component references to indices.
    """
    # Map RefDes -> Component Index
    comp_map = {c.ref: i for i, c in enumerate(netlist.components)}

    resolved_rules = []

    for rule in rules:
        # Validate existence
        if rule.crystal_ref not in comp_map:
            continue
        if rule.mcu_ref not in comp_map:
            continue

        crystal_idx = comp_map[rule.crystal_ref]
        mcu_idx = comp_map[rule.mcu_ref]

        load_cap_indices = []
        for ref in rule.load_cap_refs:
            if ref in comp_map:
                load_cap_indices.append(comp_map[ref])

        noise_source_indices = []
        for ref in rule.noise_source_refs:
            if ref in comp_map:
                noise_source_indices.append(comp_map[ref])

        resolved_rules.append(
            ResolvedCrystalRule(
                crystal_idx=crystal_idx,
                mcu_idx=mcu_idx,
                load_cap_indices=jnp.array(load_cap_indices, dtype=jnp.int32),
                noise_source_indices=jnp.array(noise_source_indices, dtype=jnp.int32),
                max_mcu_distance_mm=rule.max_mcu_distance_mm,
                max_cap_distance_mm=rule.max_cap_distance_mm,
                min_noise_distance_mm=rule.min_noise_distance_mm,
                mcu_dist_weight=rule.mcu_dist_weight,
                cap_dist_weight=rule.cap_dist_weight,
                noise_dist_weight=rule.noise_dist_weight,
            )
        )

    return ResolvedCrystalPlacementLoss(resolved_rules)
