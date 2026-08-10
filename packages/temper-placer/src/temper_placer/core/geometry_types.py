"""
Geometry types shared between the deterministic pipeline and router_v6.

These are pure dataclass types with no dependencies on router_v6 or deterministic.
They serve as the lowest-level geometry vocabulary for pads, tracks, vias, and points.

Migrated to Rust pyclasses (Wave C, temper-design-bundle, ``geometry_contracts`` submodule).
This module is now a pure-delegation shim re-exporting the pyclasses under their
original Python names.

Wave 4 (unit ``core_graph_cluster``): the scalar numeric methods were previously
migrated to ``packages/temper-geometry/src/core_graph_geometry.rs``.
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb

from temper_placer.core._contract_dataclass_compat import (
    field as _contract_field,
)
from temper_placer.core._contract_dataclass_compat import (
    install_dataclass_fields as _install_dataclass_fields,
)

Point = _tdb.geometry_contracts.Point
Track = _tdb.geometry_contracts.Track
Via = _tdb.geometry_contracts.Via
Pad = _tdb.geometry_contracts.Pad

__all__ = ["Point", "Track", "Via", "Pad"]

# A pyclass is not a dataclass, and `dataclasses.replace()` / `dataclasses.fields()`
# are used across the deterministic stages and router_v6; pickling also needs a
# resolvable `__module__` (the pyclasses' real module, the extension's
# `geometry_contracts` submodule, is not importable standalone).  See
# `_contract_dataclass_compat` for the mechanism and `core/board.py` for the
# established precedent.  Each field spec mirrors the pinned pre-migration
# oracle (`tests/core/test_geometry_types_rust_differential.py`) field-for-field:
# annotation, literal default, and the init/repr flags.
_install_dataclass_fields(
    Point,
    (
        _contract_field("x", "float"),
        _contract_field("y", "float"),
    ),
    module=__name__,
)
_install_dataclass_fields(
    Track,
    (
        _contract_field("start", "Point"),
        _contract_field("end", "Point"),
        _contract_field("width", "float"),
        _contract_field("net", "str"),
        _contract_field("layer", "int"),
        _contract_field("id", "str", ""),
        _contract_field("diff_pair_companion", "str | None", None),
    ),
    module=__name__,
)
_install_dataclass_fields(
    Via,
    (
        _contract_field("center", "Point"),
        _contract_field("diameter", "float"),
        _contract_field("drill", "float"),
        _contract_field("net", "str"),
        _contract_field("id", "str", ""),
    ),
    module=__name__,
)
_install_dataclass_fields(
    Pad,
    (
        _contract_field("center", "Point"),
        _contract_field("shape", "str"),
        _contract_field("size", "tuple[float, float]"),
        _contract_field("net", "str"),
        _contract_field("layer", "int"),
        _contract_field("id", "str", ""),
        _contract_field("rotation", "float", 0.0),
        _contract_field("mask_expansion", "float", 0.1),
        _contract_field("is_pth", "bool", False),
    ),
    module=__name__,
)
