"""
Consolidated loss functions for temper-placer.

This module provides unified versions of related losses to simplify the optimization
landscape. Instead of 40+ specialized losses, we move towards 8 core categories.
"""

from __future__ import annotations

from typing import Any

import jax.numpy as jnp
from jax import Array

from temper_placer.losses.aesthetic import AlignmentLoss
from temper_placer.losses.base import LossContext, LossFunction, LossResult
from temper_placer.losses.grid import GridAlignmentLoss
from temper_placer.losses.ground_crossing import GroundCrossingLoss
from temper_placer.losses.grouping import GroupClusterLoss, GroupSeparationLoss, ProximityLoss
from temper_placer.losses.loop_area import LoopAreaLoss
from temper_placer.losses.planarity import EdgeCrossingLoss
from temper_placer.losses.power_path import PowerPathLoss
from temper_placer.losses.return_path import ResolvedCurrentReturnPathLoss
from temper_placer.losses.star_point import StarPointLoss
from temper_placer.losses.thermal import ThermalLoss, ThermalSpreadLoss


class UnifiedGroupingLoss(LossFunction):
    """
    Unified loss for all grouping and proximity constraints.

    Combines:
    - Functional clustering (GroupClusterLoss)
    - Direct proximity rules (ProximityLoss)
    - Decoupling capacitor rules (DecouplingLoss)
    - Group separation (GroupSeparationLoss)
    """

    def __init__(
        self,
        cluster_loss: GroupClusterLoss | None = None,
        proximity_loss: ProximityLoss | None = None,
        separation_loss: GroupSeparationLoss | None = None,
    ):
        self.cluster_loss = cluster_loss
        self.proximity_loss = proximity_loss
        self.separation_loss = separation_loss

    @property
    def name(self) -> str:
        return "unified_grouping"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,  # noqa: ARG002
        **kwargs: Any,
    ) -> LossResult:
        total_val = jnp.array(0.0)
        breakdown = {}

        if self.cluster_loss:
            res = self.cluster_loss(positions, rotations, context, epoch, total_epochs, **kwargs)
            total_val += res.value
            breakdown.update({f"cluster_{k}": v for k, v in (res.breakdown or {}).items()})

        if self.proximity_loss:
            res = self.proximity_loss(positions, rotations, context, epoch, total_epochs, **kwargs)
            total_val += res.value
            breakdown.update({f"proximity_{k}": v for k, v in (res.breakdown or {}).items()})

        if self.separation_loss:
            res = self.separation_loss(positions, rotations, context, epoch, total_epochs, **kwargs)
            total_val += res.value
            breakdown.update({f"separation_{k}": v for k, v in (res.breakdown or {}).items()})

        return LossResult(value=total_val, breakdown=breakdown)

class UnifiedThermalLoss(LossFunction):
    """
    Unified loss for thermal and power path optimization.

    Combines:
    - Component thermal spread (ThermalSpreadLoss)
    - Edge heatsink proximity (ThermalLoss)
    - High-current path optimization (PowerPathLoss)
    """

    def __init__(
        self,
        spread_loss: ThermalSpreadLoss | None = None,
        edge_loss: ThermalLoss | None = None,
        power_path_loss: PowerPathLoss | None = None,
    ):
        self.spread_loss = spread_loss
        self.edge_loss = edge_loss
        self.power_path_loss = power_path_loss

    @property
    def name(self) -> str:
        return "unified_thermal"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,  # noqa: ARG002
        **kwargs: Any,
    ) -> LossResult:
        total_val = jnp.array(0.0)
        breakdown = {}

        if self.spread_loss:
            res = self.spread_loss(positions, rotations, context, epoch, total_epochs, **kwargs)
            total_val += res.value
            breakdown.update({f"spread_{k}": v for k, v in (res.breakdown or {}).items()})

        if self.edge_loss:
            res = self.edge_loss(positions, rotations, context, epoch, total_epochs, **kwargs)
            total_val += res.value
            breakdown.update({f"edge_{k}": v for k, v in (res.breakdown or {}).items()})

        if self.power_path_loss:
            res = self.power_path_loss(positions, rotations, context, epoch, total_epochs, **kwargs)
            total_val += res.value
            breakdown.update({f"power_{k}": v for k, v in (res.breakdown or {}).items()})

        return LossResult(value=total_val, breakdown=breakdown)

