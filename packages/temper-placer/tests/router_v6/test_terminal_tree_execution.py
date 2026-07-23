"""Synthetic execution of a planned terminal tree through existing A*."""

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.astar_pathfinding import _segment_search
from temper_placer.router_v6.connectivity import (
    CopperPad,
    CopperTrack,
    NetDisposition,
    PadIdentity,
    verify_net_connectivity,
)
from temper_placer.router_v6.constraints_geometry import Point
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.terminal_tree import plan_terminal_tree
from temper_placer.router_v6.terminal_tree_execution import execute_terminal_tree


def _pad(index: int, x: int, y: int = 0) -> CopperPad:
    return CopperPad(PadIdentity("U1", str(index), "NET", x, y, (0,)), Point(x, y), "rect", (1, 1))


def _grid() -> OccupancyGrid:
    return OccupancyGrid("F.Cu", np.zeros((30, 30), dtype=np.int8), (0, 0), 1.0, 30, 30)


def test_executor_routes_each_prim_edge_and_preserves_edge_geometry():
    pads = [_pad(1, 0), _pad(2, 10), _pad(3, 0, 10)]
    result = execute_terminal_tree(plan_terminal_tree(pads), pads, _grid())

    assert result.disposition is NetDisposition.ROUTED
    assert len(result.completed_edges) == 2
    assert len(result.failed_edges) == 0
    assert all(path.forced_segment_count == 0 for _edge, path in result.completed_edges)
    tracks = [
        CopperTrack(Point(*start), Point(*end), layer=0)
        for _edge, path in result.completed_edges
        for start, end in zip(path.coordinates, path.coordinates[1:])
    ]
    assert verify_net_connectivity(pads, tracks, []).disposition is NetDisposition.ROUTED


def test_executor_stops_at_first_unreachable_planned_target_without_direct_segment():
    pads = [_pad(1, 0), _pad(2, 10), _pad(3, 20)]
    grid = _grid()
    grid.grid[:, 15] = 1
    plan = plan_terminal_tree(pads)

    result = execute_terminal_tree(plan, pads, grid, max_iter=1_000)

    assert result.disposition is NetDisposition.INCOMPLETE
    assert len(result.failed_edges) >= 1
    assert result.failed_edges[0].target == pads[2].identity
    assert len(result.completed_edges) == 1
    assert all(path.forced_segment_count == 0 for _edge, path in result.completed_edges)


def test_executor_reserves_each_edge_for_same_net_attachment_but_not_other_nets():
    pads = [_pad(1, 0), _pad(2, 10), _pad(3, 20)]
    grid = _grid()

    result = execute_terminal_tree(
        plan_terminal_tree(pads),
        pads,
        grid,
        net_id=7,
        trace_width=2.0,
        clearance=1.0,
    )

    assert result.disposition is NetDisposition.ROUTED
    assert len(result.completed_edges) == 2
    assert (grid.grid == 7).any()

    blocked = _grid()
    blocked.grid[:, 15] = 8
    result = execute_terminal_tree(
        plan_terminal_tree(pads),
        pads,
        blocked,
        net_id=7,
        trace_width=2.0,
        clearance=1.0,
        max_iter=1_000,
    )
    assert result.disposition is NetDisposition.INCOMPLETE
    assert len(result.failed_edges) >= 1


@given(st.integers(min_value=3, max_value=20))
@settings(max_examples=20, deadline=30_000)
def test_owned_cells_are_deterministically_traversable_while_foreign_cells_are_not(width: int):
    own_grid = OccupancyGrid("F.Cu", np.full((4, width), 7, dtype=np.int8), (0, 0), 1.0, width, 4)
    own_first, _, _ = _segment_search(own_grid, (0, 1), (width - 1, 1), False, False, net_id=7)
    own_second, _, _ = _segment_search(own_grid, (0, 1), (width - 1, 1), False, False, net_id=7)
    foreign_grid = OccupancyGrid(
        "F.Cu", np.full((4, width), 8, dtype=np.int8), (0, 0), 1.0, width, 4
    )
    foreign_path, _, _ = _segment_search(
        foreign_grid, (0, 1), (width - 1, 1), False, False, net_id=7
    )

    assert own_first == own_second
    assert own_first is not None
    assert foreign_path is None


@given(st.lists(st.integers(min_value=0, max_value=20), min_size=2, max_size=6, unique=True))
@settings(max_examples=30, deadline=30_000)
def test_executor_connects_arbitrary_obstacle_free_terminal_trees(xs):
    pads = [_pad(index, x) for index, x in enumerate(xs)]
    plan = plan_terminal_tree(pads)

    result = execute_terminal_tree(plan, pads, _grid())

    assert result.disposition is NetDisposition.ROUTED
    assert len(result.completed_edges) == len(pads) - 1
    assert all(path.forced_segment_count == 0 for _edge, path in result.completed_edges)
