"""Observability: progress observers, stage events, and execution log."""

from __future__ import annotations

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
        }


class DAGToLegacyObserver:
    """Adapts ProgressObserver events to legacy PipelineOrchestrator callbacks."""

    def __init__(self, orchestrator: Any) -> None:
        self.orchestrator = orchestrator

    def on_stage_start(self, stage_name: str, _iteration: int, _context: dict[str, Any]) -> None:
        if self.orchestrator.on_phase_start:
            from temper_placer.pipeline.state import PipelinePhase
            try:
                phase = PipelinePhase(stage_name)
            except ValueError:
                phase = stage_name
            self.orchestrator.on_phase_start(phase, self.orchestrator.state)

    def on_stage_complete(self, stage_name: str, _duration_s: float, _outputs: dict[str, Any]) -> None:
        if self.orchestrator.on_phase_complete:
            from temper_placer.pipeline.state import PipelinePhase
            try:
                phase = PipelinePhase(stage_name)
            except ValueError:
                phase = stage_name
            self.orchestrator.on_phase_complete(phase, self.orchestrator.state)
        self._save_snapshot(stage_name)

    def _save_snapshot(self, stage_name: str) -> None:
        try:
            from temper_placer.io.snapshot import save_json_snapshot, save_svg_snapshot
            from temper_placer.pipeline.state import PipelinePhase
            config = self.orchestrator.config
            state = self.orchestrator.state
            if config.output_pcb:
                snapshot_dir = config.output_pcb.parent / "snapshots"
            else:
                snapshot_dir = Path("snapshots")
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            phase_order = [p.value for p in PipelinePhase]
            try:
                phase = PipelinePhase(stage_name)
            except ValueError:
                return
            try:
                phase_idx = phase_order.index(phase.value)
            except ValueError:
                phase_idx = 0
            prefix = f"{phase_idx:02d}_{phase.value}"
            if stage_name == "refinement":
                prefix += f"_iter{state.iteration}"
            json_path = snapshot_dir / f"{prefix}.json"
            svg_path = snapshot_dir / f"{prefix}.svg"
            save_json_snapshot(state, json_path)
            save_svg_snapshot(state, svg_path)
        except Exception:
            pass

    def on_stage_skip(self, stage_name: str, reason: str) -> None:
        pass

    def on_stage_error(self, stage_name: str, error: Exception) -> None:
        pass

    def on_feedback_triggered(self, _contract_name: str, _from_stage: str, _to_stage: str,
                               attempt: int) -> None:
        if self.orchestrator.on_iteration:
            self.orchestrator.on_iteration(attempt, self.orchestrator.state)

    def on_pipeline_complete(self, success: bool, total_duration_s: float,
                              stage_timings: dict[str, float]) -> None:
        pass


def write_execution_log_json(exec_log: PipelineExecutionLog, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "pipeline_execution.json"
    with open(path, "w") as f:
        json.dump(exec_log.to_dict(), f, indent=2)
    return path
