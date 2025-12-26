"""
Pipeline state and configuration for temper-placer.

This module defines the data structures passed between pipeline phases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class PipelinePhase(Enum):
    """Enumeration of pipeline phases in execution order."""

    INPUT = "input"
    SEMANTIC = "semantic"
    TOPOLOGICAL = "topological"
    PREFLIGHT = "preflight"
    GEOMETRIC = "geometric"
    ROUTING = "routing"
    REFINEMENT = "refinement"
    OUTPUT = "output"


class PipelineError(Exception):
    """Exception raised when a pipeline phase fails."""

    def __init__(self, message: str, phase: PipelinePhase | None = None):
        super().__init__(message)
        self.phase = phase


@dataclass
class PipelineConfig:
    """Configuration for pipeline execution."""

    input_pcb: Path

    # Optional input files
    constraints_yaml: Path | None = None
    loops_yaml: Path | None = None

    # Optional output files
    output_pcb: Path | None = None
    output_report: Path | None = None
    output_trace: Path | None = None

    # Phase control
    skip_topological: bool = False
    skip_routing: bool = False
    skip_local_refinement: bool = False
    dry_run: bool = False

    # Optimization config
    epochs: int = 8000
    seed: int = 42
    max_movement_mm: float = 2.0

    # Iteration config
    max_iterations: int = 5
    routability_threshold: float = 0.85
    convergence_threshold: float = 0.01

    # Manufacturing
    fab_preset: str = "jlcpcb_standard"


@dataclass
class PipelineState:
    """State passed between pipeline phases."""

    config: PipelineConfig

    # Execution state
    current_phase: PipelinePhase = PipelinePhase.INPUT
    iteration: int = 0

    # Status
    success: bool = False
    failure_reason: str | None = None
    failed_phase: PipelinePhase | None = None

    # Timing
    elapsed_time_s: float = 0.0
    phase_timings: dict[PipelinePhase, float] = field(default_factory=dict)

    # Data populated by phases
    board: Any = None  # Board from core
    netlist: Any = None  # Netlist from core
    loops: list = field(default_factory=list)  # Loop definitions
    constraints: Any = None  # PCLConstraints
    deterministic_result: Any = None  # PlacementResult (NumPy)
    placement_state: Any = None  # PlacementState from optimizer
    routing_result: Any = None  # RoutingResult from routing
    physics_report: Any = None  # PhysicsReport
    preflight_report: Any = None  # PreflightReport
    decision_trace: Any = None  # DecisionTrace from explainability

    # Internal flags
    _refinement_complete: bool = False
