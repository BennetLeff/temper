"""
Integration tests for the deterministic PCB routing pipeline.

These tests verify the complete pipeline from netlist to routed board,
targeting the actual failure modes observed in production:

1. Clearance Grid Over-blocking: max_clearance_mm=2.5 blocks too much area
2. Plane Connection Failures: VCC_BOOT, +15V, +3V3 stub traces rejected
3. A* Iteration Exhaustion: DC_BUS+, SW_NODE, GATE_H exceed iteration limits
4. Unrouted Signal Nets: SPI_MOSI, SPI_CLK, PWM_H can't find paths
5. Component Boundary Violations: Components placed outside board area
"""

import pytest
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional


# ============================================================================
# Test Category 1: Clearance Grid Blocking
# ============================================================================


class TestClearanceGridBlocking:
    """Tests for clearance grid over-blocking issues.

    Production failure: max_clearance_mm=2.5 blocks too much area,
    leaving no routing channels for signal nets.
    """

    def test_clearance_blocking_leaves_routing_channels(self):
        """Verify that clearance blocking doesn't block >90% of board area."""
        from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid

        # Create grid for 100x100mm board
        grid = ClearanceGrid(
            width_mm=100.0,
            height_mm=100.0,
            cell_size_mm=0.25,
            layer_count=4,
        )

        # Block a 5mm radius pad with 2.5mm clearance (worst case HV)
        grid.block_circle(
            center=(50.0, 50.0),
            radius_mm=2.5,
            clearance_mm=2.5,
            layer=0,
            net_name="DC_BUS+",
        )

        # Calculate blocked percentage
        total_cells = grid.rows * grid.cols
        blocked_cells = np.sum(grid._pad_net_ids[0] != 0)
        blocked_pct = 100.0 * blocked_cells / total_cells

        # With 5mm total radius (2.5 pad + 2.5 clearance), area = π * 5² ≈ 78.5 mm²
        # Board area = 10000 mm², so blocked should be ~0.8%
        assert blocked_pct < 5.0, f"Single pad blocked {blocked_pct:.1f}% of board (expected <5%)"

    def test_clearance_allows_routing_to_own_pads(self):
        """Verify that a net can route to its own pads (is_available works)."""
        from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid

        grid = ClearanceGrid(
            width_mm=50.0,
            height_mm=50.0,
            cell_size_mm=0.25,
            layer_count=2,
        )

        # Block two pads of the same net
        grid.block_circle((10.0, 10.0), 1.0, 2.0, 0, "NET1")
        grid.block_circle((20.0, 10.0), 1.0, 2.0, 0, "NET1")

        # Check that the net can reach its own pads
        # A route from (10,10) to (20,10) should be possible
        is_available_at_pad1 = grid.is_available(10.0, 10.0, 0, net_name="NET1")
        is_available_at_pad2 = grid.is_available(20.0, 10.0, 0, net_name="NET1")

        # Pads SHOULD be available for their own net
        assert is_available_at_pad1, "Pad 1 should be available for NET1"
        assert is_available_at_pad2, "Pad 2 should be available for NET1"

    def test_clearance_blocks_other_nets(self):
        """Verify that pads are blocked for other nets."""
        from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid

        grid = ClearanceGrid(
            width_mm=50.0,
            height_mm=50.0,
            cell_size_mm=0.25,
            layer_count=2,
        )

        # Block a GND pad
        grid.block_circle((10.0, 10.0), 1.0, 2.0, 0, "GND")

        # VCC should NOT be available near the GND pad
        is_available = grid.is_available(10.0, 10.0, 0, net_name="VCC")
        assert not is_available, "GND pad should not be available for VCC net"

    def test_hv_clearance_vs_signal_clearance(self):
        """Verify that HV nets get larger clearance than signal nets."""
        from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid

        grid = ClearanceGrid(
            width_mm=100.0,
            height_mm=100.0,
            cell_size_mm=0.25,
            layer_count=4,
        )

        # Block HV pad with 2.0mm clearance (at x=30)
        grid.block_circle((30.0, 50.0), 2.0, 2.0, 0, "DC_BUS+")

        # Block signal pad with 0.15mm clearance (at x=70)
        grid.block_circle((70.0, 50.0), 0.5, 0.15, 0, "SPI_CLK")

        # Count blocked cells in left vs right halves
        hv_blocked = np.sum(grid._pad_net_ids[0][:, :200] != 0)
        sig_blocked = np.sum(grid._pad_net_ids[0][:, 200:] != 0)

        # HV pad should block much more area than signal pad
        assert hv_blocked > sig_blocked * 5, (
            f"HV should block 5x+ more area than signal: HV={hv_blocked}, SIG={sig_blocked}"
        )

    def test_multiple_pads_leave_routing_channel(self):
        """Verify that multiple pads don't completely block routing."""
        from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid

        grid = ClearanceGrid(
            width_mm=100.0,
            height_mm=100.0,
            cell_size_mm=0.25,
            layer_count=4,
        )

        # Block pads in a line with gaps
        for i in range(5):
            grid.block_circle((20.0 + i * 15, 50.0), 1.0, 0.5, 0, f"PAD{i}")

        # Check that there's still a routing channel somewhere
        # Sample points between pads
        routing_possible = False
        for x in [12.0, 27.0, 42.0, 57.0, 72.0]:
            if grid.is_available(x, 50.0, 0, net_name="SIGNAL"):
                routing_possible = True
                break

        assert routing_possible, "Should have routing channel between pads"


