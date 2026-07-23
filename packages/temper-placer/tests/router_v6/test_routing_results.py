"""
Tests for Router V6 Stage 4.9: Compile Routing Results

Part of temper-xnsk
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.astar_pathfinding import PathfindingResult, RoutePath
from temper_placer.router_v6.connectivity import PadIdentity
from temper_placer.router_v6.routing_results import (
    CompiledRoute,
    RoutingResults,
    compile_routing_results,
)
from temper_placer.router_v6.terminal_tree import TerminalTreeEdge
from temper_placer.router_v6.trace_width_assignment import (
    TraceWidth,
    TraceWidthAssignment,
    assign_trace_widths,
)
from temper_placer.router_v6.tree_route_geometry import TreeRouteBranch, TreeRouteGeometry
from temper_placer.router_v6.via_placement import Via, ViaPlacement


def _tree(net_name: str) -> TreeRouteGeometry:
    root = PadIdentity("U1", "1", net_name, 0.0, 0.0, (0,))
    right = PadIdentity("U2", "1", net_name, 10.0, 0.0, (0,))
    top = PadIdentity("U3", "1", net_name, 0.0, 10.0, (0,))
    return TreeRouteGeometry(
        net_name,
        (
            TreeRouteBranch(
                TerminalTreeEdge(root, right),
                RoutePath(net_name, [(0, 0), (10, 0)], "F.Cu", 10.0),
            ),
            TreeRouteBranch(
                TerminalTreeEdge(root, top),
                RoutePath(net_name, [(0, 0), (0, 10)], "F.Cu", 10.0),
            ),
        ),
    )


def test_compile_empty_results():
    """Test compiling with no routes."""
    pathfinding = PathfindingResult(routed_paths={}, failed_nets=[])
    widths = TraceWidthAssignment(assignments={})
    vias = ViaPlacement(vias=[])

    compiled = compile_routing_results(pathfinding, widths, vias)

    assert compiled.success_count == 0
    assert compiled.failure_count == 0


def test_compile_single_route():
    """Test compiling single routed net."""
    path = RoutePath("NET1", [(0, 0), (10, 10)], "F.Cu", 14.14)
    pathfinding = PathfindingResult(routed_paths={"NET1": path}, failed_nets=[])

    width = TraceWidth("NET1", 0.254, "Signal")
    widths = TraceWidthAssignment(assignments={"NET1": width})

    vias = ViaPlacement(vias=[])

    compiled = compile_routing_results(pathfinding, widths, vias)

    assert compiled.success_count == 1
    route = compiled.get_route("NET1")
    assert route is not None
    assert route.net_name == "NET1"
    assert route.width_mm == 0.254


def test_compile_with_vias():
    """Test compiling route with vias."""
    path = RoutePath("NET1", [(0, 0), (10, 10)], "F.Cu", 14.14)
    pathfinding = PathfindingResult(routed_paths={"NET1": path}, failed_nets=[])

    widths = TraceWidthAssignment(assignments={"NET1": TraceWidth("NET1", 0.127, "Signal")})

    via1 = Via((5, 5), "F.Cu", "B.Cu", 0.6, 0.3, "NET1")
    vias = ViaPlacement(vias=[via1])

    compiled = compile_routing_results(pathfinding, widths, vias)

    route = compiled.get_route("NET1")
    assert route is not None
    assert len(route.vias) == 1
    assert route.vias[0].position == (5, 5)


def test_compiled_route_dataclass():
    """Test CompiledRoute dataclass."""
    path = RoutePath("TEST", [(0, 0)], "F.Cu", 0)
    via = Via((5, 5), "F.Cu", "B.Cu", 0.6, 0.3, "TEST")

    route = CompiledRoute(
        net_name="TEST",
        path=path,
        width_mm=0.254,
        vias=[via],
        matched_length_mm=12.5,
    )

    assert route.net_name == "TEST"
    assert route.width_mm == 0.254
    assert len(route.vias) == 1
    assert route.matched_length_mm == 12.5


def test_routing_results_dataclass():
    """Test RoutingResults dataclass."""
    path1 = RoutePath("NET1", [(0, 0), (10, 0)], "F.Cu", 10.0)
    path2 = RoutePath("NET2", [(0, 0), (5, 0)], "F.Cu", 5.0)

    route1 = CompiledRoute("NET1", path1, 0.127, [], None)
    route2 = CompiledRoute("NET2", path2, 0.254, [], None)

    results = RoutingResults(
        compiled_routes={"NET1": route1, "NET2": route2},
        failed_nets=["NET3"],
    )

    assert results.success_count == 2
    assert results.failure_count == 1
    assert results.total_route_length == 15.0
    assert results.get_route("NET1") == route1
    assert results.get_route("NET3") is None


def test_compile_multiple_routes():
    """Test compiling multiple routes."""
    paths = {
        "NET1": RoutePath("NET1", [(0, 0), (10, 0)], "F.Cu", 10.0),
        "NET2": RoutePath("NET2", [(0, 0), (5, 0)], "F.Cu", 5.0),
    }
    pathfinding = PathfindingResult(routed_paths=paths, failed_nets=["NET3"])

    widths = TraceWidthAssignment(
        assignments={
            "NET1": TraceWidth("NET1", 0.127, "Signal"),
            "NET2": TraceWidth("NET2", 0.508, "Power"),
        }
    )

    vias = ViaPlacement(vias=[])

    compiled = compile_routing_results(pathfinding, widths, vias)

    assert compiled.success_count == 2
    assert compiled.failure_count == 1
    assert compiled.total_route_length == 15.0


def test_partial_routes_receive_the_board_derived_width_assignment():
    partial = RoutePath("NET1", [(0, 0), (10, 0)], "F.Cu", 10.0, forced_segment_count=1)
    pathfinding = PathfindingResult(
        routed_paths={}, failed_nets=["NET1"], partial_paths={"NET1": partial}
    )

    widths = assign_trace_widths(pathfinding, default_width=0.2)
    compiled = compile_routing_results(pathfinding, widths, ViaPlacement(vias=[]))

    assert widths.get_width("NET1") == 0.2
    assert compiled.partial_routes["NET1"].width_mm == 0.2


def test_complete_and_partial_tree_routes_receive_declared_net_class_widths():
    result = PathfindingResult(
        routed_paths={},
        failed_nets=["HV_TREE"],
        tree_routes={"GND_TREE": _tree("GND_TREE")},
        partial_tree_routes={"HV_TREE": _tree("HV_TREE")},
    )
    widths = assign_trace_widths(result, default_width=0.2, power_width=0.5, hv_width=0.7)
    compiled = compile_routing_results(result, widths, ViaPlacement(vias=[]))

    assert compiled.tree_routes["GND_TREE"].width_mm == 0.5
    assert compiled.partial_tree_routes["HV_TREE"].width_mm == 0.7


@given(st.floats(min_value=0.15, max_value=1.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=30, deadline=30_000)
def test_tree_branches_preserve_each_declared_board_default(default_width: float):
    result = PathfindingResult(
        routed_paths={}, failed_nets=[], tree_routes={"TREE_SIG": _tree("TREE_SIG")}
    )

    widths = assign_trace_widths(result, default_width=default_width)
    compiled = compile_routing_results(result, widths, ViaPlacement(vias=[]))

    assert widths.get_width("TREE_SIG") == default_width
    assert compiled.tree_routes["TREE_SIG"].width_mm == default_width


@given(st.floats(min_value=0.15, max_value=1.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=30, deadline=30_000)
def test_partial_route_width_preserves_each_declared_board_default(default_width: float):
    partial = RoutePath("NET1", [(0, 0), (10, 0)], "F.Cu", 10.0, forced_segment_count=1)
    result = PathfindingResult(
        routed_paths={}, failed_nets=["NET1"], partial_paths={"NET1": partial}
    )

    widths = assign_trace_widths(result, default_width=default_width)

    assert widths.get_width("NET1") == default_width
