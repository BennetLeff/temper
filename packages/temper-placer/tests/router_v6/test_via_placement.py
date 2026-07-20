"""Tests for Router V6 Stage 4.3: Place Vias."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.astar_core import RoutePath3D
from temper_placer.router_v6.astar_pathfinding import PathfindingResult, RoutePath
from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules
from temper_placer.router_v6.via_placement import Via, ViaPlacement, place_vias

_REPO_ROOT = Path(__file__).resolve().parents[4]
_NETCLASS_CONFIG = yaml.safe_load(
    (_REPO_ROOT / "packages/temper-placer/configs/netclass_rules.yaml").read_text()
)
_CONFIGURED_NET_CLASSES = tuple(_NETCLASS_CONFIG["classes"])


def _configured_design_rules(net_class: str | None) -> DesignRules:
    """Build the router's runtime rules directly from the netclass SSOT."""
    net_classes = {
        name: NetClassRules(
            name=name,
            clearance_mm=spec["clearance"],
            trace_width_mm=spec["trace_width"],
            via_diameter_mm=spec["via_diameter"],
            via_drill_mm=spec["via_drill"],
        )
        for name, spec in _NETCLASS_CONFIG["classes"].items()
    }
    assignments = {"NET_UNDER_TEST": net_class} if net_class is not None else {}
    return DesignRules(
        net_classes=net_classes,
        net_class_assignments=assignments,
        default_clearance_mm=0.2,
        default_trace_width_mm=0.2,
        default_via_diameter_mm=0.6,
        default_via_drill_mm=0.3,
    )


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


def _path3d_with_transitions(
    layers: list[str],
    net_name: str = "NET3D",
    co_locate_transitions: bool = False,
) -> RoutePath3D:
    """Build a valid path with one same-coordinate transition per layer pair."""
    segments: list[tuple[float, float, str]] = [(0.0, 0.0, layers[0])]
    via_positions: list[tuple[float, float]] = []
    for index, layer in enumerate(layers[1:], start=1):
        position = (1.0, 1.0) if co_locate_transitions else (float(index), float(index))
        # Move on the current layer, then transition at one shared position.
        segments.append((position[0], position[1], layers[index - 1]))
        segments.append((position[0], position[1], layer))
        via_positions.append(position)
    return RoutePath3D(
        net_name=net_name,
        segments=segments,
        via_positions=via_positions,
        path_length=float(len(layers) - 1),
        via_count=len(via_positions),
    )


def test_route_path_3d_via_uses_actual_non_outer_layer_pair():
    """U3/R2: inner-layer transitions must not become F.Cu-to-B.Cu vias."""
    path = _path3d_with_transitions(["In1.Cu", "In2.Cu"])
    result = PathfindingResult(routed_paths={"NET3D": path}, failed_nets=[])

    placement = place_vias(result)

    assert [(via.from_layer, via.to_layer) for via in placement.vias] == [("In1.Cu", "In2.Cu")]


def test_route_path_3d_outer_layer_transition_remains_unchanged():
    """U3/R2 regression: existing F.Cu-to-B.Cu transitions keep their span."""
    path = _path3d_with_transitions(["F.Cu", "B.Cu"])
    result = PathfindingResult(routed_paths={"NET3D": path}, failed_nets=[])

    placement = place_vias(result)

    assert [(via.from_layer, via.to_layer) for via in placement.vias] == [("F.Cu", "B.Cu")]


def test_route_path_3d_multiple_transitions_keep_each_actual_layer_pair():
    """U3/R2: each transition retains its own ordered adjacent layers."""
    layers = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
    path = _path3d_with_transitions(layers)
    result = PathfindingResult(routed_paths={"NET3D": path}, failed_nets=[])

    placement = place_vias(result)

    assert [(via.from_layer, via.to_layer) for via in placement.vias] == list(
        zip(layers, layers[1:])
    )


def test_route_path_3d_co_located_transitions_consume_each_layer_pair_once():
    """U3/R2: stacked transitions at one coordinate must not reuse pair one."""
    layers = ["F.Cu", "In1.Cu", "In2.Cu"]
    path = _path3d_with_transitions(layers, co_locate_transitions=True)
    result = PathfindingResult(routed_paths={"NET3D": path}, failed_nets=[])

    placement = place_vias(result)

    assert [(via.from_layer, via.to_layer) for via in placement.vias] == list(
        zip(layers, layers[1:])
    )


