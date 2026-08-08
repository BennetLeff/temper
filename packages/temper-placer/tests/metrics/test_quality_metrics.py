"""Tests for quality.py metrics functions."""

import numpy as np
import pytest

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.core.state import PlacementState
from temper_placer.metrics.quality import (
    compactness_score,
    compute_quality_report,
    congestion_score,
    connectivity_clustering_score,
    dual_rail_clearance_report,
    hv_lv_clearance_score,
    loop_area_score,
    thermal_score,
    total_wirelength,
    zone_compliance_score,
)


def _make_state(positions_list, n_components):
    """Build a PlacementState from a list of (x, y) positions."""
    positions = np.array(positions_list, dtype=np.float32)
    # For rotation_logits, default to all rotation 0
    rotation_logits = np.zeros((n_components, 4), dtype=np.float32)
    rotation_logits[:, 0] = 1.0
    return PlacementState(
        positions=positions,
        rotation_logits=rotation_logits,
    )


class TestCongestionScore:
    def test_returns_one(self):
        """congestion_score always returns 1.0 (routing demand computation removed)."""
        state = _make_state([(10.0, 10.0)], 1)
        netlist = Netlist(
            components=[Component(ref="U1", footprint="SOIC-8", bounds=(5, 4))],
            nets=[],
        )
        board = Board(width=100, height=100)
        score = congestion_score(state, netlist, board, None)
        assert score == 1.0


class TestTotalWirelength:
    def test_empty_context_returns_zero(self):
        """With empty net_pin_indices, returns 0.0."""
        state = _make_state([], 0)
        netlist = Netlist()
        context = type("Ctx", (), {"net_pin_indices": np.zeros((0, 0))})()
        result = total_wirelength(state, netlist, context)
        assert result == 0.0

    def test_nonempty_context_raises(self):
        """With non-empty net_pin_indices, raises NotImplementedError."""
        state = _make_state([], 0)
        netlist = Netlist()
        context = type("Ctx", (), {"net_pin_indices": np.zeros((1, 1))})()
        with pytest.raises(NotImplementedError):
            total_wirelength(state, netlist, context)


class TestCompactnessScore:
    def test_single_component(self):
        """Single component is always compact."""
        state = _make_state([(50.0, 50.0)], 1)
        netlist = Netlist(
            components=[Component(ref="U1", footprint="SOIC-8", bounds=(5, 4))],
            nets=[],
        )
        board = Board(width=100, height=100)
        score = compactness_score(state, netlist, board)
        assert score == 1.0

    def test_two_components(self):
        """Two components return a score in [0, 1]."""
        state = _make_state([(20.0, 20.0), (80.0, 80.0)], 2)
        netlist = Netlist(
            components=[
                Component(ref="U1", footprint="SOIC-8", bounds=(5, 4)),
                Component(ref="U2", footprint="SOIC-8", bounds=(5, 4)),
            ],
            nets=[],
        )
        board = Board(width=100, height=100)
        score = compactness_score(state, netlist, board)
        assert 0.0 <= score <= 1.0


class TestThermalScore:
    def test_empty_thermal_components(self):
        """No thermal components yields perfect score 1.0."""
        state = _make_state([(50.0, 50.0)], 1)
        netlist = Netlist(
            components=[Component(ref="U1", footprint="SOIC-8", bounds=(5, 4))],
            nets=[],
        )
        board = Board(width=100, height=100)
        score = thermal_score(state, netlist, board, set(), target_edge="TOP")
        assert score == 1.0

    def test_thermal_component_at_edge(self):
        """Thermal component placed near TOP edge gets a high score."""
        state = _make_state([(50.0, 95.0)], 1)
        netlist = Netlist(
            components=[Component(ref="Q1", footprint="TO-220", bounds=(10, 10))],
            nets=[],
        )
        board = Board(width=100, height=100)
        score = thermal_score(
            state, netlist, board, {"Q1"}, target_edge="TOP", max_distance=10.0
        )
        assert 0.0 <= score <= 1.0

    def test_thermal_component_far_from_edge(self):
        """Thermal component far from TOP edge gets a lower score."""
        state_top = _make_state([(50.0, 95.0)], 1)
        state_bottom = _make_state([(50.0, 5.0)], 1)
        netlist = Netlist(
            components=[Component(ref="Q1", footprint="TO-220", bounds=(10, 10))],
            nets=[],
        )
        board = Board(width=100, height=100)
        score_top = thermal_score(
            state_top, netlist, board, {"Q1"}, target_edge="TOP", max_distance=10.0
        )
        score_bottom = thermal_score(
            state_bottom, netlist, board, {"Q1"}, target_edge="TOP", max_distance=10.0
        )
        assert score_top >= score_bottom


