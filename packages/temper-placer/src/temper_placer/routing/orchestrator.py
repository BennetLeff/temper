"""Net router orchestrator for managing routing of multiple nets.

Provides coordination, strategy selection, and result tracking for
batch routing operations.
"""

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class RoutingConfig:
    """Configuration for routing operations.

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
class RoutingResult:
    """Result of routing a single net.

    Attributes:
        success: Whether routing succeeded
        net_name: Name of the net
        length: Path length in cells
        via_count: Number of vias used
        failure_reason: Reason for failure if not successful
    """

    success: bool
    net_name: str
    length: float = 0.0
    via_count: int = 0
    failure_reason: str | None = None


@dataclass
class RoutingSummary:
    """Summary of routing results for multiple nets.

    Attributes:
        results: List of individual routing results
    """

    results: list[RoutingResult]

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def failure_count(self) -> int:
        return sum(1 for r in self.results if not r.success)

    @property
    def completion_rate(self) -> float:
        if not self.results:
            return 1.0
        return self.success_count / len(self.results)

    @property
    def total_length(self) -> float:
        return sum(r.length for r in self.results if r.success)

    @property
    def total_vias(self) -> int:
        return sum(r.via_count for r in self.results if r.success)


@dataclass
class RoutingStatistics:
    """Statistics for routing operations.

    Tracks metrics during routing execution.
    """

    total_nets: int = 0
    successful_routes: int = 0
    failed_routes: int = 0
    total_vias: int = 0
    total_length: float = 0.0
    iterations: int = 0

    def record_result(self, success: bool, via_count: int = 0, length: float = 0.0) -> None:
        """Record a routing result."""
        self.total_nets += 1
        if success:
            self.successful_routes += 1
            self.total_vias += via_count
            self.total_length += length
        else:
            self.failed_routes += 1

    @property
    def completion_rate(self) -> float:
        if self.total_nets == 0:
            return 1.0
        return self.successful_routes / self.total_nets


class NetRouterOrchestrator:
    """Orchestrator for routing multiple nets with different strategies.

    Manages router registration, strategy selection, and result aggregation.
    """

    def __init__(self, config: RoutingConfig | None = None):
        self.config = config or RoutingConfig()
        self._routers: dict[str, Any] = {}
        self._statistics = RoutingStatistics()

    def register_router(self, name: str, router: Any) -> None:
        """Register a router implementation.

        Args:
            name: Router identifier
            router: Router instance with route_net method
        """
        self._routers[name] = router

    def get_router(self, name: str) -> Any:
        """Get a registered router.

        Args:
            name: Router identifier

        Returns:
            Router instance

        Raises:
            ValueError: If router not found
        """
        if name not in self._routers:
            available = list(self._routers.keys())
            raise ValueError(f"Unknown router: {name}. Available: {available}")
        return self._routers[name]

    def get_statistics(self) -> RoutingStatistics:
        """Get routing statistics."""
        return self._statistics


def select_strategy_for_net(
    pin_count: int,
    is_critical: bool = False,
    has_obstacles: bool = False,
) -> str:
    """Select appropriate routing strategy for a net.

    Args:
        pin_count: Number of pins in the net
        is_critical: Whether this is a critical net
        has_obstacles: Whether there are many obstacles

    Returns:
        Strategy name to use
    """
    if is_critical:
        return "adaptive"

    if pin_count <= 2:
        return "direct"

    if pin_count <= 5:
        return "mst"

    return "hierarchical"


def order_nets_by_priority(
    nets: list[dict[str, Any]],
    strategy: str = "shortest_first",
) -> list[dict[str, Any]]:
    """Order nets for routing based on strategy.

    Args:
        nets: List of net dictionaries with 'name', 'pin_count', etc.
        strategy: Ordering strategy

    Returns:
        Ordered list of nets
    """
    if strategy == "arbitrary":
        return nets.copy()

    if strategy == "shortest_first":
        return sorted(nets, key=lambda n: n.get("wirelength", 0))

    if strategy == "longest_first":
        return sorted(nets, key=lambda n: n.get("wirelength", 0), reverse=True)

    if strategy == "priority":
        return sorted(nets, key=lambda n: n.get("priority", 0))

    if strategy == "fewest_pins_first":
        return sorted(nets, key=lambda n: n.get("pin_count", 0))

    if strategy == "most_pins_first":
        return sorted(nets, key=lambda n: n.get("pin_count", 0), reverse=True)

    return nets
