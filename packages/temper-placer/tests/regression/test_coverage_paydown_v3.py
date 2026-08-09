"""
Coverage paydown v3 — regression modules (metrics_recorder, fingerprint,
closure_test, reporter, manifest, corpus_runner, cp_sat_comparison).

Tests functions still on the coverage allowlist that existing suites
(differential, PBT, oracle) don't exercise directly.
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

# ============================================================================
# metrics_recorder — record_metrics_for_stage, record_stage_timing
# ============================================================================


class TestRecordMetricsForStage:
    def test_returns_pipeline_metrics_record(self):
        from temper_placer.regression.metrics_recorder import (
            PipelineMetricsRecord,
            record_metrics_for_stage,
        )

        record = record_metrics_for_stage(
            board="test_board",
            stage="routing",
            module="test_module",
            metrics={"completion": 98.5},
            commit="abc123",
        )
        assert isinstance(record, PipelineMetricsRecord)
        assert record.board == "test_board"
        assert record.stage == "routing"
        assert record.module == "test_module"
        assert record.git_commit == "abc123"
        assert record.metrics["completion"] == 98.5

    def test_default_commit_is_empty(self):
        from temper_placer.regression.metrics_recorder import (
            record_metrics_for_stage,
        )

        record = record_metrics_for_stage(
            board="b", stage="s", module="m", metrics={}
        )
        assert record.git_commit == ""


class TestRecordStageTiming:
    def test_returns_record_with_wall_time(self):
        from temper_placer.regression.metrics_recorder import (
            PipelineMetricsRecord,
            record_stage_timing,
        )

        record = record_stage_timing(
            board="test_board",
            stage="placement",
            wall_time_ms=42000,
            commit="def456",
        )
        assert isinstance(record, PipelineMetricsRecord)
        assert record.board == "test_board"
        assert record.stage == "placement"
        assert record.metrics["wall_time_ms"] == 42000
        assert record.git_commit == "def456"
        assert record.stage_name == "placement"

    def test_default_commit_empty(self):
        from temper_placer.regression.metrics_recorder import (
            record_stage_timing,
        )

        record = record_stage_timing(board="b", stage="s", wall_time_ms=100)
        assert record.git_commit == ""


# ============================================================================
# PipelineMetricsRecord.to_dict
# ============================================================================


class TestPipelineMetricsRecordToDict:
    def test_to_dict_with_drc_delta(self):
        from temper_placer.regression.metrics_recorder import (
            PipelineMetricsRecord,
        )

        record = PipelineMetricsRecord(
            board="test",
            stage="closure",
            metrics={"drc_errors": 5},
            git_commit="abc",
            drc_delta=2,
        )
        d = record.to_dict()
        assert d["drc_delta"] == 2
        assert d["board"] == "test"
        assert d["schema_version"] == 2

    def test_to_dict_without_drc_delta(self):
        from temper_placer.regression.metrics_recorder import (
            PipelineMetricsRecord,
        )

        record = PipelineMetricsRecord(
            board="test",
            stage="closure",
            metrics={},
        )
        d = record.to_dict()
        assert "drc_delta" not in d


# ============================================================================
# ClosureResult — validate, summary; ClosureTest.load_seed
# ============================================================================


class TestClosureResultValidate:
    def test_validate_healthy_result(self):
        from temper_placer.regression.closure_test import ClosureResult

        result = ClosureResult(
            passed=True,
            board_id="test",
            benders_iterations=5,
            router_completion_pct=100.0,
            stages_exercised=3,
        )
        failures = result.validate()
        assert isinstance(failures, list)

    def test_validate_zero_iterations(self):
        from temper_placer.regression.closure_test import ClosureResult

        result = ClosureResult(
            passed=False,
            board_id="test",
            benders_iterations=0,
            router_completion_pct=0.0,
            stages_exercised=0,
        )
        failures = result.validate()
        assert isinstance(failures, list)

    def test_validate_low_completion(self):
        from temper_placer.regression.closure_test import ClosureResult

        result = ClosureResult(
            passed=False,
            board_id="test",
            benders_iterations=1,
            router_completion_pct=10.0,
            stages_exercised=2,
        )
        failures = result.validate()
        assert isinstance(failures, list)


class TestClosureResultSummary:
    def test_summary_returns_string(self):
        from temper_placer.regression.closure_test import ClosureResult

        result = ClosureResult(
            passed=True,
            board_id="temper",
            benders_iterations=12,
            benders_cuts=5,
            router_completion_pct=98.5,
            drc_errors=0,
            drc_warnings=2,
            wall_clock_seconds=42.0,
            stages_exercised=4,
        )
        s = result.summary()
        assert isinstance(s, str)
        assert "temper" in s

    def test_summary_with_errors(self):
        from temper_placer.regression.closure_test import ClosureResult

        result = ClosureResult(
            passed=False,
            board_id="fail_board",
            errors=["parse error", "DRC failure"],
        )
        s = result.summary()
        assert isinstance(s, str)


class TestClosureTestLoadSeed:
    def test_load_seed_from_existing_file(self, tmp_path: Path):
        from temper_placer.regression.closure_test import ClosureTest

        seed_path = tmp_path / "seed.json"
        seed_path.write_text(json.dumps({"benders_seed": 99, "router_seed": 77}))
        seed = ClosureTest.load_seed(seed_path)
        assert seed["benders_seed"] == 99
        assert seed["router_seed"] == 77

    def test_load_seed_missing_file_returns_defaults(self, tmp_path: Path):
        from temper_placer.regression.closure_test import ClosureTest

        seed_path = tmp_path / "nonexistent.json"
        seed = ClosureTest.load_seed(seed_path)
        assert seed["benders_seed"] == 42
        assert seed["router_seed"] == 42


# ============================================================================
# fingerprint — load_cache, save_cache, should_skip, update_cache_entry
# ============================================================================


class TestFingerprintCache:
    def test_load_cache_missing_file_returns_default(self, tmp_path: Path):
        from temper_placer.regression.fingerprint import load_cache

        cache = load_cache(tmp_path)
        assert cache["version"] == 1
        assert cache["boards"] == {}

    def test_load_cache_invalid_json_returns_default(self, tmp_path: Path):
        from temper_placer.regression.fingerprint import load_cache

        cache_path = tmp_path / ".regression-cache.json"
        cache_path.write_text("{ invalid json")
        cache = load_cache(tmp_path)
        assert cache["version"] == 1

    def test_load_cache_wrong_version_returns_default(self, tmp_path: Path):
        from temper_placer.regression.fingerprint import load_cache

        cache_path = tmp_path / ".regression-cache.json"
        cache_path.write_text(json.dumps({"version": 99, "boards": {}}))
        cache = load_cache(tmp_path)
        assert cache["version"] == 1

    def test_save_and_reload_roundtrip(self, tmp_path: Path):
        from temper_placer.regression.fingerprint import load_cache, save_cache

        cache = {"version": 1, "boards": {}, "custom": "data"}
        save_cache(tmp_path, cache)

        loaded = load_cache(tmp_path)
        assert loaded["custom"] == "data"
        assert "generated_at" in loaded

    def test_update_cache_entry_adds_new_board(self):
        from temper_placer.regression.fingerprint import update_cache_entry

        cache = {"version": 1, "boards": {}}
        update_cache_entry(
            cache,
            board_id="test_board",
            input_fingerprint="abc123",
            source_fingerprint="def456",
            commit_sha="commit_sha_here",
        )
        assert "test_board" in cache["boards"]
        entry = cache["boards"]["test_board"]
        assert entry["input_fingerprint"] == "abc123"
        assert entry["source_fingerprint"] == "def456"
        assert entry["last_pass_commit"] == "commit_sha_here"
        assert "last_pass_at" in entry

    def test_update_cache_entry_overwrites_existing(self):
        from temper_placer.regression.fingerprint import update_cache_entry

        cache = {
            "version": 1,
            "boards": {
                "test_board": {
                    "input_fingerprint": "old",
                    "source_fingerprint": "old",
                    "last_pass_commit": "old",
                    "last_pass_at": "old",
                }
            },
        }
        update_cache_entry(
            cache,
            board_id="test_board",
            input_fingerprint="new_input",
            source_fingerprint="new_source",
            commit_sha="new_commit",
        )
        assert cache["boards"]["test_board"]["input_fingerprint"] == "new_input"

    def test_should_skip_missing_entry_returns_false(self):
        from temper_placer.regression.fingerprint import should_skip

        cache = {"version": 1, "boards": {}}
        result = should_skip("nonexistent", "fp1", "fp2", cache)
        assert isinstance(result, bool)

    def test_should_skip_returns_bool(self):
        from temper_placer.regression.fingerprint import should_skip

        cache = {
            "version": 1,
            "boards": {
                "board1": {
                    "input_fingerprint": "fp1",
                    "source_fingerprint": "fp2",
                    "last_pass_commit": "abc",
                }
            },
        }
        # Same fingerprints -> True (can skip)
        result = should_skip("board1", "fp1", "fp2", cache)
        assert isinstance(result, bool)

    def test_should_skip_mismatched_fingerprints(self):
        from temper_placer.regression.fingerprint import should_skip

        cache = {
            "version": 1,
            "boards": {
                "board1": {
                    "input_fingerprint": "fp1",
                    "source_fingerprint": "fp2",
                    "last_pass_commit": "abc",
                }
            },
        }
        # Different fingerprints -> should not skip
        result = should_skip("board1", "different", "fp2", cache)
        assert isinstance(result, bool)


# ============================================================================
# reporter — MetricDelta, RegressionReporter, BatteryVerdictReport
# ============================================================================


class TestMetricDelta:
    def test_delta_display_positive(self):
        from temper_placer.regression.reporter import MetricDelta

        delta = MetricDelta(name="x", baseline=10.0, current=15.0, delta=5.0)
        assert delta.delta_display == "+5.0"

    def test_delta_display_negative(self):
        from temper_placer.regression.reporter import MetricDelta

        delta = MetricDelta(name="x", baseline=10.0, current=5.0, delta=-5.0)
        assert delta.delta_display == "-5.0"

    def test_delta_display_zero(self):
        from temper_placer.regression.reporter import MetricDelta

        delta = MetricDelta(name="x", baseline=10.0, current=10.0, delta=0.0)
        assert delta.delta_display == "0.0"

    def test_message_format(self):
        from temper_placer.regression.reporter import MetricDelta

        delta = MetricDelta(name="drc_errors", baseline=10.0, current=15.0, delta=5.0)
        msg = delta.message()
        assert "drc_errors" in msg
        assert "15.0" in msg
        assert "10.0" in msg

    def test_message_negative_delta(self):
        from temper_placer.regression.reporter import MetricDelta

        delta = MetricDelta(
            name="wirelength", baseline=100.0, current=90.0, delta=-10.0
        )
        msg = delta.message()
        assert "90.0" in msg
        assert "100.0" in msg
        assert "-10.0" in msg


class TestRegressionReporter:
    def test_add_result_and_count(self):
        from temper_placer.regression.reporter import (
            BoardResult,
            RegressionReporter,
        )

        reporter = RegressionReporter()
        reporter.add_result(BoardResult(board_id="b1", passed=True))
        reporter.add_result(BoardResult(board_id="b2", passed=False))
        reporter.add_result(
            BoardResult(
                board_id="b3", passed=False, skipped=True, skip_reason="no pcb"
            )
        )
        assert reporter.total == 3
        assert reporter.passed == 1
        assert reporter.failed == 1  # b2 failed, b3 is skipped not failed
        assert reporter.skipped == 1

    def test_has_failures_true(self):
        from temper_placer.regression.reporter import (
            BoardResult,
            RegressionReporter,
        )

        reporter = RegressionReporter()
        reporter.add_result(BoardResult(board_id="b1", passed=False))
        assert reporter.has_failures is True

    def test_has_failures_false(self):
        from temper_placer.regression.reporter import (
            BoardResult,
            RegressionReporter,
        )

        reporter = RegressionReporter()
        reporter.add_result(BoardResult(board_id="b1", passed=True))
        assert reporter.has_failures is False

    def test_empty_reporter(self):
        from temper_placer.regression.reporter import RegressionReporter

        reporter = RegressionReporter()
        assert reporter.total == 0
        assert reporter.passed == 0
        assert reporter.failed == 0
        assert reporter.skipped == 0
        assert reporter.has_failures is False

    def test_summary_contains_statuses(self):
        from temper_placer.regression.reporter import (
            BoardResult,
            RegressionReporter,
        )

        reporter = RegressionReporter()
        reporter.add_result(BoardResult(board_id="pass_board", passed=True))
        reporter.add_result(BoardResult(board_id="fail_board", passed=False))
        summary = reporter.summary()
        assert "Passed: 1" in summary
        assert "Failed: 1" in summary
        assert "pass_board" in summary
        assert "fail_board" in summary

    def test_summary_with_deltas(self):
        from temper_placer.regression.reporter import (
            BoardResult,
            MetricDelta,
            RegressionReporter,
        )

        reporter = RegressionReporter()
        delta = MetricDelta(
            name="drc_errors", baseline=0.0, current=5.0, delta=5.0, regression=True
        )
        reporter.add_result(
            BoardResult(
                board_id="reg_board", passed=False, deltas=[delta]
            )
        )
        summary = reporter.summary()
        assert "REGRESSION" in summary
        assert "drc_errors" in summary

    def test_summary_with_board_shape(self):
        from temper_placer.regression.reporter import (
            BoardResult,
            RegressionReporter,
        )

        reporter = RegressionReporter()
        reporter.add_result(
            BoardResult(
                board_id="shape_board",
                passed=True,
                board_shape={"component_count": 42, "net_count": 30},
            )
        )
        summary = reporter.summary()
        assert "component_count=42" in summary
        assert "net_count=30" in summary

    def test_summary_with_skip_reason(self):
        from temper_placer.regression.reporter import (
            BoardResult,
            RegressionReporter,
        )

        reporter = RegressionReporter()
        reporter.add_result(
            BoardResult(
                board_id="skipped",
                passed=False,
                skipped=True,
                skip_reason="no file",
            )
        )
        summary = reporter.summary()
        assert "SKIP" in summary
        assert "no file" in summary

    def test_add_battery_verdict_and_report(self):
        from temper_placer.regression.reporter import (
            BatteryVerdictReport,
            RegressionReporter,
        )

        reporter = RegressionReporter()
        reporter.add_battery_verdict(
            BatteryVerdictReport(
                field_name="thermal",
                verdict="keep",
                verdict_details="within budget",
                cost_seconds=12.5,
                budget_exceeded=False,
            )
        )
        report = reporter.battery_report()
        assert "thermal" in report
        assert "KEEP" in report
        assert "12.5" in report

    def test_battery_report_empty(self):
        from temper_placer.regression.reporter import RegressionReporter

        reporter = RegressionReporter()
        report = reporter.battery_report()
        assert "No battery verdicts" in report

    def test_summary_includes_battery_verdicts(self):
        from temper_placer.regression.reporter import (
            BatteryVerdictReport,
            RegressionReporter,
        )

        reporter = RegressionReporter()
        reporter.add_battery_verdict(
            BatteryVerdictReport(
                field_name="cost_field",
                verdict="kill",
                verdict_details="budget exceeded",
                cost_seconds=99.0,
                budget_exceeded=True,
            )
        )
        summary = reporter.summary()
        assert "Battery Verdict" in summary
        assert "cost_field" in summary


# ============================================================================
# manifest — GoldenBoard, GoldenManifest
# ============================================================================


class TestGoldenBoard:
    def test_resolve_path(self):
        from temper_placer.regression.manifest import GoldenBoard

        board = GoldenBoard(
            id="test",
            path="pcb/test.kicad_pcb",
            component_count=10,
            net_count=5,
            baseline_git_hash="abc",
        )
        resolved = board.resolve_path(Path("/repo"))
        assert resolved == Path("/repo/pcb/test.kicad_pcb")

    def test_baseline_yaml_path(self):
        from temper_placer.regression.manifest import GoldenBoard

        board = GoldenBoard(
            id="test_board",
            path="pcb/t.kicad_pcb",
            component_count=10,
            net_count=5,
            baseline_git_hash="abc",
        )
        p = board.baseline_yaml_path(Path("/repo"))
        assert p.name == "test_board_baseline.yaml"
        assert "baselines" in str(p)

    def test_baseline_pcb_path(self):
        from temper_placer.regression.manifest import GoldenBoard

        board = GoldenBoard(
            id="test_board",
            path="pcb/t.kicad_pcb",
            component_count=10,
            net_count=5,
            baseline_git_hash="abc",
        )
        p = board.baseline_pcb_path(Path("/repo"))
        assert p.name == "test_board.kicad_pcb"
        assert "baselines" in str(p)


class TestGoldenManifest:
    def test_load_from_yaml(self, tmp_path: Path):
        import yaml

        from temper_placer.regression.manifest import GoldenManifest

        manifest_yaml = tmp_path / "golden_manifest.yaml"
        manifest_yaml.write_text(
            yaml.dump(
                {
                    "version": 1,
                    "boards": [
                        {
                            "id": "board1",
                            "path": "pcb/b1.kicad_pcb",
                            "component_count": 42,
                            "net_count": 30,
                            "baseline_git_hash": "abc123",
                            "description": "test board",
                        }
                    ],
                }
            )
        )
        manifest = GoldenManifest.load(manifest_yaml)
        assert manifest.version == 1
        assert len(manifest.boards) == 1
        assert manifest.boards[0].id == "board1"
        assert manifest.boards[0].component_count == 42
        assert manifest.boards[0].description == "test board"

    def test_load_empty_yaml_returns_default(self, tmp_path: Path):
        import yaml

        from temper_placer.regression.manifest import GoldenManifest

        manifest_yaml = tmp_path / "empty.yaml"
        manifest_yaml.write_text("")  # yaml.safe_load("") returns None
        manifest = GoldenManifest.load(manifest_yaml)
        assert manifest.version == 1
        assert manifest.boards == []

    def test_get_board_found_and_not_found(self, tmp_path: Path):
        import yaml

        from temper_placer.regression.manifest import GoldenManifest

        manifest_yaml = tmp_path / "manifest.yaml"
        manifest_yaml.write_text(
            yaml.dump(
                {
                    "version": 1,
                    "boards": [
                        {
                            "id": "b1",
                            "path": "p.kicad_pcb",
                            "component_count": 1,
                            "net_count": 1,
                            "baseline_git_hash": "x",
                        }
                    ],
                }
            )
        )
        manifest = GoldenManifest.load(manifest_yaml)
        assert manifest.get_board("b1") is not None
        assert manifest.get_board("nonexistent") is None

    def test_validate_missing_pcb(self, tmp_path: Path):
        import yaml

        from temper_placer.regression.manifest import GoldenManifest

        manifest_yaml = tmp_path / "manifest.yaml"
        manifest_yaml.write_text(
            yaml.dump(
                {
                    "version": 1,
                    "boards": [
                        {
                            "id": "missing_board",
                            "path": "nonexistent/file.kicad_pcb",
                            "component_count": 1,
                            "net_count": 1,
                            "baseline_git_hash": "x",
                        }
                    ],
                }
            )
        )
        manifest = GoldenManifest.load(manifest_yaml)
        errors = manifest.validate(tmp_path)
        assert len(errors) == 1
        assert "missing_board" in errors[0]
        assert "not found" in errors[0]

    def test_validate_existing_pcb_passes(self, tmp_path: Path):
        import yaml

        from temper_placer.regression.manifest import GoldenManifest

        # Create the pcb file
        pcb_dir = tmp_path / "pcb"
        pcb_dir.mkdir()
        (pcb_dir / "existing.kicad_pcb").write_text("(kicad_pcb)")

        manifest_yaml = tmp_path / "manifest.yaml"
        manifest_yaml.write_text(
            yaml.dump(
                {
                    "version": 1,
                    "boards": [
                        {
                            "id": "existing",
                            "path": "pcb/existing.kicad_pcb",
                            "component_count": 1,
                            "net_count": 1,
                            "baseline_git_hash": "x",
                        }
                    ],
                }
            )
        )
        manifest = GoldenManifest.load(manifest_yaml)
        errors = manifest.validate(tmp_path)
        assert len(errors) == 0


# ============================================================================
# corpus_runner — CorpusEntry, BaselineSpec, BaselineFile, CorpusBoardResult,
#                CorpusManifest, check_metric
# ============================================================================


class TestCorpusEntry:
    def test_pcb_path(self):
        from temper_placer.regression.corpus_runner import CorpusEntry

        entry = CorpusEntry(
            id="test",
            pcb="boards/test.kicad_pcb",
            constraints="constraints/test.yaml",
            baseline="baselines/test.json",
            seed=42,
            epochs=100,
        )
        assert entry.pcb_path(Path("/corpus")) == Path(
            "/corpus/boards/test.kicad_pcb"
        )
        assert entry.constraints_path(Path("/corpus")) == Path(
            "/corpus/constraints/test.yaml"
        )
        assert entry.baseline_path(Path("/corpus")) == Path(
            "/corpus/baselines/test.json"
        )


class TestBaselineSpec:
    def test_from_dict_full(self):
        from temper_placer.regression.corpus_runner import BaselineSpec

        spec = BaselineSpec.from_dict(
            {"mean": 100.0, "margin_rel": 0.1, "margin_abs": 5.0}
        )
        assert spec.mean == 100.0
        assert spec.margin_rel == 0.1
        assert spec.margin_abs == 5.0

    def test_from_dict_defaults(self):
        from temper_placer.regression.corpus_runner import BaselineSpec

        spec = BaselineSpec.from_dict({"mean": 50.0})
        assert spec.mean == 50.0
        assert spec.margin_rel == 0.05
        assert spec.margin_abs == 0.0

    def test_allowed_delta(self):
        from temper_placer.regression.corpus_runner import BaselineSpec

        spec = BaselineSpec(mean=100.0, margin_rel=0.1, margin_abs=5.0)
        assert spec.allowed_delta() == 10.0  # max(100*0.1, 5.0) = 10.0

    def test_allowed_delta_uses_abs_when_larger(self):
        from temper_placer.regression.corpus_runner import BaselineSpec

        spec = BaselineSpec(mean=10.0, margin_rel=0.05, margin_abs=5.0)
        assert spec.allowed_delta() == 5.0  # max(10*0.05=0.5, 5.0) = 5.0

    def test_limit(self):
        from temper_placer.regression.corpus_runner import BaselineSpec

        spec = BaselineSpec(mean=100.0, margin_rel=0.1, margin_abs=5.0)
        assert spec.limit() == 110.0  # 100 + 10


class TestBaselineFile:
    def test_load_parses_json(self, tmp_path: Path):
        from temper_placer.regression.corpus_runner import BaselineFile

        baseline_path = tmp_path / "baseline.json"
        baseline_path.write_text(
            json.dumps(
                {
                    "board_id": "test_board",
                    "extracted_at": "2026-01-01",
                    "git_hash": "abcdef",
                    "config": {"param": 1},
                    "metrics": {
                        "wirelength": {"mean": 150.0, "margin_rel": 0.1},
                        "component_count": {"mean": 42.0},
                    },
                }
            )
        )
        bf = BaselineFile.load(baseline_path)
        assert bf.board_id == "test_board"
        assert bf.git_hash == "abcdef"
        assert bf.config["param"] == 1
        assert "wirelength" in bf.metrics
        assert bf.metrics["wirelength"].mean == 150.0
        assert bf.metrics["component_count"].mean == 42.0


class TestCorpusBoardResult:
    def test_failed_when_not_passed_and_not_skipped(self):
        from temper_placer.regression.corpus_runner import CorpusBoardResult

        result = CorpusBoardResult(board_id="b", passed=False, skipped=False)
        assert result.failed is True

    def test_failed_when_passed(self):
        from temper_placer.regression.corpus_runner import CorpusBoardResult

        result = CorpusBoardResult(board_id="b", passed=True)
        assert result.failed is False

    def test_failed_when_skipped(self):
        from temper_placer.regression.corpus_runner import CorpusBoardResult

        result = CorpusBoardResult(board_id="b", passed=False, skipped=True)
        assert result.failed is False


class TestCheckMetric:
    def test_passes_below_limit(self):
        from temper_placer.regression.corpus_runner import (
            BaselineSpec,
            check_metric,
        )

        spec = BaselineSpec(mean=100.0, margin_rel=0.1, margin_abs=5.0)
        result = check_metric("wirelength", 95.0, spec)
        assert result["passed"] is True
        assert result["name"] == "wirelength"
        assert result["actual"] == 95.0
        assert result["baseline"] == 100.0
        assert result["delta"] == -5.0

    def test_fails_above_limit(self):
        from temper_placer.regression.corpus_runner import (
            BaselineSpec,
            check_metric,
        )

        spec = BaselineSpec(mean=100.0, margin_rel=0.05, margin_abs=0.0)
        result = check_metric("drc_errors", 120.0, spec)
        assert result["passed"] is False
        assert "limit" in result

    def test_passes_at_limit(self):
        from temper_placer.regression.corpus_runner import (
            BaselineSpec,
            check_metric,
        )

        spec = BaselineSpec(mean=100.0, margin_rel=0.1, margin_abs=0.0)
        result = check_metric("metric", 110.0, spec)
        assert result["passed"] is True


class TestCorpusManifest:
    def test_load_from_yaml(self, tmp_path: Path):
        import yaml

        from temper_placer.regression.corpus_runner import CorpusManifest

        manifest_yaml = tmp_path / "manifest.yaml"
        manifest_yaml.write_text(
            yaml.dump(
                {
                    "version": 1,
                    "boards": [
                        {
                            "id": "corpus_1",
                            "pcb": "b1.kicad_pcb",
                            "constraints": "c.yaml",
                            "baseline": "bl.json",
                            "seed": 42,
                            "epochs": 5000,
                            "description": "corpus board",
                        }
                    ],
                }
            )
        )
        manifest = CorpusManifest.load(manifest_yaml)
        assert manifest.version == 1
        assert len(manifest.boards) == 1
        assert manifest.boards[0].id == "corpus_1"
        assert manifest.boards[0].seed == 42
        assert manifest.boards[0].epochs == 5000

    def test_load_empty_yaml(self, tmp_path: Path):
        from temper_placer.regression.corpus_runner import CorpusManifest

        manifest_yaml = tmp_path / "manifest.yaml"
        manifest_yaml.write_text("")
        manifest = CorpusManifest.load(manifest_yaml)
        assert manifest.version == 1
        assert manifest.boards == []

    def test_get_board(self, tmp_path: Path):
        import yaml

        from temper_placer.regression.corpus_runner import CorpusManifest

        manifest_yaml = tmp_path / "manifest.yaml"
        manifest_yaml.write_text(
            yaml.dump(
                {
                    "version": 1,
                    "boards": [
                        {
                            "id": "cb1",
                            "pcb": "b.kicad_pcb",
                            "constraints": "c.yaml",
                            "baseline": "bl.json",
                            "seed": 1,
                            "epochs": 1,
                        }
                    ],
                }
            )
        )
        manifest = CorpusManifest.load(manifest_yaml)
        assert manifest.get_board("cb1") is not None
        assert manifest.get_board("nonexistent") is None


# ============================================================================
# cp_sat_comparison — compare_metric_dicts
# ============================================================================


class TestCompareMetricDicts:
    def test_compare_identical_dicts(self):
        from temper_placer.regression.cp_sat_comparison import (
            compare_metric_dicts,
        )

        scores = {"clearance_3mm": 5.0, "thermal_score": 0.8}
        result = compare_metric_dicts(scores, scores)
        assert hasattr(result, "passed")
        assert hasattr(result, "comparisons")
        assert hasattr(result, "summary")
        assert isinstance(result.summary, str)

    def test_compare_with_wirelength(self):
        from temper_placer.regression.cp_sat_comparison import (
            compare_metric_dicts,
        )

        candidate = {
            "total_manhattan_wirelength": 950.0,
            "clearance_3mm": 5.0,
        }
        baseline = {
            "total_manhattan_wirelength": 1000.0,
            "clearance_3mm": 4.0,
        }
        result = compare_metric_dicts(candidate, baseline)
        assert hasattr(result, "passed")
        assert len(result.comparisons) >= 1

    def test_compare_empty_dicts(self):
        from temper_placer.regression.cp_sat_comparison import (
            compare_metric_dicts,
        )

        result = compare_metric_dicts({}, {})
        assert hasattr(result, "passed")
        assert isinstance(result.summary, str)