# ============================================================================
# Test Category 2: Plane Connection Logic
# ============================================================================


class TestPlaneConnectionLogic:
    """Tests for power plane connection failures.

    Production failure: VCC_BOOT, +15V, +3V3 stub traces rejected
    due to clearance violations with nearby HV pads.
    """

    def test_plane_nets_identified_correctly(self):
        """Verify that power/ground nets are marked as plane nets."""
        from temper_placer.deterministic.stages.power_plane import (
            TEMPER_PLANE_NETS,
            TEMPER_PLANE_LAYERS,
        )

        # Check that key plane nets are in the set
        assert "GND" in TEMPER_PLANE_NETS
        assert "+15V" in TEMPER_PLANE_NETS
        assert "VCC_BOOT" in TEMPER_PLANE_NETS
        assert "DC_BUS+" in TEMPER_PLANE_NETS

        # Check layer assignments
        assert TEMPER_PLANE_LAYERS["GND"] == 1, "GND should be on In1.Cu"
        assert TEMPER_PLANE_LAYERS["+15V"] == 2, "+15V should be on In2.Cu"

    def test_power_plane_stage_marks_plane_attribute(self):
        """Verify that plane nets get is_plane=True in layer assignments."""
        from temper_placer.deterministic.stages.power_plane import PowerPlaneStage

        stage = PowerPlaneStage()

        # Verify stage configuration
        assert "GND" in stage.plane_nets
        assert "VCC_BOOT" in stage.plane_nets
        assert stage.plane_layers.get("GND") == 1

    def test_plane_net_layer_assignment(self):
        """Verify plane nets get assigned to correct inner layers."""
        from temper_placer.deterministic.stages.power_plane import TEMPER_PLANE_LAYERS

        # Ground nets -> In1.Cu (layer 1)
        assert TEMPER_PLANE_LAYERS["GND"] == 1
        assert TEMPER_PLANE_LAYERS["PGND"] == 1
        assert TEMPER_PLANE_LAYERS["CGND"] == 1

        # Power nets -> In2.Cu (layer 2)
        assert TEMPER_PLANE_LAYERS["+15V"] == 2
        assert TEMPER_PLANE_LAYERS["+5V"] == 2
        assert TEMPER_PLANE_LAYERS["+3V3"] == 2

        # HV nets -> F.Cu (layer 0)
        assert TEMPER_PLANE_LAYERS["DC_BUS+"] == 0
        assert TEMPER_PLANE_LAYERS["SW_NODE"] == 0


# ============================================================================
# Test Category 3: A* Pathfinding Limits
# ============================================================================


