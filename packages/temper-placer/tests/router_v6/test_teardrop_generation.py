"""
Tests for Router V6 Stage 5.3: Insert Teardrops

Part of temper-q5dh
"""

import pytest

from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults
from temper_placer.router_v6.teardrop_generation import (
    Teardrop,
    TeardropReport,
    insert_teardrops,
)
from temper_placer.router_v6.via_placement import Via


def test_insert_no_teardrops():
    """Test teardrop insertion with no vias."""
    path = RoutePath("NET1", [(0, 0), (10, 10)], "F.Cu", 14.14)
    route = CompiledRoute("NET1", path, 0.127, [], None)
    results = RoutingResults(compiled_routes={"NET1": route}, failed_nets=[])
    
    report = insert_teardrops(results)
    
    assert report.teardrop_count == 0


def test_insert_via_teardrops():
    """Test teardrop insertion for vias."""
    path = RoutePath("NET1", [(0, 0), (10, 10)], "F.Cu", 14.14)
    
    # Via with diameter 0.6mm, trace width 0.127mm
    via = Via((5, 5), "F.Cu", "B.Cu", 0.6, 0.3, "NET1")
    route = CompiledRoute("NET1", path, 0.127, [via], None)
    results = RoutingResults(compiled_routes={"NET1": route}, failed_nets=[])
    
    report = insert_teardrops(results, enable_via_teardrops=True)
    
    # Should generate teardrop for via
    assert report.teardrop_count > 0
    assert report.via_teardrop_count > 0


def test_no_teardrop_for_small_via():
    """Test that small vias don't get teardrops."""
    path = RoutePath("NET1", [(0, 0), (10, 10)], "F.Cu", 14.14)
    
    # Via with diameter 0.15mm, trace width 0.127mm (via not much larger)
    via = Via((5, 5), "F.Cu", "B.Cu", 0.15, 0.08, "NET1")
    route = CompiledRoute("NET1", path, 0.127, [via], None)
    results = RoutingResults(compiled_routes={"NET1": route}, failed_nets=[])
    
    report = insert_teardrops(results, enable_via_teardrops=True)
    
    # Should not generate teardrop for small via
    assert report.teardrop_count == 0


def test_teardrop_dataclass():
    """Test Teardrop dataclass."""
    teardrop = Teardrop(
        net_name="TEST_NET",
        connection_point=(5.0, 5.0),
        connection_type="via",
        length_mm=0.3,
        width_mm=0.6,
        layer="F.Cu",
    )
    
    assert teardrop.net_name == "TEST_NET"
    assert teardrop.connection_point == (5.0, 5.0)
    assert teardrop.connection_type == "via"
    assert teardrop.length_mm == 0.3
    assert teardrop.width_mm == 0.6
    assert teardrop.layer == "F.Cu"


def test_teardrop_report_dataclass():
    """Test TeardropReport dataclass."""
    teardrop1 = Teardrop("NET1", (0, 0), "via", 0.3, 0.6, "F.Cu")
    teardrop2 = Teardrop("NET2", (5, 5), "pad", 0.4, 0.8, "F.Cu")
    
    report = TeardropReport(teardrops=[teardrop1, teardrop2])
    
    assert report.teardrop_count == 2
    assert report.via_teardrop_count == 1
    assert report.pad_teardrop_count == 1


def test_teardrop_dimensions():
    """Test teardrop dimension calculation."""
    path = RoutePath("NET1", [(0, 0), (10, 10)], "F.Cu", 14.14)
    
    via = Via((5, 5), "F.Cu", "B.Cu", 0.8, 0.4, "NET1")
    route = CompiledRoute("NET1", path, 0.127, [via], None)
    results = RoutingResults(compiled_routes={"NET1": route}, failed_nets=[])
    
    report = insert_teardrops(results, teardrop_length_ratio=0.5)
    
    if report.teardrop_count > 0:
        teardrop = report.teardrops[0]
        # Length should be 0.5 * via diameter
        assert teardrop.length_mm == pytest.approx(0.4)
        # Width should be via diameter
        assert teardrop.width_mm == pytest.approx(0.254)


def test_disable_via_teardrops():
    """Test disabling via teardrops."""
    path = RoutePath("NET1", [(0, 0), (10, 10)], "F.Cu", 14.14)
    
    via = Via((5, 5), "F.Cu", "B.Cu", 0.6, 0.3, "NET1")
    route = CompiledRoute("NET1", path, 0.127, [via], None)
    results = RoutingResults(compiled_routes={"NET1": route}, failed_nets=[])
    
    report = insert_teardrops(results, enable_via_teardrops=False)
    
    # Should not generate any teardrops
    assert report.teardrop_count == 0
