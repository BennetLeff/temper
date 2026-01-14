"""
Tests for net-specific routing rules and differential pair clearance.

Tests Phase 1: Net-specific rules
Tests Phase 2: Differential pair aware clearance

Part of Router V6 DRC fix (temper-router-drc-fix)
"""

import pytest
import numpy as np

from temper_placer.router_v6.astar_pathfinding import (
    _mark_route_blocked,
    _unmark_route_blocked,
    RoutePath,
    RoutePath3D,
)
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules


# =============================================================================
# Phase 1: Net-Specific Rules Tests
# =============================================================================


class TestNetSpecificRules:
    """Test that routing uses net-specific trace widths and clearances."""

    def test_power_net_uses_wide_trace(self):
        """Test that power nets use wider traces than default."""
        # Setup design rules with power net class
        design_rules = DesignRules(
            default_trace_width_mm=0.2,
            default_clearance_mm=0.2,
            default_via_diameter_mm=0.6,
            default_via_drill_mm=0.3,
            net_classes={
                "Power": NetClassRules(
                    name="Power",
                    trace_width_mm=1.0,  # Wide trace
                    clearance_mm=0.5,    # Larger clearance
                    via_diameter_mm=0.8,
                    via_drill_mm=0.4,
                )
            },
            net_class_assignments={"VCC": "Power"},
        )

        # Get rules for VCC (should use Power class)
        vcc_rules = design_rules.get_rules_for_net("VCC")
        assert vcc_rules.trace_width_mm == 1.0
        assert vcc_rules.clearance_mm == 0.5

        # Get rules for signal net (should use default)
        signal_rules = design_rules.get_rules_for_net("SIG1")
        assert signal_rules.trace_width_mm == 0.2
        assert signal_rules.clearance_mm == 0.2

    def test_blocking_radius_uses_net_specific_width(self):
        """Test that blocking radius calculation uses net-specific trace width."""
        # Create grids
        grid = OccupancyGrid(
            "F.Cu",
            np.zeros((50, 50), dtype=np.int16),
            (0, 0),
            0.1,  # 0.1mm cell size
            50,
            50,
        )

        # Route a SHORT horizontal path with specific trace width
        path = RoutePath(
            net_name="VCC",
            coordinates=[(2.0, 2.0), (2.1, 2.0)],  # Very short horizontal segment
            layer_name="F.Cu",
            path_length=0.1,
        )

        # Mark with power net dimensions
        trace_width = 1.0  # Wide power trace
        clearance = 0.5
        net_id = 1

        _mark_route_blocked(
            path,
            {"F.Cu": grid},
            trace_width=trace_width,
            clearance=clearance,
            net_id=net_id,
        )

        # Check that blocking radius = trace_width + clearance = 1.5mm
        # At (2.0, 2.0), cells within 1.5mm should be blocked
        cx, cy = grid.world_to_grid(2.0, 2.0)

        # Cell at exact center should be blocked
        assert grid.grid[cy, cx] == net_id

        # Cell 1.4mm away (perpendicular to trace) should be blocked (within 1.5mm radius)
        test_x, test_y = grid.world_to_grid(2.0, 2.0 + 1.4)
        assert grid.grid[test_y, test_x] == net_id

        # Cell 1.8mm away (perpendicular to trace) should NOT be blocked (outside 1.5mm radius)
        # Using larger distance to account for grid quantization
        test_x2, test_y2 = grid.world_to_grid(2.0, 2.0 + 1.8)
        assert grid.grid[test_y2, test_x2] == 0

    def test_rip_up_uses_correct_net_width(self):
        """Test that rip-up uses the same trace width as original route."""
        grid = OccupancyGrid(
            "F.Cu",
            np.zeros((50, 50), dtype=np.int16),
            (0, 0),
            0.1,
            50,
            50,
        )

        path = RoutePath(
            net_name="VCC",
            coordinates=[(1.0, 1.0), (2.0, 2.0)],
            layer_name="F.Cu",
            path_length=1.414,
        )

        # Mark with wide trace
        trace_width = 1.0
        clearance = 0.5
        net_id = 1

        _mark_route_blocked(path, {"F.Cu": grid}, trace_width, clearance, net_id)

        # Store original state
        cx, cy = grid.world_to_grid(1.0, 1.0)
        assert grid.grid[cy, cx] == net_id

        # Unmark with SAME dimensions
        _unmark_route_blocked(path, {"F.Cu": grid}, trace_width, clearance, net_id)

        # Should be cleared
        assert grid.grid[cy, cx] == 0


