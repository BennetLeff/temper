"""Differential test: the ``_write_types.py`` surface
(``temper_io_types.write_types``) vs the pinned Python oracle.

Wave 4, Phase 3 (formats/IO) — migrates `temper_placer/io/_write_types.py`
(90 LOC): the four write-result dataclasses (`WriteResult`, `StrippingResult`,
`PlacementUpdate`, `IsolationSlotResult`) and the `_get_footprint_reference`
helper. See ``packages/temper-io-types/src/write_types.rs``'s module docstring
for what was and was not ported, and why.

The Rust symbols must reproduce the pre-migration implementation
(``_write_types.py`` at origin/main ``5e528b8aa``), pinned verbatim as the
oracle (``_write_types_py_oracle.py``).

RED before GREEN: this file is written and committed BEFORE
``write_types.rs`` is registered into the built extension, so
``temper_io_types.write_types`` does not exist yet and every test here fails
at collection. That failure is the proof the differential was never
vacuously green.

The delegation tests at the bottom of this file are a SEPARATE proof from
the bit-exactness tests above: a green differential compares the oracle
against the Rust kernel directly and passes whether or not the SHIPPED
``_write_types.py`` module actually re-exports it. Monkeypatching the Rust
symbol to raise and calling the shipped entry point is the only thing that
proves the production code path was rewired, not left as a second,
unreachable implementation next to the first.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import temper_io_types as _tio

import tests.io._write_types_py_oracle as _oracle
from temper_placer.io import _write_types as shipped

# Rust symbols under test — must exist or this file fails to collect (RED).
_RUST = _tio.write_types
GET_FOOTPRINT_REFERENCE = _RUST.get_footprint_reference_py


def _ref(fp) -> str | None:
    return GET_FOOTPRINT_REFERENCE(fp)


# ---------------------------------------------------------------------------
# _get_footprint_reference — duck-typed branch matrix
# ---------------------------------------------------------------------------


class _RaisingKey:
    """`key` attribute access raises RuntimeError — CPython 3.12's `hasattr`
    swallows only AttributeError (bpo-45522), so this PROPAGATES rather than
    skipping the item. Pinned by a dedicated test below."""

    def __getattr__(self, name):
        if name == "key":
            raise RuntimeError("boom")
        raise AttributeError(name)


class _RaisingProps:
    """`properties` attribute access raises RuntimeError — `getattr` with a
    default swallows only AttributeError, so this propagates."""

    @property
    def properties(self):
        raise RuntimeError("boom")


def _kiutils_fp(**kwargs):
    """A real kiutils Footprint — the production input type."""
    from kiutils.footprint import Footprint

    return Footprint(**kwargs)


def _kiutils_reference_text_fp(ref: str):
    """A real kiutils Footprint whose reference comes from a graphicItems
    GrText with type == "reference"."""
    from kiutils.footprint import Footprint
    from kiutils.items.gritems import GrText

    fp = Footprint(properties={"Value": "100k"})
    t = GrText(text=ref, layer="F.SilkS")
    t.type = "reference"
    fp.graphicItems = [t]
    return fp


@pytest.mark.parametrize(
    "fp",
    [
        # dict properties, Reference present and truthy
        SimpleNamespace(properties={"Reference": "U1"}),
        _kiutils_fp(properties={"Reference": "U1"}),
        _kiutils_fp(properties={"Reference": "U1", "Value": "x"}),
        # dict properties, Reference falsy -> falls through every branch
        SimpleNamespace(properties={"Reference": ""}),
        SimpleNamespace(properties={"Reference": None}),
        SimpleNamespace(properties={"Reference": 0}),
        _kiutils_fp(properties={"Reference": ""}),
        # dict properties, Reference absent
        SimpleNamespace(properties={"Value": "100k"}),
        _kiutils_fp(properties={"Value": "100k"}),
        _kiutils_fp(properties={}),
        # list properties
        SimpleNamespace(properties=[SimpleNamespace(key="Reference", value="R1")]),
        SimpleNamespace(
            properties=[
                SimpleNamespace(key="Value", value="x"),
                SimpleNamespace(key="Reference", value="C1"),
            ]
        ),
        # list branch has NO truthiness guard: empty value is returned
        SimpleNamespace(properties=[SimpleNamespace(key="Reference", value="")]),
        # list item without a `key` attribute is skipped
        SimpleNamespace(properties=[SimpleNamespace(value="x")]),
        # graphicItems with type == "reference"
        SimpleNamespace(graphicItems=[SimpleNamespace(type="reference", text="Q1")]),
        _kiutils_reference_text_fp("Q1"),
        # graphicItems with other types are skipped
        SimpleNamespace(graphicItems=[SimpleNamespace(type="user", text="Q1")]),
        SimpleNamespace(
            graphicItems=[
                SimpleNamespace(type="user", text="x"),
                SimpleNamespace(type="reference", text="Q1"),
            ]
        ),
        # type == "reference" without text -> getattr default None, returned
        # from the WHOLE function (immediate return, not loop continue)
        SimpleNamespace(graphicItems=[SimpleNamespace(type="reference")]),
        # no properties, no graphicItems
        SimpleNamespace(),
        # properties is neither dict nor list -> skipped, graphicItems used
        SimpleNamespace(properties="junk"),
        # falsy dict Reference + graphicItems reference -> graphicItems wins
        SimpleNamespace(
            properties={"Reference": ""},
            graphicItems=[SimpleNamespace(type="reference", text="Q1")],
        ),
    ],
)
def test_get_footprint_reference_matches_oracle(fp):
    py_result = _oracle._get_footprint_reference(fp)
    rust_result = _ref(fp)
    assert rust_result == py_result
    assert type(rust_result) is type(py_result)


def test_get_footprint_reference_propagates_properties_runtime_error():
    """`getattr(fp, "properties", {})` swallows only AttributeError — a
    RuntimeError from the property must propagate on both arms."""
    fp = _RaisingProps()
    with pytest.raises(RuntimeError, match="boom"):
        _oracle._get_footprint_reference(fp)
    with pytest.raises(RuntimeError, match="boom"):
        _ref(fp)


def test_get_footprint_reference_propagates_missing_value():
    """The list branch reads `prop.value` with no guard: a key == "Reference"
    item without a `value` attribute raises AttributeError on both arms."""
    fp = SimpleNamespace(properties=[SimpleNamespace(key="Reference")])
    with pytest.raises(AttributeError):
        _oracle._get_footprint_reference(fp)
    with pytest.raises(AttributeError):
        _ref(fp)


def test_get_footprint_reference_propagates_hasattr_non_attribute_error():
    """CPython 3.12 `hasattr` swallows only AttributeError (bpo-45522): a
    RuntimeError from `__getattr__("key")` propagates on both arms rather
    than skipping the item. This is the case that would have diverged if the
    Rust port had used the naive `getattr(...).is_ok()` (which swallows
    everything) — the oracle's raise is the pin."""
    fp = SimpleNamespace(properties=[_RaisingKey()])
    with pytest.raises(RuntimeError, match="boom"):
        _oracle._get_footprint_reference(fp)
    with pytest.raises(RuntimeError, match="boom"):
        _ref(fp)


