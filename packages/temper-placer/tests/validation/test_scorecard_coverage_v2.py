"""Tests for validation.scorecard module — MarginScorecard and scorer functions."""
import pytest

from temper_placer.validation.scorecard import (
    GateMargin,
    IndependenceViolationError,
    MarginScorecard,
    _assert_independent,
    _is_scorable_metric,
    build_scorecard,
)


class TestMarginScorecard:
    """Tests for MarginScorecard methods."""

    def test_empty_scorecard(self):
        sc = MarginScorecard(board_id="board_1", scorer_id="oracle_v1")
        assert sc.board_id == "board_1"
        assert sc.scorer_id == "oracle_v1"
        assert sc.margins == []
        assert sc.scorable_margins() == []

    def test_margin_for_found(self):
        gm = GateMargin(gate_name="thermal", value=15.0, unit="mm")
        sc = MarginScorecard(board_id="b", scorer_id="s", margins=[gm])
        found = sc.margin_for("thermal")
        assert found is gm
        assert found.value == 15.0

    def test_margin_for_not_found(self):
        sc = MarginScorecard(board_id="b", scorer_id="s", margins=[])
        assert sc.margin_for("missing") is None

    def test_scorable_margins_filters(self):
        gm1 = GateMargin(gate_name="thermal", value=15.0, unit="mm", is_scorable=True)
        gm2 = GateMargin(gate_name="loop_area", value=0.0, unit="mm2", is_scorable=False)
        sc = MarginScorecard(board_id="b", scorer_id="s", margins=[gm1, gm2])
        scorables = sc.scorable_margins()
        assert len(scorables) == 1
        assert scorables[0].gate_name == "thermal"

    def test_from_oracle_result_minimal(self):
        """Test from_oracle_result with a minimal quality report."""
        class FakeOracleResult:
            board_id = "test_board"
            quality_report = {}

        result = FakeOracleResult()
        sc = MarginScorecard.from_oracle_result(result, scorer_id="test_scorer")
        assert sc.board_id == "test_board"
        assert sc.scorer_id == "test_scorer"
        assert len(sc.margins) == 4  # thermal, hv_lv_clearance, loop_area, compactness
        assert sc.margins[0].gate_name == "thermal"
        assert sc.margins[1].gate_name == "hv_lv_clearance"
        assert sc.margins[2].gate_name == "loop_area"
        assert sc.margins[3].gate_name == "compactness"

    def test_from_oracle_result_with_scores(self):
        class FakeOracleResult:
            board_id = "test_board"
            quality_report = {
                "thermal_score": 0.85,
                "hv_lv_clearance_score": 0.90,
                "loop_area_score": 0.75,
                "compactness_score": 0.50,
            }

        result = FakeOracleResult()
        sc = MarginScorecard.from_oracle_result(
            result,
            scorer_id="test_scorer",
            max_heatspread_mm=10.0,
            hv_lv_threshold_mm=6.5,
            max_loop_area_mm2=100.0,
        )
        assert len(sc.margins) == 4
        assert sc.margins[0].raw_score == 0.85
        assert sc.margins[1].raw_score == 0.90
        assert sc.margins[2].raw_score == 0.75
        assert sc.margins[3].raw_score == 0.50

    def test_from_oracle_result_non_scorable(self):
        """Metrics at their default value (1.0) should be non-scorable."""
        class FakeOracleResult:
            board_id = "test_board"
            quality_report = {
                "thermal_score": 1.0,  # default -> non-scorable
            }

        result = FakeOracleResult()
        sc = MarginScorecard.from_oracle_result(result, scorer_id="test_scorer")
        # thermal at default -> is_scorable=False
        assert sc.margins[0].is_scorable is False


class TestIsScorableMetric:
    """Tests for _is_scorable_metric."""

    def test_default_value_not_scorable(self):
        assert _is_scorable_metric(1.0, {}, key="test", default_value=1.0) is False

    def test_non_default_value_is_scorable(self):
        assert _is_scorable_metric(0.85, {}, key="test", default_value=1.0) is True

    def test_explicit_default_value(self):
        assert _is_scorable_metric(0.5, {}, key="t", default_value=0.5) is False
        assert _is_scorable_metric(0.51, {}, key="t", default_value=0.5) is True


class TestBuildScorecard:
    """Tests for build_scorecard independence guard."""

    def test_independence_violation_raises(self):
        def fake_scorer(placement, board, netlist):
            class R:
                board_id = "test"
                quality_report = {}
            return R()

        with pytest.raises(IndependenceViolationError, match="Independence violation"):
            build_scorecard(
                placement=None,
                board=None,
                netlist=None,
                scorer=fake_scorer,
                scorer_id="same_id",
                field_id="same_id",
            )

    def test_build_scorecard_different_ids(self):
        def fake_scorer(placement, board, netlist):
            class R:
                board_id = "test"
                quality_report = {}
            return R()

        sc = build_scorecard(
            placement=None,
            board=None,
            netlist=None,
            scorer=fake_scorer,
            scorer_id="scorer_A",
            field_id="field_B",
        )
        assert sc.scorer_id == "scorer_A"


class TestGateMarginMore:
    """Additional GateMargin edge cases."""

    def test_non_scorable_margin(self):
        gm = GateMargin(gate_name="test", value=0.0, unit="", is_scorable=False)
        assert gm.margin == 0.0
        assert gm.is_scorable is False

    def test_margin_property(self):
        gm = GateMargin(gate_name="test", value=3.14, unit="m")
        assert gm.margin == 3.14
