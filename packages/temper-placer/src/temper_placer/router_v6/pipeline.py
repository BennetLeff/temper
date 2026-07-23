"""
Router V6 Pipeline: End-to-End Integration

Wires together Stages 0-4 of Router V6 topological architecture:
- Stage 0: Load PCB data
- Stage 1: Generate escape vias
- Stage 2: Channel extraction and analysis
- Stage 3: Topological routing (SAT-based)
- Stage 4: Geometric realization (A*)

Part of Phase 1.5: Integration & Validation

Implementation split across:
- ``_pipeline_core.py`` — ``RouterV6Pipeline`` class (config + orchestration)
- ``_pipeline_types.py`` — output dataclasses (Stage2Output, Stage3Output, etc.)
- ``_pipeline_grid.py`` — grid prep, Stage 2 channel analysis, resource bound
- ``_pipeline_route.py`` — routing dispatch (Stage 3 SAT, Stage 4 A*, Stage 5 post-process)
- ``_pipeline_verify.py`` — DRC fence, per-stage invariants, manufacturing checks
"""

from temper_placer.router_v6._pipeline_core import RouterV6Pipeline
from temper_placer.router_v6._pipeline_types import (
    ManufacturingDRCViolationError,
    RouterV6Result,
    Stage2Output,
    Stage3Output,
    Stage4Output,
)

__all__ = [
    "ManufacturingDRCViolationError",
    "RouterV6Pipeline",
    "RouterV6Result",
    "Stage2Output",
    "Stage3Output",
    "Stage4Output",
]
