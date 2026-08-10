"""Coverage paydown tests — Wave 4 router_v6 gaps (Batch G).

Covers: congestion Bottleneck.to_coordinates, CongestionGrid.get_overflow,
CongestionGrid.get_utilization, CongestionResult properties,
test_boards TestBoard properties, constraint_model dataclass properties.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from temper_placer.router_v6.congestion import (
    Bottleneck,
    CongestionGrid,
    CongestionResult,
)
from temper_placer.router_v6.constraints_spatial_index import (
    Track,
    Via,
)
from temper_placer.router_v6.test_boards import (
    TestBoard,
    get_available_boards,
    get_board_by_name,
    print_test_suite_status,
)


# =============================================================================
#  Congestion helpers
# =============================================================================


def _make_grid(width_cells=10, height_cells=10):
    """Create a small CongestionGrid for testing."""
    demand = np.zeros((height_cells, width_cells), dtype=np.float64)
    supply = np.ones((height_cells, width_cells), dtype=np.float64) * 10.0
    return CongestionGrid(
        demand=demand,
        supply=supply,
        cell_size_mm=1.0,
        width_cells=width_cells,
        height_cells=height_cells,
    )


# =============================================================================
#  Bottleneck.to_coordinates
# =============================================================================


class TestBottleneck:
    """Tests for congestion.Bottleneck."""

    def test_to_coordinates_default_origin(self):
        bn = Bottleneck(x=3, y=4, utilization=1.5, overflow=0.5)
        cx, cy = bn.to_coordinates(cell_size_mm=1.0, origin=(0.0, 0.0))
        # Center of cell (3,4) with cell_size 1.0 at origin
        assert cx == pytest.approx(3.5)
        assert cy == pytest.approx(4.5)

    def test_to_coordinates_with_offset(self):
        bn = Bottleneck(x=0, y=0, utilization=2.0, overflow=1.0)
        cx, cy = bn.to_coordinates(cell_size_mm=2.0, origin=(10.0, 20.0))
        # Center of cell (0,0) with offset
        assert cx == pytest.approx(11.0)  # 10 + 0*2 + 1
        assert cy == pytest.approx(21.0)  # 20 + 0*2 + 1

    def test_to_coordinates_with_layer(self):
        bn = Bottleneck(x=5, y=5, utilization=0.8, overflow=0.0, layer=2)
        cx, cy = bn.to_coordinates(cell_size_mm=0.5)
        assert cx == pytest.approx(2.75)  # 0 + 5*0.5 + 0.25
        assert cy == pytest.approx(2.75)


# =============================================================================
#  CongestionGrid methods
# =============================================================================


class TestCongestionGrid:
    """Tests for CongestionGrid methods."""

    def test_get_utilization_zeros(self):
        grid = _make_grid(5, 5)
        util = grid.get_utilization()
        assert util.shape == (5, 5)
        # Zero demand / 10 supply = 0 utilization
        assert np.allclose(util, 0.0)

    def test_get_utilization_some_demand(self):
        grid = _make_grid(3, 3)
        grid.demand[1, 1] = 5.0
        util = grid.get_utilization()
        assert util[1, 1] == pytest.approx(0.5)

    def test_get_overflow_zeros(self):
        grid = _make_grid(5, 5)
        overflow = grid.get_overflow()
        assert overflow.shape == (5, 5)
        assert np.allclose(overflow, 0.0)

    def test_get_overflow_some(self):
        grid = _make_grid(3, 3)
        grid.demand[0, 0] = 15.0  # supply=10, overflow=5
        overflow = grid.get_overflow()
        assert overflow[0, 0] == pytest.approx(5.0)


# =============================================================================
#  CongestionResult
# =============================================================================


class TestCongestionResult:
    """Tests for CongestionResult properties and methods."""

    def test_is_feasible_below_threshold(self):
        grid = _make_grid(5, 5)
        result = CongestionResult(grid=grid, max_utilization=0.5)
        assert result.is_feasible() is True
        assert result.is_feasible(threshold=1.0) is True

    def test_is_feasible_above_threshold(self):
        grid = _make_grid(5, 5)
        result = CongestionResult(grid=grid, max_utilization=1.5)
        assert result.is_feasible() is False

    def test_overflow_ratio_zero(self):
        grid = _make_grid(5, 5)
        result = CongestionResult(grid=grid, total_overflow=0.0)
        ratio = result.overflow_ratio()
        assert ratio == pytest.approx(0.0)

    def test_get_top_bottlenecks_empty(self):
        grid = _make_grid(5, 5)
        result = CongestionResult(grid=grid, bottlenecks=[])
        top = result.get_top_bottlenecks(5)
        assert top == []

    def test_get_top_bottlenecks_single(self):
        grid = _make_grid(5, 5)
        bn = Bottleneck(x=1, y=2, utilization=0.5, overflow=0.0)
        result = CongestionResult(grid=grid, bottlenecks=[bn])
        top = result.get_top_bottlenecks(1)
        assert len(top) == 1
        assert top[0].x == 1
        assert top[0].y == 2


# =============================================================================
#  Constraint model dataclasses — skipped (require heavy fixtures)
#
#  ConstraintModel / CapacityConstraint / DiffPairConstraint / LayerConstraint
#  all require real routing data (net indices, channel IDs, capacity values,
#  variable references) that can't be constructed meaningfully in isolation.
#  These are legitimately in the "needs heavy fixture" category.
# =============================================================================


# =============================================================================
#  Constraints spatial index — additional edge cases
# =============================================================================


class TestSpatialIndexEdgeCases:
    """Edge cases for spatial index dataclasses not covered in wave3_f."""

    def test_track_is_diff_pair_with_false(self):
        t1 = Track(
            start=(0, 0), end=(1, 1), width=0.2, net="N1", layer=0,
        )
        t2 = Track(
            start=(0, 0), end=(1, 1), width=0.2, net="N2", layer=0,
        )
        assert t1.is_diff_pair_with(t2) is False

    def test_track_is_diff_pair_with_none_companion(self):
        t = Track(
            start=(0, 0), end=(1, 1), width=0.2, net="N1", layer=0,
            diff_pair_companion=None,
        )
        other = Track(
            start=(0, 0), end=(1, 1), width=0.2, net="N1", layer=0,
        )
        assert t.is_diff_pair_with(other) is False

    def test_via_conductive_layers_legacy(self):
        via = Via(center=(0, 0), diameter=0.6, drill=0.3, net="N1")
        assert via.conductive_layers({0, 1, 2, 3}) == frozenset({0, 1, 2, 3})

    def test_track_to_segment(self):
        from temper_placer.router_v6.constraints_geometry import Point
        t = Track(
            start=Point(0, 0), end=Point(3, 4), width=0.2, net="N1", layer=0,
        )
        seg = t.to_segment()
        assert seg.length == pytest.approx(5.0)

    def test_track_midpoint(self):
        from temper_placer.router_v6.constraints_geometry import Point
        t = Track(
            start=Point(0, 0), end=Point(10, 20), width=0.2, net="N1", layer=0,
        )
        mp = t.midpoint()
        assert mp.x == pytest.approx(5.0)
        assert mp.y == pytest.approx(10.0)


# =============================================================================
#  TestBoard / test_boards functions
# =============================================================================


class TestTestBoards:
    """Tests for test_boards module functions."""

    def test_test_board_exists_false_for_missing(self):
        tb = TestBoard(
            name="fake",
            path=Path("/nonexistent/path/fake.kicad_pcb"),
            domain="digital",
            layers=2,
            expected_net_count=10,
            description="Fake board",
            source="test",
            license="MIT",
        )
        assert tb.exists() is False

    def test_test_board_exists_true(self, tmp_path):
        pcb_file = tmp_path / "test.kicad_pcb"
        pcb_file.write_text("(kicad_pcb (version 20240101))")
        tb = TestBoard(
            name="temp",
            path=pcb_file,
            domain="digital",
            layers=2,
            expected_net_count=1,
            description="Temp board",
            source="test",
            license="MIT",
        )
        assert tb.exists() is True

    def test_get_board_by_name_nonexistent(self):
        assert get_board_by_name("__nonexistent_board_xyz__") is None

    def test_get_available_boards_returns_list(self):
        boards = get_available_boards()
        assert isinstance(boards, list)

    def test_print_test_suite_status_does_not_crash(self):
        """Smoke test: print_test_suite_status should not raise."""
        print_test_suite_status()
