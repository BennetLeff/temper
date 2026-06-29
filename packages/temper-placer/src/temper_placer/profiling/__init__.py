"""CI profiling harness — per-module performance profiling for time-series metrics.

Public API:
    profile_pipeline(board_id, commit) -> list[PipelineMetricsRecord]
    profile_loss_functions(board_id, commit) -> list[PipelineMetricsRecord]
    profile_router_benchmark(commit) -> list[PipelineMetricsRecord]

Pipeline instrumentation (Plan 015):
    PipelineProfiler — context-manager profiler for auto-instrumenting pipeline stages
    ProfileReport — hierarchical timing report with JSON output and PipelineMetricsRecord adapter
    StageTiming — per-stage wall/cpu timing with optional sub-step breakdown

All functions emit PipelineMetricsRecord-compatible dataclasses with
module, board, stage, and metrics fields for direct JSONL recording.
"""

from .instrumentation import PipelineProfiler, ProfileReport, StageTiming
from .pipeline_metrics import (
    profile_loss_functions,
    profile_pipeline,
    profile_router_benchmark,
)

__all__ = [
    "PipelineProfiler",
    "ProfileReport",
    "StageTiming",
    "profile_pipeline",
    "profile_loss_functions",
    "profile_router_benchmark",
]
