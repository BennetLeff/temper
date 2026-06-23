"""Tests for the GPBM Autoprof experiment loop."""

import time
from pathlib import Path

from temper_placer.profiling.autoprof import AutoprofExperiment, AutoprofReport, DeltaRow


class TestDeltaRow:
    def test_same_timing(self):
        row = DeltaRow.from_timings("stage1", 100.0, 100.0)
        assert row.direction == "same"
        assert abs(row.delta_pct) < 0.01

    def test_slower_timing(self):
        row = DeltaRow.from_timings("stage1", 100.0, 110.0)
        assert row.direction == "slower"
        assert row.delta_pct > 5.0

    def test_faster_timing(self):
        row = DeltaRow.from_timings("stage1", 100.0, 90.0)
        assert row.direction == "faster"
        assert row.delta_pct < -5.0


class TestAutoprofReport:
    def test_to_markdown(self):
        rows = [
            DeltaRow("parse", 10.0, 10.0, 0.0, "same"),
            DeltaRow("route", 100.0, 80.0, -20.0, "faster"),
        ]
        report = AutoprofReport(
            delta_table=rows,
            bottleneck_stage="route",
            total_before_ms=110.0,
            total_after_ms=90.0,
            boards_tested=2,
        )
        md = report.to_markdown()
        assert "parse" in md
        assert "route" in md
        assert "✅" in md
        assert "110.0" in md

    def test_to_dict(self):
        report = AutoprofReport(bottleneck_stage="stage2", boards_tested=1)
        d = report.to_dict()
        assert d["experiment_type"] == "autoprof"
        assert d["bottleneck_stage"] == "stage2"


class TestAutoprofExperiment:
    def test_measure_collects_profile(self):
        exp = AutoprofExperiment()
        exp.measure(lambda: time.sleep(0.01), boards=["test"])
        assert exp._current_profile is not None

    def test_compare_empty_baseline(self):
        exp = AutoprofExperiment()
        exp._current_profile = {"stages": {"s1": {"wall_time_ms": 10.0}}, "total_wall_time_ms": 10.0}
        report = exp.compare()
        assert isinstance(report, AutoprofReport)
        assert len(report.delta_table) == 1

    def test_save_and_load_baseline(self, tmp_path: Path):
        exp = AutoprofExperiment()
        exp._current_profile = {"stages": {"s1": {"wall_time_ms": 5.0}}, "total_wall_time_ms": 5.0}
        path = tmp_path / "baseline.json"
        exp.save_baseline(path)
        assert path.exists()

        exp2 = AutoprofExperiment()
        exp2.load_baseline(path)
        assert exp2._baseline_profile["stages"]["s1"]["wall_time_ms"] == 5.0
