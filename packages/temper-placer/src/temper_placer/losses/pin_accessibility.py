"""
Pin accessibility loss function.

This loss ensures that pins have sufficient clearance from other components
and pins of different nets, facilitating escape routing and improving
overall routability.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.geometry.transform import ROTATION_MATRICES, batch_get_rotated_bounds
from temper_placer.losses.base import LossContext, LossFunction, LossResult


@dataclass
class PinAccessibilityLoss(LossFunction):
    """
    Loss function penalizing pins that are blocked or too close to each other.

    Attributes:
        pin_pin_margin: Minimum clearance between pins of different nets (mm).
        pin_body_margin: Minimum clearance between a pin and other component bodies (mm).
        weight_pin_pin: Weight for pin-pin clearance violations.
        weight_pin_body: Weight for pin-body clearance violations.
    """
    pin_pin_margin: float = 0.5
    pin_body_margin: float = 0.8
    weight_pin_pin: float = 1.0
    weight_pin_body: float = 2.0

    @property
    def name(self) -> str:
        return "pin_accessibility"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
        **kwargs: Any,
    ) -> LossResult:
        """
        Compute pin accessibility loss.
        """
        # 1. Get pin world positions
        # context.netlist_data.net_pin_indices: (M, P)
        # context.netlist_data.net_pin_offsets: (M, P, 2)
        # context.netlist_data.net_pin_mask: (M, P)

        indices = context.netlist_data.net_pin_indices
        offsets = context.netlist_data.net_pin_offsets
        mask = context.netlist_data.net_pin_mask

        if indices.shape[0] == 0:
            return LossResult(value=jnp.array(0.0))

        # Get rotation matrices for all components: (N, 2, 2)
        # rotations is (N, 4) soft one-hot
        rot_matrices = jnp.einsum("nr,rij->nij", rotations, ROTATION_MATRICES)

        # Map rotation matrices to net pins: (M, P, 2, 2)
        net_rot_matrices = rot_matrices[indices]

        # Rotate offsets: (M, P, 2) @ (M, P, 2, 2).T -> (M, P, 2)
        # Using einsum for better control: offsets[m,p,i] * net_rot_matrices[m,p,j,i] -> pin_rotated[m,p,j]
        rotated_offsets = jnp.einsum("mpi,mpji->mpj", offsets, net_rot_matrices)

        # Absolute positions: (M, P, 2)
        pin_positions = positions[indices] + rotated_offsets

        # Flatten pins: (M*P, 2)
        flat_pins = pin_positions.reshape(-1, 2)
        flat_mask = mask.reshape(-1)
        flat_comp_indices = indices.reshape(-1) # component index for each pin

        n_pins = flat_pins.shape[0]
        n_comps = positions.shape[0]

        # 2. Pin-to-Body clearance
        # Get rotated component bounds
        widths, heights = batch_get_rotated_bounds(context.bounds[:, 0], context.bounds[:, 1], rotations)
        half_dims = jnp.stack([widths, heights], axis=-1) / 2.0

        # SDF of pin P w.r.t component C:
        # d_pc = max(abs(P - pos_c) - half_dim_c)
        # diff: (N_pins, N_comps, 2)
        diff_pc = jnp.abs(flat_pins[:, None, :] - positions[None, :, :])
        sdf = jnp.max(diff_pc - half_dims[None, :, :], axis=-1)

        # self_mask: (N_pins, N_comps) where True if pin i belongs to component j
        # component_indices: (N_pins,) -> one_hot -> (N_pins, N_comps)
        self_mask = jax.nn.one_hot(flat_comp_indices, n_comps)

        pin_body_violations = jax.nn.relu(self.pin_body_margin - sdf) ** 2
        # Apply mask: ignore self-component and invalid pins
        pin_body_violations = pin_body_violations * (1.0 - self_mask) * flat_mask[:, None]

        loss_body = jnp.sum(pin_body_violations) * self.weight_pin_body

        # 3. Pin-to-Pin clearance
        # diff_pp: (N_pins, N_pins, 2)
        diff_pp = flat_pins[:, None, :] - flat_pins[None, :, :]
        dist_sq = jnp.sum(diff_pp**2, axis=-1)
        dist = jnp.sqrt(dist_sq + 1e-9)

        # Only penalize if from different nets.
        net_indices = jnp.arange(indices.shape[0])
        pin_net_indices = jnp.repeat(net_indices, context.netlist_data.max_pins_per_net)

        # net_mask_pp: (N_pins, N_pins) True if pins are on different nets
        net_mask_pp = (pin_net_indices[:, None] != pin_net_indices[None, :])

        pin_pin_violations = jax.nn.relu(self.pin_pin_margin - dist) ** 2

        # Apply mask: different nets AND both pins are valid
        valid_pp_mask = flat_mask[:, None] * flat_mask[None, :] * net_mask_pp

        # Use upper triangle to avoid double counting
        triu_mask = jnp.triu(jnp.ones((n_pins, n_pins), dtype=jnp.bool_), k=1)

        loss_pin = jnp.sum(pin_pin_violations * valid_pp_mask * triu_mask) * self.weight_pin_pin

        total_loss = loss_body + loss_pin

        return LossResult(
            value=total_loss,
            breakdown={
                "pin_body_loss": loss_body,
                "pin_pin_loss": loss_pin,
                "max_pin_body_violation": jnp.max(pin_body_violations),
                "max_pin_pin_violation": jnp.max(pin_pin_violations * valid_pp_mask),
            }
        )
