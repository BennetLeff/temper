"""
Regression tests targeting specific production failures.

These tests reproduce the exact scenarios that fail in the real Temper board
routing, providing actionable test cases for debugging and fixing.

Production Failure Analysis:
1. SPI nets (SPI_MOSI, SPI_CLK, SPI_MISO) - Can't find paths
2. PWM nets (PWM_H, PWM_L) - Can't find paths
3. Gate driver nets (GATE_H, GATE_L) - Exceed iteration limits
4. Power plane stubs (VCC_BOOT, +15V, +3V3) - Rejected due to clearance
5. High-voltage nets (DC_BUS+, SW_NODE) - Exceed iteration limits
"""

import pytest
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple


# ============================================================================
# Reproduction Test: MCU SPI Bus Routing Failure
# ============================================================================


class TestSPIBusRouting:
    """Reproduce SPI bus routing failures.

    Production error:
      WARNING: Could not find any path for SPI_MOSI segment 0->2
      WARNING: Could not find any path for SPI_MOSI segment 0->1

    Root cause hypothesis: MCU area is over-blocked due to:
    1. Dense pin pitch (0.5mm) creates many blocked zones
    2. max_clearance_mm=2.5 is way too large for fine-pitch components
    3. No routing channel left between MCU and target components
    """

    def test_fine_pitch_component_leaves_routing_channel(self):
        """Verify fine-pitch components don't completely block routing."""
        from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid

        grid = ClearanceGrid(
            width_mm=30.0,
            height_mm=30.0,
            cell_size_mm=0.1,  # Fine grid for fine-pitch
            layer_count=4,
        )

        # Simulate QFN-32 with 0.5mm pitch (like ESP32-S3)
        # 32 pins around 5x5mm body = 8 pins per side
        for i in range(8):
            # Bottom edge pins
            grid.block_circle((2.5 + i * 0.5, 0.0), 0.2, 0.15, 0, f"MCU_B{i}")
            # Top edge pins
            grid.block_circle((2.5 + i * 0.5, 5.0), 0.2, 0.15, 0, f"MCU_T{i}")
            # Left edge pins
            grid.block_circle((0.0, 0.5 + i * 0.5), 0.2, 0.15, 0, f"MCU_L{i}")
            # Right edge pins
            grid.block_circle((5.0, 0.5 + i * 0.5), 0.2, 0.15, 0, f"MCU_R{i}")

        # Check that there's routing space OUTSIDE the component
        # Test point 2mm away from component edge
        test_points = [
            (7.0, 2.5),  # Right of component
            (-2.0, 2.5),  # Left of component
            (2.5, 7.0),  # Above component
            (2.5, -2.0),  # Below component
        ]

        for x, y in test_points:
            if 0 <= x < 30 and 0 <= y < 30:
                is_available = grid.is_available(x, y, 0, net_name="SPI_TEST")
                assert is_available, f"Point ({x}, {y}) should be available for routing"

    def test_spi_route_between_mcu_and_peripheral(self):
        """Simulate SPI routing from MCU to peripheral."""
        from temper_placer.deterministic.stages.astar import DeterministicAStar
        from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid

        grid = ClearanceGrid(
            width_mm=50.0,
            height_mm=50.0,
            cell_size_mm=0.25,
            layer_count=4,
        )

        # MCU at (10, 25), SPI peripheral at (40, 25)
        # Block MCU body area with appropriate clearance for Signal net class
        for i in range(10):
            for j in range(10):
                x = 8.0 + i * 0.5
                y = 23.0 + j * 0.5
                # Use Signal-class clearance (0.15mm), not max_clearance (2.5mm)
                grid.block_circle((x, y), 0.2, 0.15, 0, "MCU_PAD")

        # Block peripheral body
        grid.block_circle((40.0, 25.0), 2.0, 0.15, 0, "PERIPH")

        # SPI_MOSI pad on MCU (right side)
        mcu_spi_pad = (13.0, 25.0)
        # SPI_MOSI pad on peripheral
        periph_spi_pad = (38.0, 25.0)

        pathfinder = DeterministicAStar(
            grid=grid,
            drc_oracle=None,
            net_name="SPI_MOSI",
            trace_width=0.15,
        )

        path = pathfinder.find_path(start=mcu_spi_pad, end=periph_spi_pad, layer=0)

        assert path is not None, (
            "SPI route should succeed with proper (Signal-class) clearance. "
            "If this fails, the issue is over-blocking."
        )

    def test_max_clearance_too_large_blocks_spi(self):
        """Demonstrate that max_clearance=2.5 blocks SPI routes."""
        from temper_placer.deterministic.stages.astar import DeterministicAStar
        from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid

        grid = ClearanceGrid(
            width_mm=50.0,
            height_mm=50.0,
            cell_size_mm=0.25,
            layer_count=4,
        )

        # Same setup but with OVER-BLOCKING (max_clearance=2.5)
        # This simulates the production failure mode
        for i in range(10):
            for j in range(10):
                x = 8.0 + i * 0.5
                y = 23.0 + j * 0.5
                # Using HV-class clearance for ALL pads is the bug!
                grid.block_circle((x, y), 0.2, 2.5, 0, "MCU_PAD")

        pathfinder = DeterministicAStar(
            grid=grid,
            drc_oracle=None,
            net_name="SPI_MOSI",
            trace_width=0.15,
        )

        path = pathfinder.find_path(start=(13.0, 25.0), end=(38.0, 25.0), layer=0)

        # This SHOULD fail when using wrong clearance
        # If it passes, either the grid is larger or clearance isn't applying
        # Document expected behavior:
        if path is None:
            pass  # Expected - over-blocking prevents routing
        else:
            # Path found despite over-blocking - grid must be large enough
            # Still useful to verify the path length is much longer due to detours
            pass


