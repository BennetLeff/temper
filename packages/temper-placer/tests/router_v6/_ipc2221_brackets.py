"""Shared IPC-2221 voltage->creepage bracket data (single copy).

UNSOURCED (flagged 2026-08-15, safety-assertion audit): this bracket table
is hedged in-source as "(simplified)" and there is **no recovered IPC-2221
table anywhere in ``docs/``** -- the values are SNAPSHOT pins of the
implementation, not verified against primary text. Do not present them as
a sourced IPC-2221 figure; re-sourcing is a separate task.

This module is the single shared test-data copy. The implementation SSOT
is ``temper-geometry``'s ``creepage_check.rs``
``required_creepage_bracket`` (the Python ``_calculate_required_creepage``
in ``router_v6/creepage_check.py`` is a pure pyo3 delegation to it). Both
test files below derive their boundary cases from ``IPC2221_CREEPAGE_BRACKETS``
so the table exists in exactly one place:

- ``tests/router_v6/test_clearance_boundary.py`` -- exact bracket
  boundaries (bottom and top of each bracket) plus the >1000V extreme.
- ``tests/router_v6/test_creepage_boundary.py`` -- bracket tops and
  just-above-top epsilon cases.

Keep the values in lockstep with the Rust implementation; a change to one
without the other is a drift defect (mechanism #1 in the 2026-08-15
handoff: one fact, many homes).
"""

from __future__ import annotations

# (lo_volts, hi_volts, required_creepage_mm) -- inclusive lo, inclusive hi,
# matching `required_creepage_bracket`'s `<=` comparisons in
# temper-geometry/src/creepage_check.rs.
IPC2221_CREEPAGE_BRACKETS: list[tuple[int, int, float]] = [
    (0, 15, 0.13),
    (16, 30, 0.25),
    (31, 50, 0.50),
    (51, 100, 0.80),
    (101, 150, 1.25),
    (151, 170, 1.60),
    (171, 250, 3.20),
    (251, 300, 6.40),
    (301, 600, 8.00),
    (601, 1000, 12.00),
]
