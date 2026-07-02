"""
Component-level loop area loss — minimizes polygon area formed by component centers.

Unlike LoopAreaLoss (which requires pin-level precision with correct pin names),
this operates on component references from pcb_spec.yaml. It matches what
loop_area_score in quality.py measures (component center positions, shoelace).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import jax

if TYPE_CHECKING:
    from temper_placer.explainability.trace import Trace
import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import LossContext, LossFunction, LossResult


@dataclass
class ComponentLoopConfig:
    """Configuration for a component-level loop."""
    name: str
    component_refs: list[str]
    max_area_mm2: float
    weight: float = 10.0
    because: str = ""


class ComponentLoopAreaLoss(LossFunction):
    """
    Penalize large polygon areas formed by component centers.

    For each loop defined by component refs, computes the shoelace polygon
    area from component center positions and penalizes areas exceeding max_area.
    Rotation-aware bounds are NOT used — this uses center positions only,
    matching the loop_area_score metric.

    Args:
        loops: List of ComponentLoopConfig defining each loop.
        margin: Soft margin for penalty transition (mm²).
    """

    def __init__(self, loops: list[ComponentLoopConfig], margin: float = 10.0,
                 min_separation_mm: float = 2.0):
        self.loops = loops
        self.margin = margin
        self.min_separation_mm = min_separation_mm

    @property
    def name(self) -> str:
        return "component_loop_area"

    def __call__(
        self,
        positions: Array,
        rotations: Array,  # noqa: ARG002
        context: LossContext,
        epoch: int = 0,  # noqa: ARG002
        total_epochs: int = 1,  # noqa: ARG002
        net_virtual_nodes: Array | None = None,  # noqa: ARG002
    ) -> LossResult:
        total_penalty = jnp.array(0.0)
        breakdown = {}

        for loop in self.loops:
            # Resolve component indices
            indices = []
            for ref in loop.component_refs:
                try:
                    idx = context.get_component_index(ref)
                    indices.append(idx)
                except KeyError:
                    pass

            if len(indices) < 3:
                breakdown[loop.name] = 0.0
                continue

            # Get component center positions
            idx_array = jnp.array(indices, dtype=jnp.int32)
            verts = positions[idx_array]  # (K, 2)

            # Shoelace formula for polygon area
            verts_next = jnp.roll(verts, -1, axis=0)
            cross = verts[:, 0] * verts_next[:, 1] - verts_next[:, 0] * verts[:, 1]
            area = jnp.abs(jnp.sum(cross)) / 2.0

            breakdown[loop.name] = area

            # Soft penalty: softplus(excess/margin) where excess = area - max_area
            excess = area - loop.max_area_mm2
            soft_excess = self.margin * jax.nn.softplus(excess / self.margin)
            penalty = loop.weight * soft_excess**2

            total_penalty = total_penalty + penalty

            # Minimum-separation floor: prevent components in the same loop
            # from being stacked on top of each other when loop area weight is low
            if self.min_separation_mm > 0.0 and len(idx_array) >= 2:
                # Compute pairwise distances
                diffs = verts[:, None, :] - verts[None, :, :]  # (K, K, 2)
                dists = jnp.sqrt(jnp.sum(diffs**2, axis=-1) + 1e-12)  # (K, K)
                upper = jnp.triu(jnp.ones_like(dists), k=1)
                # Penalize pairs below min_separation
                too_close = jax.nn.relu(self.min_separation_mm - dists)
                sep_penalty = 10.0 * jnp.sum(too_close * upper)
                total_penalty = total_penalty + sep_penalty

        return LossResult(value=total_penalty, breakdown=breakdown)

    def weight_schedule(self, epoch: int, total_epochs: int) -> float:
        """Introduce loop area after feasibility (40% of training)."""
        progress = epoch / jnp.maximum(total_epochs, 1)
        return jnp.where(progress < 0.4, 0.0,
                         jnp.where(progress < 0.6, (progress - 0.4) / 0.2, 1.0))

    def trace(
        self,
        positions: Array,
        rotations: Array,  # noqa: ARG002
        context: LossContext,
        epoch: int = 0,  # noqa: ARG002
        total_epochs: int = 1,  # noqa: ARG002
    ) -> tuple[Array, Trace]:
        from temper_placer.explainability.trace import Trace

        result = self(positions, rotations, context, epoch, total_epochs)
        trace = Trace.empty()

        for loop in self.loops:
            area = float(result.breakdown.get(loop.name, 0.0))
            if area > loop.max_area_mm2:
                trace = trace.add(
                    f"Loop:{loop.name}",
                    float(loop.weight * (area - loop.max_area_mm2)**2),
                    f"Loop {loop.name}: {area:.0f} mm² (max {loop.max_area_mm2:.0f} mm²)",
                )
        return result.value, trace
