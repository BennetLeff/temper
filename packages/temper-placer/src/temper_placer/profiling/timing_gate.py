"""Per-stage timing measurement contract for the regression gate.

Consumes PipelineProfiler from plan 015 to measure wall-clock timing
per pipeline stage across multiple runs. Provides TimingResult and
TimingReport dataclasses consumed by the CLI baseline/check commands.
"""

from __future__ import annotations

import contextlib
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.regression.metrics_recorder import PipelineMetricsRecord


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
            f"golden_manifest.yaml not found at {manifest_path}"
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
            f"Board '{board_id}' PCB not found at {pcb_path}"
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

    def to_pipeline_metrics_record(self) -> PipelineMetricsRecord:
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

    def to_pipeline_metrics_record(self) -> PipelineMetricsRecord:
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
    sub_steps: bool = False,
) -> TimingResult:
    """Measure wall-clock timing for a single pipeline stage.

    Args:
        stage_name: Name of the stage to measure.
        board_id: Board ID from golden_manifest.yaml.
        pipeline: Pipeline name ("DeterministicPipeline", "RouterV6Pipeline",
            or "PipelineOrchestrator").
        n_runs: Number of measurement runs (default 3).
        sub_steps: Passed through to measure_all_stages for sub-step capture.

    Returns:
        TimingResult with mean and individual wall-clock timings.

    Raises:
        ValueError: If the stage name is not found in the pipeline.
        FileNotFoundError: If the board or manifest is missing.
    """
    all_results = measure_all_stages(
        board_id=board_id, pipeline=pipeline, n_runs=n_runs, sub_steps=sub_steps
    )
    for result in all_results:
        if result.stage_name == stage_name:
            return result
    raise ValueError(
        f"Stage '{stage_name}' not found in pipeline '{pipeline}' on board '{board_id}'"
    )


def measure_all_stages(
    board_id: str,
    pipeline: str = "DeterministicPipeline",
    n_runs: int = 3,
    sub_steps: bool = False,
) -> list[TimingResult]:
    """Measure wall-clock timing for all stages in a pipeline.

    Args:
        board_id: Board ID from golden_manifest.yaml.
        pipeline: Pipeline name ("DeterministicPipeline", "RouterV6Pipeline",
            or "PipelineOrchestrator").
        n_runs: Number of measurement runs after warmup (default 3).
        sub_steps: If True and pipeline supports sub-steps, capture
            per-sub-step entries (e.g., RouterV6Pipeline stage2 micro-stages).

    Returns:
        List of TimingResult, one per stage, in pipeline execution order.
    """
    if pipeline == "DeterministicPipeline":
        return _measure_deterministic(board_id, n_runs)
    elif pipeline == "RouterV6Pipeline":
        return _measure_router_v6(board_id, n_runs, sub_steps=sub_steps)
    elif pipeline == "PipelineOrchestrator":
        return _measure_pipeline_orchestrator(board_id, n_runs)
    else:
        raise ValueError(
            f"Unsupported pipeline '{pipeline}'. "
            "Supported: DeterministicPipeline, RouterV6Pipeline, PipelineOrchestrator"
        )


def _measure_deterministic(board_id: str, n_runs: int) -> list[TimingResult]:
    """Measure DeterministicPipeline stages via per-stage manual timing."""
    pcb_path = _resolve_board_path(board_id)

    from temper_placer.deterministic import BoardState, create_legacy_pipeline
    from temper_placer.io.kicad_parser import parse_kicad_pcb

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
                pipeline="DeterministicPipeline",
                stage_name=name,
                wall_ms=mean_ms,
                n_runs=n_runs,
                individual_ms=individual_ms,
            )
        )

    return results


