"""
Board and Zone data structures.

This module defines the PCB board geometry and placement zones:
- Board: Overall board dimensions, outline, mounting holes
- Zone: Named regions for component placement constraints
- LayerStackup: Layer definitions for routing estimation

The data model is implemented in Rust as pyo3 pyclasses in the
``temper-design-bundle`` crate (the ``temper_design_bundle_python``
extension) — Wave 4 **Phase 3, candidate 1**
(``docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md``). This
module keeps the pre-migration public API unchanged and re-exports the Rust
pyclasses directly (the pure-delegation pattern established by
``core/loop.py`` and ``core/priority.py``).

Verification: bit-identical parity against the pinned pre-migration
implementation — including the concrete Python type of every field and the
``float32`` dtype of every returned array — is asserted by
``tests/core/test_board_rust_differential.py`` (oracle:
``tests/core/_board_py_oracle.py``) and ``tests/core/test_board_pbt.py``;
the structural proof lives in
``packages/temper-design-bundle/VERIFICATION.md``.

Deliberately NOT migrated (R3 verdict, named blocker)
-----------------------------------------------------
``LayerIndex`` and its derived tables stay Python. ``LayerIndex`` is an
``IntEnum``, and its int-ness is load-bearing in-repo:
``router_v6/constraints_drc_oracle.py`` evaluates
``LayerIndex(layer) in INTERNAL_LAYERS``, ``deterministic/stages/_grid_hv.py``
keys ``LAYER_IDX_TO_NAME`` by it, and the already-migrated ``net_types.rs``
round-trips ``LayerIndex`` members through ``NetTypeSpec.target_layer``
where they are compared with ``==`` against layer-name strings. pyo3 cannot
produce a pyclass that subclasses ``int`` — variable-sized built-ins are not
valid ``extends=`` bases — so a Rust ``LayerIndex`` would compare unequal to
its own value and hash differently from the equal ``int``. That is a silent
behaviour change a value-level differential could pass while production
broke, so the enum, its tables, and the two predicates that dispatch on it
remain here. See ``packages/temper-design-bundle/VERIFICATION.md``.
"""

from __future__ import annotations

from enum import IntEnum
from typing import TypeAlias

import numpy as np
import temper_design_bundle_python as _tdb

from temper_placer.core._contract_dataclass_compat import (
    install_dataclass_fields as _install_dataclass_fields,
)

Array: TypeAlias = np.ndarray  # numpy alias replacing JAX Array post-JAX retirement

_rs = _tdb.board_contracts

MountingHole = _rs.MountingHole
Pad = _rs.Pad
Component = _rs.Component
Trace = _rs.Trace
Via = _rs.Via
Layer = _rs.Layer
LayerStackup = _rs.LayerStackup
Rect = _rs.Rect
Zone = _rs.Zone
GroundDomain = _rs.GroundDomain
Board = _rs.Board
side_to_layer_name = _rs.side_to_layer_name

# A pyclass is not a dataclass, and `dataclasses.replace()` is used across the
# deterministic stages. See `_contract_dataclass_compat` for the mechanism.
_install_dataclass_fields(MountingHole, ("position", "diameter", "keepout_radius"))
_install_dataclass_fields(Pad, ("position", "size", "shape", "layer", "number", "net_name"))
_install_dataclass_fields(
    Component,
    (
        "ref",
        "position",
        "rotation",
        "width",
        "height",
        "footprint",
        "pads",
        "layer",
        "fixed",
    ),
)
_install_dataclass_fields(Trace, ("start", "end", "width", "layer", "net"))
_install_dataclass_fields(
    Via, ("position", "drill", "width", "layers", "net", "is_diff_pair")
)
_install_dataclass_fields(Layer, ("name", "layer_type", "copper_weight", "is_routable"))
_install_dataclass_fields(LayerStackup, ("layers", "thickness"))
_install_dataclass_fields(Rect, ("x_min", "y_min", "x_max", "y_max"))
_install_dataclass_fields(
    Zone,
    (
        "name",
        "bounds",
        "net_classes",
        "components",
        "weight",
        "polygon",
        "layers",
        "max_size",
        "can_expand",
        "zone_type",
    ),
)
_install_dataclass_fields(GroundDomain, ("name", "bounds", "star_point"))
# `_zone_map` is `init=False` on the original dataclass: `replace()` must skip
# it and reject any attempt to pass it.
_install_dataclass_fields(
    Board,
    (
        "width",
        "height",
        "origin",
        "zones",
        "mounting_holes",
        "keepouts",
        "ground_domains",
        "layer_stackup",
        "outline_polygon",
        "_zone_map",
    ),
    non_init=("_zone_map",),
)


