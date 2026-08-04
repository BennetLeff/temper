"""Internal: shared data classes and helpers for kicad_writer.

Wave 4, Phase 3, candidate 4 — the write/export engine migrates to
``temper-io-types``' ``kicad_write`` module (plan
``docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md``, D5/Q1
duck-typed boundary). The result dataclasses are Rust pyclasses and
``_get_footprint_reference`` is the Rust kernel; this module is a
pure-delegation re-export. Parity is asserted by
``tests/io/test_kicad_write_rust_differential.py`` against the verbatim
pre-migration implementation pinned as ``_write_types_py_oracle.py``.
"""

from __future__ import annotations

from temper_io_types import (
    IsolationSlotResult,
    PlacementUpdate,
    StrippingResult,
    WriteResult,
)
from temper_io_types import (
    get_footprint_reference as _get_footprint_reference,
)

__all__ = [
    "WriteResult",
    "StrippingResult",
    "PlacementUpdate",
    "IsolationSlotResult",
    "_get_footprint_reference",
]
