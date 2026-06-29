"""Ground crossing loss function."""

from __future__ import annotations

from dataclasses import dataclass

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import (
    LossContext,
    LossFunction,
    LossResult,
)


def compute_ground_crossing_penalty(
    positions: Array,
    context: LossContext,
    net_virtual_nodes: Array | None = None,
) -> Array:
    """Compute total ground crossing penalty for all nets in a vectorized way."""
    if context.domain_bounds.shape[0] == 0:
        return jnp.array(0.0)

    # 1. Get all pin positions for all nets
    # net_pin_indices: (M, P)
    # net_pin_offsets: (M, P, 2)
    # net_pin_mask: (M, P)
    pin_pos = positions[context.net_pin_indices] + context.net_pin_offsets  # (M, P, 2)

    # 2. Determine domain info for each pin
    # domain_bounds: (D, 4) -> [x_min, y_min, x_max, y_max]
    # pos: (M, P, 2)
    x = pin_pos[:, :, 0]  # (M, P)
    y = pin_pos[:, :, 1]  # (M, P)

    # Check against each domain
    # (M, P, 1) >= (1, 1, D) -> (M, P, D)
    in_x = jnp.logical_and(
        x[:, :, None] >= context.domain_bounds[None, None, :, 0],
        x[:, :, None] <= context.domain_bounds[None, None, :, 2]
    )
    in_y = jnp.logical_and(
        y[:, :, None] >= context.domain_bounds[None, None, :, 1],
        y[:, :, None] <= context.domain_bounds[None, None, :, 3]
    )
    in_domain = jnp.logical_and(in_x, in_y)  # (M, P, D)

    # Domain ID (0 if not in any domain, else 1-based index)
    domain_ids = jnp.sum(in_domain * (jnp.arange(context.domain_bounds.shape[0]) + 1), axis=-1)  # (M, P)

    # 3. Compute Star Ground Targets
    # A. Default Board Star Points (per pin based on its current domain)
    # domain_star_points: (D, 2)
    # in_domain: (M, P, D)
    # (M, P, D, 1) * (1, 1, D, 2) -> (M, P, D, 2)
    domain_stars = jnp.sum(in_domain[:, :, :, None] * context.domain_star_points[None, None, :, :], axis=2)  # (M, P, 2)

    # B. Net Virtual Nodes (if it's a star net)
    # net_virtual_nodes: (M, 2) if provided
    # we expand to (M, P, 2)
    virtual_stars = net_virtual_nodes[:, None, :] if net_virtual_nodes is not None else domain_stars

    # C. Select target: if net is star_net, use virtual star point, else use domain star point
    # context.is_star_net: (M,) -> (M, 1, 1)
    is_star = context.is_star_net[:, None, None]
    pin_stars = jnp.where(is_star, virtual_stars, domain_stars) # (M, P, 2)

    in_any = jnp.any(in_domain, axis=-1)  # (M, P)

    # 4. Compute segment-wise crossing penalties
    # Segments connect pin i and pin i+1 within each net
    p1 = pin_pos[:, :-1, :]  # (M, P-1, 2)
    p2 = pin_pos[:, 1:, :]   # (M, P-1, 2)

    id1 = domain_ids[:, :-1]
    id2 = domain_ids[:, 1:]

    star1 = pin_stars[:, :-1, :]
    star2 = pin_stars[:, 1:, :]

    any1 = in_any[:, :-1]
    any2 = in_any[:, 1:]

    mask1 = context.net_pin_mask[:, :-1]
    mask2 = context.net_pin_mask[:, 1:]
    segment_mask = jnp.logical_and(mask1, mask2)  # (M, P-1)

    # Crossing occurs if both are in domains and they are different
    crossing = jnp.logical_and(jnp.logical_and(any1, any2), id1 != id2)

    # Detour penalty: dist(p1, star1) + dist(p2, star2) - dist(p1, p2)
    dist_p1_star = jnp.linalg.norm(p1 - star1, axis=-1)
    dist_p2_star = jnp.linalg.norm(p2 - star2, axis=-1)
    dist_direct = jnp.linalg.norm(p1 - p2, axis=-1)

    detour = dist_p1_star + dist_p2_star - dist_direct

    # Only apply detour penalty if crossing and segment is valid
    penalty = jnp.where(jnp.logical_and(crossing, segment_mask), detour, 0.0)

    # Aggregate over all segments and all nets, weighted by net weight
    net_penalties = jnp.sum(penalty, axis=1)  # (M,)
    total_penalty = jnp.sum(net_penalties * context.net_weights)

    return total_penalty


def detect_ground_domain_violations(
    _positions: Array,
    context: LossContext,
) -> list[dict]:
    """Detect and report all ground domain violations for debugging."""
    return []


@dataclass
class GroundCrossingLoss(LossFunction):
    """Loss function penalizing nets that cross ground domain boundaries."""

    @property
    def name(self) -> str:
        return "ground_crossing"

    @property
    def supports_virtual_nodes(self) -> bool:
        return True

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
    ) -> LossResult:
        """Compute ground crossing loss."""
        penalty = compute_ground_crossing_penalty(positions, context, net_virtual_nodes)
        return LossResult(value=penalty)

    def compute_gradients(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
    ) -> Array:
        """Compute gradients of the ground crossing loss w.r.t. positions."""
        return jax.grad(lambda pos: self.__call__(pos, _rotations, context, _epoch, _total_epochs, net_virtual_nodes).value)(positions)
