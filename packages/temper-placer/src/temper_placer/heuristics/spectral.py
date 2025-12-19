"""
Spectral layout initialization heuristic.

Uses spectral graph theory (Laplacian eigenvectors) to compute a global
optimal relative placement that minimizes total squared wirelength.
"""

from __future__ import annotations

import networkx as nx
import numpy as np

from temper_placer.core.board import Board
from temper_placer.heuristics.base import (
    ComponentPlacement,
    Heuristic,
    HeuristicPriority,
    HeuristicResult,
    PlacementContext,
)
from temper_placer.heuristics.graph_utils import GraphBuilder


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
        """Apply spectral layout."""
        # Build the graph
        builder = GraphBuilder(context.netlist)
        G = builder.build_graph()

        if len(G) == 0:
            return HeuristicResult(success=True, message="Empty graph")

        # Compute spectral layout
        # This returns a dict {node: array([x, y])} in unit scale [-1, 1]
        try:
            # weight='weight' uses the edge weights we defined in GraphBuilder
            raw_pos = nx.spectral_layout(G, weight="weight", dim=2)
        except Exception as e:
            return HeuristicResult(success=False, message=f"Spectral layout failed: {str(e)}")

        # Scale to board dimensions
        placements = self._scale_to_board(raw_pos, context.board, context)

        return HeuristicResult(
            placements=placements,
            success=True,
            message=f"Spectrally placed {len(placements)} components",
        )

    def _scale_to_board(
        self, raw_pos: dict[str, np.ndarray], board: Board, context: PlacementContext
    ) -> dict[str, ComponentPlacement]:
        """Scale unit coordinates to board dimensions."""
        placements: dict[str, ComponentPlacement] = {}

        # Board geometry
        ox, oy = board.origin
        margin = context.constraints.board_margin_mm

        # Usable area
        width = board.width - 2 * margin
        height = board.height - 2 * margin
        center_x = ox + margin + width / 2
        center_y = oy + margin + height / 2

        # Find raw bounds to normalize
        coords = np.array(list(raw_pos.values()))
        if len(coords) == 0:
            return {}

        min_x, min_y = coords.min(axis=0)
        max_x, max_y = coords.max(axis=0)
        rng_x = max_x - min_x if max_x > min_x else 1.0
        rng_y = max_y - min_y if max_y > min_y else 1.0

        # Scale factor: use 80% of board to leave some room
        scale_x = (width * 0.8) / rng_x
        scale_y = (height * 0.8) / rng_y

        # Assign placements
        for ref, pos in raw_pos.items():
            # Skip if already placed or fixed
            if ref in context.current_placements:
                continue

            comp = context.netlist.get_component(ref)
            if comp.fixed:
                continue

            # Normalize to centered board coordinates
            # (pos - min) -> [0, range]
            # - range/2 -> [-range/2, range/2]
            # * scale -> scaled centered
            # + board_center -> final position

            x = (pos[0] - min_x - rng_x / 2) * scale_x + center_x
            y = (pos[1] - min_y - rng_y / 2) * scale_y + center_y

            # Ensure within bounds
            x = max(
                ox + margin + comp.width / 2, min(x, ox + board.width - margin - comp.width / 2)
            )
            y = max(
                oy + margin + comp.height / 2, min(y, oy + board.height - margin - comp.height / 2)
            )

            placements[ref] = ComponentPlacement(
                ref=ref,
                position=(float(x), float(y)),
                rotation=0,
                confidence=self._confidence,
                placed_by=self.name,
            )

        return placements
