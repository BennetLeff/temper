"""Per-stage timing measurement contract for the regression gate.

Consumes PipelineProfiler from plan 015 to measure wall-clock timing
per pipeline stage across multiple runs. Provides TimingResult and
TimingReport dataclasses consumed by the CLI baseline/check commands.
"""

from __future__ import annotations

import time
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    from datetime import UTC, datetime
else:
    from datetime import datetime, timezone

    UTC = timezone.utc


def _repo_root() -> Path:
    """Return the git repository root."""
    return Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )


def _current_git_hash() -> str:
    """Return the current abbreviated git commit hash."""
    return subprocess.run(
        ["git", "rev-parse", "--short=12", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _resolve_board_path(board_id: str) -> Path:
    """Resolve a board ID to its .kicad_pcb path via golden_manifest.yaml."""
    from temper_placer.regression.manifest import GoldenManifest

    root = _repo_root()
    manifest_path = root / "power_pcb_dataset" / "golden_manifest.yaml"
    if not manifest_path.exists():
        raise FileNotFoundError(
            "golden_manifest.yaml not found at {}".format(manifest_path)
        )

    manifest = GoldenManifest.load(manifest_path)
    board_entry = manifest.get_board(board_id)
    if board_entry is None:
        available = [b.id for b in manifest.boards]
        raise ValueError(
            "Unknown board '{}'. Available: {}".format(board_id, ", ".join(available))
        )

    pcb_path = board_entry.resolve_path(root)
    if not pcb_path.exists():
        raise FileNotFoundError(
            "Board '{}' PCB not found at {}".format(board_id, pcb_path)
        )
    return pcb_path


@dataclass
class TimingResult:
    """Wall-clock timing measurement for a single pipeline stage."""

    board_id: str
    pipeline: str
    stage_name: str
    wall_ms: float
    n_runs: int
    individual_ms: list[float]

    def to_pipeline_metrics_record(self) -> "PipelineMetricsRecord":
        """Map this timing result to a PipelineMetricsRecord for JSONL storage.

        Uses module='pipeline-timing' so per-stage timings participate in
        Plan 010's time-series store, PR comparison, and dashboard.
        """
        from temper_placer.regression.metrics_recorder import PipelineMetricsRecord

        return PipelineMetricsRecord(
            board=self.board_id,
            stage=self.stage_name,
            module="pipeline-timing",
            git_commit=_current_git_hash(),
            metrics={
                "wall_ms_mean": self.wall_ms,
                "n_runs": self.n_runs,
                "wall_ms_min": min(self.individual_ms),
                "wall_ms_max": max(self.individual_ms),
            },
        )


@dataclass
class StageTimingEntry:
    """Single entry in a timing check report."""

    board: str
    pipeline: str
    stage: str
    baseline_ms: float
    current_ms: float
    delta_ms: float
    delta_pct: float
    threshold_ms: float
    passed: bool

    def to_pipeline_metrics_record(self) -> "PipelineMetricsRecord":
        """Map this check result to a PipelineMetricsRecord for JSONL trend storage."""
        from temper_placer.regression.metrics_recorder import PipelineMetricsRecord

        return PipelineMetricsRecord(
            board=self.board,
            stage=self.stage,
            module="pipeline-timing",
            metrics={
                "current_ms": round(self.current_ms, 3),
                "baseline_ms": round(self.baseline_ms, 3),
                "delta_ms": round(self.delta_ms, 3),
                "delta_pct": round(self.delta_pct, 1),
                "threshold_ms": round(self.threshold_ms, 3),
                "passed": 1.0 if self.passed else 0.0,
            },
        )


@dataclass
class TimingReport:
    """Full timing check report -- all stages vs baseline."""

    entries: list[StageTimingEntry] = field(default_factory=list)
    margin: float = 0.20
    passed: bool = True
    total_stages: int = 0
    failed_stages: int = 0

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "margin": self.margin,
            "total_stages": self.total_stages,
            "failed_stages": self.failed_stages,
            "entries": [
                {
                    "board": e.board,
                    "pipeline": e.pipeline,
                    "stage": e.stage,
                    "baseline_ms": round(e.baseline_ms, 3),
                    "current_ms": round(e.current_ms, 3),
                    "delta_ms": round(e.delta_ms, 3),
                    "delta_pct": round(e.delta_pct, 1),
                    "threshold_ms": round(e.threshold_ms, 3),
                    "passed": e.passed,
                }
                for e in self.entries
            ],
        }


def measure_stage_timing(
    stage_name: str,
    board_id: str,
    pipeline: str = "DeterministicPipeline",
    n_runs: int = 3,
) -> TimingResult:
    """Measure wall-clock timing for a single pipeline stage.

    Args:
        stage_name: Name of the stage to measure.
        board_id: Board ID from golden_manifest.yaml.
        pipeline: Pipeline name (only "DeterministicPipeline" currently).
        n_runs: Number of measurement runs (default 3).

    Returns:
        TimingResult with mean and individual wall-clock timings.

    Raises:
        ValueError: If the stage name is not found in the pipeline.
        FileNotFoundError: If the board or manifest is missing.
    """
    all_results = measure_all_stages(
        board_id=board_id, pipeline=pipeline, n_runs=n_runs
    )
    for result in all_results:
        if result.stage_name == stage_name:
            return result
    raise ValueError(
        "Stage '{}' not found in pipeline '{}' on board '{}'".format(
            stage_name, pipeline, board_id
        )
    )


def measure_all_stages(
    board_id: str,
    pipeline: str = "DeterministicPipeline",
    n_runs: int = 3,
) -> list[TimingResult]:
    """Measure wall-clock timing for all stages in a pipeline.

    Args:
        board_id: Board ID from golden_manifest.yaml.
        pipeline: Pipeline name (only "DeterministicPipeline" currently).
        n_runs: Number of measurement runs after warmup (default 3).

    Returns:
        List of TimingResult, one per stage, in pipeline execution order.
    """
    if pipeline != "DeterministicPipeline":
        raise ValueError(
            "Unsupported pipeline '{}'. Only 'DeterministicPipeline' is supported.".format(
                pipeline
            )
        )

    pcb_path = _resolve_board_path(board_id)

    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.deterministic import BoardState, create_legacy_pipeline

    parse_result = parse_kicad_pcb(pcb_path)
    netlist = parse_result.netlist
    board = parse_result.board

    pipeline_obj = create_legacy_pipeline()

    stage_names = [s.name for s in pipeline_obj.stages]

    state = BoardState(board=board, netlist=netlist)
    for stage in pipeline_obj.stages:
        state = stage.run(state)

    per_run_timings: list[dict[str, float]] = []

    for _ in range(n_runs):
        state = BoardState(board=board, netlist=netlist)
        run_timings: dict[str, float] = {}
        for stage in pipeline_obj.stages:
            t0 = time.perf_counter_ns()
            state = stage.run(state)
            wall_ms = (time.perf_counter_ns() - t0) / 1e6
            run_timings[stage.name] = wall_ms
        per_run_timings.append(run_timings)

    results: list[TimingResult] = []
    for name in stage_names:
        individual_ms = [run[name] for run in per_run_timings]
        mean_ms = sum(individual_ms) / len(individual_ms)
        results.append(
            TimingResult(
                board_id=board_id,
                pipeline=pipeline,
                stage_name=name,
                wall_ms=mean_ms,
                n_runs=n_runs,
                individual_ms=individual_ms,
            )
        )

    return results
