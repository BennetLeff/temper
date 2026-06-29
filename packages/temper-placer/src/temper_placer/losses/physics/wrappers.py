"""
Loss function wrappers for PhysicsHypergraph-based losses.
"""

from __future__ import annotations

from jax import Array

from temper_placer.losses.base import LossContext, LossFunction, LossResult
from temper_placer.losses.physics.hypergraph_losses import (
    high_voltage_repulsion_loss,
    hypergraph_wirelength_loss,
)


class HypergraphWirelengthLoss(LossFunction):
    """
    Computes HPWL using sparse hypergraph incidence matrix.

    Replaces the traditional net-iterative approach with a vectorized
    H.T @ P operation.
    """
    @property
    def name(self) -> str:
        return "wirelength"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
    ) -> LossResult:
        if context.hypergraph is None:
            # Fallback or error? For now, assume it's there as we added it to factory.
            # If optimizing without hypergraph, this loss shouldn't be used.
            return LossResult(value=0.0)

        value = hypergraph_wirelength_loss(positions, context.hypergraph)
        return LossResult(value=value)


class HighVoltageRepulsionLoss(LossFunction):
    """
    Computes repulsion between HV and LV components using hypergraph connectivity.
    """
    def __init__(self, min_clearance: float = 10.0):
        self.min_clearance = min_clearance

    @property
    def name(self) -> str:
        return "hv_repulsion"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
    ) -> LossResult:
        if context.hypergraph is None:
            return LossResult(value=0.0)

        value = high_voltage_repulsion_loss(
            positions,
            context.hypergraph,
            min_clearance=self.min_clearance
        )
        return LossResult(value=value)
