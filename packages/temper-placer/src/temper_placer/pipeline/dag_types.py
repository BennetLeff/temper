"""Shared runtime types for the DAG pipeline engine.

DataContext, StageResult, error hierarchy, and the StageHandler protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

DataContext = dict[str, Any]


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

    def __call__(self, state: Any, context: DataContext) -> StageResult: ...


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
        super().__init__(f"Stage '{requiring_stage}' requires key '{key}' "
                         f"which no stage provides and is not a built-in config key")


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
        super().__init__(f"Feedback contract '{contract_name}' exhausted after "
                         f"{attempts} retriggers on stage '{stage_name}'")


class DAGExprError(DAGError):
    """Error evaluating a skip expression at runtime."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class DAGExprSyntaxError(DAGError):
    """Error parsing a skip expression."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