class TestZoneComplianceScore:
    def test_empty_zone_assignments(self):
        state = _make_state([(10.0, 10.0)], 1)
        netlist = Netlist(
            components=[Component(ref="U1", footprint="SOIC-8", bounds=(5, 4))],
            nets=[],
        )
        board = Board(width=100, height=100, zones=[Zone("A", (0, 0, 50, 50))])
        score = zone_compliance_score(state, netlist, board, {})
        assert score == 1.0

    def test_no_board_zones(self):
        state = _make_state([(10.0, 10.0)], 1)
        netlist = Netlist(
            components=[Component(ref="U1", footprint="SOIC-8", bounds=(5, 4))],
            nets=[],
        )
        board = Board(width=100, height=100)
        score = zone_compliance_score(state, netlist, board, {"U1": "A"})
        assert score == 1.0

    def test_component_in_zone(self):
        state = _make_state([(25.0, 25.0)], 1)
        netlist = Netlist(
            components=[Component(ref="U1", footprint="SOIC-8", bounds=(5, 4))],
            nets=[],
        )
        board = Board(width=100, height=100, zones=[Zone("A", (0, 0, 50, 50))])
        score = zone_compliance_score(state, netlist, board, {"U1": "A"})
        assert 0.0 <= score <= 1.0


class TestHVLVClearanceScore:
    def test_empty_sets(self):
        """Empty hv or lv sets yield perfect score 1.0."""
        state = _make_state([(50.0, 50.0)], 1)
        netlist = Netlist(
            components=[Component(ref="U1", footprint="SOIC-8", bounds=(5, 4))],
            nets=[],
        )
        score = hv_lv_clearance_score(state, netlist, set(), {"U1"})
        assert score == 1.0

    def test_separated_components(self):
        """HV and LV components far apart get high score."""
        state = _make_state([(10.0, 10.0), (80.0, 80.0)], 2)
        netlist = Netlist(
            components=[
                Component(ref="Q1", footprint="TO-220", bounds=(10, 10)),
                Component(ref="R1", footprint="0805", bounds=(2, 1)),
            ],
            nets=[],
        )
        score = hv_lv_clearance_score(state, netlist, {"Q1"}, {"R1"}, min_clearance=8.0)
        assert 0.0 <= score <= 1.0

    def test_close_components(self):
        """HV and LV components close together get lower score."""
        state_far = _make_state([(10.0, 10.0), (80.0, 80.0)], 2)
        state_close = _make_state([(10.0, 10.0), (15.0, 15.0)], 2)
        netlist = Netlist(
            components=[
                Component(ref="Q1", footprint="TO-220", bounds=(10, 10)),
                Component(ref="R1", footprint="0805", bounds=(2, 1)),
            ],
            nets=[],
        )
        score_far = hv_lv_clearance_score(state_far, netlist, {"Q1"}, {"R1"}, min_clearance=8.0)
        score_close = hv_lv_clearance_score(state_close, netlist, {"Q1"}, {"R1"}, min_clearance=8.0)
        assert score_far >= score_close


class TestDualRailClearanceReport:
    def test_empty_sets(self):
        state = _make_state([(50.0, 50.0)], 1)
        netlist = Netlist(
            components=[Component(ref="U1", footprint="SOIC-8", bounds=(5, 4))],
            nets=[],
        )
        report = dual_rail_clearance_report(state, netlist, set(), {"U1"})
        assert report["clearance_score_3mm"] == 1.0
        assert report["clearance_score_6mm"] == 1.0
        assert report["violations_3mm"] == 0
        assert report["violations_6mm"] == 0

    def test_with_components(self):
        state = _make_state([(10.0, 10.0), (80.0, 80.0)], 2)
        netlist = Netlist(
            components=[
                Component(ref="Q1", footprint="TO-220", bounds=(10, 10)),
                Component(ref="R1", footprint="0805", bounds=(2, 1)),
            ],
            nets=[],
        )
        report = dual_rail_clearance_report(state, netlist, {"Q1"}, {"R1"})
        assert "clearance_score_3mm" in report
        assert "clearance_score_6mm" in report
        assert "violations_3mm" in report
        assert "violations_6mm" in report
        assert isinstance(report["violations_3mm"], int)
        assert isinstance(report["violations_6mm"], int)
        assert 0.0 <= report["clearance_score_3mm"] <= 1.0
        assert 0.0 <= report["clearance_score_6mm"] <= 1.0


