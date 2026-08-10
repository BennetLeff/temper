"""Functional, immutable trace for explainability.

This module provides a composable, immutable trace system for recording
decisions throughout the placement and routing pipeline.

Key features:
- Immutable: Trace objects are frozen, operations return new traces
- Monoid: Traces compose via + operator with identity element
- Lazy: Natural language generation only when queried
- Simple: Just (subject, value, because) tuples

Phase A, U8 (plan ``2026-08-09-001``): ``Entry`` / ``Trace`` are Rust
pyclasses in ``temper-orchestration`` (re-exported here) — the frozen-tuple
monoid semantics migrate with them; ``Trace.why`` keeps delegating to the
single-source ``temper-io-types`` NL-generation kernel.

Example:
    >>> trace = Trace.empty()
    >>> trace = trace.add("Q1", (45.2, 12.3), "Minimize commutation loop")
    >>> trace = trace.add("Q1", (43.8, 11.9), "Thermal edge constraint")
    >>> print(trace.why("Q1"))
    Q1 is at (43.8, 11.9) because:
      - Minimize commutation loop
      - Thermal edge constraint
"""

from __future__ import annotations

from temper_orchestration import (
    Entry,
    Trace,
)

__all__ = ["Entry", "Trace"]
