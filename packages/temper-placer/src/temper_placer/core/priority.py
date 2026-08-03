"""
Priority classification for placement and routing.

Defines priority levels that mirror the professional PCB design workflow:
1. Power stage (template-based, fixed)
2. Gate drivers (proximity-constrained)
3. High-speed interfaces (zone-constrained)
4. Auto-place (full optimization)

The data model is implemented in Rust as pyo3 pyclasses in the
``temper-design-bundle`` crate (the ``temper_design_bundle_python``
extension) — the Wave 4 Phase 2 "contracts-as-pyo3-pyclasses" pivot
(``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``,
D5 / Phase B, fifth migration). This module keeps the pre-migration public
API unchanged and re-exports the Rust pyclasses directly (the
pure-delegation pattern, mirroring ``core/loop.py``), while the
``POWER_STAGE_TEMPLATES`` data table and the ``classify_net_priority``
convenience wrapper stay Python (per the gates-migration precedent of
keeping non-data helpers in the delegation module).

Verification: bit-identical parity against the pinned pre-migration
implementation is asserted by
``tests/core/test_priority_rust_differential.py`` (oracle:
``tests/core/_priority_py_oracle.py``); the structural proof lives in
``packages/temper-design-bundle/VERIFICATION.md``.

API notes (deliberate, documented deviations from CPython):
- ``PlacementPriority``/``RoutingPriority`` are pyo3 pyclass enums. They
  replicate the Python ``IntEnum`` member surface (``name``/``value``,
  ``Cls(value)`` construction, ``repr`` ``<PlacementPriority.POWER: 1>``),
  but the members are NOT equal to their int value (``POWER == 1`` is
  False, where ``IntEnum`` returns True), cross-enum ``==`` between the two
  priorities is False where ``IntEnum`` falls back to int comparison, and
  class-level iteration (``for p in PlacementPriority:``) is NOT supported
  — pyo3 exposes no metaclass hook. No consumer in-repo relies on any of
  the three; recorded in ``packages/temper-design-bundle/VERIFICATION.md``.
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb

PlacementPriority = _tdb.PlacementPriority
RoutingPriority = _tdb.RoutingPriority
PlacementPhaseConfig = _tdb.PlacementPhaseConfig
RoutingPhaseConfig = _tdb.RoutingPhaseConfig
PriorityConfig = _tdb.PriorityConfig


# Pre-defined power stage templates
POWER_STAGE_TEMPLATES = {
    "half_bridge_vertical": {
        # Relative offsets from anchor (x, y) in mm
        "Q1": (0, 5),  # High-side IGBT
        "Q2": (0, -5),  # Low-side IGBT
        "D1": (-4, 5),  # High-side diode - TIGHTER (was -8)
        "D2": (-4, -5),  # Low-side diode - TIGHTER (was -8)
        "C_BUS1": (4, 5),  # Bus cap near Q1 - TIGHTER (was 8)
        "C_BUS2": (4, -5),  # Bus cap near Q2 - TIGHTER (was 8)
    },
    "half_bridge_horizontal": {
        "Q1": (-5, 0),
        "Q2": (5, 0),
        "D1": (-5, -8),
        "D2": (5, -8),
        "C_BUS1": (-5, 8),
        "C_BUS2": (5, 8),
    },
    "full_bridge": {
        "Q1": (-10, 5),  # High-side A
        "Q2": (-10, -5),  # Low-side A
        "Q3": (10, 5),  # High-side B
        "Q4": (10, -5),  # Low-side B
        "C_BUS1": (0, 8),
        "C_BUS2": (0, -8),
    },
}


def classify_net_priority(net_name: str) -> RoutingPriority:
    """Classify a net name into a routing priority.

    Module-level convenience wrapper around :meth:`PriorityConfig.classify_net`.
    Re-exported via :mod:`temper_placer.core` for backward compatibility.
    """
    return PriorityConfig().classify_net(net_name)
