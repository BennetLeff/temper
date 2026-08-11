"""Shared runtime types for the DAG pipeline engine.

DataContext, StageResult, error hierarchy, and the StageHandler protocol.

This module is a delegation shim. ``StageResult`` is a Rust pyclass in the
``temper-orchestration`` crate (Phase-C residual of the Rust orchestration
engine, plan 2026-08-09-001; bit-identical parity pinned by
``tests/pipeline/test_phase_c_tail_rust_differential.py`` against the
verbatim pre-migration oracle ``tests/pipeline/_dag_types_py_oracle.py``).
The ``DAGError`` hierarchy (including ``DAGExprError`` / ``DAGExprSyntaxError``
consumed by ``dag_expr.py``), the ``DataContext`` type alias and the
``PipelineState`` / ``StageHandler`` Protocols stay Python (exceptions and
typing-only constructs have no pyclass mapping, the U4 ``PipelineError``
precedent). The public API is unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

import temper_orchestration as _rs

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist

DataContext = dict[str, Any]

StageResult = _rs.StageResult


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
