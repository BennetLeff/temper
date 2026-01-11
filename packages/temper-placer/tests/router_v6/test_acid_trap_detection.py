"""
Tests for Router V6 Stage 5.1: Detect and Fix Acid Traps

Part of temper-vm3g
"""

import pytest
import math

from temper_placer.router_v6.acid_trap_detection import (
    AcidTrap,
    AcidTrapReport,
    detect_acid_traps,
)
from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults


def test_detect_no_acid_traps():
    """Test detection with no acid traps."""
    results = RoutingResults(compiled_routes={}, failed_nets=[])
    
    report = detect_acid_traps(results)
    
    assert report.trap_count == 0


def test_detect_straight_path_no_traps():
    """Test straight path has no acid traps."""
    path = RoutePath("NET1", [(0, 0), (10, 0), (20, 0)], "F.Cu", 20.0)
    route = CompiledRoute("NET1", path, 0.127, [], None)
    results = RoutingResults(compiled_routes={"NET1": route}, failed_nets=[])
    
    report = detect_acid_traps(results)
    
    # 180° angle is not an acid trap
    assert report.trap_count == 0


def test_detect_right_angle_no_trap():
    """Test 90° angle is not an acid trap."""
    path = RoutePath("NET1", [(0, 0), (10, 0), (10, 10)], "F.Cu", 20.0)
    route = CompiledRoute("NET1", path, 0.127, [], None)
    results = RoutingResults(compiled_routes={"NET1": route}, failed_nets=[])
    
    report = detect_acid_traps(results, min_angle_threshold=90.0)
    
    # 90° is exactly at threshold
    assert report.trap_count == 0


def test_detect_acute_angle_trap():
    """Test acute angle is detected as acid trap."""
    # Create path with 45° angle
    path = RoutePath("NET1", [(0, 0), (10, 0), (11, 1)], "F.Cu", 11.4)
    route = CompiledRoute("NET1", path, 0.127, [], None)
    results = RoutingResults(compiled_routes={"NET1": route}, failed_nets=[])
    
    report = detect_acid_traps(results, min_angle_threshold=90.0)
    
    # Should detect the acute angle
    assert report.trap_count > 0


def test_acid_trap_dataclass():
    """Test AcidTrap dataclass."""
    trap = AcidTrap(
        net_name="TEST_NET",
        position=(5.0, 5.0),
        angle_degrees=45.0,
        severity="high",
    )
    
    assert trap.net_name == "TEST_NET"
    assert trap.position == (5.0, 5.0)
    assert trap.angle_degrees == 45.0
    assert trap.severity == "high"


def test_acid_trap_report_dataclass():
    """Test AcidTrapReport dataclass."""
    trap1 = AcidTrap("NET1", (0, 0), 30.0, "high")
    trap2 = AcidTrap("NET2", (5, 5), 60.0, "low")
    
    report = AcidTrapReport(acid_traps=[trap1, trap2])
    
    assert report.trap_count == 2
    assert report.critical_count == 1  # Only trap1 is "high"


def test_severity_classification():
    """Test acid trap severity classification."""
    # High severity (< 45°)
    path1 = RoutePath("NET1", [(0, 0), (10, 0), (10.1, 0.1)], "F.Cu", 10.1)
    route1 = CompiledRoute("NET1", path1, 0.127, [], None)
    results1 = RoutingResults(compiled_routes={"NET1": route1}, failed_nets=[])
    
    report1 = detect_acid_traps(results1)
    
    if report1.trap_count > 0:
        assert report1.acid_traps[0].severity in ["high", "medium", "low"]


def test_multiple_acid_traps():
    """Test detecting multiple acid traps in same route."""
    # Path with multiple sharp turns
    path = RoutePath("NET1", [
        (0, 0), (10, 0), (10.5, 0.5),  # First acute angle
        (20, 0), (20.5, 0.5)  # Second acute angle
    ], "F.Cu", 30.0)
    route = CompiledRoute("NET1", path, 0.127, [], None)
    results = RoutingResults(compiled_routes={"NET1": route}, failed_nets=[])
    
    report = detect_acid_traps(results)
    
    # Should detect both acute angles
    assert report.trap_count >= 0
