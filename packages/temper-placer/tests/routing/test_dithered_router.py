"""
Tests for Dithered Router (temper-akrc).

Tests the grid origin dithering functionality for escaping aliasing deadlocks.
"""

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock, patch

from temper_placer.routing.dithered_router import (
    DitheredRouter,
    DitherConfig,
    DitherAttempt,
)


class MockGridCell:
    """Mock GridCell for testing."""

    def __init__(self, x: int, y: int, layer: int = 0):
        self.x = x
        self.y = y
        self.layer = layer

    def __repr__(self):
        return f"GridCell({self.x}, {self.y}, L{self.layer})"


class MockRoutePath:
    """Mock RoutePath for testing."""

    def __init__(
        self,
        net: str,
        success: bool,
        cells: list[MockGridCell] | None = None,
        failure_reason: str | None = None,
    ):
        self.net = net
        self.success = success
        self.cells = cells or []
        self.length = len(cells) if cells else 0.0
        self.via_count = 0
        self.failure_reason = failure_reason


class MockMazeRouter:
    """Mock MazeRouter for testing."""

    def __init__(self):
        self.origin = (0.0, 0.0)
        self.cell_size = 0.1
        self.num_layers = 2
        self.layer_stackup = Mock()
        self.layer_stackup.layers = [Mock(), Mock()]
        self._route_calls = []

    def _world_to_grid(self, x: float, y: float):
        return (int(x / self.cell_size), int(y / self.cell_size))

    def route_net(self, net_name, pin_positions, assignment=None, cost_map=None):
        self._route_calls.append((net_name, pin_positions, assignment))
        return MockRoutePath(net_name, success=True, cells=[MockGridCell(1, 1)])

    def find_path_rrr(self, start, end, layer=0, **kwargs):
        return [MockGridCell(*start), MockGridCell(*end)]


class TestDitherConfig:
    """Tests for DitherConfig dataclass."""

    def test_default_config(self):
        config = DitherConfig()
        assert config.enable_dithering is True
        assert config.max_attempts == 4
        assert len(config.origin_offsets) == 4

    def test_custom_config(self):
        config = DitherConfig(
            enable_dithering=False,
            max_attempts=2,
            origin_offsets=[(0.0, 0.0), (0.05, 0.05)],
        )
        assert config.enable_dithering is False
        assert config.max_attempts == 2
        assert len(config.origin_offsets) == 2

    def test_default_offsets(self):
        config = DitherConfig()
        offsets = config.origin_offsets
        assert offsets[0] == (0.0, 0.0)
        assert offsets[1] == (0.025, 0.025)
        assert offsets[2] == (-0.025, 0.025)
        assert offsets[3] == (0.0125, -0.0125)


class TestDitherAttempt:
    """Tests for DitherAttempt dataclass."""

    def test_successful_attempt(self):
        attempt = DitherAttempt(
            offset_x=0.0,
            offset_y=0.0,
            success=True,
            path=[MockGridCell(1, 1), MockGridCell(2, 2)],
            length=2.0,
            via_count=0,
            time_ms=10.5,
        )
        assert attempt.success is True
        assert attempt.path is not None
        assert attempt.length == 2.0

    def test_failed_attempt(self):
        attempt = DitherAttempt(
            offset_x=0.025,
            offset_y=0.025,
            success=False,
            path=None,
            time_ms=5.0,
            failure_reason="No path found",
        )
        assert attempt.success is False
        assert attempt.path is None
        assert attempt.failure_reason == "No path found"


