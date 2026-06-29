"""
Power path loss function for minimizing parasitic inductance in high-current paths.

This loss targets high-current traces (e.g., DC bus, gate drive loops) where
minimizing loop inductance is critical.

It implements a hybrid model:
1. Loop Inductance (Area-based): For closed switching loops (e.g. Buck converter loop),
   minimizes the polygon area formed by the component centroids.
   Loss ~ Area * Weight

2. Path Inductance (Manhattan): For high-current traces that are not closed loops,
   minimizes the Manhattan distance (HPWL) of the net, weighted by I^2.
   Loss ~ HPWL * I^2 * Weight
"""

from __future__ import annotations

from dataclasses import dataclass

import jax.numpy as jnp
from jax import Array

from temper_placer.core.netlist import Netlist
from temper_placer.geometry.smooth import smooth_max_axis, smooth_min_axis
from temper_placer.losses.base import LossContext, LossFunction, LossResult


@dataclass(frozen=True)
class HighCurrentPathConfig:
    """
    Configuration for a high-current path (Manhattan distance optimization).

    Attributes:
        name: Path identifier (e.g., "dc_bus_positive").
        nets: List of net names forming the path.
        current_a: Peak current in Amperes.
        weight: Importance weight.
    """

    name: str
    nets: list[str]
    current_a: float
    weight: float = 1.0


@dataclass(frozen=True)
class SwitchingLoopConfig:
    """
    Configuration for a switching loop (Area optimization).

    Attributes:
        name: Loop identifier (e.g., "buck_input_loop").
        components: List of component designators forming the loop, in order.
                    e.g. ["C_IN", "Q_HS", "Q_LS"]
        weight: Importance weight.
    """

    name: str
    components: list[str]
    weight: float = 1.0


@dataclass
class PowerPathLoss(LossFunction):
    """
    Minimize parasitic inductance in high-current paths and switching loops.

    Attributes:
        path_net_indices: Indices of nets to optimize using Manhattan distance.
        path_net_weights: Weights for each path net (I^2 * config_weight).
        loop_comp_indices: List of arrays, where each array contains component indices for a loop.
        loop_next_indices: Precomputed indices for permutation in shoelace area formula.
        loop_weights: Weights for each loop.
        alpha: Smoothing parameter for LogSumExp HPWL approximation.
    """

    # Path (HPWL) Data
    path_net_indices: Array  # (K_paths,)
    path_net_weights: Array  # (K_paths,)

    # Loop (Area) Data
    loop_comp_indices: Array  # (N_loops, Max_Loop_Size) - padded with -1
    loop_next_indices: Array  # (N_loops, Max_Loop_Size) - precomputed permutation indices
    loop_weights: Array  # (N_loops,)

    alpha: float = 10.0

    @property
    def name(self) -> str:
        return "power_path"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,  # noqa: ARG002
        total_epochs: int = 1,  # noqa: ARG002
        net_virtual_nodes: Array | None = None,  # noqa: ARG002
    ) -> LossResult:
        """
        Compute total power path loss.

        Args:
            positions: (N, 2) component positions.
            rotations: (N, 4) rotation indicators.
            context: LossContext with pre-computed net pin arrays.

        Returns:
            LossResult with total weighted path length + loop area.
        """
        total_loss = jnp.array(0.0)
        metrics = {}

        # --- 1. Path Loss (Manhattan / HPWL) ---
        if self.path_net_indices.shape[0] > 0:
            # context.net_pin_indices is (M, P)
            indices = context.net_pin_indices[self.path_net_indices]  # (K, P)
            offsets = context.net_pin_offsets[self.path_net_indices]  # (K, P, 2)
            mask = context.net_pin_mask[self.path_net_indices]  # (K, P)

            # Get component positions for these pins
            pin_comp_positions = positions[indices]  # (K, P, 2)

            # Apply rotations to pin offsets
            angles = jnp.array([0.0, jnp.pi / 2, jnp.pi, 3 * jnp.pi / 2])
            comp_angles = jnp.sum(rotations * angles[None, :], axis=1)  # (N,)
            pin_angles = comp_angles[indices]  # (K, P)

            cos_a = jnp.cos(pin_angles)
            sin_a = jnp.sin(pin_angles)

            # Rotate offsets
            off_x = offsets[..., 0] * cos_a - offsets[..., 1] * sin_a
            off_y = offsets[..., 0] * sin_a + offsets[..., 1] * cos_a

            # Add rotated offsets to component positions
            pin_positions_x = pin_comp_positions[..., 0] + off_x
            pin_positions_y = pin_comp_positions[..., 1] + off_y

            # Compute HPWL (Bounding Box)
            big_val = 1e6
            masked_x_max = jnp.where(mask, pin_positions_x, -big_val)
            masked_x_min = jnp.where(mask, pin_positions_x, big_val)
            masked_y_max = jnp.where(mask, pin_positions_y, -big_val)
            masked_y_min = jnp.where(mask, pin_positions_y, big_val)

            max_x = smooth_max_axis(masked_x_max, alpha=self.alpha, axis=1)
            min_x = smooth_min_axis(masked_x_min, alpha=self.alpha, axis=1)
            max_y = smooth_max_axis(masked_y_max, alpha=self.alpha, axis=1)
            min_y = smooth_min_axis(masked_y_min, alpha=self.alpha, axis=1)

            hpwl = (max_x - min_x) + (max_y - min_y)
            path_loss = jnp.sum(hpwl * self.path_net_weights)

            total_loss = total_loss + path_loss
            metrics["power_path_hpwl"] = path_loss

        # --- 2. Loop Loss (Polygon Area) ---
        if self.loop_comp_indices.shape[0] > 0:
            # loop_comp_indices: (N_loops, Max_Loop_Size)

            # Safe indexing: replace -1 with 0, then mask later
            safe_indices = jnp.maximum(self.loop_comp_indices, 0)

            # Get positions of loop components (centroids)
            loop_pos = positions[safe_indices]  # (N_loops, Max_Loop_Size, 2)

            # Vectorized Shoelace Area Calculation
            x = loop_pos[..., 0]
            y = loop_pos[..., 1]

            # Use precomputed next indices to shift
            x_next = jnp.take_along_axis(x, self.loop_next_indices, axis=1)
            y_next = jnp.take_along_axis(y, self.loop_next_indices, axis=1)

            cross = x * y_next - x_next * y

            # Mask out entries corresponding to padding
            loss_mask = self.loop_comp_indices >= 0
            masked_cross = cross * loss_mask

            # Area = 0.5 * |sum(cross)|
            areas = 0.5 * jnp.abs(jnp.sum(masked_cross, axis=1))

            loop_loss = jnp.sum(areas * self.loop_weights)

            total_loss = total_loss + loop_loss
            metrics["power_loop_area"] = loop_loss

        return LossResult(
            value=total_loss,
            breakdown=metrics,
        )


