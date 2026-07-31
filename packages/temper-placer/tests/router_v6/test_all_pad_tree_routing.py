# @req(APC1, R3): all-pad routing connectivity — truthful completion reporting
# @req(APC1, R4): completion derived from connectivity, not path count

"""All-pad routing tree regressions for Router V6."""

from unittest.mock import patch

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.astar_pathfinding import (
    PathfindingResult,
    RoutePath,
    run_astar_pathfinding,
)
from temper_placer.router_v6.channel_mapping import (
    ChannelMapping,
    ChannelPath,
    expand_channel_path_terminals,
    fallback_channel_path,
)
from temper_placer.router_v6.connectivity import (
    CopperPad,
    CopperTrack,
    NetDisposition,
    PadIdentity,
    verify_net_connectivity,
)
from temper_placer.router_v6.constraints_geometry import Point
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.routing_results import compile_routing_results
from temper_placer.router_v6.terminal_extraction import ParsedTerminal
from temper_placer.router_v6.terminal_tree import plan_terminal_tree
from temper_placer.router_v6.trace_width_assignment import TraceWidthAssignment
from temper_placer.router_v6.via_placement import ViaPlacement


def _grid() -> OccupancyGrid:
    return OccupancyGrid("F.Cu", np.zeros((30, 30), dtype=np.int8), (0, 0), 1.0, 30, 30)


def _audit(points: list[tuple[int, int]], coordinates: list[tuple[float, float]]):
    pads = [
        CopperPad(PadIdentity("U1", str(index), "SIG", x, y, (0,)), Point(x, y), "rect", (1, 1))
        for index, (x, y) in enumerate(points)
    ]
    tracks = [
        CopperTrack(Point(*start), Point(*end), layer=0)
        for start, end in zip(coordinates, coordinates[1:])
    ]
    return verify_net_connectivity(pads, tracks, [])


def test_fallback_default_preserves_historical_two_endpoint_behavior():
    path = fallback_channel_path("SIG", [(20, 0), (0, 0), (10, 0)])

    assert path.waypoints == [(20, 0), (10, 0)]


def test_fallback_retains_every_terminal_only_when_explicitly_enabled():
    path = fallback_channel_path("SIG", [(20, 0), (0, 0), (10, 0)], enable_all_pad_tree=True)

    assert path.waypoints == [(0, 0), (10, 0), (20, 0)]


def test_sat_channel_path_appends_only_missing_physical_terminals():
    channel_path = ChannelPath("SIG", ["CH1"], [(5, 5), (15, 5)], 10.0)

    expanded = expand_channel_path_terminals(
        channel_path, [(20, 0), (0, 0), (10, 0)], enable_all_pad_tree=True
    )

    assert expanded.channel_sequence == ["CH1"]
    assert expanded.waypoints == [(5, 5), (15, 5), (10, 0), (0, 0), (20, 0)]


def test_sat_terminal_expansion_attaches_nearest_terminal_first_with_stable_ties():
    channel_path = ChannelPath("SIG", ["CH1"], [(5, 5)], 0.0)

    expanded = expand_channel_path_terminals(
        channel_path, [(10, 5), (0, 5), (20, 5)], enable_all_pad_tree=True
    )

    assert expanded.waypoints == [(5, 5), (0, 5), (10, 5), (20, 5)]


def test_sat_terminal_expansion_is_disabled_by_default():
    channel_path = ChannelPath("SIG", ["CH1"], [(5, 5), (15, 5)], 10.0)

    assert expand_channel_path_terminals(channel_path, [(0, 0), (10, 0), (20, 0)]) is channel_path


def test_two_pad_channel_path_is_unchanged():
    channel_path = ChannelPath("SIG", ["CH1"], [(0, 0), (10, 0)], 10.0)

    assert (
        expand_channel_path_terminals(channel_path, [(0, 0), (10, 0)], enable_all_pad_tree=True)
        is channel_path
    )


