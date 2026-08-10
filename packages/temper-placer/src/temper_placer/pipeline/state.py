"""
Pipeline state and configuration for temper-placer.

This module defines the data structures passed between pipeline phases.

This module is a delegation shim. ``PipelinePhase``, ``PipelineConfig`` and
``PipelineState`` are Rust pyclasses in the ``temper-orchestration`` crate
(U4 of the Rust orchestration engine, plan 2026-08-09-001; bit-identical
parity pinned by ``tests/pipeline/test_pipeline_state_rust_differential.py``
against the verbatim pre-migration oracle
``tests/pipeline/_pipeline_state_py_oracle.py``). ``PipelineError`` stays a
Python exception. The public API is unchanged: the four names re-exported by
``temper_placer.pipeline``.
"""

from __future__ import annotations

import temper_orchestration as _rs

PipelinePhase = _rs.PipelinePhase
PipelineConfig = _rs.PipelineConfig
PipelineState = _rs.PipelineState


class PipelineError(Exception):
    """Exception raised when a pipeline phase fails."""

    def __init__(self, message: str, phase: PipelinePhase | None = None):
        super().__init__(message)
        self.phase = phase


__all__ = [
    "PipelineConfig",
    "PipelineError",
    "PipelinePhase",
    "PipelineState",
]
