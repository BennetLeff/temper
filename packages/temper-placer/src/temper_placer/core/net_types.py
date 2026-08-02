"""
Type-safe net classification and connectivity semantics.

The data model is implemented in Rust as pyo3 pyclasses in the
``temper-design-bundle`` crate (the ``temper_design_bundle_python``
extension) — the Wave 4 Phase 2 "contracts-as-pyo3-pyclasses" pivot
(``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``,
D5 / Phase B). This module keeps the pre-migration public API unchanged and
re-exports the Rust pyclasses directly (the pure-delegation pattern).

This module encodes PCB design rules into the type system, making it impossible
to misconfigure critical nets like ground (which MUST connect via planes) or
high-voltage nets (which MUST have creepage clearances).

Key Design Principles:
1. Ground nets connect via planes, NEVER via trace routing
2. Power rails use planes or wide pours with via arrays
3. High-voltage nets require specific clearances per IEC 60335
4. Signal nets can be trace-routed with appropriate widths

Usage in YAML:
    net_classes:
      GND:
        type: ground
        connectivity: plane
        target_layer: In1.Cu

      "+15V":
        type: power
        connectivity: plane
        target_layer: In2.Cu
        max_current_a: 2.0

      AC_L:
        type: high_voltage
        connectivity: copper_pour
        voltage_class: mains_240v
        creepage_mm: 6.0

      SPI_CLK:
        type: signal
        connectivity: trace
        impedance_ohm: 50

Verification: bit-identical parity against the pinned pre-migration
implementation is asserted by
``tests/core/test_net_types_rust_differential.py`` (oracle:
``tests/core/_net_types_py_oracle.py``); the structural proof lives in
``packages/temper-design-bundle/VERIFICATION.md``.
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb

NetType = _tdb.NetType
ConnectivityStrategy = _tdb.ConnectivityStrategy
VoltageClass = _tdb.VoltageClass
NetTypeSpec = _tdb.NetTypeSpec
NetClassification = _tdb.NetClassification

# Pre-defined specs for common net types (module-level constants, preserved).
GROUND_PLANE_SPEC = _tdb.GROUND_PLANE_SPEC
POWER_PLANE_SPEC = _tdb.POWER_PLANE_SPEC
MAINS_HV_SPEC = _tdb.MAINS_HV_SPEC
SIGNAL_SPEC = _tdb.SIGNAL_SPEC

__all__ = [
    "NetType",
    "ConnectivityStrategy",
    "VoltageClass",
    "NetTypeSpec",
    "NetClassification",
    "GROUND_PLANE_SPEC",
    "POWER_PLANE_SPEC",
    "MAINS_HV_SPEC",
    "SIGNAL_SPEC",
]