class TestAStarPathfinding:
    """Tests for A* iteration exhaustion.

    Production failure: DC_BUS+, SW_NODE, GATE_H exceed 5000 iterations
    and fail to find paths.
    """

    def test_simple_path_finds_route(self):
        """Verify that a simple unobstructed path is found quickly."""
        from temper_placer.deterministic.stages.astar import DeterministicAStar
        from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid

        grid = ClearanceGrid(
            width_mm=50.0,
            height_mm=50.0,
            cell_size_mm=0.5,
            layer_count=2,
        )

        pathfinder = DeterministicAStar(
            grid=grid,
            drc_oracle=None,
            net_name="TEST",
            trace_width=0.2,
        )

        # Find path from (5,5) to (45,5) - straight horizontal line
        path = pathfinder.find_path(start=(5.0, 5.0), end=(45.0, 5.0), layer=0)

        assert path is not None, "Should find path for unobstructed route"
        assert len(path) > 0, "Path should have points"

    def test_path_around_obstacle(self):
        """Verify that A* routes around obstacles."""
        from temper_placer.deterministic.stages.astar import DeterministicAStar
        from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid

        grid = ClearanceGrid(
            width_mm=50.0,
            height_mm=50.0,
            cell_size_mm=0.5,
            layer_count=2,
        )

        # Block the direct path with a large obstacle
        grid.block_circle((25.0, 5.0), 3.0, 1.0, 0, "OBSTACLE")

        pathfinder = DeterministicAStar(
            grid=grid,
            drc_oracle=None,
            net_name="TEST",
            trace_width=0.2,
        )

        path = pathfinder.find_path(start=(5.0, 5.0), end=(45.0, 5.0), layer=0)

        assert path is not None, "Should find path around obstacle"
        # Path should go around, so it should have more than just start/end
        assert len(path) > 2, f"Path should detour around obstacle, got {len(path)} points"

    def test_iteration_limit_respected(self):
        """Verify A* respects iteration limits."""
        from temper_placer.deterministic.stages.astar import DeterministicAStar
        from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid

        grid = ClearanceGrid(
            width_mm=100.0,
            height_mm=100.0,
            cell_size_mm=0.25,
            layer_count=4,
        )

        # Create a heavily obstructed grid
        for i in range(20):
            for j in range(20):
                grid.block_circle((5.0 + i * 4.5, 5.0 + j * 4.5), 1.5, 0.5, 0, f"OBS_{i}_{j}")

        pathfinder = DeterministicAStar(
            grid=grid,
            drc_oracle=None,
            net_name="SIGNAL",
            trace_width=0.2,
            max_iterations=100,  # Very low limit
        )

        # This should either find a path or give up at iteration limit
        # It should NOT hang indefinitely
        path = pathfinder.find_path(start=(2.0, 2.0), end=(98.0, 98.0), layer=0)

        # We don't assert success/failure, just that it returns in reasonable time
        # (The test framework itself will timeout if it hangs)


# ============================================================================
# Test Category 4: Multi-Layer Routing
# ============================================================================


class TestMultiLayerRouting:
    """Tests for multi-layer routing with via insertion.

    Production failure: Signal nets fail when single layer is blocked.
    """

    def test_multilayer_astar_exists(self):
        """Verify MultiLayerAStar can be imported and instantiated."""
        from temper_placer.deterministic.stages.multilayer_astar import MultiLayerAStar
        from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid

        grid = ClearanceGrid(
            width_mm=50.0,
            height_mm=50.0,
            cell_size_mm=0.5,
            layer_count=4,
        )

        pathfinder = MultiLayerAStar(
            grid=grid,
            drc_oracle=None,
            net_name="TEST",
            trace_width=0.2,
            via_cost=3.0,
        )

        assert pathfinder is not None

    def test_multilayer_finds_path_when_layer_blocked(self):
        """Verify multi-layer routing works when primary layer is blocked."""
        from temper_placer.deterministic.stages.multilayer_astar import MultiLayerAStar
        from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid

        grid = ClearanceGrid(
            width_mm=50.0,
            height_mm=50.0,
            cell_size_mm=0.5,
            layer_count=4,
        )

        # Block layer 0 in the middle with a wall
        for y in range(0, 100):
            grid.block_circle((25.0, y * 0.5), 2.0, 0.5, 0, "WALL")

        pathfinder = MultiLayerAStar(
            grid=grid,
            drc_oracle=None,
            net_name="TEST",
            trace_width=0.2,
            via_cost=3.0,
        )

        result = pathfinder.find_path(
            start=(5.0, 25.0),
            end=(45.0, 25.0),
            start_layer=0,
            end_layer=-1,  # Any layer OK
        )

        # Should find a path using layer change
        assert result is not None, "Should find multi-layer path"


