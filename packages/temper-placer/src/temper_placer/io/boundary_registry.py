from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

BOUNDARY_NAMES = [
    "semantic", "topological", "placement", "routing", "validation",
    "zone_geometry", "zone_assignment", "slot_generation",
    "component_assignment", "apply_placements", "courtyard_check",
    "apply_placements_reapply", "placement_validation",
]

STAGE2_BOUNDARY_NAMES = [
    "zone_geometry", "zone_assignment", "slot_generation",
    "component_assignment", "apply_placements", "courtyard_check",
    "apply_placements_reapply", "placement_validation",
]


@dataclass(frozen=True)
class BoundaryDef:
    """Definition of a stage boundary in a pipeline."""
    pipeline_class: str
    phase_name: str
    output_format: Literal["dsn", "ses", "json"]
    serialization_fn: str
    stage_index: int = 0


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
    "zone_geometry": BoundaryDef(
        pipeline_class="DeterministicPipeline",
        phase_name="zone_geometry",
        output_format="dsn",
        serialization_fn="serialize_boardstate_to_dsn",
        stage_index=0,
    ),
    "zone_assignment": BoundaryDef(
        pipeline_class="DeterministicPipeline",
        phase_name="zone_assignment",
        output_format="dsn",
        serialization_fn="serialize_boardstate_to_dsn",
        stage_index=1,
    ),
    "slot_generation": BoundaryDef(
        pipeline_class="DeterministicPipeline",
        phase_name="slot_generation",
        output_format="dsn",
        serialization_fn="serialize_boardstate_to_dsn",
        stage_index=2,
    ),
    "component_assignment": BoundaryDef(
        pipeline_class="DeterministicPipeline",
        phase_name="component_assignment",
        output_format="dsn",
        serialization_fn="serialize_boardstate_to_dsn",
        stage_index=3,
    ),
    "apply_placements": BoundaryDef(
        pipeline_class="DeterministicPipeline",
        phase_name="apply_placements",
        output_format="dsn",
        serialization_fn="serialize_boardstate_to_dsn",
        stage_index=4,
    ),
    "courtyard_check": BoundaryDef(
        pipeline_class="DeterministicPipeline",
        phase_name="courtyard_check",
        output_format="dsn",
        serialization_fn="serialize_boardstate_to_dsn",
        stage_index=5,
    ),
    "apply_placements_reapply": BoundaryDef(
        pipeline_class="DeterministicPipeline",
        phase_name="apply_placements_reapply",
        output_format="dsn",
        serialization_fn="serialize_boardstate_to_dsn",
        stage_index=6,
    ),
    "placement_validation": BoundaryDef(
        pipeline_class="DeterministicPipeline",
        phase_name="placement_validation",
        output_format="json",
        serialization_fn="serialize_violations_to_json",
        stage_index=7,
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
