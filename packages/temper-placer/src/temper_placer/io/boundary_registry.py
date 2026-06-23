from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

BOUNDARY_NAMES = ["semantic", "topological", "placement", "routing", "validation"]


@dataclass(frozen=True)
class BoundaryDef:
    """Definition of a stage boundary in a pipeline."""
    pipeline_class: str
    phase_name: str
    output_format: Literal["dsn", "ses", "json"]
    serialization_fn: str


BOUNDARIES: dict[str, BoundaryDef] = {
    "semantic": BoundaryDef(
        pipeline_class="PipelineOrchestrator",
        phase_name="semantic",
        output_format="dsn",
        serialization_fn="export_pcb",
    ),
    "topological": BoundaryDef(
        pipeline_class="PipelineOrchestrator",
        phase_name="topological",
        output_format="dsn",
        serialization_fn="export_pcb",
    ),
    "placement": BoundaryDef(
        pipeline_class="PipelineOrchestrator",
        phase_name="geometric",
        output_format="dsn",
        serialization_fn="export_pcb",
    ),
    "routing": BoundaryDef(
        pipeline_class="PipelineOrchestrator",
        phase_name="routing",
        output_format="dsn",
        serialization_fn="export_pcb",
    ),
    "validation": BoundaryDef(
        pipeline_class="PipelineOrchestrator",
        phase_name="output",
        output_format="dsn",
        serialization_fn="export_pcb",
    ),
}


class BoundaryRegistry:
    """Registry of pipeline stage boundaries for DSN/SES export."""

    @staticmethod
    def get_boundary(name: str) -> BoundaryDef:
        if name not in BOUNDARIES:
            raise KeyError(f"Unknown boundary '{name}'. Known: {', '.join(BOUNDARY_NAMES)}")
        return BOUNDARIES[name]

    @staticmethod
    def list_boundaries() -> list[str]:
        return list(BOUNDARY_NAMES)
