"""
Heuristic pipeline orchestrator.

The HeuristicPipeline runs all registered heuristics in priority order,
managing the flow of placement information between them and resolving
conflicts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Type

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.core.state import PlacementState
from temper_placer.io.config_loader import PlacementConstraints
from temper_placer.heuristics.base import (
    ComponentPlacement,
    Heuristic,
    HeuristicPriority,
    HeuristicResult,
    PlacementContext,
)
from temper_placer.heuristics.conflict import ConflictResolver, ResolutionStrategy


@dataclass
class PipelineResult:
    """
    Result of running the full heuristic pipeline.

    Attributes:
        placements: Final component placements
        state: JAX-compatible PlacementState for optimization
        conflicts: All conflicts encountered
        heuristic_stats: Stats for each heuristic (components placed, conflicts, etc.)
        unplaced: Components that couldn't be placed by any heuristic
    """

    placements: Dict[str, ComponentPlacement]
    state: PlacementState
    conflicts: List[str]
    heuristic_stats: Dict[str, Dict]
    unplaced: List[str]


class HeuristicPipeline:
    """
    Orchestrates the execution of placement heuristics.

    The pipeline:
    1. Registers heuristics (can be done at class definition or runtime)
    2. Sorts heuristics by priority
    3. Executes each heuristic in order
    4. Resolves conflicts between placements
    5. Fills in remaining components with random placement

    Example:
        pipeline = HeuristicPipeline()
        pipeline.register(ThermalEdgeHeuristic())
        pipeline.register(ConnectorSnapHeuristic())

        result = pipeline.run(board, netlist, constraints, key)
        state = result.state  # Ready for optimization
    """

    def __init__(
        self,
        conflict_strategy: ResolutionStrategy = ResolutionStrategy.NUDGE,
        min_spacing_mm: float = 0.5,
    ):
        """
        Initialize the pipeline.

        Args:
            conflict_strategy: How to resolve placement conflicts
            min_spacing_mm: Minimum spacing between components
        """
        self.heuristics: List[Heuristic] = []
        self.conflict_strategy = conflict_strategy
        self.min_spacing_mm = min_spacing_mm

    def register(self, heuristic: Heuristic) -> None:
        """
        Register a heuristic with the pipeline.

        Heuristics are automatically sorted by priority when run.
        """
        self.heuristics.append(heuristic)

    def register_all(self, heuristics: List[Heuristic]) -> None:
        """Register multiple heuristics."""
        for h in heuristics:
            self.register(h)

    def clear(self) -> None:
        """Clear all registered heuristics."""
        self.heuristics.clear()

    def run(
        self,
        board: Board,
        netlist: Netlist,
        constraints: PlacementConstraints,
        key: Array,
        keep_out_mask: Optional[Array] = None,
    ) -> PipelineResult:
        """
        Run all heuristics to generate an initial placement.

        Args:
            board: Board geometry
            netlist: Components and nets
            constraints: Placement constraints
            key: JAX random key for stochastic decisions
            keep_out_mask: Optional (H, W) boolean mask of valid regions

        Returns:
            PipelineResult with final placements and JAX state
        """
        # Sort heuristics by priority
        sorted_heuristics = sorted(self.heuristics, key=lambda h: h.priority)

        # Initialize context
        context = PlacementContext(
            board=board,
            netlist=netlist,
            constraints=constraints,
            current_placements={},
            keep_out_mask=keep_out_mask,
            rng_key=key,
        )

        # Initialize conflict resolver
        resolver = ConflictResolver(
            strategy=self.conflict_strategy,
            min_spacing_mm=self.min_spacing_mm,
        )

        # Track stats
        heuristic_stats: Dict[str, Dict] = {}
        all_conflicts: List[str] = []

        # Run each heuristic
        for heuristic in sorted_heuristics:
            result = heuristic.apply(context)

            # Resolve conflicts and add placements
            placed_count = 0
            conflict_count = 0

            for ref, placement in result.placements.items():
                comp = netlist.get_component(ref)
                resolved, conflict = resolver.resolve(
                    placement,
                    comp.bounds[0],
                    comp.bounds[1],
                    context,
                )

                if resolved is not None:
                    context.current_placements[ref] = resolved
                    resolver.add_placement(resolved)
                    placed_count += 1

                if conflict is not None:
                    conflict_count += 1
                    all_conflicts.append(conflict.message)

            # Record stats
            heuristic_stats[heuristic.name] = {
                "priority": heuristic.priority.name,
                "placed": placed_count,
                "conflicts": conflict_count,
                "success": result.success,
                "message": result.message,
            }

            # Update key for next heuristic
            if context.rng_key is not None:
                context.rng_key, _ = jax.random.split(context.rng_key)

        # Fill remaining components with random placement
        unplaced_components = context.get_unplaced_components()
        unplaced_refs = []

        if unplaced_components and context.rng_key is not None:
            fill_result = self._fill_remaining(context, resolver)

            for ref, placement in fill_result.placements.items():
                if ref not in context.current_placements:
                    context.current_placements[ref] = placement
                    resolver.add_placement(placement)

            # Check for truly unplaced
            unplaced_refs = [
                c.ref for c in unplaced_components if c.ref not in context.current_placements
            ]

            heuristic_stats["random_fill"] = {
                "priority": "FILL",
                "placed": len(fill_result.placements),
                "conflicts": len(fill_result.conflicts),
                "success": fill_result.success,
                "message": fill_result.message,
            }

        # Convert to JAX state
        state = self._to_placement_state(context, netlist)

        return PipelineResult(
            placements=context.current_placements,
            state=state,
            conflicts=all_conflicts,
            heuristic_stats=heuristic_stats,
            unplaced=unplaced_refs,
        )

    def _fill_remaining(
        self,
        context: PlacementContext,
        resolver: ConflictResolver,
    ) -> HeuristicResult:
        """
        Fill remaining components with random placement.

        Tries to place each component in a valid position, respecting
        keep-outs and avoiding overlaps.
        """
        result = HeuristicResult()
        unplaced = context.get_unplaced_components()

        if not unplaced or context.rng_key is None:
            return result

        key = context.rng_key
        margin = context.constraints.board_margin_mm
        ox, oy = context.board.origin

        for comp in unplaced:
            key, subkey = jax.random.split(key)

            # Try up to 100 random positions
            placed = False
            for _ in range(100):
                key, subkey = jax.random.split(key)

                # Random position within bounds
                x = float(
                    jax.random.uniform(
                        subkey,
                        minval=ox + margin + comp.width / 2,
                        maxval=ox + context.board.width - margin - comp.width / 2,
                    )
                )
                key, subkey = jax.random.split(key)
                y = float(
                    jax.random.uniform(
                        subkey,
                        minval=oy + margin + comp.height / 2,
                        maxval=oy + context.board.height - margin - comp.height / 2,
                    )
                )

                # Check validity
                if not context.is_position_valid(x, y, comp.width, comp.height):
                    continue

                # Check overlap with existing placements
                placement = ComponentPlacement(
                    ref=comp.ref,
                    position=(x, y),
                    rotation=0,
                    confidence=0.5,
                    placed_by="random_fill",
                )

                resolved, conflict = resolver.resolve(
                    placement,
                    comp.width,
                    comp.height,
                    context,
                )

                if resolved is not None:
                    result.placements[comp.ref] = resolved
                    resolver.add_placement(resolved)
                    placed = True
                    break

            if not placed:
                result.conflicts.append(f"Could not place {comp.ref} after 100 attempts")

        return result

    def _to_placement_state(
        self,
        context: PlacementContext,
        netlist: Netlist,
    ) -> PlacementState:
        """
        Convert placements to a JAX PlacementState.

        Components are ordered according to their index in the netlist.
        """
        n_components = netlist.n_components
        positions = jnp.zeros((n_components, 2), dtype=jnp.float32)
        rotation_logits = jnp.zeros((n_components, 4), dtype=jnp.float32)

        for comp in netlist.components:
            idx = netlist.get_component_index(comp.ref)

            if comp.ref in context.current_placements:
                placement = context.current_placements[comp.ref]
                positions = positions.at[idx].set(jnp.array(placement.position))

                # Set rotation logits to strongly prefer the chosen rotation
                rot_idx = placement.rotation
                logits = jnp.array([-10.0, -10.0, -10.0, -10.0])
                logits = logits.at[rot_idx].set(10.0)
                rotation_logits = rotation_logits.at[idx].set(logits)

            elif comp.initial_position is not None:
                # Use initial position from netlist
                positions = positions.at[idx].set(jnp.array(comp.initial_position))
                if comp.initial_rotation is not None:
                    rot_idx = comp.initial_rotation
                    logits = jnp.array([-10.0, -10.0, -10.0, -10.0])
                    logits = logits.at[rot_idx].set(10.0)
                    rotation_logits = rotation_logits.at[idx].set(logits)

            else:
                # Fallback: center of board (shouldn't happen if fill works)
                ox, oy = context.board.origin
                center = jnp.array(
                    [
                        ox + context.board.width / 2,
                        oy + context.board.height / 2,
                    ]
                )
                positions = positions.at[idx].set(center)

        return PlacementState(positions=positions, rotation_logits=rotation_logits)

    def get_registered_heuristics(self) -> List[Tuple[str, HeuristicPriority]]:
        """Get list of registered heuristics with their priorities."""
        return [(h.name, h.priority) for h in self.heuristics]


def create_default_pipeline(
    conflict_strategy: ResolutionStrategy = ResolutionStrategy.NUDGE,
) -> HeuristicPipeline:
    """
    Create a pipeline with standard heuristics.

    This factory includes:
    1. Spectral Layout (Initial global placement)
    2. Force Directed Layout (Refinement)
    3. (Other heuristics to be added...)
    """
    from temper_placer.heuristics.spectral import SpectralPlacementHeuristic
    from temper_placer.heuristics.force_directed import ForceDirectedHeuristic

    pipeline = HeuristicPipeline(conflict_strategy=conflict_strategy)

    # Priority: INITIALIZATION (-1)
    # Spectral first (global structure)
    pipeline.register(SpectralPlacementHeuristic(confidence=0.1))
    # Force-directed second (refinement of spectral)
    pipeline.register(ForceDirectedHeuristic(confidence=0.2, iterations=50))

    # TODO: Add Hard, Structural, Organizational, Style heuristics

    return pipeline
