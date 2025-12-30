"""
Dithered Router: Grid Origin Dithering for Aliasing Escape.

Implements grid origin dithering to escape aliasing deadlocks where valid paths
align perfectly with blocked cell boundaries, causing "phantom block" failures.

The Problem:
When a valid 0.25mm gap falls exactly on a grid cell boundary:
1. C-Space inflation marks both adjacent cells as blocked
2. The one valid cell between them has its center inside the blocked zone
3. Router reports 'No Path' for a geometrically valid connection

The Solution:
Shift the coordinate system origin and retry. The aliasing alignment is
unlikely to occur twice with different origin offsets.

Part of temper-akrc: Dithering: Multi-Pass Aliasing Fix
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

import numpy as np

from temper_placer.routing.maze_router import MazeRouter, RoutePath, GridCell

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.routing.c_space_builder import CSpaceBuilder
    from temper_placer.routing.layer_assignment import LayerAssignment


logger = logging.getLogger(__name__)


@dataclass
class DitherConfig:
    """Configuration for grid origin dithering."""

    enable_dithering: bool = True
    max_attempts: int = 4
    origin_offsets: list[tuple[float, float]] = field(
        default_factory=lambda: [
            (0.0, 0.0),
            (0.025, 0.025),
            (-0.025, 0.025),
            (0.0125, -0.0125),
        ]
    )


@dataclass
class DitherAttempt:
    """Result of a single dithering attempt."""

    offset_x: float
    offset_y: float
    success: bool
    path: Optional[list[GridCell]] = None
    length: float = 0.0
    via_count: int = 0
    time_ms: float = 0.0
    failure_reason: Optional[str] = None


class DitheredRouter:
    """
    Router wrapper that applies grid origin dithering to escape aliasing deadlocks.

    The dithering approach:
    1. Attempt routing with standard (0, 0) grid origin
    2. If that fails, retry with small offset shifts
    3. If any attempt succeeds, return that result
    4. If all attempts fail, return failure with diagnostic info

    Performance: With C-Space generation ~10ms, max 4 attempts = 40ms overhead
    for nets that hit aliasing deadlocks.
    """

    DITHER_OFFSETS = [
        (0.0, 0.0),
        (0.025, 0.025),
        (-0.025, 0.025),
        (0.0125, -0.0125),
    ]

    def __init__(
        self,
        base_router: "MazeRouter",
        c_space_builder: Optional["CSpaceBuilder"] = None,
        config: Optional[DitherConfig] = None,
    ):
        self.base_router = base_router
        self.c_space_builder = c_space_builder
        self.config = config or DitherConfig()

        self._original_origin: Optional[tuple[float, float]] = None
        self._attempts: list[DitherAttempt] = []

    @classmethod
    def from_board(
        cls,
        board: "Board",
        cell_size_mm: float = 0.1,
        c_space_builder: Optional["CSpaceBuilder"] = None,
        **router_kwargs,
    ) -> "DitheredRouter":
        """Create dithered router from board geometry."""
        from temper_placer.routing.maze_router import MazeRouter

        base_router = MazeRouter.from_board(
            board,
            cell_size_mm=cell_size_mm,
            **router_kwargs,
        )
        return cls(base_router, c_space_builder)

    def _apply_origin_offset(self, offset_x: float, offset_y: float) -> None:
        """Shift the router's grid origin by the given offset."""
        if self._original_origin is None:
            self._original_origin = self.base_router.origin

        new_origin = (
            self._original_origin[0] + offset_x,
            self._original_origin[1] + offset_y,
        )
        self.base_router.origin = new_origin

    def _reset_origin(self) -> None:
        """Reset router origin to original value."""
        if self._original_origin is not None:
            self.base_router.origin = self._original_origin
            self._original_origin = None

    def _apply_inverse_offset(
        self, path: list[GridCell], offset_x: float, offset_y: float
    ) -> list[GridCell]:
        """Convert path cells back to true world space coordinates."""
        if offset_x == 0 and offset_y == 0:
            return path

        if self._original_origin is None:
            return path

        cell_size = self.base_router.cell_size
        adjusted_path = []

        for cell in path:
            world_x = cell.x * cell_size + self.base_router.origin[0] + cell_size / 2
            world_y = cell.y * cell_size + self.base_router.origin[1] + cell_size / 2

            grid_x = int((world_x - self._original_origin[0]) / cell_size)
            grid_y = int((world_y - self._original_origin[1]) / cell_size)

            adjusted_path.append(GridCell(grid_x, grid_y, cell.layer))

        return adjusted_path

    def route_net_with_dithering(  # type: ignore
        self,
        net_name: str,
        pin_positions: list[tuple[float, float]],
        assignment: Optional["LayerAssignment"] = None,
        cost_map: Optional[np.ndarray] = None,
    ) -> RoutePath:
        """Route a net with dithering fallback for aliasing escape."""
        self._attempts = []
        offsets = self.config.origin_offsets[: self.config.max_attempts]

        for offset_x, offset_y in offsets:
            attempt = self._attempt_route(
                net_name,
                pin_positions,
                assignment,
                cost_map,
                offset_x,
                offset_y,
            )
            self._attempts.append(attempt)

            if attempt.success:
                logger.debug(
                    f"Dithering succeeded at offset ({offset_x}, {offset_y}) for net {net_name}"
                )
                return RoutePath(
                    net=net_name,
                    cells=attempt.path or [],
                    length=attempt.length,
                    via_count=attempt.via_count,
                    success=True,
                    difficulty=0.0,
                    cell_difficulties=[],
                )

        all_failed = "\n".join(
            f"Offset ({a.offset_x}, {a.offset_y}): {a.failure_reason}" for a in self._attempts
        )
        logger.warning(f"All dither attempts failed for net {net_name}: {all_failed}")

        return RoutePath(
            net=net_name,
            cells=[],
            length=0.0,
            via_count=0,
            success=False,
            difficulty=0.0,
            cell_difficulties=[],
            failure_reason=f"Aliasing deadlock after {len(self._attempts)} dither attempts",
        )

    def _attempt_route(
        self,
        net_name: str,
        pin_positions: list[tuple[float, float]],
        assignment: Optional["LayerAssignment"],
        cost_map: Optional[np.ndarray],
        offset_x: float,
        offset_y: float,
    ) -> DitherAttempt:
        """Execute a single routing attempt with the given offset."""
        start_time = time.perf_counter()

        try:
            self._apply_origin_offset(offset_x, offset_y)

            if self.c_space_builder is not None:
                result = self._route_with_c_space(net_name, pin_positions, assignment, cost_map)
            else:
                result = self.base_router.route_net(
                    net_name,
                    pin_positions,
                    assignment,
                    cost_map,  # type: ignore
                )

            time_ms = (time.perf_counter() - start_time) * 1000.0

            if result.success and result.cells:
                adjusted_path = self._apply_inverse_offset(result.cells, offset_x, offset_y)
                return DitherAttempt(
                    offset_x=offset_x,
                    offset_y=offset_y,
                    success=True,
                    path=adjusted_path,
                    length=result.length,
                    via_count=result.via_count,
                    time_ms=time_ms,
                )
            else:
                return DitherAttempt(
                    offset_x=offset_x,
                    offset_y=offset_y,
                    success=False,
                    path=None,
                    length=0.0,
                    via_count=0,
                    time_ms=time_ms,
                    failure_reason=getattr(result, "failure_reason", None) or "No path found",
                )

        except Exception as e:
            time_ms = (time.perf_counter() - start_time) * 1000.0
            logger.debug(f"Dither attempt failed: {e}")
            return DitherAttempt(
                offset_x=offset_x,
                offset_y=offset_y,
                success=False,
                path=None,
                length=0.0,
                via_count=0,
                time_ms=time_ms,
                failure_reason=str(e),
            )
        finally:
            self._reset_origin()

    def _route_with_c_space(
        self,
        net_name: str,
        pin_positions: list[tuple[float, float]],
        assignment: Optional["LayerAssignment"],
        cost_map: Optional[np.ndarray],
    ) -> RoutePath:
        """Route using C-Space grid for clearance-aware routing."""
        from temper_placer.routing.layer_assignment import Layer

        if len(pin_positions) < 2:
            return RoutePath(
                net=net_name,
                cells=[],
                length=0.0,
                via_count=0,
                success=True,
            )

        layer = 0
        if assignment and assignment.primary_layer == Layer.L4_BOT:
            layer = self.base_router.num_layers - 1

        grid_pins = [self.base_router._world_to_grid(x, y) for x, y in pin_positions]

        all_cells = []
        total_vias = 0

        for i in range(1, len(grid_pins)):
            start_node = grid_pins[i - 1]
            end_node = grid_pins[i]

            path = self.base_router.find_path_rrr(
                start_node,
                end_node,
                layer,
                allow_layer_change=len(self.base_router.layer_stackup.layers) > 1,
                cost_map=cost_map,
            )

            if path is None:
                return RoutePath(
                    net=net_name,
                    cells=all_cells,
                    length=float(len(all_cells)),
                    via_count=total_vias,
                    success=False,
                    failure_reason=f"No path from {start_node} to {end_node}",
                )

            for j in range(1, len(path)):
                if path[j].layer != path[j - 1].layer:
                    total_vias += 1

            if all_cells:
                path = path[1:]
            all_cells.extend(path)

        return RoutePath(
            net=net_name,
            cells=all_cells,
            length=float(len(all_cells)),
            via_count=total_vias,
            success=True,
        )

    def route_net(
        self,
        net_name: str,
        pin_positions: list[tuple[float, float]],
        assignment: Optional["LayerAssignment"] = None,
        cost_map: Optional[np.ndarray] = None,
    ) -> RoutePath:
        """Public API: route with automatic dithering if needed."""
        if not self.config.enable_dithering:
            if self.c_space_builder is not None:
                return self._route_with_c_space(
                    net_name,
                    pin_positions,
                    assignment,
                    cost_map,  # type: ignore
                )
            return self.base_router.route_net(
                net_name,
                pin_positions,
                assignment,
                cost_map,  # type: ignore
            )

        return self.route_net_with_dithering(net_name, pin_positions, assignment, cost_map)

    @property
    def last_attempts(self) -> list[DitherAttempt]:
        """Return the list of attempts from the last routing call."""
        return self._attempts

    def get_diagnostic_report(self) -> dict:
        """Get a diagnostic report of the last routing attempts."""
        return {
            "total_attempts": len(self._attempts),
            "successful_offset": next((a.offset_x, a.offset_y) for a in self._attempts if a.success)
            if any(a.success for a in self._attempts)
            else None,
            "attempts": [
                {
                    "offset": (a.offset_x, a.offset_y),
                    "success": a.success,
                    "time_ms": a.time_ms,
                    "failure_reason": a.failure_reason,
                }
                for a in self._attempts
            ],
            "total_time_ms": sum(a.time_ms for a in self._attempts),
        }
