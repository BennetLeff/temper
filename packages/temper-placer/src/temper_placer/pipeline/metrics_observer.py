"""MetricsObserver: bridges stage-complete events to PipelineMetricsRecord JSONL.

U1 from the pipeline observability plan.  Implements ProgressObserver to
emit per-stage metrics into a time-series JSONL file, with cross-validation,
canary integrity checks, and schema validation hooks.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from temper_placer.pipeline.dag_observability import PipelineExecutionLog, ProgressObserver
from temper_placer.regression.metrics_recorder import PipelineMetricsRecord, record_metrics
from temper_placer.regression.schema_validator import SchemaValidator, SchemaValidationError

_LOGGER = logging.getLogger(__name__)

_CROSS_VALIDATION_TOLERANCE_S = 0.01
_CANARY_KEY = "__pipeline_liveness__"
_DEFAULT_CANARY_VALUE = 42.0


class CrossValidationError(ValueError):
    """Raised when stage timing cross-validation fails beyond tolerance."""


class CanaryCheckError(ValueError):
    """Raised when the canary integrity check detects pipeline corruption."""


class MetricsObserver:
    """Observes DAG pipeline stage completions and writes metrics to JSONL.

    Parameters
    ----------
    output_dir:
        Directory where ``pipeline_metrics.jsonl`` is written.
    execution_log:
        The engine's ``PipelineExecutionLog`` used for cross-validation.
    board:
        Board identifier for the metrics record (default ``"unknown"``).
    canary_value:
        Sentinel value injected into every record's metrics dict and
        verified on write to detect pipeline corruption.
    """

    def __init__(
        self,
        output_dir: str | Path,
        execution_log: PipelineExecutionLog,
        *,
        board: str = "unknown",
        canary_value: float = _DEFAULT_CANARY_VALUE,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.execution_log = execution_log
        self.board = board
        self._canary_value = canary_value
        self._stage_start_times: dict[str, float] = {}
        self._output_path = self.output_dir / "pipeline_metrics.jsonl"
        self._schema_validator = SchemaValidator()

    # -- ProgressObserver protocol ----------------------------------------

    def on_stage_start(self, stage_name: str, iteration: int, context: dict[str, Any]) -> None:
        self._stage_start_times[stage_name] = time.monotonic()

    def on_stage_complete(self, stage_name: str, duration_s: float, outputs: dict[str, Any]) -> None:
        wall_time_ms = int(duration_s * 1000)
        metrics: dict[str, float] = {
            "wall_time_ms": wall_time_ms,
            _CANARY_KEY: self._canary_value,
        }

        drc_delta: int | None = None
        if outputs and "drc_errors_before" in outputs and "drc_errors_after" in outputs:
            drc_delta = outputs["drc_errors_before"] - outputs["drc_errors_after"]

        record = PipelineMetricsRecord(
            board=self.board,
            stage=stage_name,
            stage_name=stage_name,
            metrics=metrics,
            drc_delta=drc_delta,
        )

        self._validate_schema(record)
        self._cross_validate_against(start_t = self._stage_start_times.pop(stage_name, None),
                                     stage_name = stage_name,
                                     caller_duration_s = duration_s)
        self._check_canary(record)
        self._write(record)

    def on_stage_skip(self, stage_name: str, reason: str) -> None:
        pass

    def on_stage_error(self, stage_name: str, error: Exception) -> None:
        pass

    def on_feedback_triggered(
        self,
        contract_name: str,
        from_stage: str,
        to_stage: str,
        attempt: int,
    ) -> None:
        pass

    def on_pipeline_complete(
        self,
        success: bool,
        total_duration_s: float,
        stage_timings: dict[str, float],
    ) -> None:
        pass

    # -- Internal: cross-validation ---------------------------------------

    def _cross_validate_against(
        self,
        *,
        start_t: float | None,
        stage_name: str,
        caller_duration_s: float,
    ) -> None:
        if start_t is not None:
            observer_duration_s = time.monotonic() - start_t
            if abs(caller_duration_s - observer_duration_s) > _CROSS_VALIDATION_TOLERANCE_S:
                raise CrossValidationError(
                    f"Timing mismatch for stage '{stage_name}': "
                    f"caller={caller_duration_s:.4f}s, "
                    f"observer={observer_duration_s:.4f}s "
                    f"(tolerance={_CROSS_VALIDATION_TOLERANCE_S}s)"
                )
            return
        expected = self.execution_log.stage_timings.get(stage_name)
        if expected is None:
            return
        if abs(caller_duration_s - expected) > _CROSS_VALIDATION_TOLERANCE_S:
            raise CrossValidationError(
                f"Timing mismatch for stage '{stage_name}': "
                f"observed={caller_duration_s:.4f}s, "
                f"logged={expected:.4f}s "
                f"(tolerance={_CROSS_VALIDATION_TOLERANCE_S}s)"
            )

    # -- Internal: schema validation --------------------------------------

    def _validate_schema(self, record: PipelineMetricsRecord) -> None:
        """Validate record metrics against the package-shipped schema.

        Raises ``SchemaValidationError`` on the first violation.  Runs
        before cross-validation so schema failures short-circuit the write
        path without reaching the cross-validation check.
        """
        self._schema_validator.validate(record.metrics)

    # -- Internal: canary -------------------------------------------------

    def _check_canary(self, record: PipelineMetricsRecord) -> None:
        canary = record.metrics.get(_CANARY_KEY)
        if canary != self._canary_value:
            raise CanaryCheckError(
                f"Expected canary value {self._canary_value}, got {canary}"
            )

    # -- Internal: write --------------------------------------------------

    def _write(self, record: PipelineMetricsRecord) -> None:
        record_metrics(record, self._output_path)
