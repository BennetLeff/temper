"""
Through-Hole Technology (THT) pad clearance loss.

Ensures that THT components are placed far enough apart to prevent
their holes from overlapping or being too close, which would compromise
PCB structural integrity.
"""


import jax.numpy as jnp
from jax import Array

from temper_placer.core.netlist import Netlist
from temper_placer.losses.base import LossContext, LossFunction, LossResult


class THTPadClearanceLoss(LossFunction):
    """Penalizes THT pads that are too close to each other.

    Calculates pairwise distance between all THT pads in the design.
    If distance < (drill_radius_1 + drill_radius_2 + margin), adds penalty.
    """

    def __init__(
        self,
        netlist: Netlist,
        weight: float = 1.0,
        min_clearance: float = 0.5,  # mm between hole edges
        name: str = "tht_clearance_loss",
    ):
        super().__init__(weight, name)
        self.netlist = netlist
        self.min_clearance = min_clearance

        # Extract THT pad information once
        # We need relative positions of THT pads for each component
        # Format: list of (component_index, relative_x, relative_y, drill_radius)
        self._tht_pads_info = self._extract_tht_pads(netlist)

    def _extract_tht_pads(self, netlist: Netlist) -> list[tuple[int, float, float, float]]:
        pads = []
        for i, comp in enumerate(netlist.components):
            for pad in comp.pads:
                # Check if pad is through-hole
                # Heuristic: drill > 0
                if pad.drill > 0:
                    pads.append((i, pad.position[0], pad.position[1], pad.drill / 2.0))
        return pads

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
    ) -> LossResult:
        if not self._tht_pads_info:
            return LossResult(value=jnp.array(0.0), name=self.name, weight=self.weight)

        loss = 0.0

        # Calculate absolute positions of all THT pads
        # This is a bit slow if done in loop, but number of THT pads is usually small
        # For JAX efficiency, we should ideally vectorize this.
        # But `positions` is (N, 2).
        # We can construct pad_positions array of shape (M, 2) where M is num pads.

        # We need to handle rotation if we want to be precise,
        # but for now assume component rotation doesn't change relative pad position (valid for 0 deg)
        # or that relative positions are pre-rotated?
        # The optimizer usually optimizes (x, y, rotation).
        # If rotation is optimized, we need to apply it.
        # But `positions` usually contains (x, y). Rotation might be separate or fixed.
        # In `temper-placer`, rotation is often discrete or handled separately.
        # Assuming fixed rotation for now or that `positions` includes rotation?
        # `positions` is typically (N, 2).

        # Let's assume zero rotation for simplicity or that it's fixed.
        # TODO: Handle rotation if necessary.

        pad_abs_pos = []
        pad_radii = []

        for comp_idx, rel_x, rel_y, radius in self._tht_pads_info:
            comp_pos = positions[comp_idx]
            pad_abs_pos.append([comp_pos[0] + rel_x, comp_pos[1] + rel_y])
            pad_radii.append(radius)

        if not pad_abs_pos:
            return LossResult(value=jnp.array(0.0), name=self.name, weight=self.weight)

        pad_pos_array = jnp.array(pad_abs_pos)
        pad_radii_array = jnp.array(pad_radii)

        # Pairwise distances
        # (M, 1, 2) - (1, M, 2) -> (M, M, 2)
        diff = pad_pos_array[:, None, :] - pad_pos_array[None, :, :]
        dist_sq = jnp.sum(diff**2, axis=-1)
        dist = jnp.sqrt(dist_sq + 1e-6)  # Avoid NaN gradient at 0

        # Required distance matrix
        # (M, 1) + (1, M) -> (M, M)
        req_dist = pad_radii_array[:, None] + pad_radii_array[None, :] + self.min_clearance

        # Violation: req_dist - dist > 0
        violation = jnp.maximum(0.0, req_dist - dist)

        # Zero out diagonal (self-distance)
        # and lower triangle to avoid double counting
        mask = jnp.triu(jnp.ones_like(dist), k=1)

        loss = jnp.sum(violation * mask)

        return LossResult(value=jnp.array(loss * self.weight), name=self.name, weight=self.weight)
