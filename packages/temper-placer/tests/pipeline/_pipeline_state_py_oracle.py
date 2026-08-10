# ORACLE COPY -- DO NOT EDIT, DO NOT "FIX".
#
# Verbatim copy of the bodies of
#   packages/temper-placer/src/temper_placer/pipeline/state.py
# as they existed at commit 57c083c0 (origin/main, the pre-migration pin for
# the Rust orchestration engine U4 slice -- the last commit touching the
# module was 0712b669, and the tree at the pin is byte-identical).
#
# This is the R1a behavioural oracle for the Rust Stage-engine port in
# packages/temper-orchestration/src/pipeline_state.rs (plan 2026-08-09-001,
# U4). It must keep the ORIGINAL pure-Python semantics forever, including
# any warts. If a differential test fails, the Rust side is wrong until
# proven otherwise -- never edit this file to make a test pass.
#
# test_oracle_body_matches_pinned_digest (in
# tests/pipeline/test_pipeline_state_rust_differential.py) recomputes the
# sha256 of everything below the marker and fails if this file drifts.
# --- BEGIN PINNED BODY ---
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
    # Deterministic sub-phases (BoundaryRegistry boundaries).
    ZONE_GEOMETRY = "zone_geometry"
    ZONE_ASSIGNMENT = "zone_assignment"
    SLOT_GENERATION = "slot_generation"
    COMPONENT_ASSIGNMENT = "component_assignment"
    APPLY_PLACEMENTS = "apply_placements"
    COURTYARD_CHECK = "courtyard_check"
    APPLY_PLACEMENTS_REAPPLY = "apply_placements_reapply"
    PLACEMENT_VALIDATION = "placement_validation"


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
    phase_timings: dict[PipelinePhase | str, float] = field(default_factory=dict)

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

    # Routing convergence tracking (used by convergence.py)
    _best_routed_nets: Any = None
    _best_routability: float | None = None
    _stall_count: int = 0
