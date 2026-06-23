"""PipelineRunner + data-flow validation + ``resolve_and_run``.

Provides sequential execution of ``PipelineStage`` instances with contract
validation, timing collection, and strategy dispatch with fallback.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.protocol import PipelineStage, StageInput, StageOutput

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DataFlowError(Exception):
    """Raised when a pipeline's ``requires``/``provides`` chain is broken."""

    def __init__(
        self,
        stage_name: str,
        missing_keys: list[str],
        available_keys: set[str],
    ) -> None:
        super().__init__(
            f"Stage '{stage_name}' requires keys {missing_keys} "
            f"but only {sorted(available_keys)} are available"
        )
        self.stage_name = stage_name
        self.missing_keys = missing_keys
        self.available_keys = available_keys


class StrategyExhaustedError(Exception):
    """Raised when ``resolve_and_run`` exhausts all strategies and fallback."""

    def __init__(
        self,
        phase: str,
        attempted_strategies: list[str],
        failure_chain: list[tuple[str, Exception]],
    ) -> None:
        msg = (
            f"All strategies exhausted for phase='{phase}': "
            f"{attempted_strategies}"
        )
        super().__init__(msg)
        self.phase = phase
        self.attempted_strategies = attempted_strategies
        self.failure_chain = failure_chain


# ---------------------------------------------------------------------------
# Schema validator (shared)
# ---------------------------------------------------------------------------


def _validate_schema(
    data: object,
    schema: dict[str, type],
    stage_name: str,
    schema_name: str,
) -> None:
    """Validate *data* against *schema*, raising ``ContractViolation`` on failure."""
    from temper_placer.protocol import ContractViolation

    for field_name, expected_type in schema.items():
        if not hasattr(data, field_name):
            raise ContractViolation(
                stage_name=stage_name,
                schema=schema_name,
                field_name=field_name,
                expected_type=expected_type,
                actual_type=None,
            )
        actual = getattr(data, field_name)
        if not isinstance(actual, expected_type):
            raise ContractViolation(
                stage_name=stage_name,
                schema=schema_name,
                field_name=field_name,
                expected_type=expected_type,
                actual_type=type(actual),
            )


# ---------------------------------------------------------------------------
# PipelineRunner
# ---------------------------------------------------------------------------


class PipelineRunner:
    """Execute an ordered list of ``PipelineStage`` instances sequentially.

    Validates the ``requires``/``provides`` data-flow DAG at construction time
    and enforces ``Contract`` schemas at runtime.
    """

    def __init__(self, stages: list["PipelineStage"]) -> None:
        self._stages = stages
        self._trace: list[tuple[str, float, bool | None]] = []
        self._ran = False
        _validate_data_flow(stages)

    def run(self, initial_input: "StageInput") -> "StageOutput":
        """Execute all stages in order, feeding output→input.

        Returns the final ``StageOutput`` with accumulated ``meta.timings``.
        """
        from temper_placer.protocol import StageOutput

        initial_input.meta.timestamp = time.time()
        inp = initial_input
        self._trace = []

        for stage in self._stages:
            _check_input_contract(stage, inp)

            t0 = time.perf_counter()
            out = stage.run(inp)
            dt = time.perf_counter() - t0

            out.meta.timings[stage.name] = dt
            # Forward timings accumulated so far
            for k, v in inp.meta.timings.items():
                if k not in out.meta.timings:
                    out.meta.timings[k] = v

            _check_output_contract(stage, out)

            out.contract_satisfied = (
                True
                if hasattr(stage, "contract") and stage.contract is not None
                else None
            )
            self._trace.append((stage.name, dt, out.contract_satisfied))
            inp = out

        self._ran = True
        return out if isinstance(out, StageOutput) else inp

    def trace(self) -> list[tuple[str, float, bool | None]]:
        """Return ``[(stage_name, elapsed_seconds, contract_satisfied), ...]``.

        Raises:
            RuntimeError: If ``run()`` has not been called yet.
        """
        if not self._ran:
            raise RuntimeError("trace() called before run()")
        return list(self._trace)


# ---------------------------------------------------------------------------
# Data-flow validation (construction-time)
# ---------------------------------------------------------------------------


def _validate_data_flow(stages: list["PipelineStage"]) -> None:
    """Check that every ``requires`` key is provided by a prior stage."""
    available: set[str] = set()
    for stage in stages:
        requires = getattr(stage, "requires", []) or []
        provides = getattr(stage, "provides", []) or []
        missing = [k for k in requires if k not in available]
        if missing:
            raise DataFlowError(stage.name, missing, available)
        available.update(provides)


# ---------------------------------------------------------------------------
# Per-stage contract checks
# ---------------------------------------------------------------------------


def _check_input_contract(stage: "PipelineStage", inp: "StageInput") -> None:
    contract = getattr(stage, "contract", None)
    if contract is None:
        return
    _validate_schema(inp.data, contract.input_schema, stage.name, "input")


def _check_output_contract(stage: "PipelineStage", out: "StageOutput") -> None:
    contract = getattr(stage, "contract", None)
    if contract is None:
        return
    _validate_schema(out.data, contract.output_schema, stage.name, "output")


# ---------------------------------------------------------------------------
# U5 — resolve_and_run
# ---------------------------------------------------------------------------


def resolve_and_run(
    phase: str,
    strategies: list[str],
    input: "StageInput",
    *,
    fallback: str | None = None,
) -> "StageOutput":
    """Try strategies in order with optional fallback.

    Each strategy name is first looked up as a composite; if not found it
    is treated as a single ``(phase, name)`` stage key.  Composites run
    all their stages through ``PipelineRunner``.

    Args:
        phase: Phase key for registry lookup.
        strategies: Ordered list of strategy names.  Each name may be either
            a composite name or a single ``(phase, name)`` key.
        input: Initial ``StageInput``.
        fallback: Final strategy name to try if all others fail.

    Returns:
        ``StageOutput`` from the first successful strategy.

    Raises:
        StrategyExhaustedError: When every strategy (including fallback) fails.
    """
    from temper_placer import strategy_registry

    failure_chain: list[tuple[str, Exception]] = []
    all_names = list(strategies)
    if fallback:
        all_names.append(fallback)

    for name in all_names:
        try:
            try:
                stages = strategy_registry.get_composite(name)
            except KeyError:
                stages = [strategy_registry.get(phase, name)]
            runner = PipelineRunner(stages)
            return runner.run(input)
        except Exception as exc:
            logger.warning("Strategy '%s' failed: %s", name, exc)
            failure_chain.append((name, exc))

    raise StrategyExhaustedError(phase, all_names, failure_chain)
