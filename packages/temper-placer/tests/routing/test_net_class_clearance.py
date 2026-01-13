"""
Tests for net-class-aware clearance inflation (temper-ctr6).

The router should use different clearance requirements based on net class:
- HighVoltage: 2.0mm
- HighCurrent: 1.0mm
- Power: 0.5mm
- Signal: 0.2mm
- default: 0.3mm
"""

import pytest
import numpy as np

from temper_placer.routing.maze_router import (
    MazeRouter,
    CLASS_DEFAULT,
    CLASS_HV,
    CLASS_LV,
)


class TestNetClassClearance:
    """Tests for net class clearance lookup and inflation."""

    def test_net_class_clearance_constant_exists(self):
        """NET_CLASS_CLEARANCE constant should be defined in maze_router."""
        from temper_placer.routing import maze_router

        assert hasattr(maze_router, "NET_CLASS_CLEARANCE")
        assert "HighVoltage" in maze_router.NET_CLASS_CLEARANCE
        assert "HighCurrent" in maze_router.NET_CLASS_CLEARANCE
        assert "Power" in maze_router.NET_CLASS_CLEARANCE
        assert "Signal" in maze_router.NET_CLASS_CLEARANCE
        assert "default" in maze_router.NET_CLASS_CLEARANCE

    def test_hv_clearance_is_largest(self):
        """HighVoltage clearance should be the largest."""
        from temper_placer.routing import maze_router

        hv_clearance = maze_router.NET_CLASS_CLEARANCE["HighVoltage"]
        for key, value in maze_router.NET_CLASS_CLEARANCE.items():
            if key != "HighVoltage":
                assert hv_clearance >= value, (
                    f"HighVoltage ({hv_clearance}) should be >= {key} ({value})"
                )

    def test_get_clearance_for_pair_hv_to_signal(self):
        """HV to Signal pair should use max of both clearances."""
        from temper_placer.routing.maze_router import get_clearance_for_pair

        clearance = get_clearance_for_pair("HighVoltage", "Signal")
        hv_clearance = 2.0
        signal_clearance = 0.2
        assert clearance == max(hv_clearance, signal_clearance)

    def test_get_clearance_for_pair_signal_to_signal(self):
        """Signal to Signal pair should use signal clearance."""
        from temper_placer.routing.maze_router import get_clearance_for_pair

        clearance = get_clearance_for_pair("Signal", "Signal")
        assert clearance == 0.2

    def test_get_clearance_for_pair_power_to_signal(self):
        """Power to Signal pair should use max of both."""
        from temper_placer.routing.maze_router import get_clearance_for_pair

        clearance = get_clearance_for_pair("Power", "Signal")
        assert clearance == max(0.5, 0.2)

    def test_get_clearance_for_pair_unknown_class(self):
        """Unknown net class should fall back to default."""
        from temper_placer.routing.maze_router import get_clearance_for_pair

        clearance = get_clearance_for_pair("UnknownClass", "Signal")
        assert clearance == 0.3  # default


