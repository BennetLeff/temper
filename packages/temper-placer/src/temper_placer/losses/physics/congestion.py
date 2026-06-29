"""
Routing Congestion loss functions.
"""

from __future__ import annotations

from jax import Array

from temper_placer.losses.base import LossContext, LossFunction
from temper_placer.losses.physics.hypergraph_losses import electrostatic_congestion_loss
from temper_placer.losses.types import LossResult


class ElectrostaticCongestionLoss(LossFunction):
    """
    Penalize routing congestion hotspots using electrostatic analogy.
    """

    @property
    def name(self) -> str:
        return "congestion"

    def __call__(
        self,
        positions: Array,
        _rotations: Array,
        context: LossContext,
        _epoch: int = 0,
        _total_epochs: int = 1,
        _net_virtual_nodes: Array | None = None,
    ) -> LossResult:
        if context.hypergraph is None:
            return LossResult(value=jnp.array(0.0))

        loss = electrostatic_congestion_loss(
            positions,
            context.hypergraph,
            context.board.width,
            context.board.height,
            grid_size=32 # Fixed small grid for performance
        )

        return LossResult(value=jnp.array(loss))
