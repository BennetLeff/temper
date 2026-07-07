"""
U6: Netclass-aware obstacle-grid pre-inflation tests.

Tests for ``inflate_obstacles_by_netclass``, ``clear_netclass_inflation``,
and ``populate_clearance_matrix_from_rules``.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from temper_placer.router_v6.constraints_design_rules import ClearanceMatrix
from temper_placer.router_v6.netclass_inflation import (
    clear_netclass_inflation,
    inflate_obstacles_by_netclass,
    populate_clearance_matrix_from_rules,
)
from temper_placer.router_v6.occupancy_grid import OccupancyGrid


def _make_grid(height: int, width: int, cell_size: float = 0.1) -> OccupancyGrid:
    """Create a simple free OccupancyGrid for testing."""
    g = np.zeros((height, width), dtype=np.int8)
    return OccupancyGrid(
        layer_name="F.Cu",
        grid=g,
        origin=(0.0, 0.0),
        cell_size=cell_size,
        width_cells=width,
        height_cells=height,
    )


# ---------------------------------------------------------------------------
# Test 1: Inflation — cell at centre, HV net with 6.0 mm clearance
# ---------------------------------------------------------------------------


def test_inflation_marks_cells_within_clearance_radius():
    """Signal net at (10, 10) — inflating for HV net at 6.0mm clearance."""
    grid = _make_grid(21, 21, cell_size=1.0)  # 1 mm cells for easy arithmetic
    grid.grid[10, 10] = 1  # signal_net occupies centre

    matrix = ClearanceMatrix()
    matrix.set_net_class("signal_net", "Signal")
    matrix.set_net_class("hv_net", "HighVoltage")
    matrix.set_class_to_class_clearance("Signal", "HighVoltage", 6.0)

    id_to_net = {1: "signal_net"}

    inflate_obstacles_by_netclass(
        grid, "hv_net", id_to_net, matrix, grid_cell_size=1.0,
    )

    # Radius = ceil(6.0 / 1.0) = 6 cells.  The centre cell (10,10) was
    # already occupied (>0) so it is NOT overwritten.  Free cells within
    # the 6-cell radius receive sentinel -2.
    sentinel_count = int(np.sum(grid.grid == -2))
    expected_radius_area = (2 * 6 + 1) ** 2 - 1  # exclude centre cell
    assert sentinel_count == expected_radius_area, (
        f"Expected {expected_radius_area} sentinel cells, got {sentinel_count}"
    )

    # Centre cell should still be 1 (not overwritten by sentinel)
    assert grid.grid[10, 10] == 1

    # A cell just outside radius should still be free
    assert grid.grid[3, 10] == 0  # 7 cells away, radius=6


def test_clear_inflation_restores_grid():
    """clear_netclass_inflation returns sentinel cells to free."""
    grid = _make_grid(21, 21, cell_size=1.0)
    grid.grid[10, 10] = 1

    matrix = ClearanceMatrix()
    matrix.set_net_class("signal_net", "Signal")
    matrix.set_net_class("hv_net", "HighVoltage")
    matrix.set_class_to_class_clearance("Signal", "HighVoltage", 6.0)

    id_to_net = {1: "signal_net"}

    inflate_obstacles_by_netclass(grid, "hv_net", id_to_net, matrix, 1.0)
    clear_netclass_inflation(grid)

    # All sentinel cells should be back to 0
    assert np.all(grid.grid != -2)
    # Centre cell still 1
    assert grid.grid[10, 10] == 1


# ---------------------------------------------------------------------------
# Test 2: Same-class skip — Signal → Signal, no extra inflation
# ---------------------------------------------------------------------------


def test_same_class_no_inflation():
    """Two Signal nets — inflation should be skipped (self-clearance handled)."""
    grid = _make_grid(21, 21, cell_size=1.0)
    grid.grid[10, 10] = 1  # signal_a occupies centre

    matrix = ClearanceMatrix()
    matrix.set_net_class("signal_a", "Signal")
    matrix.set_net_class("signal_b", "Signal")
    matrix.set_class_to_class_clearance("Signal", "Signal", 0.15)

    id_to_net = {1: "signal_a"}

    inflate_obstacles_by_netclass(
        grid, "signal_b", id_to_net, matrix, grid_cell_size=1.0,
    )

    # No sentinel cells should be created (same class, skip)
    assert np.all(grid.grid != -2)
    assert grid.grid[10, 10] == 1  # centre unchanged


def test_same_net_skip():
    """Inflation skips cells belonging to the CURRENT net (own cells allowed)."""
    grid = _make_grid(21, 21, cell_size=1.0)
    grid.grid[10, 10] = 1  # hv_net's own cell

    matrix = ClearanceMatrix()
    matrix.set_net_class("hv_net", "HighVoltage")
    id_to_net = {1: "hv_net"}

    inflate_obstacles_by_netclass(
        grid, "hv_net", id_to_net, matrix, grid_cell_size=1.0,
    )

    # Same net → no inflation
    assert np.all(grid.grid != -2)


def test_different_class_same_nets_inflates():
    """Same net name but different classes — inflation should apply."""
    grid = _make_grid(21, 21, cell_size=1.0)
    grid.grid[10, 10] = 1  # net_a

    matrix = ClearanceMatrix()
    matrix.set_net_class("net_a", "Signal")          # already-routed
    matrix.set_net_class("current_net", "HighVoltage")  # current
    matrix.set_class_to_class_clearance("Signal", "HighVoltage", 5.0)

    id_to_net = {1: "net_a"}

    inflate_obstacles_by_netclass(
        grid, "current_net", id_to_net, matrix, grid_cell_size=1.0,
    )

    sentinel_count = int(np.sum(grid.grid == -2))
    assert sentinel_count > 0, "Different class should inflate"


# ---------------------------------------------------------------------------
# Test 3: Clearance lookup from YAML-populated matrix
# ---------------------------------------------------------------------------


def _netclass_rules_path() -> Path:
    """Auto-discover netclass_rules.yaml."""
    import temper_placer
    pkg_root = Path(temper_placer.__file__).resolve().parent.parent.parent
    return pkg_root / "configs" / "netclass_rules.yaml"


@pytest.mark.skipif(
    not _netclass_rules_path().exists(),
    reason="netclass_rules.yaml not found (run from repo root)",
)
def test_get_clearance_from_yaml_populated_matrix():
    """ClearanceMatrix.get_clearance returns YAML values after population."""
    from temper_placer.core.netclass_rules import load_netclass_rules

    rules_path = _netclass_rules_path()
    rules = load_netclass_rules(rules_path)

    matrix = ClearanceMatrix()
    populate_clearance_matrix_from_rules(matrix, rules)

    # Set net classes so get_clearance can resolve
    matrix.set_net_class("HV_net", "HighVoltage")
    matrix.set_net_class("signal_net", "Signal")

    clearance = matrix.get_clearance("HV_net", "signal_net")
    assert clearance == 6.0, f"Expected 6.0mm, got {clearance}mm"


@pytest.mark.skipif(
    not _netclass_rules_path().exists(),
    reason="netclass_rules.yaml not found (run from repo root)",
)
def test_get_clearance_same_class_defaults_to_self_clearance():
    """Same-class pair returns self-clearance from YAML."""
    from temper_placer.core.netclass_rules import load_netclass_rules

    rules_path = _netclass_rules_path()
    rules = load_netclass_rules(rules_path)

    matrix = ClearanceMatrix()
    populate_clearance_matrix_from_rules(matrix, rules)

    matrix.set_net_class("sig_a", "Signal")
    matrix.set_net_class("sig_b", "Signal")

    clearance = matrix.get_clearance("sig_a", "sig_b")
    assert clearance == 0.15, f"Signal self-clearance should be 0.15, got {clearance}"


# ---------------------------------------------------------------------------
# Test 4: Edge cases
# ---------------------------------------------------------------------------


def test_empty_grid_no_inflation():
    """Empty grid — inflation is a no-op."""
    grid = _make_grid(5, 5)

    matrix = ClearanceMatrix()
    matrix.set_net_class("hv_net", "HighVoltage")

    inflate_obstacles_by_netclass(
        grid, "hv_net", {}, matrix, grid_cell_size=0.1,
    )

    assert np.all(grid.grid == 0)


def test_inflation_respects_grid_bounds():
    """Inflation does not extend beyond grid edges."""
    grid = _make_grid(10, 10, cell_size=1.0)
    grid.grid[0, 0] = 1  # corner cell

    matrix = ClearanceMatrix()
    matrix.set_net_class("signal_net", "Signal")
    matrix.set_net_class("hv_net", "HighVoltage")
    matrix.set_class_to_class_clearance("Signal", "HighVoltage", 100.0)  # huge

    id_to_net = {1: "signal_net"}

    inflate_obstacles_by_netclass(
        grid, "hv_net", id_to_net, matrix, grid_cell_size=1.0,
    )

    sentinel_positions = np.where(grid.grid == -2)
    ys, xs = sentinel_positions
    assert np.all(ys >= 0) and np.all(ys < 10)
    assert np.all(xs >= 0) and np.all(xs < 10)


def test_inflation_does_not_overwrite_static_obstacles():
    """Sentinel cells (-2) do not overwrite static obstacles (-1)."""
    grid = _make_grid(21, 21, cell_size=1.0)
    grid.grid[10, 10] = 1   # net cell
    grid.grid[9, 10] = -1   # static obstacle adjacent
    grid.grid[10, 9] = -1   # static obstacle adjacent

    matrix = ClearanceMatrix()
    matrix.set_net_class("signal_net", "Signal")
    matrix.set_net_class("hv_net", "HighVoltage")
    matrix.set_class_to_class_clearance("Signal", "HighVoltage", 10.0)

    id_to_net = {1: "signal_net"}

    inflate_obstacles_by_netclass(
        grid, "hv_net", id_to_net, matrix, grid_cell_size=1.0,
    )

    # Static obstacles are preserved
    assert grid.grid[9, 10] == -1
    assert grid.grid[10, 9] == -1


def test_populate_clearance_matrix_from_rules():
    """Population sets per-class rules and cross-class pair clearances."""
    from temper_placer.core.netclass_rules import NetClassRulesDict

    rules: NetClassRulesDict = {
        "net_classes": {},
        "pair_clearances": {
            ("HighVoltage", "Signal"): 6.0,
            ("Power", "Signal"): 0.25,
        },
        "default_clearance_mm": 0.2,
        "because": {},
    }

    matrix = ClearanceMatrix()
    populate_clearance_matrix_from_rules(matrix, rules)

    matrix.set_net_class("hv1", "HighVoltage")
    matrix.set_net_class("sig1", "Signal")

    assert matrix.get_clearance("hv1", "sig1") == 6.0

    # Unlisted pair falls back to max self-clearance → default 0.2
    clearance = matrix.get_clearance("sig1", "sig1")
    assert clearance == 0.2  # self-clearance = default (no NetClassRules loaded)
