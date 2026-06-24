"""
Decoupling capacitor proximity loss function.

This loss function ensures that decoupling capacitors are placed close to their
associated ICs (or specific power pins on the ICs). It is critical for
power integrity and high-frequency noise suppression.
"""

from __future__ import annotations

from dataclasses import dataclass

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import LossContext, LossFunction, LossResult


@dataclass(frozen=True)
class DecouplingRule:
    """
    Association between a decoupling cap and its IC.

    Attributes:
        cap_ref: Reference designator of the capacitor (e.g., "C1").
        ic_ref: Reference designator of the IC (e.g., "U1").
        max_distance_mm: Maximum allowed distance (center-to-center).
        power_pin: Optional name of the specific power pin on the IC.
    """

    cap_ref: str
    ic_ref: str
    max_distance_mm: float = 3.0
    power_pin: str | None = None


@dataclass
class DecouplingCapProximityLoss(LossFunction):
    """
    Penalize decoupling caps too far from their ICs.

    Uses softplus for smooth gradients near the constraint boundary.
    """

    cap_indices: Array  # (K,) indices of capacitors
    ic_indices: Array  # (K,) indices of associated ICs
    max_distances: Array  # (K,) max distance for each pair

    margin: float = 1.0  # Smoothness margin for softplus

    @property
    def name(self) -> str:
        return "decoupling_proximity"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
    ) -> LossResult:
        """
        Compute decoupling proximity penalty.
        """
        if self.cap_indices.shape[0] == 0:
            return LossResult(value=jnp.array(0.0))

        # Get positions
        cap_pos = positions[self.cap_indices]  # (K, 2)
        ic_pos = positions[self.ic_indices]  # (K, 2)

        # Compute distances (center-to-center for now)
        # TODO: Support pin-level distance if power_pin offsets provided
        diff = cap_pos - ic_pos
        dist = jnp.sqrt(jnp.sum(diff**2, axis=1) + 1e-12)  # (K,)

        # Penalize excess distance
        excess = dist - self.max_distances

        # Softplus penalty: softplus(excess/margin) * margin
        # If excess < 0 (satisfied), penalty -> 0
        # If excess > 0 (violated), penalty -> linear/quadratic

        # We use squared penalty for stronger gradient when violated
        # penalty = smooth_relu(excess) ** 2

        # Using softplus for smoothness
        penalty_val = self.margin * jax.nn.softplus(excess / self.margin)
        total_penalty = jnp.sum(penalty_val**2)

        return LossResult(
            value=total_penalty,
            breakdown={
                "decoupling_max_dist": jnp.max(dist),
                "decoupling_avg_dist": jnp.mean(dist),
                "decoupling_violations": jnp.sum(dist > self.max_distances),
            },
        )


def create_decoupling_loss(
    netlist,  # Type: Netlist
    rules: list[DecouplingRule],
    margin: float = 1.0,
) -> DecouplingCapProximityLoss:
    """Factory to create DecouplingCapProximityLoss from rules."""
    ref_to_idx = {c.ref: i for i, c in enumerate(netlist.components)}

    cap_indices = []
    ic_indices = []
    max_dists = []

    for rule in rules:
        if rule.cap_ref in ref_to_idx and rule.ic_ref in ref_to_idx:
            cap_indices.append(ref_to_idx[rule.cap_ref])
            ic_indices.append(ref_to_idx[rule.ic_ref])
            max_dists.append(rule.max_distance_mm)

    return DecouplingCapProximityLoss(
        cap_indices=jnp.array(cap_indices, dtype=jnp.int32),
        ic_indices=jnp.array(ic_indices, dtype=jnp.int32),
        max_distances=jnp.array(max_dists, dtype=jnp.float32),
        margin=margin,
    )


def auto_detect_decoupling(
    netlist,  # Type: Netlist
    _default_max_dist: float = 3.0,
) -> list[DecouplingRule]:
    """
    Auto-detect decoupling capacitor associations from netlist.

    Heuristics:
    1. Identify capacitors by refdes prefix 'C'.
    2. Check value (if available) or assume small caps are decoupling.
    3. Find caps connected to a power net and a ground net.
    4. Find ICs connected to the same power net.
    5. Associate cap with IC(s).

    For now, we implement a simplified version:
    - Find components with ref starting with 'C'
    - Check if they share a net with a component starting with 'U'
    - Filter for power/ground nets if possible (requires net classification)

    Current implementation is conservative: it returns empty list until
    we have reliable net classification (Power/Ground/Signal).
    """
    # Placeholder for future implementation
    return []
