"""
Tests for Router V6 Stage 1.6: Reserve Via Positions in Grid

Part of temper-6wgs
"""

import pytest

from temper_placer.router_v6.via_grid_reservation import (
    ReservedViaPosition,
    check_via_conflicts,
    reserve_via_positions,
)


def test_reserve_via_positions_basic():
    """Test basic via position reservation."""
    escape_vias = [
        ((5.0, 10.0), 0.35, 0.15, "USB_DP", "U1", ("L1", "L2")),
        ((5.5, 10.5), 0.35, 0.15, "USB_DN", "U1", ("L1", "L2")),
    ]
    
    reserved = reserve_via_positions(escape_vias)
    
    assert len(reserved) == 2
    assert reserved[0].net_name == "USB_DP"
    assert reserved[1].net_name == "USB_DN"
    assert reserved[0].component_ref == "U1"


def test_reserve_via_positions_grid_snapping():
    """Test that positions are snapped to grid."""
    # Position not on grid (0.1mm resolution)
    escape_vias = [
        ((5.07, 10.13), 0.35, 0.15, "NET1", "U1", ("L1", "L2")),
    ]
    
    reserved = reserve_via_positions(escape_vias, grid_resolution_mm=0.1)
    
    # Should snap to nearest 0.1mm
    assert reserved[0].position[0] == pytest.approx(5.1, abs=0.01)
    assert reserved[0].position[1] == pytest.approx(10.1, abs=0.01)


def test_reserved_via_through_via_detection():
    """Test through-via detection."""
    # Through via: L1 to L4
    through_via = ReservedViaPosition(
        position=(5.0, 10.0),
        via_diameter_mm=0.6,
        via_drill_mm=0.3,
        net_name="GND",
        layers=("L1", "L4"),
        component_ref="U1",
    )
    
    # Microvia: L1 to L2
    microvia = ReservedViaPosition(
        position=(6.0, 11.0),
        via_diameter_mm=0.35,
        via_drill_mm=0.15,
        net_name="USB_DP",
        layers=("L1", "L2"),
        component_ref="U1",
    )
    
    assert through_via.is_through_via is True
    assert microvia.is_through_via is False


def test_reserved_via_blocked_layers():
    """Test blocked layers calculation."""
    # Through via blocks all layers
    through_via = ReservedViaPosition(
        position=(5.0, 10.0),
        via_diameter_mm=0.6,
        via_drill_mm=0.3,
        net_name="GND",
        layers=("L1", "L4"),
        component_ref="U1",
    )
    
    assert set(through_via.blocked_layers) == {"L1", "L2", "L3", "L4"}
    
    # Microvia blocks only L1-L2
    microvia = ReservedViaPosition(
        position=(6.0, 11.0),
        via_diameter_mm=0.35,
        via_drill_mm=0.15,
        net_name="USB_DP",
        layers=("L1", "L2"),
        component_ref="U1",
    )
    
    assert set(microvia.blocked_layers) == {"L1", "L2"}


def test_check_via_conflicts_no_conflict():
    """Test via conflict detection when vias are well-spaced."""
    reserved = [
        ReservedViaPosition((5.0, 10.0), 0.35, 0.15, "NET1", ("L1", "L2"), "U1"),
        ReservedViaPosition((10.0, 10.0), 0.35, 0.15, "NET2", ("L1", "L2"), "U1"),
    ]
    
    conflicts = check_via_conflicts(reserved, min_via_spacing_mm=0.3)
    
    assert len(conflicts) == 0  # 5mm spacing is safe


def test_check_via_conflicts_with_conflict():
    """Test via conflict detection when vias are too close."""
    reserved = [
        ReservedViaPosition((5.0, 10.0), 0.35, 0.15, "NET1", ("L1", "L2"), "U1"),
        ReservedViaPosition((5.2, 10.0), 0.35, 0.15, "NET2", ("L1", "L2"), "U1"),
    ]
    
    conflicts = check_via_conflicts(reserved, min_via_spacing_mm=0.3)
    
    assert len(conflicts) == 1  # 0.2mm spacing < 0.3mm minimum
    assert conflicts[0][2] == pytest.approx(0.2, abs=0.01)


def test_check_via_conflicts_different_layers():
    """Test that vias on non-overlapping layers don't conflict."""
    reserved = [
        ReservedViaPosition((5.0, 10.0), 0.35, 0.15, "NET1", ("L1", "L2"), "U1"),
        ReservedViaPosition((5.1, 10.0), 0.35, 0.15, "NET2", ("L3", "L4"), "U1"),
    ]
    
    conflicts = check_via_conflicts(reserved, min_via_spacing_mm=0.3)
    
    # Vias on different layer pairs (L1-L2 vs L3-L4) don't conflict
    assert len(conflicts) == 0


def test_check_via_conflicts_overlapping_layers():
    """Test that vias on overlapping layers do conflict if close."""
    reserved = [
        ReservedViaPosition((5.0, 10.0), 0.35, 0.15, "NET1", ("L1", "L2"), "U1"),
        ReservedViaPosition((5.1, 10.0), 0.35, 0.15, "NET2", ("L2", "L3"), "U1"),
    ]
    
    conflicts = check_via_conflicts(reserved, min_via_spacing_mm=0.3)
    
    # Vias overlap on L2, so they conflict
    assert len(conflicts) == 1


def test_reserve_via_positions_custom_grid():
    """Test via reservation with custom grid resolution."""
    escape_vias = [
        ((5.123, 10.456), 0.35, 0.15, "NET1", "U1", ("L1", "L2")),
    ]
    
    # Coarse grid (0.5mm)
    reserved = reserve_via_positions(escape_vias, grid_resolution_mm=0.5)
    assert reserved[0].position[0] == pytest.approx(5.0, abs=0.01)
    assert reserved[0].position[1] == pytest.approx(10.5, abs=0.01)
    
    # Fine grid (0.05mm)
    reserved = reserve_via_positions(escape_vias, grid_resolution_mm=0.05)
    assert reserved[0].position[0] == pytest.approx(5.10, abs=0.01)
    assert reserved[0].position[1] == pytest.approx(10.45, abs=0.01)