class LayerIndex(IntEnum):
    """
    Canonical 4-layer PCB layer index (IntEnum).

    Each member's `__str__` returns the standard KiCad name
    (`"F.Cu"`, `"In1.Cu"`, `"In2.Cu"`, `"B.Cu"`); the inherited
    `Enum.name` returns the Python identifier (`"F_CU"`, etc.).
    Use `__str__(layer)` for the KiCad name and `layer.name` for the
    identifier — do not conflate them.

    Not migrated to Rust — see the module docstring's R3 note.
    """

    F_CU = 0
    IN1_CU = 1
    IN2_CU = 2
    B_CU = 3

    def __str__(self) -> str:
        return _LAYER_INDEX_TO_KICAD_NAME[self]

    @classmethod
    def from_name(cls, name: str) -> LayerIndex:
        """Look up a LayerIndex by its KiCad name (raises KeyError on miss)."""
        return LAYER_NAME_TO_IDX[name]


# Canonical 4-layer order (top to bottom).
STANDARD_LAYER_ORDER: tuple[LayerIndex, ...] = (
    LayerIndex.F_CU,
    LayerIndex.IN1_CU,
    LayerIndex.IN2_CU,
    LayerIndex.B_CU,
)

# Inner plane layers (GND/PWR) on a 4-layer board.
PLANE_LAYER_INDICES: frozenset[LayerIndex] = frozenset({LayerIndex.IN1_CU, LayerIndex.IN2_CU})

_LAYER_INDEX_TO_KICAD_NAME: dict[LayerIndex, str] = {
    LayerIndex.F_CU: "F.Cu",
    LayerIndex.IN1_CU: "In1.Cu",
    LayerIndex.IN2_CU: "In2.Cu",
    LayerIndex.B_CU: "B.Cu",
}

# Canonical layer names for the Temper 4-layer board.
# Derived from STANDARD_LAYER_ORDER / _LAYER_INDEX_TO_KICAD_NAME.
CANONICAL_4LAYER_LAYER_NAMES: frozenset[str] = frozenset(str(idx) for idx in STANDARD_LAYER_ORDER)
CANONICAL_LAYER_COUNT: int = len(STANDARD_LAYER_ORDER)

LAYER_IDX_TO_NAME: dict[LayerIndex, str] = _LAYER_INDEX_TO_KICAD_NAME
LAYER_NAME_TO_IDX: dict[str, LayerIndex] = {
    name: idx for idx, name in _LAYER_INDEX_TO_KICAD_NAME.items()
}


def _coerce_layer_index(name_or_index: str | LayerIndex) -> LayerIndex:
    if isinstance(name_or_index, LayerIndex):
        return name_or_index
    return LAYER_NAME_TO_IDX[name_or_index]


def is_plane_layer(name_or_index: str | LayerIndex) -> bool:
    """Return True if the layer is a plane layer (In1.Cu or In2.Cu)."""
    return _coerce_layer_index(name_or_index) in PLANE_LAYER_INDICES


def is_signal_layer(name_or_index: str | LayerIndex) -> bool:
    """Return True if the layer is a signal layer (F.Cu or B.Cu)."""
    return not is_plane_layer(name_or_index)


def layer_name_to_index(name: str) -> LayerIndex:
    """Map a KiCad layer name to its LayerIndex. Raises KeyError on miss."""
    return LAYER_NAME_TO_IDX[name]


__all__ = [
    "CANONICAL_4LAYER_LAYER_NAMES",
    "CANONICAL_LAYER_COUNT",
    "LAYER_IDX_TO_NAME",
    "LAYER_NAME_TO_IDX",
    "PLANE_LAYER_INDICES",
    "STANDARD_LAYER_ORDER",
    "Array",
    "Board",
    "Component",
    "GroundDomain",
    "Layer",
    "LayerIndex",
    "LayerStackup",
    "MountingHole",
    "Pad",
    "Rect",
    "Trace",
    "Via",
    "Zone",
    "is_plane_layer",
    "is_signal_layer",
    "layer_name_to_index",
    "side_to_layer_name",
]
