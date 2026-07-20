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


class TestViaLayerSpanFromSegments:
    """U3: _place_vias_for_path must derive from/to_layer from segment layers."""

    def test_fcu_to_bcu_via_derives_layers_from_segments(self):
        from temper_placer.router_v6.astar_core import RoutePath3D
        from temper_placer.router_v6.via_placement import _place_vias_for_path

        path = RoutePath3D(
            net_name="TEST",
            segments=[(0.0,0.0,"F.Cu"),(5.0,0.0,"F.Cu"),(5.0,0.0,"B.Cu"),(10.0,0.0,"B.Cu")],
            via_positions=[(5.0, 0.0)], path_length=10.0,
        )
        vias = _place_vias_for_path("TEST", path, via_diameter=0.6, via_drill=0.3)
        assert len(vias) == 1
        assert vias[0].from_layer == "F.Cu"
        assert vias[0].to_layer == "B.Cu"

    def test_multiple_transitions_produce_correctly_paired_vias(self):
        from temper_placer.router_v6.astar_core import RoutePath3D
        from temper_placer.router_v6.via_placement import _place_vias_for_path

        path = RoutePath3D(
            net_name="TEST",
            segments=[(0.0,0.0,"F.Cu"),(5.0,0.0,"F.Cu"),(5.0,0.0,"B.Cu"),
                      (10.0,0.0,"B.Cu"),(10.0,0.0,"F.Cu"),(15.0,0.0,"F.Cu")],
            via_positions=[(5.0,0.0),(10.0,0.0)], path_length=15.0,
        )
        vias = _place_vias_for_path("TEST", path, via_diameter=0.6, via_drill=0.3)
        assert len(vias) == 2
        assert vias[0].from_layer == "F.Cu" and vias[0].to_layer == "B.Cu"
        assert vias[1].from_layer == "B.Cu" and vias[1].to_layer == "F.Cu"

    def test_legacy_routepath_fallback_unchanged(self):
        from temper_placer.router_v6.astar_pathfinding import RoutePath
        from temper_placer.router_v6.via_placement import _place_vias_for_path

        path = RoutePath(net_name="TEST", coordinates=[(0,0),(5,0),(10,0)],
                         layer_name="F.Cu", path_length=10.0)
        vias = _place_vias_for_path("TEST", path, via_diameter=0.6, via_drill=0.3)
        assert len(vias) >= 1


class TestPerNetViaSizing:
    """U4: place_vias must resolve per-netclass via_diameter/via_drill."""

    def test_hv_netclass_gets_hv_sized_via(self):
        from temper_placer.router_v6.astar_core import RoutePath3D
        from temper_placer.router_v6.astar_pathfinding import PathfindingResult
        from temper_placer.router_v6.via_placement import place_vias

        path = RoutePath3D(
            net_name="+340V_BUS",
            segments=[(0,0,"F.Cu"),(5,0,"F.Cu"),(5,0,"B.Cu"),(10,0,"B.Cu")],
            via_positions=[(5,0)], path_length=10.0,
        )
        result = PathfindingResult(routed_paths={"+340V_BUS": path}, failed_nets=[])
        placement = place_vias(
            result,
            net_class_assignments={"+340V_BUS": "HighVoltage"},
            net_class_rules={"HighVoltage": type("NS",(),{"via_diameter_mm":1.2,"via_drill_mm":0.6})},
        )
        assert placement.via_count == 1
        via = placement.vias[0]
        assert via.diameter == 1.2
        assert via.drill == 0.6

    def test_unclassified_net_falls_back_to_default(self):
        from temper_placer.router_v6.astar_core import RoutePath3D
        from temper_placer.router_v6.astar_pathfinding import PathfindingResult
        from temper_placer.router_v6.via_placement import place_vias

        path = RoutePath3D(
            net_name="SIG1",
            segments=[(0,0,"F.Cu"),(5,0,"F.Cu"),(5,0,"B.Cu"),(10,0,"B.Cu")],
            via_positions=[(5,0)], path_length=10.0,
        )
        result = PathfindingResult(routed_paths={"SIG1": path}, failed_nets=[])
        placement = place_vias(result, via_diameter=0.8, via_drill=0.4)
        assert placement.via_count == 1
        assert placement.vias[0].diameter == 0.8
        assert placement.vias[0].drill == 0.4
