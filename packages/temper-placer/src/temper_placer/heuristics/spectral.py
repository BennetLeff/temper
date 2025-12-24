"""
Spectral layout initialization heuristic.

Uses spectral graph theory (Laplacian eigenvectors) to compute a global
optimal relative placement that minimizes total squared wirelength.
"""

from __future__ import annotations

import logging

import networkx as nx
import numpy as np

from temper_placer.heuristics.base import (
    ComponentPlacement,
    Heuristic,
    HeuristicPriority,
    HeuristicResult,
    PlacementContext,
)
from temper_placer.heuristics.graph_utils import GraphBuilder

logger = logging.getLogger(__name__)


class SpectralPlacementHeuristic(Heuristic):
    """
    Globally place components using Spectral Graph Layout.

    This heuristic constructs a weighted graph from the netlist and uses the
    eigenvectors of the graph Laplacian to find coordinates that minimize
    the global wirelength energy.

    This provides a mathematically grounded "warm start" that captures the
    global connectivity structure before local heuristics run.
    """

    def __init__(self, confidence: float = 0.1):
        """
        Initialize spectral placement.

        Args:
            confidence: Low confidence allows other heuristics to easily override.
                        Default 0.1 means this is just a "suggestion" or gravity.
        """
        self._confidence = confidence

    @property
    def name(self) -> str:
        return "spectral_initialization"

    @property
    def priority(self) -> HeuristicPriority:
        return HeuristicPriority.INITIALIZATION

    @property
    def description(self) -> str:
        return "Global spectral layout minimizing squared wirelength"

    def apply(self, context: PlacementContext) -> HeuristicResult:
        """Apply enhanced spectral layout."""
        # Build the graph
        builder = GraphBuilder(context.netlist)
        G = builder.build_graph()

        if len(G) == 0:
            return HeuristicResult(success=True, message="Empty graph")

        # Handle connected components independently
        components = list(nx.connected_components(G))
        all_raw_pos = {}

        # We need to distribute these components on the board
        # A simple approach: divide board into a grid based on number of components
        n_comps = len(components)
        cols = int(np.ceil(np.sqrt(n_comps)))
        rows = int(np.ceil(n_comps / cols))

        board = context.board
        margin = context.constraints.board_margin_mm
        w_eff = (board.width - 2 * margin) / cols
        h_eff = (board.height - 2 * margin) / rows

        for i, node_set in enumerate(components):
            subgraph = G.subgraph(node_set)

            if len(node_set) == 1:
                # Single node
                ref = list(node_set)[0]
                all_raw_pos[ref] = np.array([0.0, 0.0]) # Local center
            else:
                try:
                    # weight='weight' uses the edge weights we defined in GraphBuilder
                    pos = nx.spectral_layout(subgraph, weight="weight", dim=2)
                    all_raw_pos.update(pos)
                except Exception as e:
                    logger.warning(f"Spectral layout failed for component {i}: {e}")
                    # Fallback to random for this component
                    for ref in node_set:
                        all_raw_pos[ref] = np.random.uniform(-1, 1, (2,))

            # Local scaling and translation for this connected component
            # Grid cell center (relative)
            grid_x = (i % cols) * w_eff + w_eff / 2 + margin
            grid_y = (i // cols) * h_eff + h_eff / 2 + margin

            # Map nodes in this set to their grid cell
            nodes_in_set = list(node_set)
            coords = np.array([all_raw_pos[n] for n in nodes_in_set])

            if len(coords) > 1:
                c_min = coords.min(axis=0)
                c_max = coords.max(axis=0)
                c_rng = np.maximum(c_max - c_min, 1e-6)

                # Scale to fit in 80% of grid cell
                scale = np.array([w_eff, h_eff]) * 0.8 / c_rng
                for n in nodes_in_set:
                    # (pos - center) * scale + grid_center
                    all_raw_pos[n] = (all_raw_pos[n] - (c_min + c_max)/2) * scale + np.array([grid_x, grid_y])
            else:
                all_raw_pos[nodes_in_set[0]] = np.array([grid_x, grid_y])

        # Convert to final placements
        placements = self._convert_to_placements(all_raw_pos, context)

        return HeuristicResult(
            placements=placements,
            success=True,
            message=f"Spectrally placed {len(placements)} components in {n_comps} clusters",
        )

    def _convert_to_placements(
        self, raw_pos: dict[str, np.ndarray], context: PlacementContext
    ) -> dict[str, ComponentPlacement]:
        """Convert scaled coordinates to final placements with bounds checking."""
        placements: dict[str, ComponentPlacement] = {}
        board = context.board
        margin = context.constraints.board_margin_mm

        for ref, pos in raw_pos.items():
            # Skip if already placed or fixed
            if ref in context.current_placements:
                continue

            comp = context.netlist.get_component(ref)
            if comp.fixed:
                continue

            x, y = pos
            # Ensure within bounds (relative [0, width])
            x = max(
                margin + comp.width / 2, min(x, board.width - margin - comp.width / 2)
            )
            y = max(
                margin + comp.height / 2, min(y, board.height - margin - comp.height / 2)
            )

            placements[ref] = ComponentPlacement(
                ref=ref,
                position=(float(x), float(y)),
                rotation=0,
                confidence=self._confidence,
                placed_by=self.name,
            )

        return placements