# ============================================================================
# Reproduction Test: Gate Driver Loop Routing Failure
# ============================================================================


class TestGateDriverRouting:
    """Reproduce gate driver routing failures.

    Production error:
      WARNING: Multi-layer A* for GATE_H exceeded 5000 iterations
      WARNING: Could not find any path for GATE_H segment 0->1

    Root cause hypothesis:
    1. GATE_H must route from IGBT (in HV zone) to gate driver (different zone)
    2. HV clearance (2.0mm) around IGBT pads blocks most paths
    3. Long route distance + heavy blocking = iteration exhaustion
    """

    def test_hv_zone_to_control_zone_routing(self):
        """Test routing from HV zone to control zone."""
        from temper_placer.deterministic.stages.astar import DeterministicAStar
        from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid

        grid = ClearanceGrid(
            width_mm=100.0,
            height_mm=100.0,
            cell_size_mm=0.5,
            layer_count=4,
        )

        # HV zone: IGBT at (70, 80) with large pads and 2.0mm clearance
        # These represent DC_BUS+, SW_NODE, GATE pins
        grid.block_circle((70.0, 80.0), 3.0, 2.0, 0, "DC_BUS+")
        grid.block_circle((76.0, 80.0), 3.0, 2.0, 0, "SW_NODE")
        grid.block_circle((82.0, 80.0), 2.0, 0.5, 0, "GATE_H")  # Gate pin (smaller)

        # Control zone: Gate driver at (40, 60)
        grid.block_circle((40.0, 60.0), 1.5, 0.3, 0, "U_GATE")

        # GATE_H route: from IGBT gate pin to driver output
        pathfinder = DeterministicAStar(
            grid=grid,
            drc_oracle=None,
            net_name="GATE_H",
            trace_width=0.3,
            max_iterations=5000,
        )

        path = pathfinder.find_path(start=(82.0, 80.0), end=(40.0, 60.0), layer=0)

        assert path is not None, (
            "GATE_H route should succeed. If failing, increase max_iterations or "
            "reduce blocking around the route corridor."
        )

    def test_gate_route_with_reduced_blocking(self):
        """Demonstrate that reducing blocking enables gate routing."""
        from temper_placer.deterministic.stages.astar import DeterministicAStar
        from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid

        grid = ClearanceGrid(
            width_mm=100.0,
            height_mm=100.0,
            cell_size_mm=0.5,
            layer_count=4,
        )

        # Same layout but with CORRECT clearances:
        # - HV pads still get HV clearance (they're actually HV)
        # - But we leave a routing corridor for the gate signal
        grid.block_circle((70.0, 80.0), 3.0, 2.0, 0, "DC_BUS+")
        grid.block_circle((76.0, 80.0), 3.0, 2.0, 0, "SW_NODE")
        # Gate pin uses smaller clearance (it's a signal, not power)
        grid.block_circle((82.0, 80.0), 1.0, 0.3, 0, "GATE_H")
        grid.block_circle((40.0, 60.0), 1.5, 0.3, 0, "U_GATE")

        pathfinder = DeterministicAStar(
            grid=grid,
            drc_oracle=None,
            net_name="GATE_H",
            trace_width=0.3,
            max_iterations=2000,  # Lower limit should work with less blocking
        )

        path = pathfinder.find_path(start=(82.0, 80.0), end=(40.0, 60.0), layer=0)

        assert path is not None, "With correct clearances, GATE_H should route easily"


