"""Synthetic routing stub for seed-filter retrigger tests.

The stub satisfies a minimal contract that lets a unit test exercise the
seed-filter + bottleneck-map + retrigger loop without depending on a
full pipeline build:

* ``route(placement) -> (routing_completion_pct, BottleneckMap)``
* The map's per-cell score is computed from the placement (component
  density) so it is not a tautology: better-spread placements produce
  lower bottleneck scores, mimicking a real router's feedback.
* The stub is deterministic: same placement in -> same map out.

@req(2026-06-23-004, R7)
@req(2026-06-23-004, R-D5)
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from temper_placer.deterministic.bottleneck_map import BottleneckMap


class RoutingStageLike(Protocol):
    """Minimal routing-stage contract for the seed-filter feedback loop."""

    def route(
        self, placement: Mapping[str, tuple[float, float]]
    ) -> tuple[float, BottleneckMap]: ...


class SyntheticRoutingStub:
    """A deterministic, non-tautological routing stub.

    For each cell of a regular grid covering the configured board, the
    stub counts the number of component centers inside that cell and
    converts the count into a congestion score in [0, 1] using a
    saturating formula. The map's origin and cell size are stable so
    retriggers produce comparable scores.

    Routing completion is computed from the worst-case cell score: a
    placement that puts many components in the same cell has a low
    completion percentage, a placement that spreads them out has a
    high completion percentage.
    """

    def __init__(
        self,
        cell_size_mm: float = 5.0,
        width_cells: int = 8,
        height_cells: int = 8,
        origin_xy: tuple[float, float] = (0.0, 0.0),
        capacity_per_cell: int = 2,
    ) -> None:
        if width_cells <= 0 or height_cells <= 0:
            raise ValueError("width_cells/height_cells must be positive")
        if cell_size_mm <= 0:
            raise ValueError("cell_size_mm must be positive")
        if capacity_per_cell <= 0:
            raise ValueError("capacity_per_cell must be positive")
        self.cell_size_mm = cell_size_mm
        self.width_cells = width_cells
        self.height_cells = height_cells
        self.origin_xy = origin_xy
        self.capacity_per_cell = capacity_per_cell

    def _cell_counts(
        self, placement: Mapping[str, tuple[float, float]]
    ) -> list[int]:
        counts = [0] * (self.width_cells * self.height_cells)
        origin_x, origin_y = self.origin_xy
        for _ref, (x, y) in placement.items():
            col = int((x - origin_x) // self.cell_size_mm)
            row = int((y - origin_y) // self.cell_size_mm)
            if 0 <= col < self.width_cells and 0 <= row < self.height_cells:
                counts[row * self.width_cells + col] += 1
        return counts

    def _score(self, count: int) -> float:
        # Saturating linear: 0 at 0, 1.0 at 2x capacity.
        if count <= self.capacity_per_cell:
            return float(count) / (2 * self.capacity_per_cell)
        return min(1.0, (count - self.capacity_per_cell) / self.capacity_per_cell)

    def route(
        self, placement: Mapping[str, tuple[float, float]]
    ) -> tuple[float, BottleneckMap]:
        """Return ``(routing_completion_pct, bottleneck_map)``.

        ``routing_completion_pct`` is in [0, 100] and is computed from
        the worst-case cell score. ``bottleneck_map`` carries per-cell
        congestion scores derived from component density.
        """
        counts = self._cell_counts(placement)
        scores = [self._score(c) for c in counts]
        worst = max(scores) if scores else 0.0
        # Worst score -> completion deficit. completion = (1 - worst) * 100.
        completion_pct = max(0.0, (1.0 - worst) * 100.0)
        bmap = BottleneckMap(
            cell_size_mm=self.cell_size_mm,
            width=self.width_cells,
            height=self.height_cells,
            origin_xy=self.origin_xy,
            scores=tuple(scores),
        )
        return completion_pct, bmap
