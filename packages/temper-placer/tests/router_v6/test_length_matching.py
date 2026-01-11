"""
Tests for Router V6 Stage 4.5: Apply Length Matching

Part of temper-t2bv
"""

import pytest

from temper_placer.router_v6.astar_pathfinding import PathfindingResult, RoutePath
from temper_placer.router_v6.length_matching import (
    LengthMatchingResult,
    LengthMatchingResults,
    apply_length_matching,
)


def test_apply_no_length_matching():
    """Test length matching with no paths."""
    result = PathfindingResult(routed_paths={}, failed_nets=[])
    
    matching = apply_length_matching(result)
    
    assert matching.matched_net_count == 0


def test_apply_no_targets():
    """Test length matching without target lengths."""
    path = RoutePath("NET1", [(0, 0), (10, 10)], "F.Cu", 14.14)
    result = PathfindingResult(routed_paths={"NET1": path}, failed_nets=[])
    
    matching = apply_length_matching(result)
    
    # Should still have result, but no matching applied
    assert matching.matched_net_count == 1
    net_result = matching.get_result("NET1")
    assert net_result is not None
    assert not net_result.serpentine_added


def test_apply_length_matching_exact():
    """Test length matching when path already matches target."""
    path = RoutePath("NET1", [(0, 0), (10, 10)], "F.Cu", 14.14)
    result = PathfindingResult(routed_paths={"NET1": path}, failed_nets=[])
    
    # Target exactly matches original length
    matching = apply_length_matching(result, length_targets={"NET1": 14.14})
    
    net_result = matching.get_result("NET1")
    assert net_result is not None
    assert net_result.matched_length == pytest.approx(14.14, abs=0.01)
    assert not net_result.serpentine_added


def test_apply_length_matching_add_length():
    """Test adding length via serpentine."""
    path = RoutePath("NET1", [(0, 0), (10, 0)], "F.Cu", 10.0)
    result = PathfindingResult(routed_paths={"NET1": path}, failed_nets=[])
    
    # Target is longer - should add serpentine
    matching = apply_length_matching(result, length_targets={"NET1": 15.0})
    
    net_result = matching.get_result("NET1")
    assert net_result is not None
    assert net_result.original_length == 10.0
    assert net_result.target_length == 15.0
    assert net_result.matched_length > net_result.original_length
    assert net_result.serpentine_added


def test_length_matching_result_dataclass():
    """Test LengthMatchingResult dataclass."""
    result = LengthMatchingResult(
        net_name="TEST_NET",
        original_length=10.0,
        target_length=12.0,
        matched_length=11.8,
        serpentine_added=True,
    )
    
    assert result.net_name == "TEST_NET"
    assert result.original_length == 10.0
    assert result.target_length == 12.0
    assert result.matched_length == 11.8
    assert result.serpentine_added
    assert result.length_delta == pytest.approx(0.2)


def test_length_matching_results_dataclass():
    """Test LengthMatchingResults dataclass."""
    result1 = LengthMatchingResult("NET1", 10.0, 12.0, 11.9, True)
    result2 = LengthMatchingResult("NET2", 8.0, 8.0, 8.0, False)
    
    results = LengthMatchingResults(results={
        "NET1": result1,
        "NET2": result2,
    })
    
    assert results.matched_net_count == 2
    assert results.get_result("NET1") == result1
    assert results.get_result("NET2") == result2
    assert results.get_result("NET3") is None


def test_apply_multiple_nets_matching():
    """Test length matching for multiple nets."""
    paths = {
        "NET1": RoutePath("NET1", [(0, 0), (10, 0)], "F.Cu", 10.0),
        "NET2": RoutePath("NET2", [(0, 0), (8, 0)], "F.Cu", 8.0),
    }
    
    result = PathfindingResult(routed_paths=paths, failed_nets=[])
    
    # Match both nets to 12mm
    matching = apply_length_matching(result, length_targets={
        "NET1": 12.0,
        "NET2": 12.0,
    })
    
    assert matching.matched_net_count == 2
    
    # Both should have serpentines added
    net1_result = matching.get_result("NET1")
    net2_result = matching.get_result("NET2")
    
    assert net1_result.serpentine_added
    assert net2_result.serpentine_added