def test_get_footprint_reference_propagates_getattr_errors_on_graphic_items():
    """`getattr(fp, "graphicItems", [])` swallows only AttributeError."""
    class _RaisingGfx:
        @property
        def graphicItems(self):
            raise RuntimeError("boom2")

    with pytest.raises(RuntimeError, match="boom2"):
        _oracle._get_footprint_reference(_RaisingGfx())
    with pytest.raises(RuntimeError, match="boom2"):
        _ref(_RaisingGfx())


# ---------------------------------------------------------------------------
# Result types — field / has_warnings / mutability parity vs the dataclasses
# ---------------------------------------------------------------------------


def _fields_parity(py_obj, rust_obj, field_names):
    for name in field_names:
        assert getattr(rust_obj, name) == getattr(py_obj, name), name
    assert rust_obj.has_warnings == py_obj.has_warnings


def test_write_result_parity():
    py = _oracle.WriteResult(
        output_path=Path("/tmp/test.pcb"),
        components_updated=5,
        components_skipped=2,
        warnings=["warning 1"],
    )
    rust = _RUST.WriteResult(
        output_path=Path("/tmp/test.pcb"),
        components_updated=5,
        components_skipped=2,
        warnings=["warning 1"],
    )
    _fields_parity(py, rust, ["output_path", "components_updated", "components_skipped", "warnings"])


def test_write_result_no_warnings():
    py = _oracle.WriteResult(
        output_path=Path("/tmp/test.pcb"), components_updated=0, components_skipped=0, warnings=[]
    )
    rust = _RUST.WriteResult(
        output_path=Path("/tmp/test.pcb"), components_updated=0, components_skipped=0, warnings=[]
    )
    assert py.has_warnings is False
    assert rust.has_warnings is False


def test_stripping_result_parity():
    py = _oracle.StrippingResult(
        output_path=Path("/tmp/stripped.pcb"),
        traces_removed=10,
        vias_removed=5,
        zones_removed=2,
        components_preserved=20,
        warnings=["w"],
    )
    rust = _RUST.StrippingResult(
        output_path=Path("/tmp/stripped.pcb"),
        traces_removed=10,
        vias_removed=5,
        zones_removed=2,
        components_preserved=20,
        warnings=["w"],
    )
    _fields_parity(
        py,
        rust,
        [
            "output_path",
            "traces_removed",
            "vias_removed",
            "zones_removed",
            "components_preserved",
            "warnings",
        ],
    )