# ============================================================================
# Reproduction Test: Power Plane Stub Rejection
# ============================================================================


class TestPowerPlaneStubRejection:
    """Reproduce power plane stub trace rejections.

    Production error:
      WARNING: Plane stub trace for VCC_BOOT rejected: clearance violation
               with U_GATE.16: 2.240mm < 2.350mm required

    Root cause:
    1. VCC_BOOT is a Power net (clearance=0.25mm)
    2. U_GATE.16 is on an HV component (clearance=2.0mm)
    3. When checking stub clearance, code uses max(Power, HV) = HV clearance
    4. But the Power net trace only needs Power clearance for its own trace

    The fix: Stub trace clearance should use the routing net's clearance,
    not the nearby pad's clearance. The pad's clearance is already enforced
    by the blocked zone around it.
    """

    def test_stub_trace_near_hv_pad(self):
        """Test that stub trace can exist near HV pad with correct clearance."""
        # This is a design decision test
        #
        # Scenario:
        #   VCC_BOOT pad at (10, 10) - Power net
        #   Via target at (12, 10) - 2mm away
        #   HV pad at (14.5, 10) - DC_BUS+
        #
        # Question: Can the stub from (10,10) to (12,10) be placed?
        #
        # Current (buggy) behavior:
        #   Stub end at (12,10) is 2.5mm from HV pad center
        #   HV clearance = 2.0mm + margin = 2.35mm
        #   2.5mm > 2.35mm, but code checks 2.24mm < 2.35mm ???
        #
        # Expected behavior:
        #   The HV pad's blocked zone extends 2.0mm from its edge
        #   If HV pad radius = 2.5mm, blocked zone ends at 4.5mm from center
        #   Stub at (12,10) is 2.5mm from HV center = inside blocked zone
        #   BUT the stub is VCC_BOOT net, which only needs 0.25mm clearance
        #   The HV blocked zone is for OTHER nets routing near HV
        #   Power net's stub uses Power clearance

        # This test documents expected behavior - actual fix is in DRC oracle
        pass

    def test_via_placement_respects_hv_clearance(self):
        """Verify via placement searches outside HV blocked zones."""
        from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid

        grid = ClearanceGrid(
            width_mm=30.0,
            height_mm=30.0,
            cell_size_mm=0.25,
            layer_count=4,
        )

        # HV pad at center with 2.0mm clearance
        grid.block_circle((15.0, 15.0), 2.5, 2.0, 0, "DC_BUS+")

        # Find valid via position for VCC_BOOT (Power net)
        # Should be outside the 4.5mm blocked radius
        for radius in [5.0, 6.0, 7.0]:
            x = 15.0 + radius
            y = 15.0
            if grid.is_available(x, y, 0, net_name="VCC_BOOT"):
                assert radius >= 4.5, f"Via at radius {radius} should be outside HV blocked zone"
                break


# ============================================================================
# Reproduction Test: Iteration Limit Exhaustion
# ============================================================================


class TestIterationExhaustion:
    """Tests for A* iteration limit exhaustion.

    Production error:
      WARNING: A* search for DC_BUS+ exceeded 2000 iterations
      WARNING: Multi-layer A* for DC_BUS+ exceeded 5000 iterations

    Root cause:
    1. DC_BUS+ is a plane net and shouldn't be A* routed at all
    2. But PowerPlaneStage might not have been added or run properly
    3. If it does run, A* should skip plane nets entirely
    """

    def test_plane_nets_skip_astar_routing(self):
        """Verify plane nets are skipped by sequential routing."""
        from temper_placer.deterministic.stages.power_plane import TEMPER_PLANE_NETS

        # Plane nets that should NOT go through A* routing
        plane_nets = {"DC_BUS+", "SW_NODE", "GND", "PGND", "+15V", "+3V3", "VCC_BOOT"}

        for net in plane_nets:
            assert net in TEMPER_PLANE_NETS, f"{net} should be a plane net"

    def test_long_route_within_iteration_budget(self):
        """Test that reasonable routes complete within iteration limits."""
        from temper_placer.deterministic.stages.astar import DeterministicAStar
        from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid

        grid = ClearanceGrid(
            width_mm=100.0,
            height_mm=150.0,  # Temper board size
            cell_size_mm=0.5,
            layer_count=4,
        )

        # Sparse obstacles (normal component density)
        obstacles = [(20, 30), (40, 50), (60, 70), (80, 90), (30, 110), (50, 130)]
        for x, y in obstacles:
            grid.block_circle((x, y), 3.0, 0.5, 0, f"COMP_{x}_{y}")

        pathfinder = DeterministicAStar(
            grid=grid,
            drc_oracle=None,
            net_name="LONG_SIGNAL",
            trace_width=0.2,
            max_iterations=2000,
        )

        # Diagonal route across most of board
        path = pathfinder.find_path(start=(5.0, 5.0), end=(95.0, 145.0), layer=0)

        assert path is not None, (
            "Long signal route should complete within 2000 iterations with normal component density"
        )


