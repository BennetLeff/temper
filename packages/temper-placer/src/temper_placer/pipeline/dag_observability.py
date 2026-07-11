"""Observability: progress observers, stage events, and execution log."""

from __future__ import annotations

import dataclasses
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


class ProgressObserver(Protocol):
    """Protocol for observing DAG engine lifecycle events."""

    def on_stage_start(self, stage_name: str, iteration: int, context: dict[str, Any]) -> None: ...
    def on_stage_complete(self, stage_name: str, duration_s: float, outputs: dict[str, Any]) -> None: ...
    def on_stage_skip(self, stage_name: str, reason: str) -> None: ...
    def on_stage_error(self, stage_name: str, error: Exception) -> None: ...
    def on_feedback_triggered(self, contract_name: str, from_stage: str, to_stage: str,
                                attempt: int) -> None: ...
    def on_pipeline_complete(self, success: bool, total_duration_s: float,
                               stage_timings: dict[str, float]) -> None: ...

    def on_epoch(self, stage_name: str, epoch: int, loss: float) -> None: ...


@dataclass
class StageEvent:
    name: str
    kind: str
    iteration: int = 0
    duration_s: float = 0.0
    reason: str = ""
    outputs: dict[str, Any] | None = None
    error: str | None = None
    feedback_contract: str | None = None
    feedback_attempt: int | None = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class PipelineExecutionLog:
    dag_topology: list[dict[str, Any]] = field(default_factory=list)
    stage_order: list[str] = field(default_factory=list)
    stage_timings: dict[str, float] = field(default_factory=dict)
    retry_counts: dict[str, int] = field(default_factory=dict)
    feedback_activations: list[dict[str, Any]] = field(default_factory=list)
    success: bool = False
    total_duration_s: float = 0.0
    events: list[StageEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dag_topology": self.dag_topology,
            "stage_order": self.stage_order,
            "stage_timings": self.stage_timings,
            "retry_counts": self.retry_counts,
            "feedback_activations": self.feedback_activations,
            "success": self.success,
            "total_duration_s": self.total_duration_s,
            "events": [_event_to_dict(e) for e in self.events],
        }


def _event_to_dict(event: StageEvent) -> dict[str, Any]:
    d = dataclasses.asdict(event)
    return {k: v for k, v in d.items() if v is not None}


def write_execution_log_json(exec_log: PipelineExecutionLog, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "pipeline_execution.json"
    with open(path, "w") as f:
        json.dump(exec_log.to_dict(), f, indent=2)
    return path