# =============================================================================
# Phase 2: Differential Pair Clearance Tests
# =============================================================================


class TestDifferentialPairClearance:
    """Test differential pair aware clearance."""

    def test_identify_differential_pair(self):
        """Test that differential pairs use diff_pair_gap_mm from net class."""
        design_rules = DesignRules(
            default_trace_width_mm=0.15,
            default_clearance_mm=0.2,
            default_via_diameter_mm=0.6,
            default_via_drill_mm=0.3,
            net_classes={
                "DiffPair": NetClassRules(
                    name="DiffPair",
                    trace_width_mm=0.15,
                    clearance_mm=0.2,  # Normal clearance to other nets
                    via_diameter_mm=0.6,
                    via_drill_mm=0.3,
                    diff_pair_gap_mm=0.127,  # USB 2.0 pair gap (closer than normal)
                )
            },
            net_class_assignments={
                "USB_D+": "DiffPair",
                "USB_D-": "DiffPair",
            },
        )

        # Get rules for USB_D+
        dp_rules = design_rules.get_rules_for_net("USB_D+")
        assert dp_rules.diff_pair_gap_mm == 0.127
        assert dp_rules.clearance_mm == 0.2  # Normal clearance to other nets

        # Check that pair gap is smaller than normal clearance
        assert dp_rules.diff_pair_gap_mm < dp_rules.clearance_mm

    def test_pair_spacing_smaller_than_clearance(self):
        """Test that differential pair spacing is smaller than normal clearance."""
        design_rules = DesignRules(
            default_trace_width_mm=0.15,
            default_clearance_mm=0.2,
            default_via_diameter_mm=0.6,
            default_via_drill_mm=0.3,
            net_classes={
                "DiffPair": NetClassRules(
                    name="DiffPair",
                    trace_width_mm=0.15,
                    clearance_mm=0.2,
                    via_diameter_mm=0.6,
                    via_drill_mm=0.3,
                    diff_pair_gap_mm=0.127,  # Pair gap (closer than normal)
                )
            },
            net_class_assignments={"USB_D+": "DiffPair", "USB_D-": "DiffPair"},
        )

        pair_rules = design_rules.get_rules_for_net("USB_D+")
        assert pair_rules.diff_pair_gap_mm < design_rules.default_clearance_mm
        assert pair_rules.diff_pair_gap_mm == 0.127

    def test_diff_pair_blocking_allows_closer_routing(self):
        """
        Test that differential pair mate can route closer than normal clearance.

        USB_D+ and USB_D- should be able to route with 0.127mm spacing,
        even though normal clearance is 0.2mm.
        """
        design_rules = DesignRules(
            default_trace_width_mm=0.15,
            default_clearance_mm=0.2,
            default_via_diameter_mm=0.6,
            default_via_drill_mm=0.3,
            net_classes={
                "DiffPair": NetClassRules(
                    name="DiffPair",
                    trace_width_mm=0.15,
                    clearance_mm=0.2,
                    via_diameter_mm=0.6,
                    via_drill_mm=0.3,
                    diff_pair_gap_mm=0.127,
                )
            },
            net_class_assignments={"USB_D+": "DiffPair", "USB_D-": "DiffPair"},
        )

        # Create net_id mapping
        net_id_to_name = {1: "USB_D+", 2: "USB_D-", 3: "OTHER_NET"}

        grid = OccupancyGrid(
            "F.Cu",
            np.zeros((50, 50), dtype=np.int16),
            (0, 0),
            0.1,
            50,
            50,
            net_id_to_name=net_id_to_name,
            design_rules=design_rules,
        )

        # Route USB_D+ first
        path_dp = RoutePath(
            net_name="USB_D+",
            coordinates=[(2.0, 2.0), (3.0, 2.0)],  # Horizontal trace
            layer_name="F.Cu",
            path_length=1.0,
        )

        _mark_route_blocked(
            path_dp,
            {"F.Cu": grid},
            trace_width=0.15,
            clearance=0.2,
            net_id=1,
        )

        # Test pair-aware clearance checking
        # Point at (2.0, 2.15) is 0.15mm away from USB_D+ trace center
        # Required clearance for pair mate: 0.127mm + 0.075mm (half trace width) = 0.202mm
        # This point should be acceptable for USB_D- but not for OTHER_NET

        gx, gy = grid.world_to_grid(2.0, 2.15)

        # Check clearance from USB_D+ to USB_D- (pair mate)
        clearance_to_pair = grid.check_clearance(gx, gy, 2)  # net_id=2 is USB_D-
        assert clearance_to_pair == 0.127  # Pair gap

        # Check clearance from USB_D+ to OTHER_NET
        clearance_to_other = grid.check_clearance(gx, gy, 3)  # net_id=3 is OTHER_NET
        assert clearance_to_other == 0.2  # Normal clearance

    def test_distance_based_validation_prevents_shorts(self):
        """
        Phase 2.1: Test that distance-based validation prevents shorts between diff pairs.

        USB_D- should NOT be able to route too close to USB_D+ (< 0.127mm spacing).
        """
        design_rules = DesignRules(
            default_trace_width_mm=0.15,
            default_clearance_mm=0.2,
            default_via_diameter_mm=0.6,
            default_via_drill_mm=0.3,
            net_classes={
                "DiffPair": NetClassRules(
                    name="DiffPair",
                    trace_width_mm=0.15,
                    clearance_mm=0.2,
                    via_diameter_mm=0.6,
                    via_drill_mm=0.3,
                    diff_pair_gap_mm=0.127,
                )
            },
            net_class_assignments={"USB_D+": "DiffPair", "USB_D-": "DiffPair"},
        )

        net_id_to_name = {1: "USB_D+", 2: "USB_D-"}

        grid = OccupancyGrid(
            "F.Cu",
            np.zeros((200, 200), dtype=np.int16),  # Larger grid to accommodate tests
            (0, 0),
            0.05,  # 0.05mm cells for finer resolution
            200,
            200,
            net_id_to_name=net_id_to_name,
            design_rules=design_rules,
        )

        # Route USB_D+ horizontally at y=2.5mm (middle of grid)
        path_dp = RoutePath(
            net_name="USB_D+",
            coordinates=[(1.0, 2.5), (8.0, 2.5)],  # Horizontal trace
            layer_name="F.Cu",
            path_length=7.0,
        )

        _mark_route_blocked(
            path_dp,
            {"F.Cu": grid},
            trace_width=0.15,
            clearance=0.2,
            net_id=1,
        )

        # Test points at various distances from USB_D+ centerline
        # At y=2.5 is the USB_D+ trace centerline

        # Point at 0.05mm away (too close - should be blocked)
        gx_close, gy_close = grid.world_to_grid(5.0, 2.55)
        assert not grid.is_free_for_net(gx_close, gy_close, 2), "Should block at 0.05mm distance"

        # Point at 0.10mm away (still too close - should be blocked)
        gx_med, gy_med = grid.world_to_grid(5.0, 2.60)
        assert not grid.is_free_for_net(gx_med, gy_med, 2), "Should block at 0.10mm distance"

        # Phase 2.2: Edge-to-edge distance testing
        # With 0.15mm trace widths, edge-to-edge = center-to-center - 0.075 - 0.075
        # For 0.127mm edge-to-edge gap, need center-to-center = 0.127 + 0.15 = 0.277mm

        # Point at center-to-center 0.35mm (edge-to-edge 0.20mm - should be allowed)
        # Cell at y=2.85 has center at 2.825mm, distance to 2.5 = 0.325mm center-to-center
        # Edge-to-edge = 0.325 - 0.15 = 0.175mm >= 0.127mm ✓
        gx_safe1, gy_safe1 = grid.world_to_grid(5.0, 2.85)
        cell_center = grid.grid_to_world(gx_safe1, gy_safe1)
        distance = grid._distance_to_trace(gx_safe1, gy_safe1, 1, 2)  # edge-to-edge distance
        assert distance >= 0.127, f"Test setup error: edge-to-edge distance {distance:.4f}mm < required 0.127mm"
        assert grid.is_free_for_net(gx_safe1, gy_safe1, 2), f"Should allow at edge-to-edge {distance:.4f}mm distance"

        # Point at center-to-center 0.40mm (edge-to-edge 0.25mm - well within safe distance)
        gx_safe2, gy_safe2 = grid.world_to_grid(5.0, 2.90)
        assert grid.is_free_for_net(gx_safe2, gy_safe2, 2), "Should allow at 0.25mm edge-to-edge distance"


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegrationNetSpecificRouting:
    """Integration tests for net-specific routing behavior."""

    def test_multiple_nets_with_different_widths(self):
        """Test routing multiple nets with different trace widths."""
        design_rules = DesignRules(
            default_trace_width_mm=0.2,
            default_clearance_mm=0.2,
            default_via_diameter_mm=0.6,
            default_via_drill_mm=0.3,
            net_classes={
                "Power": NetClassRules(
                    name="Power",
                    trace_width_mm=1.0,
                    clearance_mm=0.5,
                    via_diameter_mm=0.8,
                    via_drill_mm=0.4,
                ),
                "Signal": NetClassRules(
                    name="Signal",
                    trace_width_mm=0.15,
                    clearance_mm=0.15,
                    via_diameter_mm=0.6,
                    via_drill_mm=0.3,
                ),
            },
            net_class_assignments={
                "VCC": "Power",
                "GND": "Power",
                "SIG1": "Signal",
                "SIG2": "Signal",
            },
        )

        # Verify each net gets correct rules
        assert design_rules.get_rules_for_net("VCC").trace_width_mm == 1.0
        assert design_rules.get_rules_for_net("GND").trace_width_mm == 1.0
        assert design_rules.get_rules_for_net("SIG1").trace_width_mm == 0.15
        assert design_rules.get_rules_for_net("SIG2").trace_width_mm == 0.15
        assert design_rules.get_rules_for_net("UNKNOWN").trace_width_mm == 0.2  # Default


