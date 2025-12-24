"""
Force-directed layout initialization heuristic.

Uses a spring-embedder model (Fruchterman-Reingold) to refine the initial
component placement. Nodes repel each other (preventing overlap) while
connected nodes attract each other (minimizing wirelength).
"""

from __future__ import annotations

import jax
import jax.numpy as jnp
import networkx as nx
import numpy as np

from temper_placer.core.board import Board
from temper_placer.core.netlist import build_adjacency_matrix
from temper_placer.core.state import PlacementState
from temper_placer.heuristics.base import (
    ComponentPlacement,
    Heuristic,
    HeuristicPriority,
    HeuristicResult,
    PlacementContext,
)
from temper_placer.heuristics.graph_utils import GraphBuilder


class ForceDirectedUnfoldingHeuristic(Heuristic):
    """
    JAX-based Force-Directed 'Unfolding' phase.

    This runs a preliminary physics simulation to untangle the graph topology
    before starting the formal optimization or analytical solvers.
    It uses simple differentiable repulsion and attraction.
    """

    def __init__(self, iterations: int = 500, learning_rate: float = 0.5):
        self.iterations = iterations
        self.lr = learning_rate

    @property
    def name(self) -> str:
        return "force_directed_unfolding"

    @property
    def priority(self) -> HeuristicPriority:
        return HeuristicPriority.INITIALIZATION

    @property
    def description(self) -> str:
        return "JAX-based graph unfolding warm-up"

    def apply(self, context: PlacementContext) -> HeuristicResult:
        n = context.netlist.n_components
        if n == 0:
            return HeuristicResult(success=True)

        # 1. Initialize from random or current if exists
        rng_key = context.rng_key if context.rng_key is not None else jax.random.PRNGKey(42)
        initial_pos = jnp.zeros((n, 2))
        for ref, p in context.current_placements.items():
            idx = context.netlist.get_component_index(ref)
            initial_pos = initial_pos.at[idx].set(jnp.array(p.position))

        if jnp.sum(jnp.abs(initial_pos)) < 1e-6:
            # Random init if nothing placed
            initial_state = PlacementState.random_init(
                n_components=n,
                board_width=context.board.width,
                board_height=context.board.height,
                key=rng_key,
                origin=context.board.origin,
                margin=context.constraints.board_margin_mm,
            )
            positions = initial_state.positions
        else:
            positions = initial_pos

        # 2. Run simulation
        curr_pos = compute_force_directed_layout(
            context.netlist,
            positions,
            iterations=self.iterations,
            learning_rate=self.lr
        )

        # 3. Clamp to board bounds (temper-p11g.1)
        ox, oy = context.board.origin
        margin = context.constraints.board_margin_mm
        curr_pos = jnp.clip(
            curr_pos,
            min=jnp.array([margin, margin]),
            max=jnp.array([context.board.width - margin, context.board.height - margin])
        )

        # 4. Map back to placements
        placements = {}
        for i, comp in enumerate(context.netlist.components):
            if comp.fixed:
                continue
            placements[comp.ref] = ComponentPlacement(
                ref=comp.ref,
                position=(float(curr_pos[i, 0]), float(curr_pos[i, 1])),
                rotation=0,
                confidence=0.3,
                placed_by=self.name,
            )

        return HeuristicResult(
            placements=placements,
            success=True,
            message=f"Unfolded graph over {self.iterations} iterations",
        )


def compute_force_directed_layout(
    netlist,
    initial_positions: jnp.ndarray,
    iterations: int = 500,
    learning_rate: float = 0.5,
) -> jnp.ndarray:
    """
    Run JAX-based force-directed simulation.
    
    Args:
        netlist: Netlist object with n_components and adjacency building capability.
        initial_positions: (N, 2) array of starting positions.
        iterations: Number of simulation steps.
        learning_rate: Step size for updates.
        
    Returns:
        (N, 2) array of refined positions.
    """
    # Build Adjacency for attraction
    adj = build_adjacency_matrix(netlist)
    # Get fixed mask
    fixed_mask = netlist.get_fixed_mask()

    # Physics Step
    @jax.jit
    def step(pos):
        # Repulsion (all-pairs)
        diff = pos[:, None, :] - pos[None, :, :]
        # Add epsilon to dist_sq to avoid division by zero
        dist_sq = jnp.sum(diff**2, axis=-1) + 1e-6
        # Add epsilon to dist_sq in division to be safe, though 1e-6 above handles it
        repulsion = jnp.sum(diff / dist_sq[:, :, None], axis=1)

        # Attraction (connected only)
        # Attraction force is proportional to distance (Hooke's law: F = -k*x)
        # Here we use F = -diff, so force increases with distance
        attraction = jnp.sum(adj[:, :, None] * -diff, axis=1)

        # Update
        new_pos = pos + learning_rate * (repulsion + attraction)
        
        # Determine strict bounds for updates
        # Ensure fixed components do not move
        new_pos = jnp.where(fixed_mask[:, None], pos, new_pos)
        
        return new_pos

    # Run simulation
    curr_pos = initial_positions
    for _ in range(iterations):
        curr_pos = step(curr_pos)

    return curr_pos


