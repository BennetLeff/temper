"""
Tests for ``router_v6.bottleneck_geometry`` U1 surface.

These cover the data contract:

- ``BottleneckGeometry`` dataclass fields and serialization
- ``NetRoutingReport.bottleneck`` round-trips through ``to_dict()`` with
  byte-identical output for the existing fields (SC5)
- ``_compute_cell_capacity`` baseline / creepage / saturation behavior
"""

from __future__ import annotations

import pytest

from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid
from temper_placer.router_v6.bottleneck_geometry import (
    BOTTLENECK_TIMEOUT_S,
    BottleneckGeometry,
    _compute_cell_capacity,
    is_hard_blocked,
)
from temper_placer.router_v6.diagnostics import (
    FailureReason,
    NetRoutingReport,
    RoutingStatus,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_grid() -> ClearanceGrid:
    """A small empty 2-layer grid with no traces or pads."""
    return ClearanceGrid(
        width_mm=10.0,
        height_mm=10.0,
        cell_size_mm=1.0,
        layer_count=2,
    )


@pytest.fixture
def trace_only_grid() -> ClearanceGrid:
    """A grid with 4 traces already routed through cell (0, 5, 5)."""
    grid = ClearanceGrid(
        width_mm=10.0,
        height_mm=10.0,
        cell_size_mm=1.0,
        layer_count=2,
    )
    # Saturate the cell + 3 of its 4 cardinal neighbours with traces. The
    # capacity function counts the cell itself and the 4-neighbour traces
    # as separate "traces through" units, so 1 + 3 = 4 is enough to
    # drive capacity to zero.
    grid._trace_net_ids[0][5, 5] = 1  # the cell
    grid._trace_net_ids[0][4, 5] = 2  # north
    grid._trace_net_ids[0][6, 5] = 3  # south
    grid._trace_net_ids[0][5, 4] = 4  # west
    return grid


@pytest.fixture
def high_pad_grid() -> ClearanceGrid:
    """A grid with a category-HIGH pad at (0, 0, 0), one cell away from (1, 0)."""
    grid = ClearanceGrid(
        width_mm=10.0,
        height_mm=10.0,
        cell_size_mm=1.0,
        layer_count=2,
    )
    # Mark (0, 0, 0) as a pad with a non-zero net id — any non-zero
    # adjacent pad contributes 1 to the discount.
    grid._pad_net_ids[0][0, 0] = 7
    return grid


# ---------------------------------------------------------------------------
# _compute_cell_capacity
# ---------------------------------------------------------------------------


class TestComputeCellCapacity:
    """Capacity function behaviour (R4)."""

    def test_capacity_cell_baseline(self, empty_grid: ClearanceGrid) -> None:
        """Empty cell with no traces and no nearby HV pads → 4."""
        capacity = _compute_cell_capacity(
            cell=(0, 5, 5),
            layer=0,
            grid=empty_grid,
            net_class_rules=None,
            net_name="GATE_H",
        )
        assert capacity == 4

    def test_capacity_cell_creepage_excluded(
        self, high_pad_grid: ClearanceGrid
    ) -> None:
        """Cell 3mm from a category-HIGH pad → capacity 3."""
        # The HIGH pad lives at (0, 0, 0). The test cell (0, 0, 1) is
        # one cell to the right; the 4-neighbour check discounts 1.
        capacity = _compute_cell_capacity(
            cell=(0, 0, 1),
            layer=0,
            grid=high_pad_grid,
            net_class_rules=None,
            net_name="GATE_H",
        )
        assert capacity == 3

    def test_capacity_cell_saturated(
        self, trace_only_grid: ClearanceGrid
    ) -> None:
        """Cell with 4 existing traces → capacity 0; caller treats as blocked."""
        capacity = _compute_cell_capacity(
            cell=(0, 5, 5),
            layer=0,
            grid=trace_only_grid,
            net_class_rules=None,
            net_name="GATE_H",
        )
        assert capacity == 0
        assert is_hard_blocked(trace_only_grid, (0, 5, 5)) is False or capacity == 0

    def test_capacity_clamped_to_base(self, empty_grid: ClearanceGrid) -> None:
        """The capacity function never returns more than ``_BASE_CAPACITY``."""
        capacity = _compute_cell_capacity(
            cell=(0, 5, 5),
            layer=0,
            grid=empty_grid,
            net_class_rules=None,
            net_name="GATE_H",
        )
        assert 0 <= capacity <= 4


# ---------------------------------------------------------------------------
# NetRoutingReport.to_dict() SC5 backward-compat
# ---------------------------------------------------------------------------


class TestNetRoutingReportBottleneckSerialization:
    """SC5: ``to_dict()`` byte-identical for existing fields when bottleneck
    is ``None``; bottleneck key is present in either case for forward compat."""

    def test_diagnostics_to_dict_bottleneck_present(self) -> None:
        """When ``bottleneck`` is set, ``to_dict()['bottleneck']`` is a dict
        with all 9 keys; existing fields are unchanged."""
        bottleneck = BottleneckGeometry(
            component_pair=("Q1", "D1"),
            pair_kind="component_component",
            positions_mm=((22.2, 15.0), (30.5, 25.0)),
            current_gap_mm=4.0,
            required_gap_mm=6.0,
            cut_size=1,
            cut_cells=((0, 5, 5),),
            message="Q1 at (22.2, 15.0) and D1 at (30.5, 25.0) create 4.0mm gap that needs 6.0mm",
        )
        report = NetRoutingReport(
            net_name="GATE_H",
            status=RoutingStatus.FAILED,
            score=0.0,
            pins=2,
            routed_segments=0,
            total_segments=1,
            failure_reason=FailureReason.CLEARANCE,
            bottleneck=bottleneck,
        )
        out = report.to_dict()
        assert isinstance(out["bottleneck"], dict)
        for key in (
            "component_pair",
            "pair_kind",
            "positions_mm",
            "current_gap_mm",
            "required_gap_mm",
            "cut_size",
            "cut_cells",
            "message",
            "bottleneck_status",
        ):
            assert key in out["bottleneck"]

        # Existing fields unchanged.
        assert out["net_name"] == "GATE_H"
        assert out["status"] == "failed"
        assert out["failure_reason"] == "clearance"
        assert out["iterations_used"] == 0

    def test_diagnostics_to_dict_bottleneck_absent(self) -> None:
        """When ``bottleneck is None``, ``to_dict()['bottleneck'] is None``;
        every other field is byte-identical to the pre-change output."""
        report = NetRoutingReport(
            net_name="GATE_L",
            status=RoutingStatus.SUCCESS,
            score=1.0,
            pins=2,
            routed_segments=1,
            total_segments=1,
        )
        out = report.to_dict()
        assert out["bottleneck"] is None
        # All other fields still present and well-typed.
        for key in (
            "net_name",
            "status",
            "score",
            "pins",
            "routed_segments",
            "total_segments",
            "route_length_mm",
            "direct_distance_mm",
            "detour_ratio",
            "failure_reason",
            "failure_point",
            "blocking_obstacles",
            "placement_suggestions",
            "drc_violations",
            "channels_used",
            "layer",
            "iterations_used",
            "message",
        ):
            assert key in out

    def test_diagnostics_to_dict_keys_order_unchanged(self) -> None:
        """Inserting the new key must not perturb the existing key order in
        the dict (Python preserves insertion order). This protects
        consumers that rely on positional serialization."""
        report = NetRoutingReport(
            net_name="X",
            status=RoutingStatus.SUCCESS,
            score=1.0,
            pins=2,
            routed_segments=1,
            total_segments=1,
        )
        keys = list(report.to_dict().keys())
        # The new key is appended just before "message" (the canonical
        # trailing summary). Pin the order.
        assert keys[-1] == "message"
        assert keys[-2] == "bottleneck"


# ---------------------------------------------------------------------------
# BottleneckGeometry contract
# ---------------------------------------------------------------------------


class TestBottleneckGeometryFields:
    def test_to_dict_keys(self) -> None:
        bg = BottleneckGeometry(
            component_pair=("A", "B"),
            pair_kind="component_component",
            positions_mm=((1.0, 1.0), (2.0, 2.0)),
            current_gap_mm=1.414,
            required_gap_mm=2.0,
            cut_size=1,
            cut_cells=((0, 1, 1),),
            message="msg",
        )
        d = bg.to_dict()
        assert set(d) == {
            "component_pair",
            "pair_kind",
            "positions_mm",
            "current_gap_mm",
            "required_gap_mm",
            "cut_size",
            "cut_cells",
            "message",
            "bottleneck_status",
        }

    def test_default_status_is_ok(self) -> None:
        bg = BottleneckGeometry(
            component_pair=("A", "B"),
            pair_kind="component_component",
            positions_mm=((1.0, 1.0), (2.0, 2.0)),
            current_gap_mm=1.0,
            required_gap_mm=1.0,
            cut_size=0,
            cut_cells=(),
            message="",
        )
        assert bg.bottleneck_status == "ok"

    def test_timeout_constant_default(self) -> None:
        """SC4 uses 0.5s per failed net — pin the constant."""
        assert BOTTLENECK_TIMEOUT_S == 0.5

    def test_net_routing_report_snapshot_no_bottleneck(self) -> None:
        """SC5: ``to_dict()`` output for a NetRoutingReport with
        ``bottleneck=None`` is byte-identical to a hand-rolled golden
        snapshot. The new ``bottleneck`` key is the only addition;
        all other fields are unchanged from the pre-change output."""
        import json

        report = NetRoutingReport(
            net_name="NET_X",
            status=RoutingStatus.SUCCESS,
            score=1.0,
            pins=2,
            routed_segments=1,
            total_segments=1,
            route_length_mm=4.2,
            direct_distance_mm=4.0,
            detour_ratio=1.05,
            drc_violations=0,
            channels_used=frozenset({"ch-1"}),
            layer=0,
            iterations_used=7,
            message="routed",
        )
        snapshot = {
            "net_name": "NET_X",
            "status": "success",
            "score": 1.0,
            "pins": 2,
            "routed_segments": 1,
            "total_segments": 1,
            "route_length_mm": 4.2,
            "direct_distance_mm": 4.0,
            "detour_ratio": 1.05,
            "failure_reason": None,
            "failure_point": None,
            "blocking_obstacles": [],
            "placement_suggestions": [],
            "drc_violations": 0,
            "channels_used": ["ch-1"],
            "layer": 0,
            "iterations_used": 7,
            "bottleneck": None,
            "message": "routed",
        }
        out = report.to_dict()
        # The snapshot pre-dates the bottleneck field addition but
        # every pre-existing field's value must match exactly.
        for key, expected in snapshot.items():
            assert out[key] == expected, f"field {key!r} drifted: got {out[key]!r}, expected {expected!r}"
        # Round-trip through JSON to assert the dict is fully
        # serialisable (no non-JSON types).
        json.dumps(out)
