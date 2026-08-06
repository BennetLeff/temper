"""
Loop-centric data model for power electronics PCB design.

The data model is implemented in Rust as pyo3 pyclasses in the
``temper-design-bundle`` crate (the ``temper_design_bundle_python``
extension) — the Wave 4 Phase 2 "contracts-as-pyo3-pyclasses" pivot
(``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``,
D5 / Phase B). This module keeps the pre-migration public API unchanged and
re-exports the Rust pyclasses directly (the pure-delegation pattern,
mirroring ``core/net_types.py``).

This module provides first-class representations of current loops, which are THE
critical abstraction for power electronics PCB layout. EMI and switching performance
are dominated by current loop areas:

- Commutation loop: DC+ -> high-side switch -> low-side switch -> DC- -> DC link cap
- Gate drive loops: Driver output -> gate -> emitter/source -> driver ground
- Bootstrap loop: Bootstrap diode -> bootstrap cap -> high-side supply

Minimizing these loop areas is the primary layout objective for power electronics.

Example usage:
    >>> from temper_placer.core.loop import Loop, LoopType, LoopEvent, LoopPriority
    >>>
    >>> # Define a gate drive loop
    >>> gate_loop = Loop(
    ...     name="gate_drive_high",
    ...     loop_type=LoopType.GATE_DRIVE_HIGH,
    ...     description="High-side IGBT gate drive loop",
    ...     components=["U_GATE_DRV", "Q1"],
    ...     max_area_mm2=50.0,
    ...     priority=LoopPriority.CRITICAL,
    ...     events=LoopEvent(di_dt=1e9, frequency_hz=50000),
    ... )
    >>>
    >>> gate_loop.involves_component("Q1")
    True

Verification: bit-identical parity against the pinned pre-migration
implementation is asserted by
``tests/core/test_loop_rust_differential.py`` (oracle:
``tests/core/_loop_py_oracle.py``); the structural proof lives in
``packages/temper-design-bundle/VERIFICATION.md``.

API notes (deliberate, documented deviations from CPython Enum):
- ``LoopType``/``LoopPriority`` are pyo3 pyclass enums. Value-based
  construction ``LoopType("commutation")`` works (same ``ValueError`` text
  as Python Enum), but class-level iteration (``for lt in LoopType:``) is
  NOT supported — pyo3 exposes no metaclass hook. Use
  ``LoopType.members()`` (declaration order) instead; ``io/loop_loader.py``
  is the adapted consumer.
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb

LoopType = _tdb.LoopType
LoopPriority = _tdb.LoopPriority
LoopEvent = _tdb.LoopEvent
LoopPin = _tdb.LoopPin
Loop = _tdb.Loop
LoopCollection = _tdb.LoopCollection

__all__ = [
    "LoopType",
    "LoopPriority",
    "LoopEvent",
    "LoopPin",
    "Loop",
    "LoopCollection",
]
