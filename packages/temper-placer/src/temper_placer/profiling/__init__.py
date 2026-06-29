"""CI profiling harness — per-module performance profiling for time-series metrics.

Public API (Plan 010 — per-module profilers):
    profile_pipeline(board_id, commit) -> list[PipelineMetricsRecord]
    profile_loss_functions(board_id, commit) -> list[PipelineMetricsRecord]
    profile_router_benchmark(commit) -> list[PipelineMetricsRecord]

Public API (Plan 022 — per-stage timing regression gate):
    TimingResult, TimingReport, StageTimingEntry,
    measure_stage_timing, measure_all_stages

All functions emit PipelineMetricsRecord-compatible dataclasses with
module, board, stage, and metrics fields for direct JSONL recording.

Plan 015 (PipelineProfiler, ProfileReport) lives in .instrumentation;
Plan 022 (timing gate) lives in .timing_gate.
"""

from .pipeline_metrics import (
    profile_loss_functions,
    profile_pipeline,
    profile_router_benchmark,
)
from .timing_gate import (
    TimingReport,
    TimingResult,
    StageTimingEntry,
    measure_stage_timing,
    measure_all_stages,
)

__all__ = [
    "profile_pipeline",
    "profile_loss_functions",
    "profile_router_benchmark",
    "TimingResult",
    "TimingReport",
    "StageTimingEntry",
    "measure_stage_timing",
    "measure_all_stages",
]