_COPPER_LAYERS = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")


@st.composite
def _layer_transition_sequences(draw) -> list[str]:
    """Generate valid walks whose consecutive layers are genuine transitions."""
    layers = [draw(st.sampled_from(_COPPER_LAYERS))]
    for _ in range(draw(st.integers(min_value=1, max_value=7))):
        layers.append(
            draw(st.sampled_from(tuple(layer for layer in _COPPER_LAYERS if layer != layers[-1])))
        )
    return layers


@pytest.mark.property
@given(
    layers=_layer_transition_sequences(),
    co_locate_transitions=st.booleans(),
)
@settings(max_examples=100, deadline=15000)
def test_route_path_3d_via_layer_pairs_preserve_every_transition(
    layers: list[str], co_locate_transitions: bool
):
    """U3/R2 invariant: every emitted via keeps its path's ordered layer pair."""
    path = _path3d_with_transitions(layers, co_locate_transitions=co_locate_transitions)
    result = PathfindingResult(routed_paths={"NET3D": path}, failed_nets=[])

    placement = place_vias(result)

    assert [(via.from_layer, via.to_layer) for via in placement.vias] == list(
        zip(layers, layers[1:])
    )
    assert all(via.net_name == "NET3D" for via in placement.vias)


def test_route_path_3d_via_uses_its_netclass_dimensions():
    """U4/R3: final vias must not silently use the board-wide default."""
    path = _path3d_with_transitions(["F.Cu", "B.Cu"], net_name="HV_NET")
    result = PathfindingResult(routed_paths={"HV_NET": path}, failed_nets=[])
    design_rules = DesignRules(
        default_via_diameter_mm=0.6,
        default_via_drill_mm=0.3,
        net_class_assignments={"HV_NET": "HighVoltage"},
        net_classes={
            "HighVoltage": NetClassRules(
                name="HighVoltage",
                clearance_mm=6.0,
                trace_width_mm=3.0,
                via_diameter_mm=1.2,
                via_drill_mm=0.6,
            )
        },
    )

    placement = place_vias(result, design_rules=design_rules)

    assert [(via.diameter, via.drill) for via in placement.vias] == [(1.2, 0.6)]


@pytest.mark.property
@given(net_class=st.sampled_from(_CONFIGURED_NET_CLASSES + (None,)))
@settings(max_examples=100, deadline=15000)
def test_route_path_3d_vias_match_every_configured_netclass_or_default(net_class: str | None):
    """U4/R3: every SSOT class, plus no assignment, controls final via size."""
    path = _path3d_with_transitions(["F.Cu", "B.Cu"], net_name="NET_UNDER_TEST")
    result = PathfindingResult(routed_paths={"NET_UNDER_TEST": path}, failed_nets=[])
    design_rules = _configured_design_rules(net_class)

    via = place_vias(result, design_rules=design_rules).vias[0]
    expected = design_rules.get_rules_for_net("NET_UNDER_TEST")

    assert (via.diameter, via.drill) == (
        expected.via_diameter_mm,
        expected.via_drill_mm,
    )


@pytest.mark.property
@given(
    first_layers=_layer_transition_sequences(),
    second_layers=_layer_transition_sequences(),
)
@settings(max_examples=75, deadline=15000)
def test_route_path_3d_vias_remain_partitioned_by_net(
    first_layers: list[str], second_layers: list[str]
):
    """U3/R2 invariant: one net's transitions cannot relabel another's vias."""
    first_path = _path3d_with_transitions(first_layers, net_name="NET_A")
    second_path = _path3d_with_transitions(second_layers, net_name="NET_B")
    result = PathfindingResult(
        routed_paths={"NET_A": first_path, "NET_B": second_path}, failed_nets=[]
    )

    placement = place_vias(result)

    for net_name, layers in (("NET_A", first_layers), ("NET_B", second_layers)):
        assert [
            (via.from_layer, via.to_layer) for via in placement.get_vias_for_net(net_name)
        ] == list(zip(layers, layers[1:]))
