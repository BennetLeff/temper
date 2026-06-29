from dataclasses import dataclass

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import LossContext, LossFunction, LossResult


@dataclass
class ReturnPathConfig:
    """Configuration for return path optimization."""

    source: str
    dest: str
    weight: float = 1.0


class CurrentReturnPathLoss(LossFunction):
    """
    Minimizes current return path impedance by penalizing obstacles in the
    likely return path corridor between signal source and destination.
    """

    def __init__(
        self,
        critical_nets: list[ReturnPathConfig],
        corridor_width: float = 3.0,
    ):
        # LossFunction doesn't take weight in init usually, it's handled by WeightedLoss wrapper
        # or it is mixed in. But WeightedLoss wraps a LossFunction.
        # If we inherit from LossFunction directly, we don't have self.weight unless we add it.
        # Base LossFunction is just an interface.
        # Let's check base.py for LossFunction definition.
        # It seems WeightedLoss wraps it.
        # But commonly we implement __call__ to return unweighted value,
        # and the framework weights it.
        pass

    @property
    def name(self) -> str:
        return "current_return_path"

    def __call__(
        self,
        _positions: jnp.ndarray,
        _rotations: jnp.ndarray,
        _context: LossContext,
        _epoch: int = 0,
        _total_epochs: int = 1,
        _net_virtual_nodes: Array | None = None,
    ) -> LossResult:
        return LossResult(value=jnp.array(0.0))


class ResolvedCurrentReturnPathLoss(LossFunction):
    def __init__(self, resolved_nets, corridor_width):
        self.resolved_nets = resolved_nets
        self.corridor_width = corridor_width

    @property
    def name(self) -> str:
        return "current_return_path"

    def __call__(
        self,
        positions: jnp.ndarray,
        _rotations: jnp.ndarray,
        _context: LossContext,
        _epoch: int = 0,
        _total_epochs: int = 1,
        _net_virtual_nodes: Array | None = None,
    ) -> LossResult:
        total_loss = jnp.array(0.0)

        # We can loop in python because resolved_nets is static list
        for net in self.resolved_nets:
            src_idx = net["src_idx"]
            dst_idx = net["dst_idx"]
            net_weight = net["weight"]

            p_src = positions[src_idx]
            p_dst = positions[dst_idx]

            # Vector from src to dst
            diff = p_dst - p_src
            dist_sq = jnp.sum(diff**2)
            dist = jnp.sqrt(dist_sq + 1e-6)

            # Normalized direction vector
            direction = diff / (dist + 1e-6)

            # Normal vector (rotated 90 deg)
            normal = jnp.array([-direction[1], direction[0]])

            # Vectorize over all components
            V_sp = positions - p_src  # (N, 2)

            proj_long = jnp.sum(V_sp * direction, axis=1)  # (N,)
            proj_lat = jnp.abs(jnp.sum(V_sp * normal, axis=1))  # (N,)

            # Parameters
            comp_radius = 2.0
            limit_lat = (self.corridor_width / 2.0) + comp_radius
            beta = 5.0  # Sigmoid sharpness

            # Masks
            mask_long_start = jax.nn.sigmoid(beta * proj_long)
            mask_long_end = jax.nn.sigmoid(beta * (dist - proj_long))
            mask_long = mask_long_start * mask_long_end

            mask_lat = jax.nn.sigmoid(beta * (limit_lat - proj_lat))

            intrusion = mask_long * mask_lat

            # Zero out src and dst
            N = positions.shape[0]
            # Create a boolean mask for indices that are NOT src or dst
            # Since src_idx/dst_idx are ints, we can't use 'is'
            arange = jnp.arange(N)
            idx_mask = (arange != src_idx) & (arange != dst_idx)

            weighted_intrusion = intrusion * idx_mask

            total_loss = total_loss + jnp.sum(weighted_intrusion) * net_weight

        return LossResult(value=total_loss)


def create_return_path_loss(
    netlist,
    critical_nets: list[ReturnPathConfig | dict],
    corridor_width: float = 3.0,
) -> ResolvedCurrentReturnPathLoss:
    """
    Factory to resolve component names to indices.
    Returns an instance of ResolvedCurrentReturnPathLoss.

    Args:
        netlist: Netlist with components to resolve
        critical_nets: List of ReturnPathConfig objects or dicts with 'source', 'dest', 'weight' keys
        corridor_width: Width of the return path corridor
    """
    resolved_nets = []
    # Netlist might have different attribute for components ref
    # Assuming c.ref based on previous files
    comp_map = {c.ref: i for i, c in enumerate(netlist.components)}

    for net in critical_nets:
        # Handle both dict and ReturnPathConfig dataclass
        if isinstance(net, dict):
            s = net.get("source")
            d = net.get("dest")
            w = net.get("weight", 1.0)
        else:
            s = net.source
            d = net.dest
            w = net.weight

        if s in comp_map and d in comp_map:
            resolved_nets.append(
                {
                    "src_idx": comp_map[s],
                    "dst_idx": comp_map[d],
                    "weight": float(w),
                }
            )

    return ResolvedCurrentReturnPathLoss(
        resolved_nets=resolved_nets,
        corridor_width=corridor_width,
    )