def _measure_router_v6(
    board_id: str, n_runs: int, sub_steps: bool = False
) -> list[TimingResult]:
    """Measure RouterV6Pipeline stages via PipelineProfiler instrumentation."""
    pcb_path = _resolve_board_path(board_id)

    from temper_placer.profiling.instrumentation import PipelineProfiler
    from temper_placer.router_v6.pipeline import RouterV6Pipeline

    _STAGES = ["stage1", "stage2", "stage3", "stage4", "stage5"]
    _SUB_STEPS = [
        "obstacle_map", "routing_space", "channel_skeleton",
        "channel_widths", "occupancy_grid", "layer_capacity",
        "routing_demand", "bottleneck_analysis",
    ]

    # Warmup run (no profiler)
    warmup = RouterV6Pipeline(verbose=False, enable_smoothing=False, enable_legalization=False)
    warmup.run(pcb_path)

    per_run_timings: list[dict[str, float]] = []
    per_sub_step_runs: list[dict[str, float]] = []

    for _ in range(n_runs):
        profiler = PipelineProfiler()
        pipeline_obj = RouterV6Pipeline(
            verbose=False,
            enable_smoothing=False,
            enable_legalization=False,
            profiler=profiler,
        )
        profiler.start()
        pipeline_obj.run(pcb_path)
        profiler.stop()

        run_timings: dict[str, float] = {}
        for stage_name in _STAGES:
            timing = profiler.report.stage_timings.get(stage_name)
            run_timings[stage_name] = timing.wall_time_ms if timing else 0.0
        per_run_timings.append(run_timings)

        if sub_steps:
            stage2_timing = profiler.report.stage_timings.get("stage2")
            sub_run: dict[str, float] = {}
            if stage2_timing and stage2_timing.sub_steps:
                for ssn in _SUB_STEPS:
                    ss = stage2_timing.sub_steps.get(ssn)
                    sub_run[ssn] = ss.wall_time_ms if ss else 0.0
            else:
                for ssn in _SUB_STEPS:
                    sub_run[ssn] = 0.0
            per_sub_step_runs.append(sub_run)

    results: list[TimingResult] = []

    for stage_name in _STAGES:
        individual_ms = [run.get(stage_name, 0.0) for run in per_run_timings]
        mean_ms = sum(individual_ms) / len(individual_ms)
        results.append(
            TimingResult(
                board_id=board_id,
                pipeline="RouterV6Pipeline",
                stage_name=stage_name,
                wall_ms=mean_ms,
                n_runs=n_runs,
                individual_ms=individual_ms,
            )
        )

    if sub_steps:
        for ssn in _SUB_STEPS:
            individual_ms = [run.get(ssn, 0.0) for run in per_sub_step_runs]
            mean_ms = sum(individual_ms) / len(individual_ms) if individual_ms else 0.0
            results.append(
                TimingResult(
                    board_id=board_id,
                    pipeline="RouterV6Pipeline",
                    stage_name=f"stage2.{ssn}",
                    wall_ms=mean_ms,
                    n_runs=n_runs,
                    individual_ms=individual_ms,
                )
            )

    return results


def _measure_pipeline_orchestrator(
    board_id: str, n_runs: int
) -> list[TimingResult]:
    """Measure PipelineOrchestrator phases via DAG engine timing."""
    pcb_path = _resolve_board_path(board_id)

    from temper_placer.pipeline.orchestrator import PipelineConfig, PipelineOrchestrator

    phase_names = [
        "input", "semantic", "topological", "preflight",
        "geometric", "routing", "refinement", "output",
    ]

    # Warmup run (JAX JIT compilation etc.)
    config = PipelineConfig(input_pcb=pcb_path, skip_routing=False, dry_run=False)
    orchestrator = PipelineOrchestrator(config)
    with contextlib.suppress(Exception):
        orchestrator.run()

    results: list[TimingResult] = []
    per_run_timings: list[dict[str, float]] = []

    class _TimingObserver:
        def __init__(self):
            self.stage_timings: dict[str, float] = {}

        def on_stage_start(self, *args, **kwargs) -> None:
            pass

        def on_stage_complete(self, stage_name, duration_s, _outputs) -> None:
            self.stage_timings[stage_name] = duration_s * 1000.0

        def on_stage_skip(self, *args, **kwargs) -> None:
            pass

        def on_stage_error(self, *args, **kwargs) -> None:
            pass

        def on_feedback_triggered(self, *args, **kwargs) -> None:
            pass

        def on_pipeline_complete(self, success, total_duration_s, stage_timings) -> None:
            pass

    for _ in range(n_runs):
        config = PipelineConfig(input_pcb=pcb_path, skip_routing=False, dry_run=False)
        orchestrator = PipelineOrchestrator(config)
        observer = _TimingObserver()
        orchestrator._engine.add_observer(observer)

        with contextlib.suppress(Exception):
            orchestrator.run()

        run_timings: dict[str, float] = {}
        for phase_name in phase_names:
            run_timings[phase_name] = observer.stage_timings.get(phase_name, 0.0)
        per_run_timings.append(run_timings)

    for phase_name in phase_names:
        individual_ms = [run.get(phase_name, 0.0) for run in per_run_timings]
        mean_ms = sum(individual_ms) / len(individual_ms) if individual_ms else 0.0
        results.append(
            TimingResult(
                board_id=board_id,
                pipeline="PipelineOrchestrator",
                stage_name=phase_name,
                wall_ms=mean_ms,
                n_runs=n_runs,
                individual_ms=individual_ms,
            )
        )

    return results
