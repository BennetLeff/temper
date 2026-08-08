"""Coverage paydown tests — Wave 3 easy wins (Batch E).

Covers: power_plane CopperPour properties, resource_bound
(trivial path), tree_route_geometry.
"""

from __future__ import annotations

import numpy as np
import pytest

from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.power_plane import CopperPour, PowerPlaneGeometry
from temper_placer.router_v6.resource_bound import (
    demand_budget_summary,
    max_routable_nets,
)


# ── power_plane CopperPour ────────────────────────────────────────


def test_copper_pour_width():
    pour = CopperPour(
        net="GND",
        layer="In1.Cu",
        bounds=(10.0, 20.0, 50.0, 80.0),
    )
    assert pour.width == pytest.approx(40.0)


def test_copper_pour_height():
    pour = CopperPour(
        net="GND",
        layer="In1.Cu",
        bounds=(10.0, 20.0, 50.0, 80.0),
    )
    assert pour.height == pytest.approx(60.0)


def test_copper_pour_area():
    pour = CopperPour(
        net="GND",
        layer="In1.Cu",
        bounds=(10.0, 20.0, 50.0, 80.0),
    )
    assert pour.area == pytest.approx(2400.0)


def test_power_plane_geometry_via_count():
    ppg = PowerPlaneGeometry(
        ground_pour=CopperPour(net="GND", layer="In1.Cu", bounds=(0, 0, 100, 100)),
        power_pours=[],
        thermal_vias=[],
    )
    assert ppg.via_count == 0


# ── resource_bound ────────────────────────────────────────────────


def test_max_routable_nets_empty():
    grid = OccupancyGrid(
        "F.Cu",
        np.zeros((10, 10), dtype=np.int8),
        (0.0, 0.0),
        1.0,
        10,
        10,
    )
    result = max_routable_nets(grid, {}, 0.2)
    assert result == 0


def test_demand_budget_summary():
    summary = demand_budget_summary(
        edt_grid=OccupancyGrid(
            "F.Cu",
            np.zeros((10, 10), dtype=np.int8),
            (0.0, 0.0),
            1.0,
            10,
            10,
        ),
        net_bboxes={},
        trace_width=0.2,
    )
    assert isinstance(summary, dict)


# ── tree_route_geometry ───────────────────────────────────────────


def test_tree_route_geometry_iter_segments():
    from temper_placer.router_v6.astar_core import RoutePath
    from temper_placer.router_v6.connectivity import PadIdentity
    from temper_placer.router_v6.tree_route_geometry import TreeRouteBranch, TreeRouteGeometry
    from temper_placer.router_v6.terminal_tree import TerminalTreeEdge
    src = PadIdentity("C1", "1", "N1", 0.0, 0.0, (0,))
    tgt = PadIdentity("C1", "2", "N1", 10.0, 10.0, (0,))
    edge = TerminalTreeEdge(source=src, target=tgt)
    path = RoutePath("N1", [(0, 0), (10, 10)], "F.Cu", 14.14)
    branch = TreeRouteBranch(edge=edge, path=path)
    trg = TreeRouteGeometry(net_name="N1", branches=(branch,))
    segments = trg.iter_segments()
    assert len(segments) > 0


def test_tree_route_geometry_via_positions_empty():
    from temper_placer.router_v6.astar_core import RoutePath
    from temper_placer.router_v6.connectivity import PadIdentity
    from temper_placer.router_v6.tree_route_geometry import TreeRouteBranch, TreeRouteGeometry
    from temper_placer.router_v6.terminal_tree import TerminalTreeEdge
    src = PadIdentity("C1", "1", "N1", 0.0, 0.0, (0,))
    tgt = PadIdentity("C1", "2", "N1", 10.0, 10.0, (0,))
    edge = TerminalTreeEdge(source=src, target=tgt)
    path = RoutePath("N1", [(0, 0), (10, 10)], "F.Cu", 14.14)
    branch = TreeRouteBranch(edge=edge, path=path)
    trg = TreeRouteGeometry(net_name="N1", branches=(branch,))
    assert trg.via_positions == ()
