"""
Manufacturing tolerance models for PCB production.

This module provides tools to analyze the impact of manufacturing variability
(etching, drilling, layer registration) on the design.

The data model is implemented in Rust as pyo3 pyclasses in the
``temper-design-bundle`` crate (the ``temper_design_bundle_python``
extension) — Wave 4 Phase 4 leftovers slice (the manufacturing/tolerances
migration). This module keeps the pre-migration public API unchanged and
re-exports the Rust pyclasses directly (the pure-delegation pattern
established by ``core/loop.py``, ``core/priority.py`` and
``core/board.py``).

Verification: bit-identical parity against the pinned pre-migration
implementation — including the concrete Python type of every field and the
exact ``ValueError`` text for invalid enum values — is asserted by
``tests/manufacturing/test_tolerances_rust_differential.py`` (oracle:
``tests/manufacturing/_tolerances_py_oracle.py``) and the closed-form
properties in ``tests/manufacturing/test_tolerances_pbt.py``; the
structural proof lives in ``packages/temper-design-bundle/VERIFICATION.md``.

Deliberately NOT migrated (R3 verdict, named blocker)
-----------------------------------------------------
Nothing in this module stays Python: the whole surface is the five
pyclasses below. ``ToleranceAnalyzer``'s dict lookups, the fallback
constants (``0.05`` / ``0.1``), the ``2 * etch + reg`` arithmetic, and the
dataclass reprs are all reproduced bit-identically in Rust; the dict
fields remain real Python dicts (keyed by the pyclass enum members) so
CPython owns lookup/repr/insertion-order semantics.
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb

CopperWeight = _tdb.CopperWeight
LayerType = _tdb.LayerType
ToleranceTable = _tdb.ToleranceTable
FeatureTolerance = _tdb.FeatureTolerance
ToleranceAnalyzer = _tdb.ToleranceAnalyzer

__all__ = [
    "CopperWeight",
    "LayerType",
    "ToleranceTable",
    "FeatureTolerance",
    "ToleranceAnalyzer",
]
