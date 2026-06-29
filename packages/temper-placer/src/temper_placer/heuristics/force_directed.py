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

DEFAULT_NET_CLASS_WEIGHTS: dict[str, float] = {
    "Signal": 1.0,
    "Clock": 2.0,
    "Critical": 1.5,
    "HighSpeed": 1.5,
    "Power": 0.5,
    "GND": 0.3,
}


def build_weighted_adjacency_matrix(
    netlist,
    net_class_weights: dict[str, float] | None = None,
) -> jnp.ndarray:
    """
    Build weighted adjacency matrix from netlist.

    Weights are based on:
    1. Net weight/priority (from netlist)
    2. Net class multiplier (Clock, Critical, Power, etc.)
    3. Inverse of pin count (high-fanout nets weighted lower per-edge)

    Args:
        netlist: Netlist with components and nets.
        net_class_weights: Optional overrides for net class multipliers.

    Returns:
        (N, N) weighted adjacency matrix as JAX array.
    """
    if net_class_weights is None:
        net_class_weights = DEFAULT_NET_CLASS_WEIGHTS

    n = netlist.n_components
    adj = np.zeros((n, n), dtype=np.float32)

    for net in netlist.nets:
        base_weight = net.weight

        class_multiplier = net_class_weights.get(net.net_class, 1.0)
        base_weight *= class_multiplier

        n_pins = net.pin_count
        edge_weight = base_weight / np.sqrt(n_pins - 1) if n_pins > 2 else base_weight

        comp_refs = net.get_component_refs()
        comp_indices = [netlist.get_component_index(ref) for ref in comp_refs]

        for i in range(len(comp_indices)):
            for j in range(i + 1, len(comp_indices)):
                ci, cj = comp_indices[i], comp_indices[j]
                adj[ci, cj] = max(adj[ci, cj], edge_weight)
                adj[cj, ci] = max(adj[cj, ci], edge_weight)

    return jnp.array(adj)


