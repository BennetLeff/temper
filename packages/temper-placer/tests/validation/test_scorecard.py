"""Tests for scorecard.py — U2 margin scorecard + independence guard."""

import numpy as np
import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist
from temper_placer.core.state import PlacementState
from temper_placer.metrics.quality import (
    hv_lv_clearance_score,
    thermal_score,
)
from temper_placer.regression.physics_oracle import (
    PhysicsOracleResult,
    compute_oracle_margins,
)
from temper_placer.validation.scorecard import (
    GateMargin,
    IndependenceViolationError,
    MarginScorecard,
    _assert_independent,
    build_scorecard,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(positions):
    return PlacementState(
        positions=np.array(positions, dtype=np.float32),
        rotation_logits=np.zeros((len(positions), 4), dtype=np.float32),
    )


def _minimal_board(width=100.0, height=150.0):
    return Board(width=width, height=height)


def _minimal_netlist(components):
    nl = Netlist()
    nl.components = list(components)
    nl.build_indices()
    return nl


# ---------------------------------------------------------------------------
# compute_oracle_margins unit tests
# ---------------------------------------------------------------------------


class TestComputeOracleMargins:
    """Verify the margin conversion from quality_report scores."""

    def test_perfect_scores_give_full_headroom(self):
        """quality_report of all 1.0s gives max headroom margins."""
        report = {
            "thermal_score": 1.0,
            "hv_lv_clearance_score": 1.0,
            "loop_area_score": 1.0,
        }
        margins = compute_oracle_margins(report)
        assert margins["thermal_headroom_mm"] == 10.0
        assert margins["clearance_margin_mm"] == 0.0  # exactly at threshold
        assert margins["loop_area_margin_mm2"] == 100.0

    def test_zero_scores_give_zero_headroom(self):
        """quality_report of all 0.0s gives zero or negative headroom."""
        report = {
            "thermal_score": 0.0,
            "hv_lv_clearance_score": 0.0,
            "loop_area_score": 0.0,
        }
        margins = compute_oracle_margins(report)
        assert margins["thermal_headroom_mm"] == 0.0
        assert margins["clearance_margin_mm"] == -6.5  # full violation
        assert margins["loop_area_margin_mm2"] == 0.0

    def test_proportional_thermal_margin(self):
        """Thermal margin scales linearly with score."""
        report = {"thermal_score": 0.5, "hv_lv_clearance_score": 1.0, "loop_area_score": 1.0}
        margins = compute_oracle_margins(report, max_heatspread_mm=40.0)
        assert margins["thermal_headroom_mm"] == 20.0  # 0.5 * 40

    def test_clearance_margin_negative_for_violation(self):
        """Score below 1.0 gives negative margin (violation)."""
        report = {"thermal_score": 1.0, "hv_lv_clearance_score": 0.3, "loop_area_score": 1.0}
        margins = compute_oracle_margins(report, hv_lv_threshold_mm=8.0)
        # 0.3 score means 0.3*8 = 2.4mm actual, so margin = 2.4 - 8.0 = -5.6mm
        assert margins["clearance_margin_mm"] == pytest.approx(-5.6, abs=0.01)

    def test_missing_keys_default_to_one(self):
        """Missing quality_report keys default to 1.0 (perfect)."""
        margins = compute_oracle_margins({})
        assert margins["thermal_headroom_mm"] == 10.0
        assert margins["clearance_margin_mm"] == 0.0
        assert margins["loop_area_margin_mm2"] == 100.0


# ---------------------------------------------------------------------------
# MarginScorecard.from_oracle_result tests
# ---------------------------------------------------------------------------


class TestMarginScorecardFromOracleResult:
    """Verify MarginScorecard from oracle results."""

    def test_creates_scorecard_with_all_gates(self):
        """from_oracle_result creates four gate margins."""
        report = {
            "thermal_score": 0.75,
            "hv_lv_clearance_score": 0.9,
            "loop_area_score": 0.5,
            "compactness_score": 0.3,
        }
        result = PhysicsOracleResult(
            board_id="test_board",
            passed=True,
            quality_report=report,
        )
        sc = MarginScorecard.from_oracle_result(result, scorer_id="physics_oracle")
        assert sc.board_id == "test_board"
        assert sc.scorer_id == "physics_oracle"
        assert len(sc.margins) == 4

    def test_all_gates_scorable_when_not_default(self):
        """All gates are scorable when quality_report has non-default values."""
        report = {
            "thermal_score": 0.5,
            "hv_lv_clearance_score": 0.8,
            "loop_area_score": 0.6,
            "compactness_score": 0.4,
        }
        result = PhysicsOracleResult(
            board_id="b",
            passed=True,
            quality_report=report,
        )
        sc = MarginScorecard.from_oracle_result(result, scorer_id="o")
        assert all(m.is_scorable for m in sc.margins)
        assert len(sc.scorable_margins()) == 4

    def test_default_score_is_not_scorable(self):
        """A gate at its default pass-through value (1.0) is flagged non-scorable."""
        report = {
            "thermal_score": 1.0,  # default — empty thermal set
            "hv_lv_clearance_score": 0.8,
            "loop_area_score": 1.0,  # default — no loop components
            "compactness_score": 0.5,
        }
        result = PhysicsOracleResult(
            board_id="b",
            passed=True,
            quality_report=report,
        )
        sc = MarginScorecard.from_oracle_result(result, scorer_id="o")

        thermal = sc.margin_for("thermal")
        assert thermal is not None
        assert not thermal.is_scorable

        clearance = sc.margin_for("hv_lv_clearance")
        assert clearance is not None
        assert clearance.is_scorable

        loop = sc.margin_for("loop_area")
        assert loop is not None
        assert not loop.is_scorable

        assert len(sc.scorable_margins()) == 2

    def test_margin_for_unknown_gate_returns_none(self):
        report = {"thermal_score": 0.5}
        result = PhysicsOracleResult(board_id="b", passed=True, quality_report=report)
        sc = MarginScorecard.from_oracle_result(result, scorer_id="o")
        assert sc.margin_for("nonexistent") is None

    def test_all_default_report_all_not_scorable(self):
        """All-1.0 report → all gates non-scorable (dynamic-range guard)."""
        report = {
            "thermal_score": 1.0,
            "hv_lv_clearance_score": 1.0,
            "loop_area_score": 1.0,
            "compactness_score": 1.0,
        }
        result = PhysicsOracleResult(board_id="b", passed=True, quality_report=report)
        sc = MarginScorecard.from_oracle_result(result, scorer_id="o")
        assert all(not m.is_scorable for m in sc.margins)
        assert len(sc.scorable_margins()) == 0


# ---------------------------------------------------------------------------
# Independence guard tests
# ---------------------------------------------------------------------------


class TestIndependenceGuard:
    """The scoring contract must block self-scoring."""

    def test_assert_independent_raises_on_same_id(self):
        with pytest.raises(IndependenceViolationError, match="same instrument"):
            _assert_independent(scorer_id="thermal_field", field_id="thermal_field")

    def test_assert_independent_passes_on_different_ids(self):
        _assert_independent(scorer_id="physics_oracle", field_id="thermal_field")

    def test_build_scorecard_raises_when_scorer_equals_field(self, tmp_path):
        """build_scorecard raises if scorer_id and field_id are the same,
        before attempting any scoring."""
        called = []

        def dummy_scorer(placement, board, netlist):
            called.append(True)
            return PhysicsOracleResult(board_id="x", passed=True)

        board = _minimal_board()
        netlist = _minimal_netlist([])
        state = _make_state([])

        with pytest.raises(IndependenceViolationError):
            build_scorecard(
                state,
                board,
                netlist,
                scorer=dummy_scorer,
                scorer_id="my_solver",
                field_id="my_solver",
            )
        # Scorer must NOT be called — guard fires before invocation
        assert len(called) == 0

    def test_build_scorecard_succeeds_with_independent_instruments(self):
        """build_scorecard runs fine when scorer and field are distinct."""
        board = _minimal_board(200, 200)
        q1 = Component(
            ref="Q1",
            footprint="TO-247",
            bounds=(10.0, 5.0),
            pins=[],
            initial_position=(50.0, 190.0),
            net_class="HighVoltage",
        )
        netlist = _minimal_netlist([q1])
        state = _make_state([[50.0, 190.0]])
        # Score through score_placement() from physics_oracle
        from temper_placer.placer.deterministic import PlacementResult
        from temper_placer.regression.physics_oracle import score_placement

        placement = PlacementResult(
            positions=state.positions,
            rotations=np.zeros(1, dtype=np.float32),
            placed_refs=["Q1"],
            unplaced_refs=[],
        )

        def scorer(p, b, n):
            report = score_placement(placement, b, n)
            return PhysicsOracleResult(
                board_id="test",
                passed=True,
                quality_report=report,
            )

        sc = build_scorecard(
            placement,
            board,
            netlist,
            scorer=scorer,
            scorer_id="physics_oracle",
            field_id="thermal_field",
        )
        assert sc.scorer_id == "physics_oracle"
        assert len(sc.margins) > 0


# ---------------------------------------------------------------------------
# Happy path: monotonic thermal margin
# ---------------------------------------------------------------------------


class TestThermalMarginMonotonic:
    """A board with more thermal headroom scores larger margin than a hotter board."""

    def test_closer_to_edge_gives_larger_thermal_margin(self):
        """Component at y=198 (2mm from TOP at 200mm board) scores larger
        thermal margin than component at y=180 (20mm from TOP)."""
        board = Board(width=100.0, height=200.0)

        # Near-edge placement
        near_comp = Component(
            ref="Q1",
            footprint="TO-247",
            bounds=(10.0, 5.0),
            pins=[],
            initial_position=(50.0, 198.0),
            net_class="HighVoltage",
        )
        near_nl = _minimal_netlist([near_comp])
        near_state = _make_state([[50.0, 198.0]])

        near_thermal = thermal_score(
            near_state,
            near_nl,
            board,
            {"Q1"},
            target_edge="TOP",
            max_distance=40.0,
        )

        # Far-from-edge placement
        far_comp = Component(
            ref="Q1",
            footprint="TO-247",
            bounds=(10.0, 5.0),
            pins=[],
            initial_position=(50.0, 180.0),
            net_class="HighVoltage",
        )
        far_nl = _minimal_netlist([far_comp])
        far_state = _make_state([[50.0, 180.0]])

        far_thermal = thermal_score(
            far_state,
            far_nl,
            board,
            {"Q1"},
            target_edge="TOP",
            max_distance=40.0,
        )

        # Raw scores: near > far
        assert near_thermal > far_thermal

        # Margin: near_margin > far_margin
        near_report = {
            "thermal_score": near_thermal,
            "hv_lv_clearance_score": 1.0,
            "loop_area_score": 1.0,
        }
        far_report = {
            "thermal_score": far_thermal,
            "hv_lv_clearance_score": 1.0,
            "loop_area_score": 1.0,
        }

        near_margins = compute_oracle_margins(near_report, max_heatspread_mm=40.0)
        far_margins = compute_oracle_margins(far_report, max_heatspread_mm=40.0)

        assert near_margins["thermal_headroom_mm"] > far_margins["thermal_headroom_mm"], (
            f"near={near_margins['thermal_headroom_mm']}, far={far_margins['thermal_headroom_mm']}"
        )


# ---------------------------------------------------------------------------
# Edge case: empty/default input yields non-scorable
# ---------------------------------------------------------------------------


class TestEdgeDefaultNotScorable:
    """Empty-component or all-default inputs produce flagged non-scorable results."""

    def test_empty_netlist_produces_non_scorable_thermal(self):
        """Scorecard from empty board has non-scorable gates, not silent 0.0."""
        board = _minimal_board()
        netlist = _minimal_netlist([])
        state = _make_state([])

        thermal = thermal_score(state, netlist, board, set(), target_edge="TOP")
        assert thermal == 1.0  # default pass-through

        report = {"thermal_score": thermal, "hv_lv_clearance_score": 1.0, "loop_area_score": 1.0}
        result = PhysicsOracleResult(board_id="empty", passed=True, quality_report=report)
        sc = MarginScorecard.from_oracle_result(result, scorer_id="o")

        tm = sc.margin_for("thermal")
        assert tm is not None
        assert not tm.is_scorable
        assert tm.value == 10.0  # full headroom from default, BUT not scorable

    def test_empty_hv_lv_sets_produce_non_scorable_clearance(self):
        """No HV or LV components → clearance score is default 1.0 → not scorable."""
        _minimal_board()

        # Single component — no HV/LV pairs
        c = Component(
            ref="U1",
            footprint="QFP",
            bounds=(8.0, 8.0),
            pins=[],
            initial_position=(50.0, 50.0),
            net_class="Signal",
        )
        netlist = _minimal_netlist([c])
        state = _make_state([[50.0, 50.0]])

        clearance = hv_lv_clearance_score(state, netlist, hv_components=set(), lv_components={"U1"})
        assert clearance == 1.0  # default — no HV components

        report = {"thermal_score": 0.5, "hv_lv_clearance_score": clearance, "loop_area_score": 1.0}
        result = PhysicsOracleResult(board_id="nohv", passed=True, quality_report=report)
        sc = MarginScorecard.from_oracle_result(result, scorer_id="o")

        cm = sc.margin_for("hv_lv_clearance")
        assert cm is not None
        assert not cm.is_scorable


# ---------------------------------------------------------------------------
# Integration: margins flow from oracle through to scorecard
# ---------------------------------------------------------------------------


class TestIntegrationOracleToScorecard:
    """End-to-end: scorecard margins flow from physics_oracle through to a
    battery-consumable record."""

    def test_scorecard_from_oracle_margins(self):
        """Scorecard built from oracle result carries correct engineering-unit margins."""
        report = {
            "thermal_score": 0.6,
            "hv_lv_clearance_score": 0.8,
            "loop_area_score": 0.3,
            "compactness_score": 0.45,
        }
        oracle_margins = compute_oracle_margins(report, max_heatspread_mm=30.0)
        result = PhysicsOracleResult(
            board_id="integ",
            passed=True,
            quality_report=report,
            margins=oracle_margins,
        )
        sc = MarginScorecard.from_oracle_result(
            result,
            scorer_id="physics_oracle",
            max_heatspread_mm=30.0,
        )

        # Thermal: 0.6 * 30 = 18.0 mm headroom
        tm = sc.margin_for("thermal")
        assert tm is not None
        assert tm.value == pytest.approx(18.0, abs=0.01)
        assert tm.unit == "mm"
        assert tm.is_scorable

        # Clearance: (0.8 - 1.0) * 6.5 = -1.3 mm margin
        cm = sc.margin_for("hv_lv_clearance")
        assert cm is not None
        assert cm.value == pytest.approx(-1.3, abs=0.01)
        assert cm.unit == "mm"
        assert cm.is_scorable

        # Loop area: 0.3 * 100 = 30.0 mm² headroom
        lm = sc.margin_for("loop_area")
        assert lm is not None
        assert lm.value == pytest.approx(30.0, abs=0.01)
        assert lm.unit == "mm2"
        assert lm.is_scorable

    def test_scorecard_margin_attribute_is_value(self):
        """GateMargin.margin property is an alias for value."""
        m = GateMargin(gate_name="thermal", value=12.5, unit="mm", raw_score=0.5)
        assert m.margin == 12.5

    def test_full_integration_via_score_placement(self):
        """Build a scorecard via the score_placement path (no PCB file needed)."""
        from temper_placer.placer.deterministic import PlacementResult
        from temper_placer.regression.physics_oracle import score_placement

        board = Board(width=200.0, height=200.0)

        # Create a realistic fixture: 2 HV + 3 LV, well-separated
        q1 = Component(
            ref="Q1",
            footprint="TO-247",
            bounds=(10.0, 5.0),
            pins=[],
            initial_position=(20.0, 20.0),
            net_class="HighVoltage",
        )
        q2 = Component(
            ref="Q2",
            footprint="TO-247",
            bounds=(10.0, 5.0),
            pins=[],
            initial_position=(20.0, 70.0),
            net_class="HighVoltage",
        )
        u1 = Component(
            ref="U1",
            footprint="QFP",
            bounds=(8.0, 8.0),
            pins=[],
            initial_position=(80.0, 20.0),
            net_class="Signal",
        )
        u2 = Component(
            ref="U2",
            footprint="QFP",
            bounds=(8.0, 8.0),
            pins=[],
            initial_position=(80.0, 50.0),
            net_class="Signal",
        )
        u3 = Component(
            ref="U3",
            footprint="QFP",
            bounds=(8.0, 8.0),
            pins=[],
            initial_position=(80.0, 80.0),
            net_class="Signal",
        )

        netlist = _minimal_netlist([q1, q2, u1, u2, u3])
        positions = np.array(
            [
                [20.0, 20.0],
                [20.0, 70.0],
                [80.0, 20.0],
                [80.0, 50.0],
                [80.0, 80.0],
            ],
            dtype=np.float32,
        )
        placement = PlacementResult(
            positions=positions,
            rotations=np.zeros(5, dtype=np.float32),
            placed_refs=["Q1", "Q2", "U1", "U2", "U3"],
            unplaced_refs=[],
        )

        report = score_placement(placement, board, netlist)
        oracle_margins = compute_oracle_margins(report)
        result = PhysicsOracleResult(
            board_id="fixture",
            passed=True,
            quality_report=report,
            margins=oracle_margins,
        )
        sc = MarginScorecard.from_oracle_result(result, scorer_id="physics_oracle")

        # All gates should be present
        gate_names = {m.gate_name for m in sc.margins}
        assert "thermal" in gate_names
        assert "hv_lv_clearance" in gate_names
        assert "loop_area" in gate_names
        assert "compactness" in gate_names

        # Clearance should be scorable (HV and LV components present)
        clearance = sc.margin_for("hv_lv_clearance")
        assert clearance is not None
        # With 50mm+ separation between HV and LV clusters and small bounds,
        # clearance should be 1.0 (passed) and thus margin = 0 (> threshold)
        assert clearance.raw_score == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# GateMargin value type checks
# ---------------------------------------------------------------------------


class TestGateMarginContract:
    """U3 consumers rely on these field names, types, and shapes."""

    def test_all_gate_names_are_strings(self):
        m = GateMargin(gate_name="thermal", value=1.0, unit="degC", raw_score=1.0)
        assert isinstance(m.gate_name, str)
        assert isinstance(m.value, float)
        assert isinstance(m.unit, str)
        assert isinstance(m.is_scorable, bool)

    def test_margin_from_public_api_is_dict_ready(self):
        """Scorecard margins can be consumed as a dict for battery records."""
        report = {
            "thermal_score": 0.42,
            "hv_lv_clearance_score": 0.67,
            "loop_area_score": 0.58,
            "compactness_score": 0.33,
        }
        result = PhysicsOracleResult(board_id="b", passed=True, quality_report=report)
        sc = MarginScorecard.from_oracle_result(result, scorer_id="o")

        record = {
            m.gate_name: {"margin": m.value, "unit": m.unit, "scorable": m.is_scorable}
            for m in sc.margins
        }
        assert record["thermal"]["unit"] == "mm"
        assert record["hv_lv_clearance"]["unit"] == "mm"
        assert record["loop_area"]["unit"] == "mm2"

    def test_independence_violation_is_value_error_subclass(self):
        """U3 can catch IndependenceViolationError via ValueError."""
        with pytest.raises(ValueError):
            raise IndependenceViolationError("test")
