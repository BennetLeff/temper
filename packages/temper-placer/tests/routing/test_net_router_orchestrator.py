"""Tests for NetRouter orchestrator.

Tests for the net routing orchestrator that manages routing of multiple nets
with different routing strategies and coordination.
"""

from dataclasses import dataclass
from typing import Any
import pytest


class MockRouteResult:
    """Mock route result for testing."""

    def __init__(self, success: bool = True, length: float = 0.0, via_count: int = 0):
        self.success = success
        self.length = length
        self.via_count = via_count
        self.cells = []
        self.failure_reason = None if success else "Unknown failure"


class MockNetRouter:
    """Mock net router for testing."""

    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.routed_nets = []
        self.call_args = []

    def route_net(self, net_name: str, **kwargs: Any) -> MockRouteResult:
        self.call_args.append(("route_net", net_name, kwargs))
        if self.should_fail and net_name.startswith("fail"):
            return MockRouteResult(success=False, failure_reason=f"Failed to route {net_name}")
        return MockRouteResult(success=True, length=10.0, via_count=2)

    def rip_up_net(self, net_name: str, **kwargs: Any) -> None:
        self.call_args.append(("rip_up_net", net_name, kwargs))
        if net_name in self.routed_nets:
            self.routed_nets.remove(net_name)


class TestNetRouterOrchestrator:
    """Test basic net router orchestrator functionality."""

    def test_orchestrator_creation(self):
        from temper_placer.routing.orchestrator import NetRouterOrchestrator

        orchestrator = NetRouterOrchestrator()
        assert orchestrator is not None

    def test_register_router(self):
        from temper_placer.routing.orchestrator import NetRouterOrchestrator

        orchestrator = NetRouterOrchestrator()
        mock_router = MockNetRouter()
        orchestrator.register_router("rrr", mock_router)
        assert "rrr" in orchestrator._routers

    def test_get_router(self):
        from temper_placer.routing.orchestrator import NetRouterOrchestrator

        orchestrator = NetRouterOrchestrator()
        mock_router = MockNetRouter()
        orchestrator.register_router("rrr", mock_router)
        router = orchestrator.get_router("rrr")
        assert router is mock_router

    def test_unknown_router_raises(self):
        from temper_placer.routing.orchestrator import NetRouterOrchestrator

        orchestrator = NetRouterOrchestrator()
        with pytest.raises(ValueError):
            orchestrator.get_router("unknown")


class TestRoutingStrategies:
    """Test routing strategy selection."""

    def test_strategy_selection_by_net_count(self):
        from temper_placer.routing.orchestrator import select_strategy_for_net

        # 2-pin net should use direct strategy
        strategy = select_strategy_for_net(pin_count=2)
        assert strategy == "direct"

    def test_strategy_selection_multi_pin(self):
        from temper_placer.routing.orchestrator import select_strategy_for_net

        # Multi-pin net should use MST strategy
        strategy = select_strategy_for_net(pin_count=5)
        assert strategy == "mst"

    def test_strategy_selection_critical(self):
        from temper_placer.routing.orchestrator import select_strategy_for_net

        # Critical nets should use adaptive strategy
        strategy = select_strategy_for_net(pin_count=3, is_critical=True)
        assert strategy == "adaptive"


class TestRoutingResults:
    """Test routing result handling."""

    def test_result_success(self):
        from temper_placer.routing.orchestrator import RoutingResult

        result = RoutingResult(success=True, net_name="net_a", length=10.0)
        assert result.success is True
        assert result.net_name == "net_a"
        assert result.length == 10.0

    def test_result_failure(self):
        from temper_placer.routing.orchestrator import RoutingResult

        result = RoutingResult(success=False, net_name="net_b")
        assert result.success is False

    def test_result_summary(self):
        from temper_placer.routing.orchestrator import RoutingResult, RoutingSummary

        results = [
            RoutingResult(success=True, net_name="net_a", length=10.0),
            RoutingResult(success=True, net_name="net_b", length=20.0),
            RoutingResult(success=False, net_name="net_c"),
        ]
        summary = RoutingSummary(results)
        assert summary.success_count == 2
        assert summary.failure_count == 1
        assert summary.completion_rate == pytest.approx(2 / 3)


class TestNetRoutingOrder:
    """Test net ordering for routing."""

    def test_order_nets_by_length(self):
        from temper_placer.routing.orchestrator import order_nets_by_priority

        nets = [
            {"name": "net_a", "pin_count": 2, "wirelength": 100.0},
            {"name": "net_b", "pin_count": 2, "wirelength": 50.0},
            {"name": "net_c", "pin_count": 2, "wirelength": 75.0},
        ]
        ordered = order_nets_by_priority(nets, strategy="shortest_first")
        assert ordered[0]["name"] == "net_b"
        assert ordered[1]["name"] == "net_c"
        assert ordered[2]["name"] == "net_a"

    def test_order_nets_by_priority(self):
        from temper_placer.routing.orchestrator import order_nets_by_priority

        nets = [
            {"name": "net_a", "pin_count": 2, "wirelength": 100.0, "priority": 1},
            {"name": "net_b", "pin_count": 2, "wirelength": 50.0, "priority": 3},
            {"name": "net_c", "pin_count": 2, "wirelength": 75.0, "priority": 2},
        ]
        ordered = order_nets_by_priority(nets, strategy="priority")
        assert ordered[0]["name"] == "net_a"
        assert ordered[1]["name"] == "net_c"
        assert ordered[2]["name"] == "net_b"


class TestRoutingStatistics:
    """Test routing statistics tracking."""

    def test_statistics_creation(self):
        from temper_placer.routing.orchestrator import RoutingStatistics

        stats = RoutingStatistics()
        assert stats.total_nets == 0
        assert stats.successful_routes == 0
        assert stats.failed_routes == 0
        assert stats.total_vias == 0

    def test_statistics_update(self):
        from temper_placer.routing.orchestrator import RoutingStatistics

        stats = RoutingStatistics()
        stats.record_result(success=True, via_count=3, length=10.0)
        stats.record_result(success=True, via_count=2, length=15.0)
        stats.record_result(success=False)
        assert stats.total_nets == 3
        assert stats.successful_routes == 2
        assert stats.failed_routes == 1
        assert stats.total_vias == 5
        assert stats.total_length == 25.0

    def test_statistics_completion_rate(self):
        from temper_placer.routing.orchestrator import RoutingStatistics

        stats = RoutingStatistics()
        for _ in range(7):
            stats.record_result(success=True)
        for _ in range(3):
            stats.record_result(success=False)
        assert stats.completion_rate == pytest.approx(7 / 10)


class TestRoutingConfig:
    """Test routing configuration."""

    def test_default_config(self):
        from temper_placer.routing.orchestrator import RoutingConfig

        config = RoutingConfig()
        assert config.max_iterations == 3
        assert config.allow_layer_change is True
        assert config.via_cost == 1.0

    def test_custom_config(self):
        from temper_placer.routing.orchestrator import RoutingConfig

        config = RoutingConfig(
            max_iterations=5,
            via_cost=2.0,
            strict_mode=True,
        )
        assert config.max_iterations == 5
        assert config.via_cost == 2.0
        assert config.strict_mode is True
