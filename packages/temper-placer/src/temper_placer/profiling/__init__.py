"""CI profiling harness — per-module performance profiling for time-series metrics.

Public API:
    profile_pipeline(board_id, commit) -> list[PipelineMetricsRecord]
    profile_loss_functions(board_id, commit) -> list[PipelineMetricsRecord]
    profile_router_benchmark(commit) -> list[PipelineMetricsRecord]

All functions emit PipelineMetricsRecord-compatible dataclasses with
module, board, stage, and metrics fields for direct JSONL recording.
"""

from .pipeline_metrics import (
    profile_loss_functions,
    profile_pipeline,
    profile_router_benchmark,
)

__all__ = [
    "profile_pipeline",
    "profile_loss_functions",
    "profile_router_benchmark",
]