class TestDitheredRouter:
    """Tests for DitheredRouter class."""

    def test_init_with_defaults(self):
        mock_router = MockMazeRouter()
        router = DitheredRouter(mock_router)
        assert router.base_router is mock_router
        assert router.c_space_builder is None
        assert router.config.enable_dithering is True

    def test_init_with_c_space_builder(self):
        mock_router = MockMazeRouter()
        mock_c_space_builder = Mock()
        router = DitheredRouter(mock_router, c_space_builder=mock_c_space_builder)
        assert router.c_space_builder is mock_c_space_builder

    def test_init_with_custom_config(self):
        mock_router = MockMazeRouter()
        config = DitherConfig(enable_dithering=False)
        router = DitheredRouter(mock_router, config=config)
        assert router.config.enable_dithering is False

    def test_apply_origin_offset(self):
        mock_router = MockMazeRouter()
        router = DitheredRouter(mock_router)

        assert router._original_origin is None
        router._apply_origin_offset(0.025, 0.025)
        assert router._original_origin == (0.0, 0.0)
        assert router.base_router.origin == (0.025, 0.025)

    def test_reset_origin(self):
        mock_router = MockMazeRouter()
        router = DitheredRouter(mock_router)

        router._apply_origin_offset(0.025, 0.025)
        assert router.base_router.origin != (0.0, 0.0)

        router._reset_origin()
        assert router._original_origin is None
        assert router.base_router.origin == (0.0, 0.0)

    def test_route_net_standard_success(self):
        mock_router = MockMazeRouter()
        router = DitheredRouter(mock_router)

        result = router.route_net(
            net_name="TEST_NET",
            pin_positions=[(0.0, 0.0), (1.0, 1.0)],
        )

        assert result.success is True
        assert result.net == "TEST_NET"

    def test_route_net_with_dithering_first_attempt_success(self):
        mock_router = MockMazeRouter()
        router = DitheredRouter(mock_router)

        result = router.route_net(
            net_name="TEST_NET",
            pin_positions=[(0.0, 0.0), (1.0, 1.0)],
        )

        assert result.success is True
        assert len(router.last_attempts) == 1
        assert router.last_attempts[0].offset_x == 0.0
        assert router.last_attempts[0].offset_y == 0.0

    def test_route_net_with_dithering_fallback(self):
        mock_router = MockMazeRouter()
        router = DitheredRouter(mock_router)

        call_count = [0]

        def mock_route(net_name, pin_positions, assignment=None, cost_map=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return MockRoutePath(
                    net_name, success=False, failure_reason="First attempt blocked"
                )
            return MockRoutePath(net_name, success=True, cells=[MockGridCell(1, 1)])

        mock_router.route_net = mock_route

        result = router.route_net(
            net_name="TEST_NET",
            pin_positions=[(0.0, 0.0), (1.0, 1.0)],
        )

        assert result.success is True
        assert len(router.last_attempts) == 2

    def test_route_net_all_attempts_fail(self):
        mock_router = MockMazeRouter()
        router = DitheredRouter(mock_router)

        def mock_route(net_name, pin_positions, assignment=None, cost_map=None):
            return MockRoutePath(net_name, success=False, failure_reason="Always blocked")

        mock_router.route_net = mock_route

        result = router.route_net(
            net_name="TEST_NET",
            pin_positions=[(0.0, 0.0), (1.0, 1.0)],
        )

        assert result.success is False
        assert "Aliasing deadlock" in result.failure_reason
        assert len(router.last_attempts) == 4

    def test_route_net_dithering_disabled(self):
        mock_router = MockMazeRouter()
        config = DitherConfig(enable_dithering=False)
        router = DitheredRouter(mock_router, config=config)

        result = router.route_net(
            net_name="TEST_NET",
            pin_positions=[(0.0, 0.0), (1.0, 1.0)],
        )

        assert result.success is True
        assert len(router.last_attempts) == 0

    def test_route_net_with_custom_max_attempts(self):
        mock_router = MockMazeRouter()
        config = DitherConfig(max_attempts=2)
        router = DitheredRouter(mock_router, config=config)

        call_count = [0]

        def mock_route(net_name, pin_positions, assignment=None, cost_map=None):
            call_count[0] += 1
            return MockRoutePath(net_name, success=False, failure_reason="Blocked")

        mock_router.route_net = mock_route

        result = router.route_net(
            net_name="TEST_NET",
            pin_positions=[(0.0, 0.0), (1.0, 1.0)],
        )

        assert result.success is False
        assert len(router.last_attempts) == 2

    def test_get_diagnostic_report_success(self):
        mock_router = MockMazeRouter()
        router = DitheredRouter(mock_router)

        router.route_net(
            net_name="TEST_NET",
            pin_positions=[(0.0, 0.0), (1.0, 1.0)],
        )

        report = router.get_diagnostic_report()

        assert report["total_attempts"] == 1
        assert report["successful_offset"] == (0.0, 0.0)
        assert report["total_time_ms"] > 0

    def test_get_diagnostic_report_failure(self):
        mock_router = MockMazeRouter()
        router = DitheredRouter(mock_router)

        def mock_route(net_name, pin_positions, assignment=None, cost_map=None):
            return MockRoutePath(net_name, success=False, failure_reason="Blocked")

        mock_router.route_net = mock_route

        router.route_net(
            net_name="TEST_NET",
            pin_positions=[(0.0, 0.0), (1.0, 1.0)],
        )

        report = router.get_diagnostic_report()

        assert report["total_attempts"] == 4
        assert report["successful_offset"] is None

    def test_last_attempts_property(self):
        mock_router = MockMazeRouter()
        router = DitheredRouter(mock_router)

        assert router.last_attempts == []

        router.route_net(
            net_name="TEST_NET",
            pin_positions=[(0.0, 0.0), (1.0, 1.0)],
        )

        assert len(router.last_attempts) == 1
        assert isinstance(router.last_attempts[0], DitherAttempt)

    def test_origin_offset_tracking(self):
        mock_router = MockMazeRouter()
        router = DitheredRouter(mock_router)

        router.route_net(
            net_name="TEST_NET",
            pin_positions=[(0.0, 0.0), (1.0, 1.0)],
        )

        assert router._original_origin is None

    def test_apply_inverse_offset_identity(self):
        mock_router = MockMazeRouter()
        router = DitheredRouter(mock_router)
        router._original_origin = (0.0, 0.0)

        path = [MockGridCell(1, 1), MockGridCell(2, 2)]
        result = router._apply_inverse_offset(path, 0.0, 0.0)

        assert result == path

    def test_apply_inverse_offset_nonzero(self):
        mock_router = MockMazeRouter()
        router = DitheredRouter(mock_router)
        router._original_origin = (0.0, 0.0)
        router.base_router.origin = (0.025, 0.025)

        path = [MockGridCell(10, 10), MockGridCell(20, 20)]
        result = router._apply_inverse_offset(path, 0.025, 0.025)

        assert len(result) == 2


class TestDitheredRouterIntegration:
    """Integration tests for dithered router with simulated aliasing."""

    def test_aliasing_escape_scenario(self):
        """
        Simulate an aliasing scenario where first attempt fails
        but second attempt with offset succeeds.
        """
        mock_router = MockMazeRouter()
        router = DitheredRouter(mock_router)

        attempts_before_success = [0]

        def mock_route(net_name, pin_positions, assignment=None, cost_map=None):
            attempts_before_success[0] += 1
            if attempts_before_success[0] == 1:
                return MockRoutePath(
                    net_name, success=False, failure_reason="Phantom block at boundary"
                )
            return MockRoutePath(net_name, success=True, cells=[MockGridCell(1, 1)])

        mock_router.route_net = mock_route

        result = router.route_net(
            net_name="GATE_DRIVER_FANOUT",
            pin_positions=[(5.0, 5.0), (5.5, 5.0)],
        )

        assert result.success is True
        assert attempts_before_success[0] == 2
        assert router.last_attempts[1].offset_x == 0.025
        assert router.last_attempts[1].offset_y == 0.025

    def test_diagnostic_report_format(self):
        """Test that diagnostic report has expected structure."""
        mock_router = MockMazeRouter()
        router = DitheredRouter(mock_router)

        def mock_route(net_name, pin_positions, assignment=None, cost_map=None):
            return MockRoutePath(net_name, success=False, failure_reason="Blocked")

        mock_router.route_net = mock_route

        router.route_net(
            net_name="TEST_NET",
            pin_positions=[(0.0, 0.0), (1.0, 1.0)],
        )

        report = router.get_diagnostic_report()

        assert "total_attempts" in report
        assert "successful_offset" in report
        assert "attempts" in report
        assert "total_time_ms" in report

        assert len(report["attempts"]) == 4
        for attempt in report["attempts"]:
            assert "offset" in attempt
            assert "success" in attempt
            assert "time_ms" in attempt
            assert "failure_reason" in attempt
