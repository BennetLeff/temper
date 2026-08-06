"""Pure dataclass types used by KiCad parsing — no temper_placer deps at runtime.

Extracting ``ParseResult``, ``ViaData``, ``TraceData``, and ``PadData`` here
breaks the ``router_v6 → io`` cycle: router_v6 modules can import these types
from ``io._kicad_types`` without pulling in ``io.kicad_parser`` (which has
lazy imports from ``router_v6.stage0_data``).

Migrated to Rust pyo3 pyclasses in ``temper_design_bundle_python.parse_engine``
(Wave 4 Phase 3 candidate 3, plan 2026-08-02-001). This module is a
pure-delegation re-export; the import cycle it breaks is unchanged. Bit-identical
parity (including the concrete type of every field and the dataclass repr/eq/
hash semantics) is asserted by
``tests/io/test_parse_engine_rust_differential.py`` against the verbatim
kiutils oracle (``tests/io/_parse_engine_py_oracle/``).
"""

import temper_design_bundle_python as _tdb

_rs = _tdb.parse_engine

TraceData = _rs.TraceData
PadData = _rs.PadData
ViaData = _rs.ViaData
ParseResult = _rs.ParseResult

__all__ = ["TraceData", "PadData", "ViaData", "ParseResult"]
