"""Golden-board regression runner.

Runs all golden boards against frozen GPBM baselines and reports
pass/fail per board.
"""

from __future__ import annotations

import importlib.util
import statistics
from pathlib import Path

from temper_placer.regression.manifest import GoldenManifest
from temper_placer.regression.reporter import (
    BoardResult,
    MetricDelta,
    RegressionReporter,
)

# KiCad's DRC is not reproducible run-to-run on the production board --
# packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py documents
# shorting_items scattering by ~20 on a byte-identical file across repeated
# `kicad-cli pcb drc` invocations. A single reading here cannot distinguish a
# real regression from measurement noise, so drc_errors/drc_warnings are
# compared on the median of DRC_SAMPLE_RUNS samples, matching the discipline
# that test module uses (PRODUCTION_DRC_SAMPLE_RUNS = 5).
DRC_SAMPLE_RUNS = 5


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
            from types import SimpleNamespace

            import yaml as _yaml  # type: ignore[import-untyped]

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

        # component_count and net_count are DESCRIPTIONS of the board, not
        # quality metrics -- a board legitimately gains and loses parts and
        # nets as the design changes underneath it. Comparing them to a
        # frozen number stored in the baseline YAML guarantees a recurring
        # false failure on every legitimate board change: this exact
        # baseline was hand-corrected three times chasing that failure (see
        # docs/solutions/best-practices/stale-absolute-baseline-vs-mutable-board-2026-07-29.md).
        # They are measured live from the checked-in board on every run and
        # reported for visibility below; they never gate pass/fail. Real
        # quality ratchets (drc_errors, drc_warnings below) remain pinned.
        board_shape = {
            "component_count": current_component_count,
            "net_count": current_net_count,
        }

        deltas: list[MetricDelta] = []

        quality_available = (
            importlib.util.find_spec("temper_placer.metrics.quality_score") is not None
        )
        if quality_available:
            current_drc_errors = 0
            current_drc_warnings = 0

            if baseline.drc_available:
                try:
                    from temper_placer.validation._drc_api import run_drc

                    error_samples = []
                    warning_samples = []
                    for _ in range(DRC_SAMPLE_RUNS):
                        drc_result = run_drc(pcb_path)
                        error_samples.append(drc_result.error_count)
                        warning_samples.append(drc_result.warning_count)
                    current_drc_errors = int(statistics.median(error_samples))
                    current_drc_warnings = int(statistics.median(warning_samples))
                except Exception as e:
                    # drc_available: true means this board's baseline was
                    # measured WITH real DRC data -- an unmeasured run here
                    # must never silently read as a clean one. Falling back
                    # to a fabricated 0 would always pass against a real
                    # pinned threshold, quietly turning a genuine ratchet
                    # into a vacuous one (the exact failure this method
                    # exists to prevent -- see docs/solutions/best-practices/
                    # stale-absolute-baseline-vs-mutable-board-2026-07-29.md
                    # and docs/solutions/best-practices/
                    # falsify-the-fix-before-believing-it-2026-07-29.md).
                    # Fail the whole board instead of skipping the metric.
                    return BoardResult(
                        board_id=board_id,
                        passed=False,
                        warnings=warnings,
                        errors=[
                            f"DRC required for {board_id} (drc_available: true in "
                            f"the baseline) but kicad-cli DRC could not be run: "
                            f"{e!r}. This is a hard failure, not a skip -- an "
                            "unmeasured DRC run must never be silently treated "
                            "as a clean one. Ensure kicad-cli is installed and "
                            "on PATH in this job."
                        ],
                        board_shape=board_shape,
                    )

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
                errors=[
                    f"Regression detected for {board_id}: {msg}. "
                    "drc_errors/drc_warnings are genuine quality ratchets, not board "
                    "descriptions -- do not silently bump the baseline number to match. "
                    "Re-measure the DRC run, confirm the increase is explained by an "
                    "intentional, reviewed design change (not a placer/router "
                    "regression), and record that justification alongside the new "
                    f"number in {baseline_yaml.relative_to(self.repo_root)}."
                ],
                board_shape=board_shape,
            )

        return BoardResult(
            board_id=board_id,
            passed=True,
            deltas=deltas,
            warnings=warnings,
            board_shape=board_shape,
        )
