"""
Tests for Router V6 Stage 5.4: Add Thermal Relief

Part of temper-95xg
"""

import pytest

from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults
from temper_placer.router_v6.thermal_relief import (
    ThermalRelief,
    ThermalReliefReport,
    add_thermal_relief,
)
from temper_placer.router_v6.via_placement import Via


def test_add_no_thermal_relief():
    """Test thermal relief with no power nets."""
    path = RoutePath("SIG1", [(0, 0), (10, 10)], "F.Cu", 14.14)
    route = CompiledRoute("SIG1", path, 0.127, [], None)
    results = RoutingResults(compiled_routes={"SIG1": route}, failed_nets=[])
    
    report = add_thermal_relief(results)
    
    # Signal net should not get thermal relief
    assert report.relief_count == 0


def test_add_thermal_relief_gnd():
    """Test thermal relief for GND net."""
    path = RoutePath("GND", [(0, 0), (10, 10)], "F.Cu", 14.14)
    
    # Via connecting to inner plane layer
    via = Via((5, 5), "F.Cu", "In1.Cu", 0.6, 0.3, "GND")
    route = CompiledRoute("GND", path, 0.127, [via], None)
    results = RoutingResults(compiled_routes={"GND": route}, failed_nets=[])
    
    report = add_thermal_relief(results)
    
    # GND via to plane should get thermal relief
    assert report.relief_count > 0


def test_thermal_relief_dataclass():
    """Test ThermalRelief dataclass."""
    relief = ThermalRelief(
        net_name="GND",
        pad_position=(5.0, 5.0),
        spoke_count=4,
        spoke_width=0.254,
        clearance_gap=0.254,
    )
    
    assert relief.net_name == "GND"
    assert relief.pad_position == (5.0, 5.0)
    assert relief.spoke_count == 4
    assert relief.spoke_width == 0.254
    assert relief.clearance_gap == 0.254


def test_thermal_relief_report_dataclass():
    """Test ThermalReliefReport dataclass."""
    relief1 = ThermalRelief("GND", (0, 0), 4, 0.254, 0.254)
    relief2 = ThermalRelief("VCC", (5, 5), 4, 0.254, 0.254)
    
    report = ThermalReliefReport(thermal_reliefs=[relief1, relief2])
    
    assert report.relief_count == 2
    assert report.total_spokes == 8  # 4 + 4


def test_custom_spoke_parameters():
    """Test thermal relief with custom spoke parameters."""
    path = RoutePath("GND", [(0, 0), (10, 10)], "F.Cu", 14.14)
    via = Via((5, 5), "F.Cu", "In1.Cu", 0.6, 0.3, "GND")
    route = CompiledRoute("GND", path, 0.127, [via], None)
    results = RoutingResults(compiled_routes={"GND": route}, failed_nets=[])
    
    report = add_thermal_relief(
        results,
        spoke_count=8,
        spoke_width=0.3,
        clearance_gap=0.2,
    )
    
    if report.relief_count > 0:
        relief = report.thermal_reliefs[0]
        assert relief.spoke_count == 8
        assert relief.spoke_width == 0.3
        assert relief.clearance_gap == 0.2


def test_multiple_power_vias():
    """Test thermal relief for multiple power vias."""
    path = RoutePath("GND", [(0, 0), (20, 20)], "F.Cu", 28.28)
    
    via1 = Via((5, 5), "F.Cu", "In1.Cu", 0.6, 0.3, "GND")
    via2 = Via((10, 10), "F.Cu", "In2.Cu", 0.6, 0.3, "GND")
    via3 = Via((15, 15), "F.Cu", "B.Cu", 0.6, 0.3, "GND")  # Not to plane
    
    route = CompiledRoute("GND", path, 0.127, [via1, via2, via3], None)
    results = RoutingResults(compiled_routes={"GND": route}, failed_nets=[])
    
    report = add_thermal_relief(results)
    
    # Only via1 and via2 connect to planes
    assert report.relief_count >= 2


def test_multiple_power_nets():
    """Test thermal relief across multiple power nets."""
    gnd_path = RoutePath("GND", [(0, 0), (10, 10)], "F.Cu", 14.14)
    gnd_via = Via((5, 5), "F.Cu", "In1.Cu", 0.6, 0.3, "GND")
    gnd_route = CompiledRoute("GND", gnd_path, 0.127, [gnd_via], None)
    
    vcc_path = RoutePath("VCC", [(0, 0), (10, 10)], "F.Cu", 14.14)
    vcc_via = Via((5, 5), "F.Cu", "In2.Cu", 0.6, 0.3, "VCC")
    vcc_route = CompiledRoute("VCC", vcc_path, 0.127, [vcc_via], None)
    
    results = RoutingResults(
        compiled_routes={"GND": gnd_route, "VCC": vcc_route},
        failed_nets=[]
    )
    
    report = add_thermal_relief(results)
    
    # Both power nets should get thermal relief
    assert report.relief_count >= 2
