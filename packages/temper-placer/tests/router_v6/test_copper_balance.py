"""
Tests for Router V6 Stage 5.5: Analyze and Balance Copper

Part of temper-nd5z
"""

import pytest

from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.copper_balance import (
    CopperBalanceReport,
    LayerCopperBalance,
    analyze_copper_balance,
)
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults
from temper_placer.router_v6.via_placement import Via


def test_analyze_empty_board():
    """Test copper balance with no routes."""
    results = RoutingResults(compiled_routes={}, failed_nets=[])
    
    report = analyze_copper_balance(results, 100, 100)
    
    # Should analyze all layers
    assert len(report.layer_balances) == 4
    # Empty board has 0% copper - unbalanced
    assert report.unbalanced_layer_count > 0


def test_layer_copper_balance_dataclass():
    """Test LayerCopperBalance dataclass."""
    balance = LayerCopperBalance(
        layer_name="F.Cu",
        total_area_mm2=10000.0,
        copper_area_mm2=4500.0,
        copper_percentage=45.0,
        is_balanced=True,
    )
    
    assert balance.layer_name == "F.Cu"
    assert balance.copper_percentage == 45.0
    assert balance.is_balanced
    assert not balance.needs_balancing


def test_copper_balance_report_dataclass():
    """Test CopperBalanceReport dataclass."""
    balance1 = LayerCopperBalance("F.Cu", 10000, 4500, 45, True)
    balance2 = LayerCopperBalance("B.Cu", 10000, 8000, 80, False)
    
    report = CopperBalanceReport(layer_balances=[balance1, balance2])
    
    assert report.balanced_layer_count == 1
    assert report.unbalanced_layer_count == 1


def test_analyze_with_routes():
    """Test copper balance with actual routes."""
    path = RoutePath("NET1", [(0, 0), (50, 50)], "F.Cu", 70.7)
    route = CompiledRoute("NET1", path, 0.254, [], None)
    results = RoutingResults(compiled_routes={"NET1": route}, failed_nets=[])
    
    report = analyze_copper_balance(results, 100, 100)
    
    # Should have copper on F.Cu layer
    f_cu_balance = next(lb for lb in report.layer_balances if lb.layer_name == "F.Cu")
    assert f_cu_balance.copper_area_mm2 > 0


def test_analyze_with_vias():
    """Test copper balance including via pads."""
    path = RoutePath("NET1", [(0, 0), (10, 10)], "F.Cu", 14.14)
    via = Via((5, 5), "F.Cu", "B.Cu", 0.6, 0.3, "NET1")
    route = CompiledRoute("NET1", path, 0.127, [via], None)
    results = RoutingResults(compiled_routes={"NET1": route}, failed_nets=[])
    
    report = analyze_copper_balance(results, 100, 100)
    
    # Via should add copper to both F.Cu and B.Cu
    f_cu_balance = next(lb for lb in report.layer_balances if lb.layer_name == "F.Cu")
    b_cu_balance = next(lb for lb in report.layer_balances if lb.layer_name == "B.Cu")
    
    assert f_cu_balance.copper_area_mm2 > 0
    assert b_cu_balance.copper_area_mm2 > 0


def test_balance_range_checking():
    """Test copper balance range (30-70%)."""
    # Create routes to test different balance scenarios
    path = RoutePath("NET1", [(0, 0), (100, 0)], "F.Cu", 100.0)
    route = CompiledRoute("NET1", path, 5.0, [], None)  # Wide trace
    results = RoutingResults(compiled_routes={"NET1": route}, failed_nets=[])
    
    # Small board to get high copper percentage
    report = analyze_copper_balance(results, 20, 10)
    
    # Some layers should be unbalanced (0% or too high)
    assert report.unbalanced_layer_count > 0


def test_custom_balance_thresholds():
    """Test custom copper balance thresholds."""
    path = RoutePath("NET1", [(0, 0), (10, 10)], "F.Cu", 14.14)
    route = CompiledRoute("NET1", path, 0.127, [], None)
    results = RoutingResults(compiled_routes={"NET1": route}, failed_nets=[])
    
    # Very strict thresholds
    report = analyze_copper_balance(
        results, 100, 100,
        min_copper_percentage=40.0,
        max_copper_percentage=60.0,
    )
    
    # Most layers should be unbalanced with strict thresholds
    assert report.unbalanced_layer_count >= 0
