# ORACLE COPY -- DO NOT EDIT, DO NOT "FIX".
#
# Verbatim copy of the bodies of
#   packages/temper-placer/src/temper_placer/pipeline/dag_types.py
# as they existed at commit 5747d2df6 (origin/main, the pre-migration pin for
# the Rust orchestration engine Phase-C residual slice).
#
# This is the R1a behavioural oracle for the Rust Stage-engine port in
# packages/temper-orchestration/src/dag_types.rs (plan 2026-08-09-001,
# Phase-C residual). It must keep the ORIGINAL pure-Python semantics forever,
# including any warts. If a differential test fails, the Rust side is wrong
# until proven otherwise -- never edit this file to make a test pass.
#
# test_oracle_body_matches_pinned_digest (in
# tests/pipeline/test_phase_c_tail_rust_differential.py) recomputes the
# sha256 of everything below the marker and fails if this file drifts.
# --- BEGIN PINNED BODY ---
"""Shared runtime types for the DAG pipeline engine.

DataContext, StageResult, error hierarchy, and the StageHandler protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist

DataContext = dict[str, Any]


class PipelineState(Protocol):
    """Minimal protocol for pipeline state passed between stages.

    Stages that read additional fields can refine this with a narrower
    Protocol or use hasattr checks in their ``__call__``.
    """

    board: Board
    netlist: Netlist
    constraints: Any
    loops: list[Any]
    deterministic_result: Any | None
    placement_state: Any | None
    routing_result: Any | None
    thermal_anchoring_applied: bool
    physics_report: Any | None
    preflight_report: Any | None


@dataclass
class StageResult:
    outputs: dict[str, Any] = field(default_factory=dict)
    duration_s: float = 0.0

    @classmethod
    def success(cls, outputs: dict[str, Any] | None = None) -> StageResult:
        return cls(outputs=outputs or {}, duration_s=0.0)


class StageHandler(Protocol):
    """Protocol for stage handler callables.

    (state: PipelineState, context: DataContext) -> StageResult
    """

    def __call__(self, state: PipelineState, context: DataContext) -> StageResult: ...


class DAGError(Exception):
    """Base exception for DAG pipeline errors."""


class DAGCycleError(DAGError):
    def __init__(self, cycle: list[str]) -> None:
        self.cycle = cycle
        super().__init__(f"Cycle detected in DAG: {' -> '.join(cycle)}")


class DAGMissingDependencyError(DAGError):
    def __init__(self, key: str, requiring_stage: str) -> None:
        self.key = key
        self.requiring_stage = requiring_stage
        super().__init__(
            f"Stage '{requiring_stage}' requires key '{key}' "
            f"which no stage provides and is not a built-in config key"
        )


class DAGDuplicateStageError(DAGError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Duplicate stage name '{name}' in DAG manifest")


class StageTimeoutError(DAGError):
    def __init__(self, stage_name: str, timeout_s: float) -> None:
        self.stage_name = stage_name
        self.timeout_s = timeout_s
        super().__init__(f"Stage '{stage_name}' timed out after {timeout_s:.1f}s")


class FeedbackExhaustedError(DAGError):
    def __init__(self, contract_name: str, stage_name: str, attempts: int) -> None:
        self.contract_name = contract_name
        self.stage_name = stage_name
        self.attempts = attempts
        super().__init__(
            f"Feedback contract '{contract_name}' exhausted after "
            f"{attempts} retriggers on stage '{stage_name}'"
        )


class DAGExprError(DAGError):
    """Error evaluating a skip expression at runtime."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class DAGExprSyntaxError(DAGError):
    """Error parsing a skip expression."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
