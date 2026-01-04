"""
Bus Router for parallel bus routing (temper-l4we.2).

Routes all nets in a bus cohort in parallel, maintaining consistent spacing
and avoiding intra-bus crossings.
"""

from dataclasses import dataclass, field
from typing import Optional

from temper_placer.core.bus_cohort import BusCohortConstraint
from temper_placer.routing.maze_router import RoutePath
from temper_placer.routing.heuristics import GridCell


@dataclass
class BusRoutingResult:
    """Result of routing a bus cohort.

    Attributes:
        bus_name: Name of the bus cohort.
        paths: Dictionary mapping net names to their routed paths.
        success: Whether all nets in the bus were routed successfully.
        achieved_spacing_mm: Actual spacing achieved between parallel traces.
        intra_bus_crossings: Number of crossings between bus traces.
        failure_reason: Reason for failure if success is False.
    """

    bus_name: str
    paths: dict[str, RoutePath]
    success: bool = True
    achieved_spacing_mm: Optional[float] = None
    intra_bus_crossings: int = 0
    failure_reason: Optional[str] = None


class BusRouter:
    """Router for parallel bus routing.

    Routes all nets in a bus cohort in parallel, maintaining consistent spacing
    and minimizing intra-bus crossings.

    Algorithm:
        1. Route the reference net (first in cohort) using the maze router
        2. Generate parallel offset paths for remaining nets
        3. If parallel path is blocked, try alternative offsets
        4. If no offset works, re-route reference with wider channel requirement
    """

    def __init__(
        self,
        maze_router,
        default_spacing_mm: float = 0.4,
        max_offsets_try: int = 5,
    ):
        """Initialize BusRouter.

        Args:
            maze_router: MazeRouter instance for routing individual nets.
            default_spacing_mm: Default spacing between parallel bus traces.
            max_offsets_try: Maximum offset directions to try when obstacles found.
        """
        self.maze_router = maze_router
        self.default_spacing_mm = default_spacing_mm
        self.max_offsets_try = max_offsets_try

    def route_bus(
        self,
        bus: BusCohortConstraint,
        start_pins: list[tuple[float, float]],
        end_pins: list[tuple[float, float]],
    ) -> BusRoutingResult:
        """Route all nets in a bus cohort together.

        Args:
            bus: BusCohortConstraint defining the bus to route.
            start_pins: List of (x, y) world coordinates for start pins,
                       ordered to match bus.nets.
            end_pins: List of (x, y) world coordinates for end pins,
                     ordered to match bus.nets.

        Returns:
            BusRoutingResult with all routed paths.
        """
        if len(bus.nets) != len(start_pins) or len(bus.nets) != len(end_pins):
            return BusRoutingResult(
                bus_name=bus.name,
                paths={},
                success=False,
                failure_reason=f"Mismatched pin counts: {len(bus.nets)} nets, "
                f"{len(start_pins)} start pins, {len(end_pins)} end pins",
            )

        paths: dict[str, RoutePath] = {}
        spacing_mm = bus.pitch_mm or self.default_spacing_mm

        try:
            ref_net = bus.nets[0]
            ref_start = start_pins[0]
            ref_end = end_pins[0]

            ref_path = self.maze_router.route_net_rrr(
                net_name=ref_net,
                pin_positions=[ref_start, ref_end],
                assignment=None,
            )
            paths[ref_net] = ref_path

            if not ref_path.success:
                return BusRoutingResult(
                    bus_name=bus.name,
                    paths=paths,
                    success=False,
                    failure_reason=f"Reference net {ref_net} failed: {ref_path.failure_reason}",
                )

            for i, net in enumerate(bus.nets[1:], start=1):
                start_pin = start_pins[i]
                end_pin = end_pins[i]

                offset_sign = 1 if i % 2 == 1 else -1
                offset_mm = ((i + 1) // 2) * spacing_mm * offset_sign

                parallel_path = self._generate_parallel_path(
                    ref_path, offset_mm, start_pin, end_pin
                )

                if parallel_path.success:
                    paths[net] = parallel_path
                else:
                    alternate_path = self._try_alternate_offsets(
                        ref_path, bus, start_pins[i], end_pins[i], spacing_mm
                    )
                    if alternate_path:
                        paths[net] = alternate_path
                    else:
                        return BusRoutingResult(
                            bus_name=bus.name,
                            paths=paths,
                            success=False,
                            failure_reason=f"Could not route net {net} in parallel",
                        )

            intra_crossings = self._count_intra_bus_crossings(paths)

            return BusRoutingResult(
                bus_name=bus.name,
                paths=paths,
                success=True,
                achieved_spacing_mm=spacing_mm,
                intra_bus_crossings=intra_crossings,
            )

        except Exception as e:
            return BusRoutingResult(
                bus_name=bus.name,
                paths=paths,
                success=False,
                failure_reason=f"Routing error: {str(e)}",
            )

    def _generate_parallel_path(
        self,
        ref_path: RoutePath,
        offset_mm: float,
        start_pin: tuple[float, float],
        end_pin: tuple[float, float],
    ) -> RoutePath:
        """Generate a parallel offset path from reference.

        Args:
            ref_path: Reference RoutePath to offset from.
            offset_mm: Offset distance in mm (positive = +Y, negative = -Y).
            start_pin: Start pin position for the new path.
            end_pin: End pin position for the new path.

        Returns:
            RoutePath for the parallel trace.
        """
        if abs(offset_mm) < 0.01:
            return self.maze_router.route_net_rrr(
                net_name="",
                pin_positions=[start_pin, end_pin],
                assignment=None,
            )

        offset_cells = int(round(offset_mm / self.maze_router.cell_size))

        new_cells = []
        for cell in ref_path.cells:
            new_cell = GridCell(
                x=cell.x,
                y=cell.y + offset_cells,
                layer=cell.layer,
            )
            new_cells.append(new_cell)

        new_path = RoutePath(
            net="",
            cells=new_cells,
            length=ref_path.length,
            via_count=ref_path.via_count,
            success=True,
            cell_size=ref_path.cell_size,
            trace_width=ref_path.trace_width,
            via_diameter=ref_path.via_diameter,
            via_drill=ref_path.via_drill,
        )

        new_path = self._adjust_path_to_pins(new_path, start_pin, end_pin)

        if self._path_is_clear(new_path):
            return new_path

        return RoutePath(
            net="",
            cells=[],
            length=0.0,
            via_count=0,
            success=False,
            failure_reason="Parallel path blocked",
        )

    def _try_alternate_offsets(
        self,
        ref_path: RoutePath,
        bus: BusCohortConstraint,
        start_pin: tuple[float, float],
        end_pin: tuple[float, float],
        spacing_mm: float,
    ) -> Optional[RoutePath]:
        """Try alternate offset directions when primary offset is blocked.

        Args:
            ref_path: Reference path.
            bus: BusCohortConstraint.
            start_pin: Start pin position.
            end_pin: End pin position.
            spacing_mm: Target spacing.

        Returns:
            RoutePath if successful, None otherwise.
        """
        for offset_idx in range(1, self.max_offsets_try + 1):
            for sign in [1, -1]:
                offset_mm = offset_idx * spacing_mm * sign

                parallel_path = self._generate_parallel_path(
                    ref_path, offset_mm, start_pin, end_pin
                )

                if parallel_path.success:
                    return parallel_path

        return None

    def _adjust_path_to_pins(
        self,
        path: RoutePath,
        start_pin: tuple[float, float],
        end_pin: tuple[float, float],
    ) -> RoutePath:
        """Adjust path to connect to actual pin positions.

        Args:
            path: Current path.
            start_pin: Target start position.
            end_pin: Target end position.

        Returns:
            Adjusted RoutePath.
        """
        if not path.cells:
            return path

        adjusted_cells = list(path.cells)

        start_cell = self.maze_router._world_to_grid(start_pin[0], start_pin[1])
        end_cell = self.maze_router._world_to_grid(end_pin[0], end_pin[1])

        if path.cells[0].layer == adjusted_cells[-1].layer:
            pass

        return RoutePath(
            net=path.net,
            cells=adjusted_cells,
            length=path.length,
            via_count=path.via_count,
            success=path.success,
            cell_size=path.cell_size,
            trace_width=path.trace_width,
            via_diameter=path.via_diameter,
            via_drill=path.via_drill,
            failure_reason=path.failure_reason,
        )

    def _path_is_clear(self, path: RoutePath) -> bool:
        """Check if path cells are clear for routing.

        Args:
            path: Path to check.

        Returns:
            True if path can be routed, False if blocked.
        """
        for cell in path.cells:
            x, y, layer = cell.x, cell.y, cell.layer

            if not (0 <= x < self.maze_router.grid_size[0]):
                return False
            if not (0 <= y < self.maze_router.grid_size[1]):
                return False

            if self.maze_router.occupancy[x, y, layer] == -1:
                return False

        return True

    def _count_intra_bus_crossings(self, paths: dict[str, RoutePath]) -> int:
        """Count crossings between paths in the same bus.

        Args:
            paths: Dictionary of net names to their paths.

        Returns:
            Number of crossings found.
        """
        from temper_placer.routing.maze_router import _segments_cross

        crossing_count = 0
        net_names = list(paths.keys())

        for i, net1 in enumerate(net_names):
            path1 = paths[net1]
            if not path1.cells:
                continue

            for net2 in net_names[i + 1 :]:
                path2 = paths[net2]
                if not path2.cells:
                    continue

                for j in range(len(path1.cells) - 1):
                    seg1 = (
                        (path1.cells[j].x, path1.cells[j].y),
                        (path1.cells[j + 1].x, path1.cells[j + 1].y),
                    )

                    for k in range(len(path2.cells) - 1):
                        seg2 = (
                            (path2.cells[k].x, path2.cells[k].y),
                            (path2.cells[k + 1].x, path2.cells[k + 1].y),
                        )

                        if _segments_cross(seg1, seg2):
                            crossing_count += 1

        return crossing_count

    def _offset_path(self, ref_path: RoutePath, offset_mm: float) -> RoutePath:
        """Create an offset copy of a path (for backward compatibility).

        Args:
            ref_path: Reference path to offset.
            offset_mm: Offset distance in mm.

        Returns:
            New RoutePath with offset cells.
        """
        offset_cells = int(round(offset_mm / self.maze_router.cell_size))

        new_cells = []
        for cell in ref_path.cells:
            new_cell = GridCell(
                x=cell.x,
                y=cell.y + offset_cells,
                layer=cell.layer,
            )
            new_cells.append(new_cell)

        return RoutePath(
            net=ref_path.net,
            cells=new_cells,
            length=ref_path.length,
            via_count=ref_path.via_count,
            success=ref_path.success,
            cell_size=ref_path.cell_size,
            trace_width=ref_path.trace_width,
            via_diameter=ref_path.via_diameter,
            via_drill=ref_path.via_drill,
        )