class ForceDirectedUnfoldingHeuristic(Heuristic):
    """
    JAX-based Force-Directed 'Unfolding' phase.

    This runs a preliminary physics simulation to untangle the graph topology
    before starting the formal optimization or analytical solvers.
    It uses simple differentiable repulsion and attraction.
    """

    def __init__(
        self,
        iterations: int = 500,
        learning_rate: float = 0.5,
        repulsion_k: float | None = None,
        repulsion_power: float = 1.0,
    ):
        self.iterations = iterations
        self.lr = learning_rate
        self.repulsion_k = repulsion_k
        self.repulsion_power = repulsion_power

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

        # Compute optimal k from board area if not provided
        board_area = context.board.width * context.board.height
        if self.repulsion_k is None:
            optimal_k = float(jnp.sqrt(board_area / n))
        else:
            optimal_k = self.repulsion_k

        # 1. Initialize positions - use random for ALL, then override with placed components
        # This ensures unplaced components have valid non-zero positions for physics
        rng_key = context.rng_key if context.rng_key is not None else jax.random.PRNGKey(42)

        initial_state = PlacementState.random_init(
            n_components=n,
            board_width=context.board.width,
            board_height=context.board.height,
            key=rng_key,
            origin=context.board.origin,
            margin=context.constraints.board_margin_mm,
        )
        positions = initial_state.positions

        # Override with positions from already-placed components
        for ref, p in context.current_placements.items():
            idx = context.netlist.get_component_index(ref)
            positions = positions.at[idx].set(jnp.array(p.position))

        # 2. Run simulation with weighted adjacency
        weighted_adj = build_weighted_adjacency_matrix(context.netlist)
        curr_pos = compute_force_directed_layout(
            context.netlist,
            positions,
            board_width=context.board.width,
            board_height=context.board.height,
            board_origin=context.board.origin,
            iterations=self.iterations,
            learning_rate=self.lr,
            repulsion_k=optimal_k,
            repulsion_power=self.repulsion_power,
            weighted_adj=weighted_adj,
        )

        # 3. Clamp to board bounds (temper-p11g.1)
        ox, oy = context.board.origin
        margin = context.constraints.board_margin_mm
        curr_pos = jnp.clip(
            curr_pos,
            min=jnp.array([margin, margin]),
            max=jnp.array([context.board.width - margin, context.board.height - margin]),
        )

        # 4. Map back to placements
        placements = {}
        for i, comp in enumerate(context.netlist.components):
            if comp.fixed:
                continue
            # Skip components already placed by higher-priority heuristics
            if comp.ref in context.current_placements:
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
    board_width: float = 100.0,
    board_height: float = 100.0,
    board_origin: tuple[float, float] = (0.0, 0.0),
    iterations: int = 500,
    learning_rate: float = 0.5,
    repulsion_k: float = 10.0,
    repulsion_power: float = 1.0,
    weighted_adj: jnp.ndarray | None = None,
    attraction_k: float = 0.1,
    initial_temp: float | None = None,
    cooling_factor: float = 0.97,
    min_temp: float = 0.1,
) -> jnp.ndarray:
    """
    Run JAX-based force-directed simulation using standard Fruchterman-Reingold.

    Standard F-R uses:
    - Repulsion: F = k² / d (force magnitude proportional to 1/distance)
    - Attraction: F = d (spring force proportional to distance)
    - Temperature annealing: displacement is clamped by decreasing temperature

    Args:
        netlist: Netlist object with n_components and adjacency building capability.
        initial_positions: (N, 2) array of starting positions.
        board_width: Actual board width in mm.
        board_height: Actual board height in mm.
        board_origin: Board origin (x, y) in mm. Defaults to (0, 0).
        iterations: Number of simulation steps.
        learning_rate: Step size for updates.
        repulsion_k: Repulsion strength parameter. Optimal k = sqrt(area / n).
                     If not provided, computed from board area.
        repulsion_power: Power for distance falloff. 1.0 = standard F-R (1/r),
                        2.0 = quadratic (1/r²), values < 1.0 for stronger long-range repulsion.
        weighted_adj: Optional pre-computed weighted adjacency matrix. If None,
                     uses binary adjacency from netlist.
        attraction_k: Spring constant for attraction forces. Higher = stronger pull.
        initial_temp: Initial temperature for annealing. If None, computed from board diagonal.
                     Components can move up to this distance per iteration early on.
        cooling_factor: Temperature multiplier per iteration. Lower = faster cooling.
        min_temp: Minimum temperature (displacement won't shrink below this).

    Returns:
        (N, 2) array of refined positions.
    """
    n = len(initial_positions)

    adj = build_adjacency_matrix(netlist) if weighted_adj is None else weighted_adj

    fixed_mask = netlist.get_fixed_mask()

    origin_x, origin_y = board_origin
    bounds_min = jnp.array([origin_x, origin_y])
    bounds_max = jnp.array([origin_x + board_width, origin_y + board_height])

    if repulsion_k is None:
        board_area = board_width * board_height
        repulsion_k = jnp.sqrt(board_area / n)

    if initial_temp is None:
        board_diagonal = float(jnp.sqrt(board_width**2 + board_height**2))
        initial_temp = board_diagonal / 10.0

    @jax.jit
    def step(pos, temp):
        diff = pos[:, None, :] - pos[None, :, :]
        dist_sq = jnp.sum(diff**2, axis=-1) + 1e-6
        dist = jnp.sqrt(dist_sq)

        unit_diff = diff / (dist[:, :, None] + 1e-6)

        repulsion_mag = repulsion_k**2 / (dist**repulsion_power + 1e-6)
        repulsion_mag = repulsion_mag.at[jnp.arange(n), jnp.arange(n)].set(0.0)

        repulsion = jnp.sum(unit_diff * repulsion_mag[:, :, None], axis=1)
        repulsion = jnp.clip(repulsion, -100.0, 100.0)

        attraction = jnp.sum(adj[:, :, None] * -diff, axis=1)
        attraction = attraction * attraction_k
        attraction = jnp.clip(attraction, -100.0, 100.0)

        displacement = repulsion + attraction

        disp_magnitude = jnp.sqrt(jnp.sum(displacement**2, axis=-1, keepdims=True))

        clamped_disp = jnp.where(
            disp_magnitude > temp, displacement * (temp / (disp_magnitude + 1e-6)), displacement
        )

        new_pos = pos + learning_rate * clamped_disp

        new_pos = jnp.clip(new_pos, bounds_min, bounds_max)
        new_pos = jnp.where(fixed_mask[:, None], pos, new_pos)

        new_temp = jnp.maximum(temp * cooling_factor, min_temp)

        return new_pos, new_temp

    curr_pos = initial_positions
    temp = initial_temp
    for _ in range(iterations):
        curr_pos, temp = step(curr_pos, temp)

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
            # Skip components already placed by higher-priority heuristics
            if comp.ref in context.current_placements:
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
