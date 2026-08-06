"""
Congestion heatmap for placer-router feedback.

Extracts routing difficulty from MazeRouter to inform placement optimization.

Part of temper-gzur.1

Wave 4 Phase B: ``CongestionHeatmap.from_router`` delegates to
``temper_geometry`` (``congestion_heatmap_from_router_py``) -- it builds a
fresh grid from a ``router`` snapshot every call, matching the classmethod's
own contract exactly.

``get_congestion_at``, ``get_total_congestion`` and ``get_hotspots`` do
**not** delegate. Their Rust counterparts
(``congestion_heatmap_at_py``/``congestion_heatmap_total_py``/``congestion_heatmap_hotspots_py``)
each *rebuild* the grid from ``(present, history, conflicts, cell_size,
origin)`` on every call rather than operating on an already-built grid --
``CongestionHeatmap`` is a plain ``@dataclass`` with only ``grid``,
``cell_size`` and ``origin`` fields; it does not retain the router snapshot
``from_router`` was built from. These three instance methods only ever have
``self.grid`` to work with, so wiring them to those kernels would mean
either storing the router on every heatmap (a public dataclass-shape change,
which the substitution rules here rule out) or recomputing the grid from
scratch on every query -- and if the router's state has moved on since
``from_router`` was called (the ordinary case: the heatmap is a snapshot),
that recompute would silently answer with a DIFFERENT, newer grid than the
one the caller actually holds. Kept as plain Python operations over
``self.grid`` instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import temper_geometry as _tg

if TYPE_CHECKING:
    from typing import Any
else:
    Any = object


@dataclass
class CongestionHeatmap:
    """2D congestion map from routing analysis.

    Provides query interface for placement optimization:
    - High congestion areas should repel components
    - Enables RoutingCongestionLoss to steer placement
    """

    grid: np.ndarray  # 2D float array, values 0-1 (normalized congestion)
    cell_size: float  # mm per grid cell
    origin: tuple[float, float]  # world coordinates of grid origin

    @classmethod
    def from_router(cls, router: Any) -> CongestionHeatmap:
        """Build heatmap from router's congestion data.

        Combines:
        - present_congestion: current net overlap counts
        - history_cost: accumulated routing difficulty
        - conflict_locations: explicit conflict points

        Args:
            router: MazeRouter with routing results

        Returns:
            Normalized congestion heatmap
        """
        grid, cell_size, origin = _tg.congestion_heatmap_from_router_py(
            np.asarray(router.present_congestion).tolist(),
            np.asarray(router.history_cost).tolist(),
            list(router.get_conflict_locations()),
            router.cell_size,
            router.origin,
        )
        return cls(grid=grid, cell_size=cell_size, origin=origin)

    def get_congestion_at(self, x: float, y: float) -> float:
        """Query congestion at world coordinate.

        Args:
            x, y: World coordinates in mm

        Returns:
            Congestion score 0-1 (0 = free, 1 = highly congested)
        """
        gx = int((x - self.origin[0]) / self.cell_size)
        gy = int((y - self.origin[1]) / self.cell_size)

        # Clamp to grid bounds
        gx = max(0, min(gx, self.grid.shape[0] - 1))
        gy = max(0, min(gy, self.grid.shape[1] - 1))

        return float(self.grid[gx, gy])

    def get_total_congestion(self) -> float:
        """Sum of all congestion values."""
        return float(np.sum(self.grid))

    def get_hotspots(
        self, threshold: float = 0.5, max_count: int = 10
    ) -> list[tuple[float, float, float]]:
        """Find high-congestion locations.

        Args:
            threshold: Minimum congestion to consider a hotspot
            max_count: Maximum hotspots to return

        Returns:
            List of (x, y, congestion) tuples in world coordinates
        """
        hotspots = []

        # Find cells above threshold
        for gx in range(self.grid.shape[0]):
            for gy in range(self.grid.shape[1]):
                val = self.grid[gx, gy]
                if val >= threshold:
                    world_x = gx * self.cell_size + self.origin[0]
                    world_y = gy * self.cell_size + self.origin[1]
                    hotspots.append((world_x, world_y, val))

        # Sort by congestion descending
        hotspots.sort(key=lambda h: h[2], reverse=True)

        return hotspots[:max_count]