class TestBlockTracesNetClassAware:
    """Tests for net-class-aware trace blocking in MazeRouter."""

    def test_block_traces_with_net_class(self):
        """block_traces should accept net_class parameter for clearance inflation."""
        from temper_placer.io.kicad_parser import TraceData

        router = MazeRouter(
            grid_size=(50, 50),
            cell_size_mm=0.2,
            num_layers=2,
            min_clearance=0.2,
        )

        trace = TraceData(
            start=(5.0, 5.0),
            end=(6.0, 5.0),
            width=0.25,
            layer="F.Cu",
            net="HV_NET",
        )

        original_blocked_count = np.sum(router.occupancy != 0)

        router.block_traces([trace], net_class="HighVoltage")

        new_blocked_count = np.sum(router.occupancy != 0)
        assert new_blocked_count > original_blocked_count

    def test_hv_trace_blocks_more_area_than_signal(self):
        """HV trace should block larger area than Signal trace."""
        from temper_placer.io.kicad_parser import TraceData

        router = RouterForTest(
            grid_size=(50, 50),
            cell_size_mm=0.2,
            num_layers=2,
            min_clearance=0.2,
        )

        trace = TraceData(
            start=(5.0, 5.0),
            end=(6.0, 5.0),
            width=0.25,
            layer="F.Cu",
            net="TEST_NET",
        )

        router2 = RouterForTest(
            grid_size=(50, 50),
            cell_size_mm=0.2,
            num_layers=2,
            min_clearance=0.2,
        )

        router.block_traces([trace], net_class="HighVoltage")
        router2.block_traces([trace], net_class="Signal")

        blocked_hv = np.sum(router.occupancy != 0)
        blocked_signal = np.sum(router2.occupancy != 0)

        assert blocked_hv > blocked_signal, (
            f"HV should block more area ({blocked_hv}) than Signal ({blocked_signal})"
        )

    def test_block_traces_preserves_net_exclusion(self):
        """Same net should be able to route through its own traces."""
        from temper_placer.io.kicad_parser import TraceData

        router = MazeRouter(
            grid_size=(50, 50),
            cell_size_mm=0.2,
            num_layers=2,
            min_clearance=0.2,
        )

        trace = TraceData(
            start=(5.0, 5.0),
            end=(6.0, 5.0),
            width=0.25,
            layer="F.Cu",
            net="NET_A",
        )

        router.block_traces([trace], net_class="Signal")

        cell = router.grid_converter.world_to_grid(5.5, 5.0)
        assert router.occupancy[cell[0], cell[1], 0] == 2

    def test_different_nets_blocked_for_other_routing(self):
        """Different nets should be blocked when routing."""
        from temper_placer.io.kicad_parser import TraceData

        router = MazeRouter(
            grid_size=(50, 50),
            cell_size_mm=0.2,
            num_layers=2,
            min_clearance=0.2,
        )

        trace = TraceData(
            start=(5.0, 5.0),
            end=(6.0, 5.0),
            width=0.25,
            layer="F.Cu",
            net="NET_A",
        )

        router.block_traces([trace], net_class="Signal", blocking_nets=["NET_B"])

        cell = router.grid_converter.world_to_grid(5.5, 5.0)
        assert router.occupancy[cell[0], cell[1], 0] == 2


class TestClearanceInflationIntegration:
    """Integration tests for net-class-aware clearance in routing."""

    def test_hv_net_avoids_signal_net_clearance(self):
        """HV net should maintain required clearance from Signal net."""
        from temper_placer.io.kicad_parser import TraceData

        router = MazeRouter(
            grid_size=(100, 100),
            cell_size_mm=0.2,
            num_layers=1,
            min_clearance=0.2,
        )

        hv_trace = TraceData(
            start=(10.0, 10.0),
            end=(10.0, 15.0),
            width=0.25,
            layer="F.Cu",
            net="HV_POWER",
        )

        router.block_traces([hv_trace], net_class="HighVoltage")

        cell_near_hv = router.grid_converter.world_to_grid(10.5, 12.0)
        cell_far_from_hv = router.grid_converter.world_to_grid(15.0, 12.0)

        assert router.occupancy[cell_near_hv[0], cell_near_hv[1], 0] != 0
        assert router.occupancy[cell_far_from_hv[0], cell_far_from_hv[1], 0] == 0

    def test_power_net_clearance_intermediate(self):
        """Power net should have intermediate clearance (between HV and Signal)."""
        from temper_placer.io.kicad_parser import TraceData

        router = MazeRouter(
            grid_size=(100, 100),
            cell_size_mm=0.2,
            num_layers=1,
            min_clearance=0.2,
        )

        power_trace = TraceData(
            start=(10.0, 10.0),
            end=(10.0, 15.0),
            width=0.3,
            layer="F.Cu",
            net="VCC",
        )

        router.block_traces([power_trace], net_class="Power")

        blocked_count = np.sum(router.occupancy != 0)

        assert blocked_count > 0


class RouterForTest(MazeRouter):
    """Test subclass that exposes protected methods for testing."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
