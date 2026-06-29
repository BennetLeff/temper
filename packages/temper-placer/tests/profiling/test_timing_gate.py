"""Tests for per-stage timing measurement contract (U1 of plan 022)."""

import pytest

from temper_placer.profiling.timing_gate import (
    StageTimingEntry,
    TimingReport,
    TimingResult,
    measure_all_stages,
    measure_stage_timing,
)


class TestTimingResult:
    def test_creation(self):
        result = TimingResult(
            board_id="temper_placed",
            pipeline="DeterministicPipeline",
            stage_name="zone_geometry",
            wall_ms=12.3,
            n_runs=3,
            individual_ms=[12.0, 12.5, 12.4],
        )
        assert result.wall_ms == 12.3
        assert result.n_runs == 3
        assert len(result.individual_ms) == 3


class TestTimingReport:
    def test_all_pass(self):
        report = TimingReport(
            entries=[
                StageTimingEntry(
                    board="t", pipeline="P", stage="s",
                    baseline_ms=10.0, current_ms=11.0,
                    delta_ms=1.0, delta_pct=10.0,
                    threshold_ms=12.0, passed=True,
                )
            ],
            margin=0.20,
            passed=True,
            total_stages=1,
            failed_stages=0,
        )
        assert report.passed

    def test_has_failures(self):
        report = TimingReport(
            entries=[
                StageTimingEntry(
                    board="t", pipeline="P", stage="s",
                    baseline_ms=10.0, current_ms=15.0,
                    delta_ms=5.0, delta_pct=50.0,
                    threshold_ms=12.0, passed=False,
                )
            ],
            margin=0.20,
            passed=False,
            total_stages=1,
            failed_stages=1,
        )
        assert not report.passed
        assert report.failed_stages == 1

    def test_to_dict(self):
        report = TimingReport(
            entries=[
                StageTimingEntry(
                    board="t", pipeline="P", stage="s",
                    baseline_ms=10.0, current_ms=11.0,
                    delta_ms=1.0, delta_pct=10.0,
                    threshold_ms=12.0, passed=True,
                )
            ],
            margin=0.20,
            passed=True,
            total_stages=1,
            failed_stages=0,
        )
        d = report.to_dict()
        assert d["passed"] is True
        assert d["total_stages"] == 1
        assert len(d["entries"]) == 1
        assert d["entries"][0]["stage"] == "s"


class TestMeasureStageTiming:
    def test_measure_returns_timing_result(self):
        result = measure_stage_timing("zone_geometry", "temper_placed")
        assert isinstance(result, TimingResult)
        assert result.board_id == "temper_placed"
        assert result.pipeline == "DeterministicPipeline"
        assert result.stage_name == "zone_geometry"
        assert result.wall_ms > 0
        assert result.n_runs == 3

    def test_n_runs_respected(self):
        result = measure_stage_timing("zone_geometry", "temper_placed", n_runs=2)
        assert result.n_runs == 2
        assert len(result.individual_ms) == 2

    def test_unknown_stage_raises_valueerror(self):
        with pytest.raises(ValueError, match="not found"):
            measure_stage_timing("nonexistent_stage", "temper_placed")

    def test_unknown_board_raises_valueerror(self):
        with pytest.raises(ValueError, match="Unknown board"):
            measure_stage_timing("zone_geometry", "nonexistent_board")

    def test_apply_placements_positive_wall_ms(self):
        result = measure_stage_timing("apply_placements", "temper_placed")
        assert result.wall_ms > 0, f"Expected positive wall_ms, got {result.wall_ms}"

    def test_all_stages_returned(self):
        results = measure_all_stages("temper_placed", n_runs=2)
        assert len(results) > 5, f"Expected at least 5 stages, got {len(results)}"
        stage_names = [r.stage_name for r in results]
        assert "zone_geometry" in stage_names
        assert "clearance_grid" in stage_names
        for r in results:
            assert r.wall_ms >= 0, f"{r.stage_name} has negative wall_ms: {r.wall_ms}"
            assert r.n_runs == 2
            assert len(r.individual_ms) == 2

    def test_unsupported_pipeline(self):
        with pytest.raises(ValueError, match="Unsupported pipeline"):
            measure_stage_timing("zone_geometry", "temper_placed", pipeline="RouterV6Pipeline")
