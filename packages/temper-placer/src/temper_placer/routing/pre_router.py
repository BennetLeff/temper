"""
Pre-routing integration for critical net pre-routing (temper-cjxg).

This module integrates CriticalNetDetector and PDNRouter with the MazeRouter
to enable automatic pre-routing of critical nets before general routing.

Integration flow:
1. Detect critical nets using CriticalNetDetector
2. Route power distribution network using PDNRouter
3. Register pre-routed paths with MazeRouter
4. Order remaining nets by criticality
5. Route non-critical nets using standard maze routing

Example usage:
    >>> from temper_placer.routing.pre_router import PreRouter
    >>> from temper_placer.routing.maze_router import MazeRouter
    >>>
    >>> pre_router = PreRouter()
    >>> pre_routes = pre_router.pre_route_critical_nets(netlist, positions, board)
    >>> maze_router = MazeRouter(...)
    >>> maze_router.register_pre_routes(pre_routes)
    >>> # Then continue with normal routing
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist

logger = logging.getLogger(__name__)


@dataclass
class PreRouteResult:
    """Result of pre-routing critical nets.

    Attributes:
        critical_nets: Critical net detection result.
        pdn_result: PDN routing result for power nets.
        escaped_nets: Nets that have pre-routed escape traces.
        remaining_nets: Non-critical nets to be routed by maze router.
        locked_nets: Nets that are locked (pre-routed and should not be rip-up'd).
    """

    critical_nets: "CriticalNetDetectionResult"
    pdn_result: "PDNRouteResult"
    escaped_nets: list[str] = field(default_factory=list)
    remaining_nets: list[str] = field(default_factory=list)
    locked_nets: list[str] = field(default_factory=list)


class PreRouter:
    """Pre-routing orchestrator for critical net handling.

    This class coordinates:
    1. Critical net detection
    2. Power distribution network routing
    3. Integration with MazeRouter for pre-route registration

    Attributes:
        detector: CriticalNetDetector instance.
        pdn_router: PDNRouter instance.
    """

    def __init__(
        self,
        detector: "Optional[CriticalNetDetector]" = None,
        pdn_router: "Optional[PDNRouter]" = None,
    ):
        """Initialize the pre-router.

        Args:
            detector: Optional CriticalNetDetector (creates default if None).
            pdn_router: Optional PDNRouter (creates default if None).
        """
        self._detector = detector
        self._pdn_router = pdn_router

    @property
    def detector(self) -> "CriticalNetDetector":
        """Get the CriticalNetDetector instance."""
        if self._detector is None:
            from temper_placer.routing.critical_net_detector import CriticalNetDetector

            self._detector = CriticalNetDetector()
        return self._detector

    @property
    def pdn_router(self) -> "PDNRouter":
        """Get the PDNRouter instance."""
        if self._pdn_router is None:
            from temper_placer.routing.pdn_router import PDNRouter

            self._pdn_router = PDNRouter()
        return self._pdn_router

    def pre_route_critical_nets(
        self,
        netlist: "Netlist",
        positions: dict[str, tuple[float, float]],
        board: "Board | None" = None,
    ) -> PreRouteResult:
        """Execute pre-routing for all critical nets.

        Args:
            netlist: Netlist containing all components and nets.
            positions: Dictionary mapping component ref to (x, y) position.
            board: Optional Board for additional constraints.

        Returns:
            PreRouteResult with detection and routing results.
        """
        logger.info("Starting critical net pre-routing")

        result = self.detector.detect_critical_nets(netlist)
        logger.info(
            f"Detected {len(result.critical_nets)} critical nets: "
            f"{len(result.power_nets)} power, {len(result.ground_nets)} ground, "
            f"{len(result.clock_nets)} clock, {len(result.high_speed_nets)} high-speed"
        )

        pdn_result = self.pdn_router.route_from_detection_result(netlist, result, board)

        escaped_nets = list(pdn_result.paths.keys())
        remaining_nets = [n for n in netlist.nets if n.name not in result.critical_nets]
        remaining_net_names = [n.name for n in remaining_nets]

        locked_nets = list(result.critical_nets.keys())

        logger.info(
            f"Pre-routing complete: {len(escaped_nets)} nets routed, "
            f"{len(remaining_net_names)} nets remaining for maze routing"
        )

        return PreRouteResult(
            critical_nets=result,
            pdn_result=pdn_result,
            escaped_nets=escaped_nets,
            remaining_nets=remaining_net_names,
            locked_nets=locked_nets,
        )

    def integrate_with_maze_router(
        self,
        maze_router: "MazeRouter",
        pre_result: PreRouteResult,
    ) -> None:
        """Register pre-routed paths with the maze router.

        This method directly updates the maze router's internal state:
        - Adds cells to occupancy grid
        - Registers net ownership
        - Adds to routed_paths dictionary

        Args:
            maze_router: MazeRouter instance to register with.
            pre_result: PreRouteResult from pre_route_critical_nets.
        """
        from temper_placer.routing.maze_router import GridCell

        for net_name, path in pre_result.pdn_result.paths.items():
            if path.cells and path.success:
                cells = path.cells

                for cell in cells:
                    ax, ay = cell.x, cell.y
                    al = getattr(cell, "layer", 0)

                    if 0 <= ax < maze_router.grid_size[0] and 0 <= ay < maze_router.grid_size[1]:
                        maze_router.occupancy[ax, ay, al] = 2
                        maze_router.present_congestion[ax, ay, al] += 1.0
                        key = (ax, ay, al)
                        if key not in maze_router.net_occupancy:
                            maze_router.net_occupancy[key] = set()
                        maze_router.net_occupancy[key].add(net_name)
                        maze_router.cell_owner[(ax, ay, al)] = net_name

                if net_name not in maze_router.routed_paths:
                    maze_router.routed_paths[net_name] = path

        logger.info(f"Registered {len(pre_result.pdn_result.paths)} pre-routes with maze router")

    def get_net_order(
        self,
        pre_result: PreRouteResult,
        netlist: "Netlist",
        strategy: str = "critical_first",
    ) -> list[str]:
        """Get net ordering for maze routing.

        Args:
            pre_result: PreRouteResult from pre_route_critical_nets.
            netlist: Netlist for accessing net information.
            strategy: Ordering strategy ("critical_first", "power_first", "shortest_first").

        Returns:
            List of net names in routing order.
        """
        from temper_placer.routing.critical_net_detector import CriticalNetCategory

        if strategy == "critical_first":
            critical_order = []
            for category in [
                CriticalNetCategory.POWER,
                CriticalNetCategory.GROUND,
                CriticalNetCategory.CLOCK,
                CriticalNetCategory.HIGH_SPEED,
                CriticalNetCategory.HIGH_CURRENT,
            ]:
                critical_order.extend(pre_result.critical_nets.get_nets_by_category(category))

            remaining = [n for n in pre_result.remaining_nets if n not in critical_order]
            return critical_order + remaining

        elif strategy == "power_first":
            power_ground = [
                n
                for n in pre_result.remaining_nets
                if n in pre_result.critical_nets.power_nets
                or n in pre_result.critical_nets.ground_nets
            ]
            signal = [n for n in pre_result.remaining_nets if n not in power_ground]
            return power_ground + signal

        else:
            return pre_result.remaining_nets

    def get_locked_nets(self, pre_result: PreRouteResult) -> list[str]:
        """Get list of nets that should not be rip-up'd during routing.

        Args:
            pre_result: PreRouteResult from pre_route_critical_nets.

        Returns:
            List of net names that are locked.
        """
        return pre_result.locked_nets


def create_pre_routing_pipeline(
    netlist: "Netlist",
    positions: dict[str, tuple[float, float]],
    board: "Board | None" = None,
    maze_router: "MazeRouter | None" = None,
) -> tuple[PreRouteResult, "MazeRouter"]:
    """Create a complete pre-routing pipeline.

    This is a convenience function that:
    1. Detects critical nets
    2. Routes power distribution
    3. Integrates with maze router
    4. Returns both the result and configured maze router

    Args:
        netlist: Netlist containing all components and nets.
        positions: Dictionary mapping component ref to (x, y) position.
        board: Optional Board for additional constraints.
        maze_router: Optional MazeRouter (creates default if None).

    Returns:
        Tuple of (PreRouteResult, MazeRouter).

    Example:
        >>> result, router = create_pre_routing_pipeline(netlist, positions)
        >>> net_order = pre_router.get_net_order(result, netlist)
        >>> # Continue with normal routing...
    """
    from temper_placer.routing.maze_router import MazeRouter

    pre_router = PreRouter()
    pre_result = pre_router.pre_route_critical_nets(netlist, positions, board)

    if maze_router is None:
        maze_router = MazeRouter(
            grid_size=(100, 100),
            cell_size_mm=0.5,
            num_layers=2,
        )

    pre_router.integrate_with_maze_router(maze_router, pre_result)

    return pre_result, maze_router