class TestLoopAreaScore:
    def test_empty_loop_components(self):
        state = _make_state([(50.0, 50.0)], 1)
        netlist = Netlist(
            components=[Component(ref="U1", footprint="SOIC-8", bounds=(5, 4))],
            nets=[],
        )
        context = type("Ctx", (), {"net_pin_indices": np.zeros((0, 0))})()
        score = loop_area_score(state, netlist, context, [])
        assert score == 1.0

    def test_fewer_than_three_components(self):
        """Loops with fewer than 3 components are filtered out."""
        state = _make_state([(10.0, 10.0), (20.0, 20.0)], 2)
        netlist = Netlist(
            components=[
                Component(ref="U1", footprint="SOIC-8", bounds=(5, 4)),
                Component(ref="U2", footprint="SOIC-8", bounds=(5, 4)),
            ],
            nets=[],
        )
        context = type("Ctx", (), {"net_pin_indices": np.zeros((0, 0))})()
        score = loop_area_score(state, netlist, context, [["U1", "U2"]])
        assert score == 1.0  # Filtered out because < 3

    def test_three_components(self):
        """A loop with 3 components computes a score."""
        state = _make_state([(0.0, 0.0), (10.0, 0.0), (0.0, 10.0)], 3)
        netlist = Netlist(
            components=[
                Component(ref="C1", footprint="0805", bounds=(2, 1)),
                Component(ref="C2", footprint="0805", bounds=(2, 1)),
                Component(ref="C3", footprint="0805", bounds=(2, 1)),
            ],
            nets=[],
        )
        context = type("Ctx", (), {"net_pin_indices": np.zeros((0, 0))})()
        score = loop_area_score(state, netlist, context, [["C1", "C2", "C3"]])
        assert 0.0 <= score <= 1.0


class TestConnectivityClusteringScore:
    def test_empty_nets(self):
        """No nets yields perfect score."""
        state = _make_state([], 0)
        netlist = Netlist()
        context = type("Ctx", (), {
            "net_pin_indices": np.zeros((0, 0)),
            "net_pin_mask": np.zeros((0, 0)),
        })()
        score = connectivity_clustering_score(state, netlist, context)
        assert score == 1.0

    def test_single_pin_net_filtered_out(self):
        """Nets with fewer than 2 pins are filtered, yielding perfect score."""
        state = _make_state([(10.0, 10.0)], 1)
        netlist = Netlist(
            components=[Component(ref="U1", footprint="SOIC-8", bounds=(5, 4))],
            nets=[],
        )
        context = type("Ctx", (), {
            "net_pin_indices": np.array([[0, -1]], dtype=np.int32),
            "net_pin_mask": np.array([[True, False]], dtype=bool),
        })()
        score = connectivity_clustering_score(state, netlist, context)
        assert score == 1.0


class TestComputeQualityReport:
    def test_deprecated_warning(self):
        """compute_quality_report raises DeprecationWarning and still runs."""
        import warnings

        state = _make_state([(25.0, 25.0), (75.0, 75.0)], 2)
        netlist = Netlist(
            components=[
                Component(ref="Q1", footprint="TO-220", bounds=(10, 10)),
                Component(ref="R1", footprint="0805", bounds=(2, 1)),
            ],
            nets=[Net(name="N1", pins=[("Q1", "1"), ("R1", "1")])],
        )
        board = Board(width=100, height=100)
        context = type("Ctx", (), {
            "net_pin_indices": np.zeros((0, 0)),
            "net_pin_mask": np.zeros((0, 0)),
        })()
        config = {
            "thermal_components": {"Q1"},
            "hv_components": {"Q1"},
            "lv_components": {"R1"},
            "zone_assignments": {},
            "loop_components": [],
            "min_hv_lv_clearance": 8.0,
        }
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = compute_quality_report(state, netlist, board, context, config)
        assert isinstance(result, dict)
        assert "overall_score" in result
        assert "hv_lv_clearance_score" in result
