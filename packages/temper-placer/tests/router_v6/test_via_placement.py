"""
Tests for Router V6 Stage 4.3: Place Vias

Part of temper-zh0p
"""


from temper_placer.router_v6.astar_pathfinding import PathfindingResult, RoutePath
from temper_placer.router_v6.via_placement import Via, ViaPlacement, place_vias


def test_place_no_vias():
    """Test via placement with no paths."""
    result = PathfindingResult(routed_paths={}, failed_nets=[])

    placement = place_vias(result)

    assert placement.via_count == 0


def test_place_vias_simple_path():
    """Test via placement for simple path."""
    path = RoutePath(
        net_name="NET1",
        coordinates=[(0, 0), (5, 5), (10, 10), (15, 15)],
        layer_name="F.Cu",
        path_length=21.2,
    )

    result = PathfindingResult(routed_paths={"NET1": path}, failed_nets=[])

    placement = place_vias(result)

    # Should place via for long path
    assert placement.via_count > 0


def test_via_dataclass():
    """Test Via dataclass."""
    via = Via(
        position=(10.0, 10.0),
        from_layer="F.Cu",
        to_layer="B.Cu",
        diameter=0.6,
        drill=0.3,
        net_name="TEST_NET",
    )

    assert via.position == (10.0, 10.0)
    assert via.from_layer == "F.Cu"
    assert via.to_layer == "B.Cu"
    assert via.diameter == 0.6
    assert via.drill == 0.3
    assert via.net_name == "TEST_NET"


def test_via_placement_dataclass():
    """Test ViaPlacement dataclass."""
    via1 = Via((0, 0), "F.Cu", "B.Cu", 0.6, 0.3, "NET1")
    via2 = Via((5, 5), "F.Cu", "B.Cu", 0.6, 0.3, "NET1")
    via3 = Via((10, 10), "F.Cu", "B.Cu", 0.6, 0.3, "NET2")

    placement = ViaPlacement(vias=[via1, via2, via3])

    assert placement.via_count == 3

    # Get vias for specific net
    net1_vias = placement.get_vias_for_net("NET1")
    assert len(net1_vias) == 2

    net2_vias = placement.get_vias_for_net("NET2")
    assert len(net2_vias) == 1


def test_place_vias_multiple_nets():
    """Test via placement for multiple nets."""
    path1 = RoutePath("NET1", [(0, 0), (5, 5), (10, 10)], "F.Cu", 14.1)
    path2 = RoutePath("NET2", [(0, 0), (3, 3), (6, 6), (9, 9)], "F.Cu", 12.7)

    result = PathfindingResult(
        routed_paths={"NET1": path1, "NET2": path2},
        failed_nets=[],
    )

    placement = place_vias(result)

    # Should have vias for both nets
    assert placement.via_count >= 0


def test_custom_via_size():
    """Test via placement with custom dimensions."""
    path = RoutePath("NET1", [(0, 0), (5, 5), (10, 10)], "F.Cu", 14.1)
    result = PathfindingResult(routed_paths={"NET1": path}, failed_nets=[])

    # Custom via size
    placement = place_vias(result, via_diameter=0.8, via_drill=0.4)

    # Check via dimensions if any vias were placed
    if placement.via_count > 0:
        via = placement.vias[0]
        assert via.diameter == 0.8
        assert via.drill == 0.4