# =============================================================================
# Test Fixtures and Helpers
# =============================================================================


@pytest.fixture
def basic_design_rules():
    """Basic design rules for testing."""
    return DesignRules(
        default_trace_width_mm=0.2,
        default_clearance_mm=0.2,
        default_via_diameter_mm=0.6,
        default_via_drill_mm=0.3,
    )


@pytest.fixture
def power_design_rules():
    """Design rules with power net class."""
    return DesignRules(
        default_trace_width_mm=0.2,
        default_clearance_mm=0.2,
        default_via_diameter_mm=0.6,
        default_via_drill_mm=0.3,
        net_classes={
            "Power": NetClassRules(
                name="Power",
                trace_width_mm=1.0,
                clearance_mm=0.5,
                via_diameter_mm=0.8,
                via_drill_mm=0.4,
            )
        },
        net_class_assignments={"VCC": "Power", "GND": "Power"},
    )


@pytest.fixture
def diff_pair_design_rules():
    """Design rules with differential pairs."""
    return DesignRules(
        default_trace_width_mm=0.15,
        default_clearance_mm=0.2,
        default_via_diameter_mm=0.6,
        default_via_drill_mm=0.3,
        net_classes={
            "DiffPair": NetClassRules(
                name="DiffPair",
                trace_width_mm=0.15,
                clearance_mm=0.2,
                via_diameter_mm=0.6,
                via_drill_mm=0.3,
                diff_pair_gap_mm=0.127,
            )
        },
        net_class_assignments={"USB_D+": "DiffPair", "USB_D-": "DiffPair"},
    )


@pytest.fixture
def empty_grid():
    """Empty 50x50 occupancy grid."""
    return OccupancyGrid(
        "F.Cu",
        np.zeros((50, 50), dtype=np.int16),
        (0, 0),
        0.1,  # 0.1mm cell size
        50,
        50,
    )