class ForceDirectedHeuristic(Heuristic):
    """
    Refine placements using Force-Directed (Spring) Layout.

    This heuristic treats components as charged particles (repulsion) connected
    by springs (attraction). It's excellent for untangling the "hairball" produced
    by spectral layout or random initialization.

    It respects pre-existing positions from earlier heuristics (like Spectral)
    and uses them as the starting state for the simulation.
    """

    def __init__(self, confidence: float = 0.2, iterations: int = 50, k: float | None = None):
        """
        Initialize force-directed placement.

        Args:
            confidence: Confidence score for these placements (0.0-1.0).
                        Slightly higher than Spectral (0.1) since this is a refinement.
            iterations: Number of simulation iterations.
            k: Optimal distance between nodes. If None, set to 1/sqrt(n).
               Increase this to spread components out more.
        """
        self._confidence = confidence
        self._iterations = iterations
        self._k = k

    @property
    def name(self) -> str:
        return "force_directed_layout"

    @property
    def priority(self) -> HeuristicPriority:
        # Run during initialization, but ideally AFTER spectral
        return HeuristicPriority.INITIALIZATION

    @property
    def description(self) -> str:
        return "Force-directed (spring) layout refinement"

    def apply(self, context: PlacementContext) -> HeuristicResult:
        """Apply force-directed layout."""
        builder = GraphBuilder(context.netlist)
        G = builder.build_graph()

        if len(G) == 0:
            return HeuristicResult(success=True, message="Empty graph")

        # 1. Prepare Initial Positions
        # If components have already been placed (e.g. by Spectral), use those positions.
        # NetworkX expects a dict {node: [x, y]}
        initial_pos = {}

        # We need to map board coordinates back to a somewhat normalized space for NetworkX,
        # or just use them as-is. NetworkX spring_layout is scale-agnostic but usually works
        # best in [0,1] or [-1,1]. Let's normalize current placements to [0,1] based on board.

        ox, oy = context.board.origin
        width, height = context.board.width, context.board.height

        for ref, placement in context.current_placements.items():
            if ref in G:
                # Normalize to [0, 1] relative to board
                nx_x = (placement.position[0] - ox) / width
                nx_y = (placement.position[1] - oy) / height
                initial_pos[ref] = np.array([nx_x, nx_y])

        # If we have no initial positions, spring_layout will start random.
        # But we only pass initial_pos if it's not empty, otherwise None.
        pos_arg = initial_pos if initial_pos else None

        # 2. Run Spring Layout
        # fixed: list of nodes with fixed coordinates.
        # We fix components that are explicitly marked as fixed in the netlist.
        fixed_nodes = []
        for ref in G.nodes():
            comp = context.netlist.get_component(ref)
            if comp and comp.fixed:
                fixed_nodes.append(ref)
                # Ensure fixed nodes are in initial_pos
                if ref not in initial_pos:
                    # This shouldn't happen if current_placements is up to date,
                    # but let's be safe.
                    # Default to center if unknown (unlikely for fixed comp)
                    initial_pos[ref] = np.array([0.5, 0.5])

        # If ALL nodes are fixed, nothing to do
        if len(fixed_nodes) == len(G):
            return HeuristicResult(success=True, message="All components fixed")

        try:
            # We assume the graph is connected or spring_layout handles components well.
            # weight='weight' uses the edge weights from GraphBuilder.
            refined_pos = nx.spring_layout(
                G,
                pos=pos_arg,
                fixed=fixed_nodes if fixed_nodes else None,
                iterations=self._iterations,
                weight="weight",
                k=self._k,  # optimal distance
                scale=1.0,  # Result fits in [-1, 1] usually, or [0, 1] if scale=1?
                # Docs say: "Scale factor for positions." Defaults to 1.
                # It centers around center (default origin).
                center=(0.5, 0.5),  # Center in [0,1] unit square
            )
        except Exception as e:
            return HeuristicResult(success=False, message=f"Spring layout failed: {str(e)}")

        # 3. Scale back to Board Dimensions
        # Since we centered at (0.5, 0.5) and scaled to fit, the output should be roughly in [0, 1].
        # However, spring_layout is not strict about bounds. We need to rescale.
        placements = self._scale_to_board(refined_pos, context.board, context)

        return HeuristicResult(
            placements=placements,
            success=True,
            message=f"Force-directed placement of {len(placements)} components",
        )

    def _scale_to_board(
        self, raw_pos: dict[str, np.ndarray], board: Board, context: PlacementContext
    ) -> dict[str, ComponentPlacement]:
        """Scale normalized coordinates to board dimensions."""
        placements: dict[str, ComponentPlacement] = {}

        # Board geometry
        ox, oy = board.origin
        margin = context.constraints.board_margin_mm

        # Usable area
        # We treat the output of spring_layout (centered at 0.5, 0.5) as being in the [0, 1] unit square
        # mapping directly to the usable board area.
        usable_w = board.width - 2 * margin
        usable_h = board.height - 2 * margin

        # Helper to clamp
        def clamp(val, min_val, max_val):
            return max(min_val, min(val, max_val))

        for ref, pos in raw_pos.items():
            # Don't move fixed components
            comp = context.netlist.get_component(ref)
            if comp.fixed:
                continue

            # pos is roughly in [0, 1] (because we set center=0.5,0.5)
            # but physics might push it outside.

            # Map [0, 1] -> [margin, width-margin]
            x = ox + margin + (pos[0] * usable_w)
            y = oy + margin + (pos[1] * usable_h)

            # Clamp to board bounds (respecting component size)
            half_w = comp.width / 2
            half_h = comp.height / 2

            x = clamp(x, ox + margin + half_w, ox + board.width - margin - half_w)
            y = clamp(y, oy + margin + half_h, oy + board.height - margin - half_h)

            placements[ref] = ComponentPlacement(
                ref=ref,
                position=(float(x), float(y)),
                rotation=0,  # Force-directed doesn't handle rotation
                confidence=self._confidence,
                placed_by=self.name,
            )

        return placements