def test_placement_update_parity():
    py = _oracle.PlacementUpdate(ref="U1", x=10.5, y=20.5, rotation=90.0)
    rust = _RUST.PlacementUpdate(ref="U1", x=10.5, y=20.5, rotation=90.0)
    assert rust.ref == py.ref
    assert rust.x == py.x
    assert rust.y == py.y
    assert rust.rotation == py.rotation


def test_isolation_slot_result_parity():
    py = _oracle.IsolationSlotResult(
        output_path=Path("/tmp/isolated.pcb"), slots_added=3, slots_skipped=1, warnings=[]
    )
    rust = _RUST.IsolationSlotResult(
        output_path=Path("/tmp/isolated.pcb"), slots_added=3, slots_skipped=1, warnings=[]
    )
    _fields_parity(py, rust, ["output_path", "slots_added", "slots_skipped", "warnings"])


def test_warnings_append_mutability_matches_dataclass():
    """The shipped `_write_tracks.strip_routing_preserve_nets` mutates a
    result in place (`result.warnings.append(...)`) after construction; the
    Rust class must hold the SAME list object so the append is visible to
    `has_warnings` and `len(warnings)` — exactly like the dataclass."""
    py = _oracle.StrippingResult(
        output_path=Path("/tmp/s.pcb"),
        traces_removed=0,
        vias_removed=0,
        zones_removed=0,
        components_preserved=0,
        warnings=[],
    )
    rust = _RUST.StrippingResult(
        output_path=Path("/tmp/s.pcb"),
        traces_removed=0,
        vias_removed=0,
        zones_removed=0,
        components_preserved=0,
        warnings=[],
    )
    assert py.has_warnings is False
    assert rust.has_warnings is False
    py.warnings.append("w1")
    rust.warnings.append("w1")
    assert py.has_warnings is True
    assert rust.has_warnings is True
    assert len(rust.warnings) == 1
    assert rust.warnings == ["w1"]
    # A second append on the same object is still visible (shared list).
    rust.warnings.append("w2")
    assert rust.has_warnings is True
    assert rust.warnings == ["w1", "w2"]


def test_placement_update_positional_construction_matches_dataclass():
    py = _oracle.PlacementUpdate("R1", 1.0, 2.0, 0.0)
    rust = _RUST.PlacementUpdate("R1", 1.0, 2.0, 0.0)
    assert rust.ref == py.ref == "R1"
    assert rust.x == py.x == 1.0
    assert rust.y == py.y == 2.0
    assert rust.rotation == py.rotation == 0.0


# ---------------------------------------------------------------------------
# Shipped-module delegation proof -- NOT a bit-exactness check.
# ---------------------------------------------------------------------------


def test_shipped_types_are_the_rust_classes():
    """The SHIPPED `_write_types` module must re-export the Rust classes by
    identity, not shadow them with Python copies. (`_get_footprint_reference`
    is a thin wrapper by design — call-time lookup — so its reachability is
    proven by the delegation test below, not by identity.)"""
    assert shipped.WriteResult is _RUST.WriteResult
    assert shipped.StrippingResult is _RUST.StrippingResult
    assert shipped.PlacementUpdate is _RUST.PlacementUpdate
    assert shipped.IsolationSlotResult is _RUST.IsolationSlotResult


def test_get_footprint_reference_delegates_to_rust():
    """The SHIPPED `_write_types._get_footprint_reference` must reach the
    Rust function. Monkeypatch the Rust symbol to raise; call the shipped
    entry point; the raise must propagate."""
    sentinel = RuntimeError("REACHED_RUST_REF")

    def boom(*_a, **_k):
        raise sentinel

    original = _RUST.get_footprint_reference_py
    _RUST.get_footprint_reference_py = boom
    try:
        with pytest.raises(RuntimeError, match="REACHED_RUST_REF"):
            shipped._get_footprint_reference(SimpleNamespace(properties={"Reference": "U1"}))
    finally:
        _RUST.get_footprint_reference_py = original


def test_write_engine_modules_import_through_the_shim():
    """Every production consumer of `_write_types` must still import after
    the module became a delegation shim (no kiutils import remains)."""
    from temper_placer.io import _write_board, _write_modules, _write_tracks, _write_zones
    from temper_placer.io import kicad_writer

    assert kicad_writer.WriteResult is _RUST.WriteResult
    assert kicad_writer.PlacementUpdate is _RUST.PlacementUpdate
    assert kicad_writer.StrippingResult is _RUST.StrippingResult
    assert kicad_writer.IsolationSlotResult is _RUST.IsolationSlotResult
    # Every consumer resolves the reference helper to the shim's wrapper —
    # which the delegation test proves reaches the Rust function at call time.
    assert _write_tracks._get_footprint_reference is shipped._get_footprint_reference
    assert _write_board._get_footprint_reference is shipped._get_footprint_reference
    assert _write_modules._get_footprint_reference is shipped._get_footprint_reference