# ============================================================================
# Test Category 5: Component Boundary Clamping
# ============================================================================


class TestComponentBoundary:
    """Tests for component placement within board boundaries.

    Production failure: CourtyardCheckStage nudges components outside
    the board boundary, causing via_dangling violations.
    """

    def test_clamp_position_within_bounds(self):
        """Verify _clamp_position keeps coordinates within bounds."""
        from temper_placer.deterministic.stages.courtyard_check import CourtyardCheckStage

        stage = CourtyardCheckStage(
            courtyards={},
            board_width=100.0,
            board_height=150.0,
            margin=5.0,
        )

        # Position already within bounds
        pos = (50.0, 75.0)
        clamped = stage._clamp_position(pos)
        assert clamped == pos, "Valid position should not change"

    def test_clamp_position_right_edge(self):
        """Verify clamping from right edge."""
        from temper_placer.deterministic.stages.courtyard_check import CourtyardCheckStage

        stage = CourtyardCheckStage(
            courtyards={},
            board_width=100.0,
            board_height=150.0,
            margin=5.0,
        )

        # Position outside right edge
        pos = (105.0, 75.0)
        clamped = stage._clamp_position(pos)

        assert clamped[0] == 95.0, f"X should be clamped to 95.0, got {clamped[0]}"
        assert clamped[1] == 75.0, "Y should not change"

    def test_clamp_position_corner(self):
        """Verify clamping from corner."""
        from temper_placer.deterministic.stages.courtyard_check import CourtyardCheckStage

        stage = CourtyardCheckStage(
            courtyards={},
            board_width=100.0,
            board_height=150.0,
            margin=5.0,
        )

        # Position outside top-right corner
        pos = (110.0, 160.0)
        clamped = stage._clamp_position(pos)

        assert clamped[0] == 95.0, f"X should be clamped to 95.0, got {clamped[0]}"
        assert clamped[1] == 145.0, f"Y should be clamped to 145.0, got {clamped[1]}"

    def test_clamp_position_negative(self):
        """Verify clamping from negative coordinates."""
        from temper_placer.deterministic.stages.courtyard_check import CourtyardCheckStage

        stage = CourtyardCheckStage(
            courtyards={},
            board_width=100.0,
            board_height=150.0,
            margin=5.0,
        )

        # Position outside left edge
        pos = (-5.0, 75.0)
        clamped = stage._clamp_position(pos)

        assert clamped[0] == 5.0, f"X should be clamped to 5.0, got {clamped[0]}"


# ============================================================================
# Test Category 6: Net Class Clearance Application
# ============================================================================


class TestNetClassClearance:
    """Tests for correct net class clearance application.

    The clearance between two objects depends on BOTH their net classes.
    HV nets need 2.0mm+ clearance from everything, not just other HV nets.
    """

    def test_temper_net_classes_defined(self):
        """Verify TEMPER_NET_CLASSES has expected entries."""
        from temper_placer.core.design_rules import TEMPER_NET_CLASSES

        assert "Signal" in TEMPER_NET_CLASSES
        assert "Power" in TEMPER_NET_CLASSES
        assert "HighVoltage" in TEMPER_NET_CLASSES

    def test_hv_clearance_larger_than_signal(self):
        """Verify HV clearance is much larger than Signal."""
        from temper_placer.core.design_rules import TEMPER_NET_CLASSES

        hv_rules = TEMPER_NET_CLASSES.get("HighVoltage", {})
        sig_rules = TEMPER_NET_CLASSES.get("Signal", {})

        hv_clearance = (
            hv_rules.get("clearance", 2.0)
            if isinstance(hv_rules, dict)
            else getattr(hv_rules, "clearance", 2.0)
        )
        sig_clearance = (
            sig_rules.get("clearance", 0.15)
            if isinstance(sig_rules, dict)
            else getattr(sig_rules, "clearance", 0.15)
        )

        assert hv_clearance >= 2.0, f"HV clearance should be >= 2.0mm, got {hv_clearance}"
        assert sig_clearance <= 0.3, f"Signal clearance should be <= 0.3mm, got {sig_clearance}"
        assert hv_clearance > sig_clearance * 5, "HV should be 5x+ Signal clearance"


