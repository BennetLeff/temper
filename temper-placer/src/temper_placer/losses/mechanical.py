from typing import List, Optional, Tuple, Any
from dataclasses import dataclass, field
import jax.numpy as jnp
from temper_placer.losses.base import LossFunction, LossResult, LossContext, MountingRule
from temper_placer.core.board import Board


@dataclass
class ResolvedMountingRule:
    """Resolved data for mechanical mounting loss."""

    component_idx: int
    rule_type_idx: int  # 0:edge, 1:near_mount, 2:fixed_pos, 3:accessible

    # Edge constraints (encoded as indices or distances)
    # Edge index: 0=TOP, 1=BOTTOM, 2=LEFT, 3=RIGHT, -1=None
    edge_idx: int

    max_distance_mm: float
    weight: float

    # For near_mount (multiple mount points)
    # We flatten mount points into a single array for all rules?
    # Or just store them here if we aren't batching fully.
    # To be JAX-friendly, we should probably pass arrays.
    # For now, let's keep it simple and iterate in Python loop inside __call__
    # if performance allows, or pre-compute arrays if we need massive speed.
    mount_positions: jnp.ndarray  # (M, 2)

    # For fixed_position
    target_position: jnp.ndarray  # (2,)


class MechanicalMountingLoss(LossFunction):
    """
    Enforce mechanical placement constraints.
    - Connectors on edges
    - Heavy components near mounts
    - UI elements at fixed positions
    - Accessibility
    """

    def __init__(self, rules: List[ResolvedMountingRule]):
        self.rules = rules

    @property
    def name(self) -> str:
        return "mechanical_mounting"

    def __call__(
        self, positions: jnp.ndarray, rotations: jnp.ndarray, context: LossContext
    ) -> LossResult:
        total_loss = jnp.array(0.0)
        board = context.board

        # Board dimensions for edge calculations
        # Using context.bounds might be needed if component size matters for edge distance
        # But usually we place component CENTER or specific anchor.
        # Let's assume CENTER for now.

        # We need board edges.
        # Board is defined by origin (0,0) usually?
        # Or context.board.width, context.board.height

        # Note: In JAX, we cannot iterate over python lists if we want full JIT unless unrolled.
        # Since rules are configuration (static structure), we can iterate over them
        # and JAX will unroll the loop during tracing.

        for rule in self.rules:
            comp_pos = positions[rule.component_idx]

            # 0: Edge Rule
            if rule.rule_type_idx == 0:
                dist = jnp.array(0.0)
                # 0=TOP (max Y), 1=BOTTOM (min Y), 2=LEFT (min X), 3=RIGHT (max X)
                # Assumes board origin at (0,0) and extends to (width, height)

                if rule.edge_idx == 0:  # TOP (Y = height)
                    dist = jnp.abs(comp_pos[1] - board.height)
                elif rule.edge_idx == 1:  # BOTTOM (Y = 0)
                    dist = jnp.abs(comp_pos[1] - 0.0)
                elif rule.edge_idx == 2:  # LEFT (X = 0)
                    dist = jnp.abs(comp_pos[0] - 0.0)
                elif rule.edge_idx == 3:  # RIGHT (X = width)
                    dist = jnp.abs(comp_pos[0] - board.width)

                violation = jnp.maximum(0.0, dist - rule.max_distance_mm)
                total_loss = total_loss + (violation**2 * rule.weight)

            # 1: Near Mount Rule
            elif rule.rule_type_idx == 1:
                # Minimum distance to ANY mount point
                # mount_positions: (M, 2)
                # comp_pos: (2,)

                if rule.mount_positions.shape[0] > 0:
                    diff = comp_pos[None, :] - rule.mount_positions
                    dists_sq = jnp.sum(diff**2, axis=-1)
                    min_dist_sq = jnp.min(dists_sq)
                    min_dist = jnp.sqrt(min_dist_sq + 1e-6)

                    violation = jnp.maximum(0.0, min_dist - rule.max_distance_mm)
                    total_loss = total_loss + (violation**2 * rule.weight)

            # 2: Fixed Position Rule
            elif rule.rule_type_idx == 2:
                diff = comp_pos - rule.target_position
                dist_sq = jnp.sum(diff**2)
                dist = jnp.sqrt(dist_sq + 1e-6)

                # For fixed position, we penalize ANY distance from target
                total_loss = total_loss + (dist**2 * rule.weight)

            # 3: Accessible Rule (Placeholder - complex geometric check)
            # Checking if "blocked by tall components" requires height info (3D)
            # and "blocking" definition (cone? cylinder?).
            # For now, we skip or implement basic 2D clearance from other components?
            # The prompt implies "not blocked by tall components".
            # We don't have height info easily accessible in context.bounds (it's 2D).
            # We can implement a simple "clearance from specific other components" if provided.
            # But without height data, "accessible" is hard.
            # Let's leave as placeholder or implement minimal logic.
            elif rule.rule_type_idx == 3:
                pass

        return LossResult(value=total_loss)


def create_mechanical_loss(
    netlist,
    mounting_rules: List[MountingRule],
) -> MechanicalMountingLoss:
    """
    Factory to resolve component references to indices and create loss.
    """
    resolved_rules = []

    # Map edge string to int index
    edge_map = {
        "TOP": 0,
        "top": 0,
        "BOTTOM": 1,
        "bottom": 1,
        "LEFT": 2,
        "left": 2,
        "RIGHT": 3,
        "right": 3,
    }

    rule_type_map = {"edge": 0, "near_mount": 1, "fixed_position": 2, "accessible": 3}

    for rule in mounting_rules:
        # Resolve rule type
        r_type_idx = rule_type_map.get(rule.rule_type, -1)
        if r_type_idx == -1:
            continue  # Invalid rule type

        # Resolve edge
        edge_idx = -1
        if rule.edge:
            edge_idx = edge_map.get(rule.edge, -1)

        # Resolve mount positions
        mounts = jnp.zeros((0, 2))
        if rule.mount_positions:
            mounts = jnp.array(rule.mount_positions, dtype=jnp.float32)

        # Resolve target position
        target = jnp.zeros((2,), dtype=jnp.float32)
        if rule.target_position:
            target = jnp.array(rule.target_position, dtype=jnp.float32)

        # Default max_distance
        max_dist = rule.max_distance_mm if rule.max_distance_mm is not None else 0.0

        resolved_rules.append(
            ResolvedMountingRule(
                component_idx=rule.component_idx,
                rule_type_idx=r_type_idx,
                edge_idx=edge_idx,
                max_distance_mm=float(max_dist),
                weight=float(rule.weight),
                mount_positions=mounts,
                target_position=target,
            )
        )

    return MechanicalMountingLoss(resolved_rules)
