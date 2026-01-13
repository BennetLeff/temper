"""NetRouter class for routing a single net.

Orchestrates the routing process for a single net, reducing complexity
of the main MazeRouter.route_net_adaptive method.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.routing.grid import GridCell


@dataclass
class NetRouterConfig:
    """Configuration for single net routing.

    Attributes:
        max_iterations: Maximum rip-up and re-route iterations
        allow_layer_change: Whether to allow layer transitions
        via_cost: Base cost for via placement
        strict_mode: Whether to use strict DRC checking
        soft_blocking: Whether to use soft blocking for negotiation
    """

    max_iterations: int = 3
    allow_layer_change: bool = True
    via_cost: float = 1.0
    strict_mode: bool = False
    soft_blocking: bool = True
    layer_balance_weight: float = 0.1
    congestion_via_discount: float = 0.5


@dataclass
class NetRouterResult:
    """Result of routing a single net.

    Attributes:
        success: Whether routing succeeded
        net_name: Name of the net
        path: The routed path, if successful
        length: Path length in cells
        via_count: Number of vias used
        failure_reason: Reason for failure if not successful
        iterations: Number of iterations used
    """

    success: bool
    net_name: str
    path: Any = None
    length: float = 0.0
    via_count: int = 0
    failure_reason: str | None = None
    iterations: int = 0


class NetRouter:
    """Orchestrates routing for a single net.

    Provides a clean interface for routing individual nets,
    handling:
    - Pin ordering and assignment
    - Route selection and refinement
    - Rip-up and re-route iterations
    - Result reporting

    This class reduces complexity of the main MazeRouter by extracting
    single-net routing logic into a focused, testable component.
    """

    def __init__(
        self,
        config: NetRouterConfig | None = None,
        maze_router=None,
    ):
        """Initialize the NetRouter.

        Args:
            config: Optional routing configuration
            maze_router: Optional MazeRouter instance for actual routing
        """
        self.config = config or NetRouterConfig()
        self._maze_router = maze_router

    def set_maze_router(self, maze_router) -> None:
        """Set the MazeRouter instance for actual routing.

        Args:
            maze_router: MazeRouter instance
        """
        self._maze_router = maze_router

    def route(
        self,
        net_name: str,
        pin_positions: list[GridCell],
        assignment: Any = None,
    ) -> NetRouterResult:
        """Route a single net.

        Args:
            net_name: Name of the net to route
            pin_positions: List of pin cell positions
            assignment: Optional pin-to-order assignment

        Returns:
            NetRouterResult with path or failure reason
        """
        if self._maze_router is None:
            return NetRouterResult(
                success=False,
                net_name=net_name,
                failure_reason="No maze_router configured",
            )

        try:
            path = self._maze_router.route_net_adaptive(
                net_name=net_name,
                pin_positions=pin_positions,
                assignment=assignment,
                max_iterations=self.config.max_iterations,
                allow_layer_change=self.config.allow_layer_change,
                via_cost=self.config.via_cost,
                strict_mode=self.config.strict_mode,
                soft_blocking=self.config.soft_blocking,
                layer_balance_weight=self.config.layer_balance_weight,
                congestion_via_discount=self.config.congestion_via_discount,
            )

            if path is None or path.status.value == "No path":
                return NetRouterResult(
                    success=False,
                    net_name=net_name,
                    failure_reason=f"Routing failed: {getattr(path, 'status', 'unknown')}",
                )

            via_count = getattr(path, "via_count", 0)
            length = getattr(path, "length", 0.0)

            return NetRouterResult(
                success=True,
                net_name=net_name,
                path=path,
                length=length,
                via_count=via_count,
            )

        except Exception as e:
            return NetRouterResult(
                success=False,
                net_name=net_name,
                failure_reason=f"Routing exception: {str(e)}",
            )

    def route_with_iterations(
        self,
        net_name: str,
        pin_positions: list[GridCell],
        assignment: Any = None,
    ) -> NetRouterResult:
        """Route a single net with rip-up and re-route iterations.

        Args:
            net_name: Name of the net to route
            pin_positions: List of pin cell positions
            assignment: Optional pin-to-order assignment

        Returns:
            NetRouterResult with path, iterations, and failure details
        """
        if self._maze_router is None:
            return NetRouterResult(
                success=False,
                net_name=net_name,
                failure_reason="No maze_router configured",
            )

        result = self.route(net_name, pin_positions, assignment)

        # Track iterations used
        if hasattr(result.path, "iterations"):
            result.iterations = result.path.iterations
        else:
            result.iterations = 1

        return result


def create_net_router(
    maze_router=None,
    max_iterations: int = 3,
    allow_layer_change: bool = True,
    via_cost: float = 1.0,
    strict_mode: bool = False,
    soft_blocking: bool = True,
) -> NetRouter:
    """Create a NetRouter with the specified configuration.

    Convenience function for creating a configured NetRouter.

    Args:
        maze_router: Optional MazeRouter instance
        max_iterations: Maximum rip-up and re-route iterations
        allow_layer_change: Whether to allow layer transitions
        via_cost: Base cost for via placement
        strict_mode: Whether to use strict DRC checking
        soft_blocking: Whether to use soft blocking for negotiation

    Returns:
        Configured NetRouter instance
    """
    config = NetRouterConfig(
        max_iterations=max_iterations,
        allow_layer_change=allow_layer_change,
        via_cost=via_cost,
        strict_mode=strict_mode,
        soft_blocking=soft_blocking,
    )
    router = NetRouter(config=config, maze_router=maze_router)
    return router
