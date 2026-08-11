"""Observability: progress observers, stage events, and execution log.

This module is a delegation shim. ``StageEvent`` and ``PipelineExecutionLog``
are Rust pyclasses in the ``temper-orchestration`` crate (Phase-C residual of
the Rust orchestration engine, plan 2026-08-09-001, module home ``dag``;
bit-identical parity pinned by ``tests/pipeline/test_phase_c_tail_rust_differential.py``
against the verbatim pre-migration oracle
``tests/pipeline/_dag_observability_py_oracle.py``). ``ProgressObserver``
stays a Python Protocol (typing-only), and ``write_execution_log_json`` stays
Python (stdlib file-I/O + ``json.dump`` over the Rust ``to_dict()`` shape —
the ``explainability`` logger precedent). The public API is unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

import temper_orchestration as _rs

StageEvent = _rs.StageEvent
PipelineExecutionLog = _rs.PipelineExecutionLog


class ProgressObserver(Protocol):
    """Protocol for observing DAG engine lifecycle events."""

    def on_stage_start(self, stage_name: str, iteration: int, context: dict[str, Any]) -> None: ...
    def on_stage_complete(
        self, stage_name: str, duration_s: float, outputs: dict[str, Any]
    ) -> None: ...
    def on_stage_skip(self, stage_name: str, reason: str) -> None: ...
    def on_stage_error(self, stage_name: str, error: Exception) -> None: ...
    def on_feedback_triggered(
        self, contract_name: str, from_stage: str, to_stage: str, attempt: int
    ) -> None: ...
    def on_pipeline_complete(
        self, success: bool, total_duration_s: float, stage_timings: dict[str, float]
    ) -> None: ...

    def on_epoch(self, stage_name: str, epoch: int, loss: float) -> None: ...


def write_execution_log_json(exec_log: PipelineExecutionLog, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "pipeline_execution.json"
    with open(path, "w") as f:
        json.dump(exec_log.to_dict(), f, indent=2)
    return path
