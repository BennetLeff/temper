"""MetricsObserver: bridges stage-complete events to PipelineMetricsRecord JSONL.

U1 from the pipeline observability plan.  Implements ProgressObserver to
emit per-stage metrics into a time-series JSONL file, with cross-validation,
canary integrity checks, and schema validation hooks.

This module is a delegation shim. ``MetricsObserver``, ``CanaryCheckError``
and ``CrossValidationError`` are Rust in the ``temper-orchestration`` crate
(Phase-C residual of the Rust orchestration engine, plan 2026-08-09-001,
module home ``metrics``; bit-identical parity pinned by
``tests/pipeline/test_phase_c_tail_rust_differential.py`` against the
verbatim pre-migration oracle ``tests/pipeline/_metrics_observer_py_oracle.py``).
The schema-validator and metrics-recorder call-backs stay single-source in
their owning modules (``regression.schema_validator`` /
``regression.metrics_recorder``). The public API is unchanged: the two
exception classes and the observer.
"""

from __future__ import annotations

import temper_orchestration as _rs

CrossValidationError = _rs.CrossValidationError
CanaryCheckError = _rs.CanaryCheckError
MetricsObserver = _rs.MetricsObserver

__all__ = [
    "CanaryCheckError",
    "CrossValidationError",
    "MetricsObserver",
]
