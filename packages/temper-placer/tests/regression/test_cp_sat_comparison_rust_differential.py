"""Wiring check: CP-SAT comparison kernel in Rust
(``temper_design_bundle_python.compare_metric_dicts``).

Wave 4 Phase 4 regression slice, then U4/U5 FREEZE retirement (batch 4):
the portable compute behind ``compare_metric_dicts`` (the Pareto-style
per-metric gate, the wirelength ratio/tolerance rule, the fixed-precision
detail strings, and the summary composition) is frozen into
``temper-design-bundle``'s golden corpus (``cp_sat_comparison.rs`` ::
``frozen_tests``, regenerate via
``scripts/oracle_freeze_specs/cp_sat_comparison.py``). The pinned oracle
(``_cp_sat_comparison_py_oracle.py``) was deleted by that freeze; the
oracle-comparison differential this file used to carry is superseded by
the frozen corpus.

What remains here is the Stage-7 WIRING check only: it proves the shipped
Python module actually delegates to the Rust kernel (catching the
RUST-EXISTS-UNWIRED state), by monkey-patching the pyfunction to raise.
"""

from __future__ import annotations

import pytest


def test_shipped_module_delegates_to_rust(monkeypatch):
    """The shipped shim must route through the Rust pyfunction.

    Patching ``temper_design_bundle_python.compare_metric_dicts`` to raise
    proves the call crosses FFI: if the shim ever regains a Python
    implementation of the comparison, this fails loudly.
    """
    import temper_design_bundle_python as _tdb

    from temper_placer.regression.cp_sat_comparison import compare_metric_dicts

    def _boom(*_a, **_k):
        raise RuntimeError("REACHED_RUST")

    monkeypatch.setattr(_tdb, "compare_metric_dicts", _boom)
    with pytest.raises(RuntimeError, match="REACHED_RUST"):
        compare_metric_dicts({"m": 2.0}, {"m": 1.0})
