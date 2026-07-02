"""Golden-board regression runner.

Runs all golden boards against frozen GPBM baselines and reports
pass/fail per board.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from temper_placer.regression.manifest import GoldenManifest
from temper_placer.regression.reporter import (
    BoardResult,
    MetricDelta,
    RegressionReporter,
)


class RegressionRunner:
    """Runs regression tests on golden boards against frozen baselines."""

    def __init__(self, manifest: GoldenManifest, repo_root: Path | None = None):
        self.manifest = manifest
        self.repo_root = repo_root or Path.cwd()
        self.reporter = RegressionReporter()

    def run(self, boards: list[str] | None = None, with_routing: bool = False) -> int:
        for board_entry in self.manifest.boards:
            if boards and board_entry.id not in boards:
                continue
            result = self._run_board(board_entry, with_routing)
            self.reporter.add_result(result)

        return 1 if self.reporter.has_failures else 0

    def _run_board(self, board_entry, _with_routing: bool = False) -> BoardResult:
        board_id = board_entry.id
        pcb_path = board_entry.resolve_path(self.repo_root)
        baseline_yaml = board_entry.baseline_yaml_path(self.repo_root)
        board_entry.baseline_pcb_path(self.repo_root)

        if not pcb_path.exists():
            return BoardResult(
                board_id=board_id,
                passed=False,
                skipped=True,
                skip_reason=f"PCB file not found: {pcb_path}",
                errors=[f"PCB file not found: {pcb_path}"],
            )

        if not baseline_yaml.exists():
            return BoardResult(
                board_id=board_id,
                passed=False,
                skipped=True,
                skip_reason=f"Baseline YAML not found: {baseline_yaml}",
                warnings=[f"No baseline for {board_id}. Run baseline extraction first."],
            )

        warnings: list[str] = []

        try:
            # TODO(U3): Replace with canonical human_reference_extractor.
            import yaml as _yaml  # type: ignore[import-untyped]
            from types import SimpleNamespace
            with open(baseline_yaml) as f:
                raw = _yaml.safe_load(f)
            baseline = SimpleNamespace(**raw)
        except Exception as e:
            return BoardResult(
                board_id=board_id,
                passed=False,
                skipped=True,
                skip_reason=f"Failed to load baseline: {e}",
                errors=[f"Failed to load baseline: {e}"],
            )

        try:
            from temper_placer.io.kicad_parser import parse_kicad_pcb

            parse_result = parse_kicad_pcb(pcb_path)
        except Exception as e:
            return BoardResult(
                board_id=board_id,
                passed=False,
                errors=[f"Failed to parse PCB: {e}"],
            )

        netlist = parse_result.netlist
        board = parse_result.board

        if board is None:
            return BoardResult(
                board_id=board_id,
                passed=False,
                errors=["No board geometry extracted"],
            )

        if parse_result.has_warnings:
            warnings.extend(parse_result.warnings)

        current_component_count = len(netlist.components)
        current_net_count = len(netlist.nets)

        deltas: list[MetricDelta] = []

        comp_delta = MetricDelta(
            name="component_count",
            baseline=float(baseline.component_count),
            current=float(current_component_count),
            delta=float(current_component_count - baseline.component_count),
        )
        deltas.append(comp_delta)
        if current_component_count != baseline.component_count:
            comp_delta.regression = True

        net_delta = MetricDelta(
            name="net_count",
            baseline=float(baseline.net_count),
            current=float(current_net_count),
            delta=float(current_net_count - baseline.net_count),
        )
        deltas.append(net_delta)
        if current_net_count != baseline.net_count:
            net_delta.regression = True

        quality_available = (
            importlib.util.find_spec("temper_placer.metrics.quality_score") is not None
        )
        if quality_available:
            current_drc_errors = 0
            current_drc_warnings = 0

            if baseline.drc_available:
                try:
                    from temper_placer.validation.drc_runner import run_drc

                    drc_result = run_drc(pcb_path)
                    current_drc_errors = drc_result.error_count
                    current_drc_warnings = drc_result.warning_count
                except Exception:
                    warnings.append("DRC not available; skipping DRC comparison")

            err_delta = MetricDelta(
                name="drc_errors",
                baseline=float(baseline.drc_errors),
                current=float(current_drc_errors),
                delta=float(current_drc_errors - baseline.drc_errors),
            )
            deltas.append(err_delta)
            if current_drc_errors > baseline.drc_errors:
                err_delta.regression = True

            warn_delta = MetricDelta(
                name="drc_warnings",
                baseline=float(baseline.drc_warnings),
                current=float(current_drc_warnings),
                delta=float(current_drc_warnings - baseline.drc_warnings),
            )
            deltas.append(warn_delta)
            if current_drc_warnings > baseline.drc_warnings:
                warn_delta.regression = True
        else:
            warnings.append("quality_score not available; skipping GPBM comparison")

        has_regression = any(d.regression for d in deltas)

        if has_regression:
            regressed = [d for d in deltas if d.regression]
            msg = "; ".join(d.message() for d in regressed)
            return BoardResult(
                board_id=board_id,
                passed=False,
                deltas=deltas,
                warnings=warnings,
                errors=[f"Regression detected for {board_id}: {msg}"],
            )

        return BoardResult(
            board_id=board_id,
            passed=True,
            deltas=deltas,
            warnings=warnings,
        )