def test_three_pad_fallback_routes_two_legal_edges_without_forcing():
    path = fallback_channel_path("SIG", [(0, 0), (10, 0), (20, 0)], enable_all_pad_tree=True)
    result = run_astar_pathfinding(
        ChannelMapping({"SIG": path}), _grid(), enforce_all_pad_tree=True
    )

    route = result.get_path("SIG")
    assert result.failed_nets == []
    assert route is not None
    assert route.forced_segment_count == 0
    assert (0, 0) in route.coordinates
    assert (10, 0) in route.coordinates
    assert (20, 0) in route.coordinates
    assert (
        _audit([(0, 0), (10, 0), (20, 0)], route.coordinates).disposition is NetDisposition.ROUTED
    )


def test_opt_in_terminal_plan_dispatches_branch_geometry_without_serial_bridge():
    terminals = tuple(
        ParsedTerminal(
            identity=PadIdentity("U1", str(index), "SIG", x, y, (0,)),
            center=Point(x, y),
            layer_names=("F.Cu",),
            is_pth=False,
        )
        for index, (x, y) in enumerate(((0, 0), (10, 0), (0, 10)))
    )
    path = ChannelPath(
        "SIG",
        [],
        [(0, 0), (10, 0), (0, 10)],
        20.0,
        terminal_tree=plan_terminal_tree(terminals),
        terminals=terminals,
    )

    result = run_astar_pathfinding(
        ChannelMapping({"SIG": path}), _grid(), enforce_all_pad_tree=True
    )

    assert result.failed_nets == []
    assert "SIG" not in result.routed_paths
    tree = result.tree_routes["SIG"]
    assert len(tree.branches) == 2
    assert ((10, 0, "F.Cu"), (0, 10, "F.Cu")) not in tree.iter_segments()

    compiled = compile_routing_results(result, TraceWidthAssignment({}), ViaPlacement([]))
    assert compiled.success_count == 1
    assert compiled.compiled_routes == {}
    assert compiled.tree_routes["SIG"].geometry == tree


def test_unreachable_third_terminal_is_failed_without_forced_geometry():
    grid = _grid()
    grid.grid[:, 15] = 1
    path = fallback_channel_path("SIG", [(0, 0), (10, 0), (20, 0)], enable_all_pad_tree=True)

    result = run_astar_pathfinding(
        ChannelMapping({"SIG": path}), grid, max_iter=1_000, enforce_all_pad_tree=True
    )

    assert "SIG" in result.failed_nets
    assert "SIG" not in result.routed_paths
    assert result.tree_failures["SIG"].unresolved_terminal == (20, 0)
    partial = result.partial_paths["SIG"]
    assert partial.forced_segment_count == 1
    assert (0, 0) in partial.coordinates
    assert (10, 0) in partial.coordinates
    assert (20, 0) not in partial.coordinates
    assert (
        _audit([(0, 0), (10, 0), (20, 0)], partial.coordinates).disposition
        is NetDisposition.INCOMPLETE
    )


def test_experimental_tree_3d_fallback_is_bounded_per_edge_and_fails_honestly(
    monkeypatch: pytest.MonkeyPatch,
):
    # Patch where the names are looked up. Both `_segment_search` and
    # `_route_segment_3d` are called from inside `_astar_route_multilayer`,
    # which lives in _astar_search, so that is the module whose globals the
    # lookups resolve against. Patching astar_pathfinding's re-exports does
    # not intercept them, and neither does patching _astar_reconstruct, which
    # only re-exports `_segment_search` for import-site stability.
    import temper_placer.router_v6._astar_search as search_mod

    caps: list[int] = []
    monkeypatch.setattr(search_mod, "_segment_search", lambda *_args, **_kwargs: (None, None, 0))

    def no_3d_path(*_args, max_iter: int, **_kwargs):
        caps.append(max_iter)
        return None

    monkeypatch.setattr(search_mod, "_route_segment_3d", no_3d_path)
    path = fallback_channel_path("SIG", [(0, 0), (10, 0), (20, 0)], enable_all_pad_tree=True)
    result = run_astar_pathfinding(
        ChannelMapping({"SIG": path}),
        _grid(),
        alternate_grid=OccupancyGrid(
            "B.Cu", np.zeros((30, 30), dtype=np.int8), (0, 0), 1.0, 30, 30
        ),
        enforce_all_pad_tree=True,
        tree_3d_fallback_max_iter=7,
    )

    assert caps == [7]
    assert result.tree_failures["SIG"].unresolved_terminal == (10, 0)
    assert "SIG" not in result.routed_paths


