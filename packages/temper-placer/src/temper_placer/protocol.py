"""Unified Stage Protocol for temper-placer pipelines.

Defines the shared data containers (StageMeta, StageInput, StageOutput) and
the PipelineStage Protocol that allows stages from all three pipeline systems
to be composed without coupling to any specific backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# U1 — Core dataclasses
# ---------------------------------------------------------------------------


@dataclass
class StageMeta:
    """Shared metadata passed across pipeline stages.

    Carries seed, trace context, and accumulated per-stage timings across
    all adapters and the runner without coupling to any pipeline backend.

    Attributes:
        seed: Random seed for reproducibility.
        timestamp: ``time.time()`` at pipeline start.
        trace_context: Opaque dict for stage-specific configuration.
        timings: Per-stage wall-clock times keyed by stage name.
    """

    seed: int = 42
    timestamp: float = 0.0
    trace_context: dict[str, Any] = field(default_factory=dict)
    timings: dict[str, float] = field(default_factory=dict)


@dataclass
class StageInput:
    """Input container for a single pipeline stage.

    Attributes:
        data: Stage-specific payload (``ParsedPCB``, ``BoardState``,
            ``PipelineState``, etc.).  The Protocol does not constrain its type.
        meta: Shared metadata forwarded across stages.
    """

    data: Any = None
    meta: StageMeta = field(default_factory=StageMeta)


@dataclass
class StageOutput:
    """Output container from a single pipeline stage.

    Attributes:
        data: Stage-specific result.
        meta: Shared metadata (forwarded + annotated with timings).
        contract_satisfied: Whether the stage's ``Contract`` (if any) was
            satisfied.  ``None`` means no contract was declared.
    """

    data: Any = None
    meta: StageMeta = field(default_factory=StageMeta)
    contract_satisfied: bool | None = None


# ---------------------------------------------------------------------------
# U2 — PipelineStage Protocol + Contract
# ---------------------------------------------------------------------------


@dataclass
class Contract:
    """Schema-based contract for stage input/output validation.

    Each ``(field_name, expected_type)`` entry is checked at runtime by
    ``PipelineRunner`` via ``_validate_schema()``.  Validation is limited to
    field presence and ``isinstance`` checks — content-level validation is
    deferred.

    Attributes:
        input_schema: Mapping of required input field names to expected types.
        output_schema: Mapping of required output field names to expected types.
    """

    input_schema: dict[str, type] = field(default_factory=dict)
    output_schema: dict[str, type] = field(default_factory=dict)


class ContractViolation(Exception):
    """Raised when a stage's input or output fails a ``Contract`` check.

    Attributes:
        stage_name: Name of the stage that failed validation.
        schema: ``"input"`` or ``"output"``.
        field_name: The missing or wrongly-typed field.
        expected_type: The type declared in the contract.
        actual_type: The type actually observed (``None`` if missing).
    """

    def __init__(
        self,
        stage_name: str,
        schema: str,
        field_name: str,
        expected_type: type,
        actual_type: type | None = None,
    ) -> None:
        super().__init__(
            f"[{stage_name}] Contract violation on {schema} field "
            f"'{field_name}': expected {expected_type.__name__}, "
            f"got {actual_type.__name__ if actual_type else 'missing'}"
        )
        self.stage_name = stage_name
        self.schema = schema
        self.field_name = field_name
        self.expected_type = expected_type
        self.actual_type = actual_type


@runtime_checkable
class PipelineStage(Protocol):
    """Structural protocol for any pipeline stage.

    Stages from all three pipeline systems satisfy this protocol by
    structural subtyping — no inheritance required.

    Required:
        ``name: str`` — class attribute or property.
        ``run(self, input: StageInput) -> StageOutput``

    Optional (class-level):
        ``requires: list[str]`` — data-keys consumed (default ``[]``).
        ``provides: list[str]`` — data-keys produced (default ``[]``).
        ``contract: Contract | None`` — input/output schema (default ``None``).
    """

    name: str

    def run(self, input: StageInput) -> StageOutput: ...  # noqa: E704
