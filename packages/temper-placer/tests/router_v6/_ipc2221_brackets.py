"""Shared IPC-2221 voltage->creepage bracket data (single copy).

UNSOURCED -- NOW VERIFIED MISLABELED (flagged 2026-08-15, safety-assertion
audit; cross-validated 2026-08-15 against a recovered free copy of
IPC-2221 (1998) Table 6-1 -- see
docs/evidence/2026-08-15-pending-decisions.md item C): the values below
(0.13/0.25/0.5/0.8/1.25/1.6/3.2/6.4/8.0/12.0) appear in **no column** of
the real Table 6-1 at any row. The bracket *boundaries* are IPC-2221's
row structure (15/30/50/100/150/170/250/300 V); the *values* are from an
unidentified source (closest partial match: IPC-9592B's low-voltage
spacing 0.13/0.25; the 8.0/12.0 tail matches nothing recovered). Relative
to the real Table 6-1 (B2 external-uncoated column: 0.1/0.1/0.6/0.6/0.6/
1.25/1.25/1.25/2.5 + per-volt formulae above 500V), this table
**overestimates** at every row where it can win a max() -- i.e. the error
direction is conservative, never dangerous. Do NOT silently "correct" it
to the real IPC-2221 values: that would *lower* a live gate's floor
(weakening), and re-sourcing is a separate attributed decision with its
own proof discipline. Do not present these values as a sourced IPC-2221
figure.

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
