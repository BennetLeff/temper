import pytest

from temper_placer.router_v6.astar_pathfinding import PathfindingResult, RoutePath
from temper_placer.router_v6.length_group_inference import LengthGroup
from temper_placer.router_v6.length_matching import apply_length_matching, equalize_group_lengths


@pytest.fixture
def mock_pathfinding_result():
    # Net 1: 100mm, Net 2: 105mm (Length group)
    # Net 3: 50mm (Individual target 60mm)
    paths = {
        "NET1": RoutePath("NET1", [], "F.Cu", 100.0),
        "NET2": RoutePath("NET2", [], "F.Cu", 105.0),
        "NET3": RoutePath("NET3", [], "F.Cu", 50.0)
    }
    return PathfindingResult(routed_paths=paths, failed_nets=[])

def test_equalize_group_lengths(mock_pathfinding_result):
    group = LengthGroup("TEST_GROUP", ["NET1", "NET2"], 0.1)
    results = equalize_group_lengths(group, mock_pathfinding_result)

    # Target should be 105.0 (max of 100 and 105)
    net1_res = next(r for r in results if r.net_name == "NET1")
    assert net1_res.target_length == 105.0
    assert net1_res.serpentine_added
    # Real geometry: 5 mm deficit → 2 cycles × 1 mm amplitude → 4 mm added
    assert net1_res.matched_length == pytest.approx(104.0)

    net2_res = next(r for r in results if r.net_name == "NET2")
    assert net2_res.target_length == 105.0
    assert not net2_res.serpentine_added
    assert net2_res.matched_length == 105.0

def test_apply_length_matching_combined(mock_pathfinding_result):
    groups = [LengthGroup("G1", ["NET1", "NET2"], 0.5)]
    targets = {"NET3": 60.0}

    results = apply_length_matching(mock_pathfinding_result, length_groups=groups, individual_targets=targets)

    assert results.matched_net_count == 3

    # Check group
    # Real geometry: 5 mm deficit → 2 cycles × 1 mm amplitude → 4 mm added
    assert results.get_result("NET1").matched_length == pytest.approx(104.0)
    assert results.get_result("NET2").matched_length == 105.0

    # Check individual
    assert results.get_result("NET3").target_length == 60.0
    assert results.get_result("NET3").serpentine_added
    assert results.get_result("NET3").matched_length == 60.0

def test_length_matching_tolerance(mock_pathfinding_result):
    # Within tolerance (max_skew = 10mm)
    group = LengthGroup("TOL_GROUP", ["NET1", "NET2"], 10.0)
    results = equalize_group_lengths(group, mock_pathfinding_result)

    net1_res = next(r for r in results if r.net_name == "NET1")
    assert not net1_res.serpentine_added # 105 - 100 = 5 < 10
    assert net1_res.matched_length == 100.0
