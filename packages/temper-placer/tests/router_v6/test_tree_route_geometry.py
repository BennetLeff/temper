"""Branch-aware route geometry prevents fake serial tree connections."""

from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.astar_core import RoutePath, RoutePath3D
from temper_placer.router_v6.connectivity import (
    CopperPad,
    CopperTrack,
    CopperVia,
    NetDisposition,
    PadIdentity,
    verify_net_connectivity,
)
from temper_placer.router_v6.constraints_geometry import Point
from temper_placer.router_v6.terminal_tree import TerminalTreeEdge
from temper_placer.router_v6.tree_route_geometry import (
    TreeRouteBranch,
    TreeRouteGeometry,
)


def _identity(pad: str, x: int, y: int) -> PadIdentity:
    return PadIdentity("U1", pad, "NET", x, y, (0,))


def test_branch_segments_do_not_bridge_unrelated_branch_endpoints():
    root, east, north = _identity("1", 0, 0), _identity("2", 10, 0), _identity("3", 0, 10)
    tree = TreeRouteGeometry(
        "NET",
        (
            TreeRouteBranch(TerminalTreeEdge(root, east), RoutePath("NET", [(0, 0), (10, 0)], "F.Cu", 10)),
            TreeRouteBranch(TerminalTreeEdge(root, north), RoutePath("NET", [(0, 0), (0, 10)], "F.Cu", 10)),
        ),
    )

    assert set(tree.iter_segments()) == {
        ((0, 0, "F.Cu"), (10, 0, "F.Cu")),
        ((0, 0, "F.Cu"), (0, 10, "F.Cu")),
    }
    assert ((10, 0, "F.Cu"), (0, 0, "F.Cu")) not in set(tree.iter_segments())
    assert ((10, 0, "F.Cu"), (0, 10, "F.Cu")) not in set(tree.iter_segments())


def test_branch_geometry_preserves_layer_and_via_metadata_and_connects_pads():
    root, east, north = _identity("1", 0, 0), _identity("2", 10, 0), _identity("3", 0, 10)
    tree = TreeRouteGeometry(
        "NET",
        (
            TreeRouteBranch(TerminalTreeEdge(root, east), RoutePath("NET", [(0, 0), (10, 0)], "F.Cu", 10)),
            TreeRouteBranch(
                TerminalTreeEdge(root, north),
                RoutePath3D("NET", [(0, 0, "F.Cu"), (0, 0, "B.Cu"), (0, 10, "B.Cu")], [(0, 0)], 10, 1),
            ),
        ),
    )
    pads = [
        CopperPad(root, Point(0, 0), "rect", (1, 1)),
        CopperPad(east, Point(10, 0), "rect", (1, 1)),
        CopperPad(PadIdentity("U1", "3", "NET", 0, 10, (1,)), Point(0, 10), "rect", (1, 1)),
    ]
    tracks = [CopperTrack(Point(start[0], start[1]), Point(end[0], end[1]), 0 if start[2] == "F.Cu" else 1) for start, end in tree.iter_segments()]

    assert tree.via_positions == ((0, 0),)
    assert verify_net_connectivity(
        pads, tracks, [CopperVia(Point(0, 0), frozenset({0, 1}))]
    ).disposition is NetDisposition.ROUTED


@given(st.permutations([0, 1, 2]))
@settings(max_examples=10, deadline=30_000)
def test_branch_order_is_canonical_under_input_permutation(order):
    root, east, north = _identity("1", 0, 0), _identity("2", 10, 0), _identity("3", 0, 10)
    branches = [
        TreeRouteBranch(TerminalTreeEdge(root, east), RoutePath("NET", [(0, 0), (10, 0)], "F.Cu", 10)),
        TreeRouteBranch(TerminalTreeEdge(root, north), RoutePath("NET", [(0, 0), (0, 10)], "F.Cu", 10)),
        TreeRouteBranch(TerminalTreeEdge(east, north), RoutePath("NET", [(10, 0), (0, 10)], "F.Cu", 14)),
    ]
    expected = TreeRouteGeometry("NET", tuple(branches))

    actual = TreeRouteGeometry("NET", tuple(branches[index] for index in order))

    assert actual == expected