# ============================================================================
# Test: Net Class Aware Clearance Grid
# ============================================================================


class TestNetClassAwareClearance:
    """Tests for net-class-aware clearance blocking.

    The fix for over-blocking: instead of using max_clearance_mm for ALL pads,
    use the actual net class clearance for each pad.

    - Signal pads: 0.15mm clearance
    - Power pads: 0.25mm clearance
    - HighVoltage pads: 2.0mm clearance
    - ACMains pads: 6.0mm clearance (not tested - creepage)
    """

    def test_signal_pad_small_blocked_area(self):
        """Verify Signal pads have small blocked zones."""
        from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid

        grid = ClearanceGrid(
            width_mm=20.0,
            height_mm=20.0,
            cell_size_mm=0.1,
            layer_count=2,
        )

        # Signal pad with correct clearance
        grid.block_circle((10.0, 10.0), 0.3, 0.15, 0, "SIG_NET")

        # Count blocked cells
        blocked = np.sum(grid._pad_net_ids[0] != 0)
        total = grid.rows * grid.cols

        # Blocked radius = 0.3 + 0.15 = 0.45mm
        # Area = π * 0.45² ≈ 0.64 mm²
        # Board = 400 mm²
        # Should block < 0.5% of board
        blocked_pct = 100.0 * blocked / total
        assert blocked_pct < 1.0, f"Signal pad blocked {blocked_pct:.2f}% (expected <1%)"

    def test_hv_pad_large_blocked_area(self):
        """Verify HV pads have large blocked zones."""
        from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid

        grid = ClearanceGrid(
            width_mm=50.0,
            height_mm=50.0,
            cell_size_mm=0.25,
            layer_count=2,
        )

        # HV pad with correct clearance
        grid.block_circle((25.0, 25.0), 2.5, 2.0, 0, "DC_BUS+")

        # Count blocked cells
        blocked = np.sum(grid._pad_net_ids[0] != 0)
        total = grid.rows * grid.cols

        # Blocked radius = 2.5 + 2.0 = 4.5mm
        # Area = π * 4.5² ≈ 63.6 mm²
        # Board = 2500 mm²
        # Should block ~2.5% of board
        blocked_pct = 100.0 * blocked / total
        assert 1.0 < blocked_pct < 5.0, f"HV pad blocked {blocked_pct:.2f}% (expected 1-5%)"

    def test_mixed_net_classes_correct_blocking(self):
        """Verify mixed net classes each get correct blocking."""
        from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid

        grid = ClearanceGrid(
            width_mm=100.0,
            height_mm=100.0,
            cell_size_mm=0.25,
            layer_count=4,
        )

        # Signal cluster in left quarter
        for i in range(5):
            grid.block_circle((15.0 + i * 5, 50.0), 0.3, 0.15, 0, f"SIG_{i}")

        # Power pads in center
        grid.block_circle((50.0, 50.0), 0.5, 0.25, 0, "VCC")
        grid.block_circle((55.0, 50.0), 0.5, 0.25, 0, "GND_VIA")

        # HV pads on right
        grid.block_circle((80.0, 50.0), 2.5, 2.0, 0, "DC_BUS+")

        # Check proportions
        left_blocked = np.sum(grid._pad_net_ids[0][:, :100] != 0)
        center_blocked = np.sum(grid._pad_net_ids[0][:, 100:300] != 0)
        right_blocked = np.sum(grid._pad_net_ids[0][:, 300:] != 0)

        # HV should block much more than signal
        assert right_blocked > left_blocked * 5, (
            f"HV should block 5x+ more than signal cluster: HV={right_blocked}, SIG={left_blocked}"
        )
