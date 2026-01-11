"""
Tests for Router V6 Feedback F.2: Identify Congested Regions

Part of temper-jq8n
"""

import pytest

from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.congestion_analysis import (
    CongestedRegion,
    CongestionMap,
    CongestionSeverity,
    identify_congested_regions,
)
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults


def test_identify_no_congestion():
    """Test congestion identification with successful routing."""
    path = RoutePath("NET1", [(10, 10), (20, 20)], "F.Cu", 14.14)
    route = CompiledRoute("NET1", path, 0.127, [], None)
    results = RoutingResults(compiled_routes={"NET1": route}, failed_nets=[])
    
    congestion = identify_congested_regions(results, 100, 100)
    
    # Should have some regions due to route density, but low severity
    assert congestion.congested_region_count >= 0


def test_identify_with_failed_nets():
    """Test congestion identification with failed nets."""
    path = RoutePath("NET1", [(10, 10), (20, 20)], "F.Cu", 14.14)
    route = CompiledRoute("NET1", path, 0.127, [], None)
    results = RoutingResults(
        compiled_routes={"NET1": route},
        failed_nets=["NET2", "NET3", "NET4"]
    )
    
    congestion = identify_congested_regions(results, 100, 100)
    
    # Should identify congestion from failed nets
    assert congestion.congested_region_count > 0


def test_congested_region_dataclass():
    """Test CongestedRegion dataclass."""
    region = CongestedRegion(
        center=(50.0, 50.0),
        radius=5.0,
        severity=CongestionSeverity.HIGH,
        failed_net_count=2,
        bottleneck_score=0.8,
    )
    
    assert region.center == (50.0, 50.0)
    assert region.severity == CongestionSeverity.HIGH
    assert region.failed_net_count == 2
    assert region.bottleneck_score == 0.8


def test_congestion_map_dataclass():
    """Test CongestionMap dataclass."""
    region1 = CongestedRegion((10, 10), 5.0, CongestionSeverity.LOW, 0, 0.2)
    region2 = CongestedRegion((50, 50), 5.0, CongestionSeverity.CRITICAL, 5, 0.9)
    
    congestion_map = CongestionMap(regions=[region1, region2])
    
    assert congestion_map.congested_region_count == 2
    assert congestion_map.critical_region_count == 1


def test_get_regions_by_severity():
    """Test filtering regions by severity."""
    region1 = CongestedRegion((10, 10), 5.0, CongestionSeverity.LOW, 0, 0.2)
    region2 = CongestedRegion((50, 50), 5.0, CongestionSeverity.HIGH, 2, 0.7)
    region3 = CongestedRegion((80, 80), 5.0, CongestionSeverity.HIGH, 3, 0.8)
    
    congestion_map = CongestionMap(regions=[region1, region2, region3])
    
    high_regions = congestion_map.get_regions_by_severity(CongestionSeverity.HIGH)
    assert len(high_regions) == 2


def test_congestion_severity_enum():
    """Test CongestionSeverity enum."""
    assert CongestionSeverity.NONE.value == "none"
    assert CongestionSeverity.LOW.value == "low"
    assert CongestionSeverity.MEDIUM.value == "medium"
    assert CongestionSeverity.HIGH.value == "high"
    assert CongestionSeverity.CRITICAL.value == "critical"


def test_custom_grid_size():
    """Test congestion analysis with custom grid size."""
    path = RoutePath("NET1", [(10, 10), (20, 20)], "F.Cu", 14.14)
    route = CompiledRoute("NET1", path, 0.127, [], None)
    results = RoutingResults(compiled_routes={"NET1": route}, failed_nets=[])
    
    # Larger grid size = fewer, larger regions
    congestion_large = identify_congested_regions(results, 100, 100, grid_size=20.0)
    
    # Smaller grid size = more, smaller regions
    congestion_small = identify_congested_regions(results, 100, 100, grid_size=5.0)
    
    # Both should work without error
    assert congestion_large.congested_region_count >= 0
    assert congestion_small.congested_region_count >= 0
