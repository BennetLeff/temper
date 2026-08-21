"""Internal: shared data classes and helpers for kicad_writer.

Delegation shim over ``temper-io-types``' ``write_types`` submodule (Wave 4
Phase 3, formats/IO migration): the four write-result dataclasses are Rust
pyclasses and ``_get_footprint_reference`` is a thin wrapper over a Rust
pyfunction. All public names are preserved; ``kiutils`` is no longer imported
here (the R4 gate). The differential
``tests/io/test_write_types_rust_differential.py`` pins the Rust surface
against the verbatim pre-migration oracle
(``tests/io/_write_types_py_oracle.py``).

``_get_footprint_reference`` stays a one-line function rather than a
module-level binding so the Rust symbol is looked up at call time — the
delegation-proof convention (the shipped entry point must reach the Rust
kernel, which a captured reference would defeat).
"""

from __future__ import annotations

from temper_io_types import write_types as _RUST

WriteResult = _RUST.WriteResult
StrippingResult = _RUST.StrippingResult
PlacementUpdate = _RUST.PlacementUpdate
IsolationSlotResult = _RUST.IsolationSlotResult


def _get_footprint_reference(fp):
    """Extract reference designator from footprint (Rust kernel)."""
    return _RUST.get_footprint_reference_py(fp)