class UnifiedAestheticLoss(LossFunction):
    """
    Unified loss for visual and manufacturing aesthetics.

    Combines:
    - Alignment and symmetry (AestheticLoss)
    - Grid snapping (GridAlignmentLoss)
    - Orientation planarity (PlanarityLoss)
    """

    def __init__(
        self,
        aesthetic_loss: AlignmentLoss | None = None,
        grid_loss: GridAlignmentLoss | None = None,
        planarity_loss: EdgeCrossingLoss | None = None,
    ):
        self.aesthetic_loss = aesthetic_loss
        self.grid_loss = grid_loss
        self.planarity_loss = planarity_loss

    @property
    def name(self) -> str:
        return "unified_aesthetic"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,  # noqa: ARG002
        **kwargs: Any,
    ) -> LossResult:
        total_val = jnp.array(0.0)
        breakdown = {}

        if self.aesthetic_loss:
            res = self.aesthetic_loss(positions, rotations, context, epoch, total_epochs, **kwargs)
            total_val += res.value
            breakdown.update({f"aes_{k}": v for k, v in (res.breakdown or {}).items()})

        if self.grid_loss:
            res = self.grid_loss(positions, rotations, context, epoch, total_epochs, **kwargs)
            total_val += res.value
            breakdown.update({f"grid_{k}": v for k, v in (res.breakdown or {}).items()})

        if self.planarity_loss:
            res = self.planarity_loss(positions, rotations, context, epoch, total_epochs, **kwargs)
            total_val += res.value
            breakdown.update({f"planarity_{k}": v for k, v in (res.breakdown or {}).items()})

        return LossResult(value=total_val, breakdown=breakdown)

class UnifiedLoopLoss(LossFunction):
    """
    Unified loss for loop area and return path optimization.

    Combines:
    - Current loop area minimization (LoopAreaLoss)
    - Return path impedance minimization (CurrentReturnPathLoss)
    """

    def __init__(
        self,
        loop_area_loss: LoopAreaLoss | None = None,
        return_path_loss: ResolvedCurrentReturnPathLoss | None = None,
    ):
        self.loop_area_loss = loop_area_loss
        self.return_path_loss = return_path_loss

    @property
    def name(self) -> str:
        return "unified_loop"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,  # noqa: ARG002
        **kwargs: Any,
    ) -> LossResult:
        total_val = jnp.array(0.0)
        breakdown = {}

        if self.loop_area_loss:
            res = self.loop_area_loss(positions, rotations, context, epoch, total_epochs, **kwargs)
            total_val += res.value
            breakdown.update({f"loop_{k}": v for k, v in (res.breakdown or {}).items()})

        if self.return_path_loss:
            res = self.return_path_loss(positions, rotations, context, epoch, total_epochs, **kwargs)
            total_val += res.value
            breakdown.update({f"return_{k}": v for k, v in (res.breakdown or {}).items()})

        return LossResult(value=total_val, breakdown=breakdown)

class UnifiedStarPointLoss(LossFunction):
    """
    Unified loss for star point and ground split constraints.

    Combines:
    - Star point topology (StarPointLoss)
    - Ground crossing/split penalties (GroundCrossingLoss)
    """

    def __init__(
        self,
        star_point_loss: StarPointLoss | None = None,
        crossing_loss: GroundCrossingLoss | None = None,
    ):
        self.star_point_loss = star_point_loss
        self.crossing_loss = crossing_loss

    @property
    def name(self) -> str:
        return "unified_star_point"

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
        net_virtual_nodes: Array | None = None,  # noqa: ARG002
        **kwargs: Any,
    ) -> LossResult:
        total_val = jnp.array(0.0)
        breakdown = {}

        if self.star_point_loss:
            res = self.star_point_loss(positions, rotations, context, epoch, total_epochs, **kwargs)
            total_val += res.value
            breakdown.update({f"star_{k}": v for k, v in (res.breakdown or {}).items()})

        if self.crossing_loss:
            res = self.crossing_loss(positions, rotations, context, epoch, total_epochs, **kwargs)
            total_val += res.value
            breakdown.update({f"crossing_{k}": v for k, v in (res.breakdown or {}).items()})

        return LossResult(value=total_val, breakdown=breakdown)
