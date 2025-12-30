"""
Tests for C-Space Routing Pipeline.

Part of temper-2qqd: Integration: Wire Up C-Space Pipeline
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

from temper_placer.routing.c_space_pipeline import (
    CSpaceRoutingPipeline,
    PipelineConfig,
    RoutingResult,
    FunnelSmoother,
    TraceBallooner,
)


class TestPipelineConfig:
    """Tests for PipelineConfig."""

    def test_default_config(self):
        config = PipelineConfig()
        assert config.resolution_mm == 0.1
        assert config.enable_dithering is True
        assert config.enable_smoothing is True
        assert config.enable_ballooning is True
        assert config.max_dither_attempts == 4
        assert config.via_cost == 50.0
        assert "DC_BUS+" in config.power_nets

    def test_custom_config(self):
        config = PipelineConfig(
            resolution_mm=0.05,
            enable_dithering=False,
            max_dither_attempts=8,
            via_cost=100.0,
        )
        assert config.resolution_mm == 0.05
        assert config.enable_dithering is False
        assert config.max_dither_attempts == 8
        assert config.via_cost == 100.0


class TestRoutingResult:
    """Tests for RoutingResult."""

    def test_routing_result_creation(self):
        result = RoutingResult(
            net_results={},
            total_time_ms=100.0,
            successful_count=5,
            failed_count=1,
            completion_rate=83.33,
        )
        assert result.total_time_ms == 100.0
        assert result.successful_count == 5
        assert result.failed_count == 1
        assert result.completion_rate == 83.33

    def test_routing_result_with_results(self):
        from temper_placer.routing.maze_router import RoutePath, GridCell

        mock_path = RoutePath(
            net="test_net",
            cells=[GridCell(0, 0), GridCell(1, 0), GridCell(2, 0)],
            length=3.0,
            via_count=0,
            success=True,
        )
        result = RoutingResult(
            net_results={"test_net": mock_path},
            total_time_ms=50.0,
            successful_count=1,
            failed_count=0,
            completion_rate=100.0,
        )
        assert "test_net" in result.net_results
        assert result.net_results["test_net"].success is True


class TestFunnelSmoother:
    """Tests for FunnelSmoother."""

    def test_smoother_initialization(self):
        smoother = FunnelSmoother(cell_size_mm=0.1)
        assert smoother.cell_size == 0.1

    def test_smoother_empty_path(self):
        smoother = FunnelSmoother()
        result = smoother.smooth([], Mock())
        assert result == []

    def test_smoother_single_cell(self):
        smoother = FunnelSmoother()
        mock_c_space = Mock()
        mock_c_space.pixel_to_world.return_value = (1.0, 2.0)

        from temper_placer.routing.maze_router import GridCell

        path = [GridCell(10, 20)]
        result = smoother.smooth(path, mock_c_space)

        assert len(result) == 1
        mock_c_space.pixel_to_world.assert_called_once()

    def test_smoother_multiple_cells(self):
        smoother = FunnelSmoother()
        mock_c_space = Mock()
        mock_c_space.pixel_to_world.side_effect = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]

        from temper_placer.routing.maze_router import GridCell

        path = [GridCell(0, 0), GridCell(10, 0), GridCell(20, 0)]
        result = smoother.smooth(path, mock_c_space)

        assert len(result) == 3

    def test_validate_path_valid(self):
        smoother = FunnelSmoother()
        mock_c_space = Mock()
        mock_c_space.is_free.return_value = True

        waypoints = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
        assert smoother.validate_path(waypoints, mock_c_space) is True

    def test_validate_path_invalid(self):
        smoother = FunnelSmoother()
        mock_c_space = Mock()
        mock_c_space.is_free.side_effect = [True, False, True]

        waypoints = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
        assert smoother.validate_path(waypoints, mock_c_space) is False


class TestTraceBallooner:
    """Tests for TraceBallooner."""

    def test_ballooner_initialization(self):
        ballooner = TraceBallooner(power_nets=["VCC", "GND"])
        assert "VCC" in ballooner.power_nets
        assert "GND" in ballooner.power_nets
        assert ballooner.max_width == 6.0
        assert ballooner.safety_margin == 0.2

    def test_ballooner_non_power_net(self):
        ballooner = TraceBallooner(power_nets=["VCC"])
        mock_c_space = Mock()

        waypoints = [(0.0, 0.0), (1.0, 0.0)]
        tracks = ballooner.balloon_traces("SIGNAL_NET", waypoints, mock_c_space)

        assert len(tracks) == 1
        assert tracks[0][2] == 0.2  # Default trace width

    def test_ballooner_power_net(self):
        ballooner = TraceBallooner(power_nets=["DC_BUS+"])
        ballooner._get_max_clearance = Mock(return_value=5.0)
        mock_c_space = Mock()

        waypoints = [(0.0, 0.0), (1.0, 0.0)]
        tracks = ballooner.balloon_traces("DC_BUS+", waypoints, mock_c_space)

        assert len(tracks) == 1
        assert tracks[0][2] > 0.2  # Should be expanded


class TestCSpaceRoutingPipeline:
    """Tests for CSpaceRoutingPipeline."""

    @pytest.fixture
    def mock_board(self):
        board = Mock()
        board.width = 100.0
        board.height = 140.0
        board.origin = (0.0, 0.0)
        board.source_pcb = Path("/mock/board.kicad_pcb")
        return board

    @pytest.fixture
    def mock_netlist(self):
        netlist = Mock()
        netlist.components = []
        return netlist

    def test_pipeline_initialization(self, mock_board, mock_netlist):
        pipeline = CSpaceRoutingPipeline(mock_board, mock_netlist)
        assert pipeline.board == mock_board
        assert pipeline.netlist == mock_netlist
        assert pipeline.config is not None
        assert pipeline.c_space_builder is not None
        assert pipeline.c_space_cache is not None
        assert pipeline.smoother is not None
        assert pipeline.ballooner is not None

    def test_net_classification(self, mock_board, mock_netlist):
        pipeline = CSpaceRoutingPipeline(mock_board, mock_netlist)

        assert pipeline._classify_net("DC_BUS+") == "DC_BUS"
        assert pipeline._classify_net("VBUS") == "DC_BUS"
        assert pipeline._classify_net("AC_L") == "MAINS"
        assert pipeline._classify_net("AC_N") == "MAINS"
        assert pipeline._classify_net("SIGNAL_A") == "LOGIC"
        assert pipeline._classify_net("GPIO_0") == "LOGIC"

    def test_get_pin_positions_empty(self, mock_board, mock_netlist):
        pipeline = CSpaceRoutingPipeline(mock_board, mock_netlist)
        positions = pipeline._get_pin_positions("NONEXISTENT_NET")
        assert positions == []

    def test_clear_cache(self, mock_board, mock_netlist):
        pipeline = CSpaceRoutingPipeline(mock_board, mock_netlist)
        pipeline.clear_cache()
        assert pipeline.c_space_cache.cache_size == 0

    def test_get_cache_stats(self, mock_board, mock_netlist):
        pipeline = CSpaceRoutingPipeline(mock_board, mock_netlist)
        stats = pipeline.get_cache_stats()

        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate" in stats
        assert "cache_size" in stats
        assert "memory_mb" in stats

    def test_initialize_router_without_dithering(self, mock_board, mock_netlist):
        config = PipelineConfig(enable_dithering=False)
        pipeline = CSpaceRoutingPipeline(mock_board, mock_netlist, config)
        pipeline.initialize_router()

        from temper_placer.routing.maze_router import MazeRouter

        assert isinstance(pipeline.router, MazeRouter)

    def test_initialize_router_with_dithering(self, mock_board, mock_netlist):
        config = PipelineConfig(enable_dithering=True)
        pipeline = CSpaceRoutingPipeline(mock_board, mock_netlist, config)
        pipeline.initialize_router()

        from temper_placer.routing.dithered_router import DitheredRouter

        assert isinstance(pipeline.router, DitheredRouter)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