# ============================================================================
# Test Category 7: End-to-End Pipeline
# ============================================================================


class TestPipelineEndToEnd:
    """End-to-end tests for the complete deterministic pipeline."""

    def test_pipeline_creates_valid_stages(self):
        """Verify pipeline has expected stages."""
        from temper_placer.deterministic import create_drc_aware_pipeline

        pipeline = create_drc_aware_pipeline()
        assert pipeline is not None
        assert len(pipeline.stages) > 0

    def test_pipeline_stage_order(self):
        """Verify pipeline stages are in correct order."""
        from temper_placer.deterministic import create_drc_aware_pipeline

        pipeline = create_drc_aware_pipeline()
        stage_names = [s.name for s in pipeline.stages]

        # Critical ordering requirements
        assert "clearance_grid" in stage_names
        assert "sequential_routing" in stage_names

        clearance_idx = stage_names.index("clearance_grid")
        routing_idx = stage_names.index("sequential_routing")

        assert clearance_idx < routing_idx, "ClearanceGrid must run before routing"

    def test_pipeline_has_validation_stages(self):
        """Verify pipeline includes DRC validation."""
        from temper_placer.deterministic import create_drc_aware_pipeline

        pipeline = create_drc_aware_pipeline()
        stage_names = [s.name for s in pipeline.stages]

        assert "drc_validation" in stage_names, "Pipeline should have DRC validation"
        assert "connectivity_validation" in stage_names, (
            "Pipeline should have connectivity validation"
        )

    def test_power_plane_stage_in_pipeline(self):
        """Verify PowerPlaneStage is included before routing."""
        from temper_placer.deterministic import create_drc_aware_pipeline

        pipeline = create_drc_aware_pipeline()
        stage_names = [s.name for s in pipeline.stages]

        assert "power_plane" in stage_names, "Pipeline should have PowerPlaneStage"

        power_idx = stage_names.index("power_plane")
        routing_idx = stage_names.index("sequential_routing")

        assert power_idx < routing_idx, "PowerPlaneStage must run before routing"


# ============================================================================
# Test Category 8: Grid Utils
# ============================================================================


class TestGridUtils:
    """Tests for grid coordinate utilities."""

    def test_snap_to_grid(self):
        """Verify snap_to_grid works correctly."""
        from temper_placer.deterministic.stages.sequential_routing import snap_to_grid

        # Snap to 0.25mm grid - rounds to nearest grid point
        snapped = snap_to_grid((10.13, 20.37), 0.25)
        # 10.13 / 0.25 = 40.52 -> round to 41 -> 41 * 0.25 = 10.25
        assert snapped[0] == 10.25, f"X should snap to 10.25, got {snapped[0]}"
        # 20.37 / 0.25 = 81.48 -> round to 81 -> 81 * 0.25 = 20.25
        assert snapped[1] == 20.25, f"Y should snap to 20.25, got {snapped[1]}"

    def test_add_endpoint_nudge(self):
        """Verify endpoint nudge adds segments for exact pad connection."""
        from temper_placer.deterministic.stages.sequential_routing import add_endpoint_nudge

        # Path from snapped coords, but actual pads are offset
        path = [(10.0, 10.0), (20.0, 10.0)]
        start_actual = (10.1, 10.1)
        end_actual = (19.9, 9.9)

        nudged = add_endpoint_nudge(path, start_actual, end_actual)

        # Should have nudge segments at start and end
        assert nudged[0] == start_actual, "Should start at actual pad position"
        assert nudged[-1] == end_actual, "Should end at actual pad position"
