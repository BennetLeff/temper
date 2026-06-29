"""Tests for U2: ClosureTest per-stage metrics recording via MetricsObserver."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from temper_placer.pipeline.dag_observability import PipelineExecutionLog
from temper_placer.pipeline.metrics_observer import MetricsObserver
from temper_placer.regression.closure_test import ClosureResult, ClosureTest
from temper_placer.regression.metrics_recorder import load_metrics


class TestClosureTestWithObserver:
    """U2: ClosureTest.run(observer=observer) emits per-stage metrics."""

    def _make_observer(self, tmp_path: Path) -> MetricsObserver:
        execution_log = PipelineExecutionLog()
        return MetricsObserver(
            tmp_path / "metrics",
            execution_log,
            board="test_board",
        )

    def test_run_with_observer_produces_nonzero_records(self, tmp_path: Path):
        """ClosureTest.run() with observer records parse/placement/routing/drc timings."""
        pcb_path = tmp_path / "test.kicad_pcb"
        pcb_path.write_text("(kicad_pcb)")

        observer = self._make_observer(tmp_path)

        # Mock parse, placement, routing, DRC to succeed with non-zero results
        with patch(
            "temper_placer.io.kicad_parser.parse_kicad_pcb_v6",
            return_value={"components": []},
        ), patch(
            "temper_placer.runner.resolve_and_run",
            side_effect=[
                # placement result
                MagicMock(data=MagicMock(iterations=5, cuts=10, placements={"U1": (0, 0)})),
                # routing result
                MagicMock(
                    data=MagicMock(
                        completion_rate=95.0,
                    )
                ),
            ],
        ), patch(
            "temper_placer.validation.drc_runner.run_drc",
            return_value=MagicMock(error_count=0, warning_count=1),
        ), patch(
            "temper_placer.deterministic.SIDECAR_FILENAME",
            "nonexistent_sidecar.json",
        ), patch(
            "temper_placer.deterministic.ChannelMap",
            MagicMock(),
        ), patch(
            "temper_placer.regression.closure_test._run_channel_analysis",
            return_value=0,
        ):
            test = ClosureTest(pcb_path=pcb_path)
            result = test.run(observer=observer)

        assert result.passed
        assert result.benders_iterations == 5
        assert result.router_completion_pct == 95.0

        metrics_path = tmp_path / "metrics" / "pipeline_metrics.jsonl"
        assert metrics_path.exists()

        records = load_metrics(metrics_path)
        assert len(records) >= 3, f"Expected >=3 records (parse+placement+routing+drc), got {len(records)}"

        stage_names = {r["stage_name"] for r in records}
        assert "parse" in stage_names
        assert "placement" in stage_names
        assert "routing" in stage_names
        assert "drc" in stage_names

        for r in records:
            assert r["stage"] == r["stage_name"]
            assert r["metrics"]["wall_time_ms"] >= 0
            assert r["metrics"]["__pipeline_liveness__"] == 42.0
            assert r["board"] == "test_board"

    def test_run_without_observer_works_unchanged(self, tmp_path: Path):
        """ClosureTest.run() without observer must not break existing behavior."""
        pcb_path = tmp_path / "test.kicad_pcb"
        pcb_path.write_text("(kicad_pcb)")

        with patch(
            "temper_placer.io.kicad_parser.parse_kicad_pcb_v6",
            return_value={"components": []},
        ), patch(
            "temper_placer.runner.resolve_and_run",
            side_effect=[
                MagicMock(data=MagicMock(iterations=3, cuts=6, placements={"U1": (0, 0)})),
                MagicMock(data=MagicMock(completion_rate=100.0)),
            ],
        ), patch(
            "temper_placer.validation.drc_runner.run_drc",
            return_value=MagicMock(error_count=0, warning_count=0),
        ), patch(
            "temper_placer.deterministic.SIDECAR_FILENAME",
            "nonexistent_sidecar.json",
        ), patch(
            "temper_placer.deterministic.ChannelMap",
            MagicMock(),
        ), patch(
            "temper_placer.regression.closure_test._run_channel_analysis",
            return_value=0,
        ):
            test = ClosureTest(pcb_path=pcb_path)
            result = test.run()

        assert result.passed
        assert result.benders_iterations == 3
        assert result.router_completion_pct == 100.0

    def test_observer_records_on_parse_failure(self, tmp_path: Path):
        """Observer still records the parse stage even on parse failure."""
        pcb_path = tmp_path / "test.kicad_pcb"
        pcb_path.write_text("(kicad_pcb)")

        observer = self._make_observer(tmp_path)

        with patch(
            "temper_placer.io.kicad_parser.parse_kicad_pcb_v6",
            side_effect=ValueError("bad PCB"),
        ):
            test = ClosureTest(pcb_path=pcb_path)
            result = test.run(observer=observer)

        assert not result.passed
        assert any("Parse failed" in e for e in result.errors)

        metrics_path = tmp_path / "metrics" / "pipeline_metrics.jsonl"
        assert metrics_path.exists()
        records = load_metrics(metrics_path)
        assert len(records) == 1
        assert records[0]["stage_name"] == "parse"
        assert records[0]["stage"] == "parse"
        assert records[0]["metrics"]["wall_time_ms"] >= 0

    def test_observer_preserves_canary(self, tmp_path: Path):
        """Every record written through the observer carries the canary value."""
        pcb_path = tmp_path / "test.kicad_pcb"
        pcb_path.write_text("(kicad_pcb)")

        observer = self._make_observer(tmp_path)

        with patch(
            "temper_placer.io.kicad_parser.parse_kicad_pcb_v6",
            return_value={"components": []},
        ), patch(
            "temper_placer.runner.resolve_and_run",
            side_effect=[
                MagicMock(data=MagicMock(iterations=1, cuts=0, placements={})),
                MagicMock(data=MagicMock(completion_rate=50.0)),
            ],
        ), patch(
            "temper_placer.validation.drc_runner.run_drc",
            return_value=MagicMock(error_count=0, warning_count=0),
        ), patch(
            "temper_placer.deterministic.SIDECAR_FILENAME",
            "nonexistent_sidecar.json",
        ), patch(
            "temper_placer.deterministic.ChannelMap",
            MagicMock(),
        ), patch(
            "temper_placer.regression.closure_test._run_channel_analysis",
            return_value=0,
        ):
            test = ClosureTest(pcb_path=pcb_path)
            test.run(observer=observer)

        metrics_path = tmp_path / "metrics" / "pipeline_metrics.jsonl"
        records = load_metrics(metrics_path)
        for r in records:
            assert r["metrics"]["__pipeline_liveness__"] == 42.0


class TestCIEntrypointObserverIntegration:
    """Verify ci_closure_test.py wires the observer end-to-end."""

    def test_ci_script_passes_observer_to_closure_test(self, tmp_path: Path, monkeypatch):
        """ci_closure_test.main() creates MetricsObserver and passes to ClosureTest.run()."""
        import sys

        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))

        pcb_path = tmp_path / "test.kicad_pcb"
        pcb_path.write_text("(kicad_pcb)")
        seed_path = tmp_path / "seed.json"
        seed_path.write_text('{"benders_seed": 42, "router_seed": 42}')
        metrics_dir = tmp_path / "metrics_out"

        # Simulate CLI args
        test_args = [
            "ci_closure_test.py",
            "--pcb", str(pcb_path),
            "--seed", str(seed_path),
            "--metrics-dir", str(metrics_dir),
        ]
        monkeypatch.setattr(sys, "argv", test_args)

        with patch(
            "temper_placer.io.kicad_parser.parse_kicad_pcb_v6",
            return_value={"components": []},
        ), patch(
            "temper_placer.runner.resolve_and_run",
            side_effect=[
                MagicMock(data=MagicMock(iterations=2, cuts=4, placements={"U1": (0, 0)})),
                MagicMock(data=MagicMock(completion_rate=80.0)),
            ],
        ), patch(
            "temper_placer.validation.drc_runner.run_drc",
            return_value=MagicMock(error_count=0, warning_count=0),
        ), patch(
            "temper_placer.deterministic.SIDECAR_FILENAME",
            "nonexistent_sidecar.json",
        ), patch(
            "temper_placer.deterministic.ChannelMap",
            MagicMock(),
        ), patch(
            "temper_placer.regression.closure_test._run_channel_analysis",
            return_value=0,
        ):
            from scripts.ci_closure_test import main

            exit_code = main()

        assert exit_code == 0
        metrics_path = metrics_dir / "pipeline_metrics.jsonl"
        assert metrics_path.exists()
        records = load_metrics(metrics_path)
        assert len(records) >= 3
        stage_names = {r["stage_name"] for r in records}
        assert "placement" in stage_names
        assert "routing" in stage_names
        assert "drc" in stage_names