def create_power_path_loss(
    netlist: Netlist,
    path_configs: list[HighCurrentPathConfig],
    loop_configs: list[SwitchingLoopConfig] = None,
    alpha: float = 10.0,
) -> PowerPathLoss:
    """
    Factory to create PowerPathLoss from netlist and configs.
    """
    if loop_configs is None:
        loop_configs = []
    net_name_to_idx = {net.name: i for i, net in enumerate(netlist.nets)}
    comp_name_to_idx = {comp.ref: i for i, comp in enumerate(netlist.components)}

    # 1. Prepare Paths
    path_indices = []
    path_weights = []

    for config in path_configs:
        p_weight = config.weight * (config.current_a**2)
        for net_name in config.nets:
            if net_name in net_name_to_idx:
                path_indices.append(net_name_to_idx[net_name])
                path_weights.append(p_weight)

    # 2. Prepare Loops
    loop_indices_list = []
    loop_weights_list = []

    max_loop_len = 0
    if loop_configs:
        max_loop_len = max(len(c.components) for c in loop_configs)

    # Ensure at least 1 to avoid empty shape errors
    max_loop_len = max(max_loop_len, 1)

    for config in loop_configs:
        idxs = []
        for d in config.components:  # type: ignore[attr-defined]
            if d in comp_name_to_idx:
                idxs.append(comp_name_to_idx[d])
            else:
                # Warning: Missing component in loop config
                pass

        if len(idxs) < 3:
            # Cannot form a polygon with < 3 points
            continue

        loop_indices_list.append(idxs)
        loop_weights_list.append(config.weight)

    # Pad loops
    N_loops = len(loop_indices_list)

    import numpy as np

    l_indices_np = np.full((N_loops, max_loop_len), -1, dtype=np.int32)
    l_next_np = np.zeros((N_loops, max_loop_len), dtype=np.int32)

    for i, idxs in enumerate(loop_indices_list):
        n = len(idxs)
        l_indices_np[i, :n] = idxs

        # Next indices: [1, 2, ..., n-1, 0] then 0 padding
        nexts = np.roll(np.arange(n), -1)  # [0,1,2] -> [1,2,0] if n=3
        l_next_np[i, :n] = nexts
        # Padding remains 0 (safe index)

    # If no loops, create empty arrays with correct dimensionality
    if N_loops == 0:
        l_indices_np = np.zeros((0, 0), dtype=np.int32)
        l_next_np = np.zeros((0, 0), dtype=np.int32)
        loop_weights_list = []

    return PowerPathLoss(
        path_net_indices=jnp.array(path_indices, dtype=jnp.int32),
        path_net_weights=jnp.array(path_weights, dtype=jnp.float32),
        loop_comp_indices=jnp.array(l_indices_np, dtype=jnp.int32),
        loop_next_indices=jnp.array(l_next_np, dtype=jnp.int32),
        loop_weights=jnp.array(loop_weights_list, dtype=jnp.float32),
        alpha=alpha,
    )