@given(st.integers(min_value=3, max_value=6))
@settings(max_examples=20, deadline=30_000)
def test_tree_3d_failure_budget_is_bounded_for_arbitrary_terminal_counts(
    terminal_count: int,
):
    # See the note in the test above: both names resolve inside
    # _astar_search, which is where they must be patched.
    import temper_placer.router_v6._astar_search as search_mod

    caps: list[int] = []
    points = [(index * 4, 0) for index in range(terminal_count)]
    path = fallback_channel_path("SIG", points, enable_all_pad_tree=True)
    with (
        patch.object(search_mod, "_segment_search", return_value=(None, None, 0)),
        patch.object(
            search_mod,
            "_route_segment_3d",
            side_effect=lambda *_args, max_iter, **_kwargs: caps.append(max_iter) or None,
        ),
    ):
        result = run_astar_pathfinding(
            ChannelMapping({"SIG": path}),
            _grid(),
            alternate_grid=OccupancyGrid(
                "B.Cu", np.zeros((30, 30), dtype=np.int8), (0, 0), 1.0, 30, 30
            ),
            enforce_all_pad_tree=True,
            tree_3d_fallback_max_iter=11,
        )

    assert caps == [11]
    assert sum(caps) <= (terminal_count - 1) * 11
    assert result.tree_failures["SIG"].unresolved_terminal == points[1]


@given(st.integers(min_value=3, max_value=6))
@settings(max_examples=20, deadline=30_000)
def test_partial_tree_geometry_never_claims_the_unreachable_terminal(terminal_count: int):
    points = [(index * 5, 0) for index in range(terminal_count)]
    grid = _grid()
    grid.grid[:, 8] = 1
    path = fallback_channel_path("SIG", points, enable_all_pad_tree=True)

    result = run_astar_pathfinding(
        ChannelMapping({"SIG": path}), grid, enforce_all_pad_tree=True, max_iter=1_000
    )

    partial = result.partial_paths["SIG"]
    assert "SIG" not in result.routed_paths
    assert points[1] in partial.coordinates
    assert points[2] not in partial.coordinates
    assert _audit(points, partial.coordinates).disposition is NetDisposition.INCOMPLETE


def test_partial_tree_geometry_is_excluded_from_routing_results_and_writer_input():
    partial = RoutePath("SIG", [(0, 0), (10, 0)], "F.Cu", 10.0, forced_segment_count=1)
    result = PathfindingResult(
        routed_paths={},
        failed_nets=["SIG"],
        partial_paths={"SIG": partial},
    )

    compiled = compile_routing_results(result, TraceWidthAssignment({}), ViaPlacement([]))

    assert compiled.get_route("SIG") is None
    assert compiled.success_count == 0
    assert compiled.failure_count == 1


@given(st.lists(st.integers(min_value=0, max_value=20), min_size=2, max_size=6, unique=True))
@settings(max_examples=30, deadline=30_000)
def test_obstacle_free_multiterminal_fallback_never_forces_and_visits_all_pads(xs):
    points = [(x, 0) for x in xs]
    path = fallback_channel_path("SIG", points, enable_all_pad_tree=True)
    result = run_astar_pathfinding(
        ChannelMapping({"SIG": path}), _grid(), enforce_all_pad_tree=True
    )

    route = result.get_path("SIG")
    assert route is not None
    assert route.forced_segment_count == 0
    assert result.failed_nets == []
    assert all(point in route.coordinates for point in sorted(points))
    assert _audit(points, route.coordinates).disposition is NetDisposition.ROUTED


@given(st.lists(st.integers(min_value=0, max_value=20), min_size=3, max_size=6, unique=True))
@settings(max_examples=30, deadline=30_000)
def test_sat_terminal_expansion_is_permutation_invariant(xs):
    pads = [(x, 0) for x in xs]
    path = ChannelPath("SIG", ["CH1"], [(5, 5), (15, 5)], 10.0)

    expanded = expand_channel_path_terminals(path, list(reversed(pads)), enable_all_pad_tree=True)

    assert expanded.waypoints[:2] == [(5, 5), (15, 5)]
    assert set(expanded.waypoints[2:]) == set(pads)
    assert expanded.waypoints[2] == min(
        pads, key=lambda pad: (abs(pad[0] - 15) + abs(pad[1] - 5), pad)
    )
