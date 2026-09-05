"""Phase-A U7 differential: typed wire path vs the pinned terminal oracle.

Gate G1 (``docs/wave4-discipline-contract.md``) — the Rust orchestration
plan's Phase A (``docs/plans/2026-08-09-001-feat-rust-orchestration-engine-plan.md``,
unit U7) turns the residual ``terminal_extraction`` wire-format marshaler
into typed structs in ``temper-design-bundle`` (``PinWire``,
``ComponentWire``, ``StackupLayerWire``).  The Python-side marshalling
helpers (``_pin_wire`` / ``_component_wire`` / ``_stackup_layer_wire``) were
deleted in a prior Wave-4 pass; this unit moves the attribute-extraction they
performed (and that the kernel still does by ``getattr``) into typed Rust
constructors, so the kernel receives typed wire objects instead of arbitrary
pyobjects.

**THIS SUITE IS DELIBERATELY RED.**  Both arms below are compared at the
kernel's wire-tuple level with no tolerance anywhere; the Rust arm resolves
its types through ``temper_design_bundle_python.terminal_wire_contracts`` and
fails with an ``ImportError`` until the migration supplies the pyclasses.

Arms
----
* **oracle** — ``tests/router_v6/_terminal_extraction_py_oracle.py``, a
  verbatim ``git show`` copy of the pre-migration ``terminal_extraction.py``
  (pinned; see ``test_terminal_extraction_rust_differential.py``).
* **wire path** — ``temper_rust_router.extract_net_terminals_py`` fed with
  ``ComponentWire`` / ``StackupLayerWire`` objects built by the
  ``temper-design-bundle`` typed constructors.  The kernel is unchanged; the
  typed pyclasses expose exactly the attributes it reads (``ref``,
  ``initial_position``, ``initial_rotation_quadrant``, ``initial_side``, ``pins``,
  ``name``, ``number``, ``position``, ``is_pth``, ``layer``, ``index``,
  ``layer_type``), so the comparison pins that the typed construction path
  is bit-identical to the pre-migration oracle.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import tests.router_v6._terminal_extraction_py_oracle as ORACLE
from temper_placer.core.netlist import Component, Pin

# ===========================================================================
# ADAPTER BLOCK -- the ONLY part of this file that knows the Rust arm exists.
# ===========================================================================

_RUST_MODULE = "temper_design_bundle_python"
_RUST_SUBMODULE = "terminal_wire_contracts"

REQUIRED_RUST_SYMBOLS: tuple[str, ...] = ("PinWire", "ComponentWire", "StackupLayerWire")


def _tdb():
    import temper_design_bundle_python as _m  # noqa: PLC0415

    return getattr(_m, _RUST_SUBMODULE)


# ===========================================================================
# END ADAPTER BLOCK
# ===========================================================================

_ORACLE_NAMES: tuple[str, ...] = ("ParsedTerminal", "extract_net_terminals")


def _capture(fn):
    try:
        return fn()
    except BaseException as exc:  # noqa: BLE001 - error parity is the point
        return exc


def _terminal_wire(t) -> tuple:
    return (
        t.identity.component_ref,
        t.identity.pad,
        t.identity.net,
        t.identity.x,
        t.identity.y,
        list(t.identity.layers),
        list(t.layer_names),
        t.is_pth,
    )


def _build_wires(pcb) -> tuple[list, list]:
    """The typed wire path: ``ComponentWire.from_component`` /
    ``StackupLayerWire.from_layer`` over the parsed PCB's components/stackup."""
    wires = _tdb()
    components = [
        wires.ComponentWire.from_component(c) for c in getattr(pcb, "components", ())
    ]
    stackup = getattr(pcb, "stackup", None)
    stackup_layers = [
        wires.StackupLayerWire.from_layer(layer)
        for layer in (getattr(stackup, "layers", ()) or ())
    ]
    return components, stackup_layers


def _wire_path(pcb, net_name, net_pins):
    import temper_rust_router as _trr  # noqa: PLC0415

    components, stackup_layers = _build_wires(pcb)
    return tuple(_trr.extract_net_terminals_py(net_name, list(net_pins), components, stackup_layers))


def _assert_same(label: str, oracle_fn, wire_fn):
    """The oracle arm runs first, so a broken oracle fails with its own error."""
    a = _capture(oracle_fn)
    b = _capture(wire_fn)
    assert type(a) is type(b) and a == b, f"{label}: oracle={a!r} wire={b!r}"


# ---------------------------------------------------------------------------
# G1 evidence: the evidence-backed oracle definitions are content-addressed.
# ---------------------------------------------------------------------------


def test_oracle_pin_still_verbatim():
    import ast
    import hashlib
    import textwrap

    expected = {
        "ParsedTerminal": "3d3a17e6b528636887637631f8e52800e9d10c87075995438d16e74e4db96900",
        "extract_net_terminals": "b9c8cc005c63ce98589c94e86758bea27e5089ec12c5fca65af7393ad91e45bc",
    }
    with open(ORACLE.__file__, encoding="utf-8") as fh:
        copied_src = fh.read()
    copied_tree = ast.parse(copied_src)
    copied_lines = copied_src.splitlines()

    for node in copied_tree.body:
        nm = getattr(node, "name", None)
        if nm in _ORACLE_NAMES:
            decos = getattr(node, "decorator_list", [])
            start = (min(d.lineno for d in decos) if decos else node.lineno) - 1
            copied = "\n".join(copied_lines[start : node.end_lineno])
            digest = hashlib.sha256(textwrap.dedent(copied).encode()).hexdigest()
            assert digest == expected[nm], f"{nm} changed without an evidence-backed re-pin"


def test_rust_symbols_exist():
    """The migration checklist. RED until the typed wire pyclasses land."""
    try:
        wires = _tdb()
    except ImportError as exc:  # pragma: no cover - the RED state
        pytest.fail(f"{_RUST_MODULE}.{_RUST_SUBMODULE} missing: {exc}")
    missing = [s for s in REQUIRED_RUST_SYMBOLS if not hasattr(wires, s)]
    assert not missing, (
        f"{_RUST_MODULE}.{_RUST_SUBMODULE} is missing "
        f"{len(missing)} of {len(REQUIRED_RUST_SYMBOLS)} wire types: {missing}"
    )


# ---------------------------------------------------------------------------
# Corpus (mirrors the existing kernel differential's cases)
# ---------------------------------------------------------------------------


def _basic_pcb() -> SimpleNamespace:
    u1 = Component("U1", "fp", (2, 2), initial_position=(10, 20))
    u1.pins = [Pin("1", "1", (1, 0), net="NET", layer="F.Cu")]
    j1 = Component("J1", "fp", (2, 2), initial_position=(30, 20))
    j1.pins = [Pin("2", "2", (0, 0), net="NET", layer="all", is_pth=True)]
    return SimpleNamespace(
        components=[j1, u1],
        stackup=SimpleNamespace(
            layers=[
                SimpleNamespace(name="F.Cu", index=0, layer_type="signal"),
                SimpleNamespace(name="In1.Cu", index=1, layer_type="plane"),
                SimpleNamespace(name="B.Cu", index=31, layer_type="signal"),
            ]
        ),
    )


def _rotated_mirrored_pcb() -> SimpleNamespace:
    u1 = Component(
        "U1", "fp", (2, 2), initial_position=(5, 5), initial_rotation_quadrant=1, initial_side=1
    )
    u1.pins = [Pin("A1", "1", (2.0, 3.0), net="NET", layer="F.Cu")]
    return SimpleNamespace(
        components=[u1],
        stackup=SimpleNamespace(layers=[SimpleNamespace(name="F.Cu", index=0, layer_type="signal")]),
    )


def _defaults_pcb() -> SimpleNamespace:
    u1 = Component("U1", "fp", (2, 2))
    u1.pins = [Pin("1", "1", (1.5, -2.5), net="NET", layer="F.Cu")]
    return SimpleNamespace(
        components=[u1],
        stackup=SimpleNamespace(layers=[SimpleNamespace(name="F.Cu", index=0, layer_type="signal")]),
    )


def _get_pin_name_vs_number_pcb() -> SimpleNamespace:
    u1 = Component("U1", "fp", (2, 2), initial_position=(0, 0))
    u1.pins = [
        Pin("2", "1", (1, 0), net="NET", layer="F.Cu"),  # name="2", number="1"
        Pin("A", "2", (5, 5), net="NET", layer="F.Cu"),  # name="A", number="2"
    ]
    return SimpleNamespace(
        components=[u1],
        stackup=SimpleNamespace(layers=[SimpleNamespace(name="F.Cu", index=0, layer_type="signal")]),
    )


def _empty_layer_string_pcb() -> SimpleNamespace:
    u1 = Component("U1", "fp", (2, 2), initial_position=(0, 0))
    u1.pins = [Pin("1", "1", (0, 0), net="NET", layer="")]
    return SimpleNamespace(
        components=[u1],
        stackup=SimpleNamespace(layers=[SimpleNamespace(name="F.Cu", index=0, layer_type="signal")]),
    )


def _unknown_smd_layer_pcb() -> SimpleNamespace:
    pcb = _basic_pcb()
    pcb.components[1].pins[0].layer = "User.Cu"
    return pcb


def _mixed_layer_type_pcb() -> SimpleNamespace:
    u1 = Component("U1", "fp", (2, 2), initial_position=(0, 0))
    u1.pins = [Pin("1", "1", (0, 0), net="NET", layer="all", is_pth=True)]
    return SimpleNamespace(
        components=[u1],
        stackup=SimpleNamespace(
            layers=[
                SimpleNamespace(name="F.Cu", index=0, layer_type="signal"),
                SimpleNamespace(name="In2.Cu", index=2, layer_type="mixed"),
                SimpleNamespace(name="In3.Cu", index=3, layer_type="power"),
            ]
        ),
    )


def _missing_component_and_pin_pcb() -> SimpleNamespace:
    u1 = Component("U1", "fp", (2, 2), initial_position=(0, 0))
    u1.pins = [Pin("1", "1", (0, 0), net="NET", layer="F.Cu")]
    return SimpleNamespace(
        components=[u1],
        stackup=SimpleNamespace(layers=[SimpleNamespace(name="F.Cu", index=0, layer_type="signal")]),
    )


def _stackup_layer_name_none_pcb() -> SimpleNamespace:
    u1 = Component("U1", "fp", (2, 2), initial_position=(0, 0))
    u1.pins = [Pin("1", "1", (0, 0), net="NET", layer="all", is_pth=True)]
    return SimpleNamespace(
        components=[u1],
        stackup=SimpleNamespace(
            layers=[
                SimpleNamespace(name=None, index=None, layer_type="signal"),
                SimpleNamespace(name="F.Cu", index=0, layer_type="signal"),
            ]
        ),
    )


CASES: tuple[tuple[str, SimpleNamespace, str, list[tuple[str, str]]], ...] = (
    ("basic", _basic_pcb(), "NET", [("U1", "1"), ("J1", "2")]),
    ("basic_reordered", _basic_pcb(), "NET", [("J1", "2"), ("U1", "1")]),
    ("rotated_mirrored", _rotated_mirrored_pcb(), "NET", [("U1", "1")]),
    ("defaults", _defaults_pcb(), "NET", [("U1", "1")]),
    ("get_pin_name_vs_number", _get_pin_name_vs_number_pcb(), "NET", [("U1", "2")]),
    ("empty_layer_string", _empty_layer_string_pcb(), "NET", [("U1", "1")]),
    ("unknown_smd_layer", _unknown_smd_layer_pcb(), "NET", [("U1", "1")]),
    ("mixed_layer_type", _mixed_layer_type_pcb(), "NET", [("U1", "1")]),
    (
        "missing_component_and_pin",
        _missing_component_and_pin_pcb(),
        "NET",
        [("U1", "1"), ("GHOST", "1"), ("U1", "99")],
    ),
    ("stackup_layer_name_none", _stackup_layer_name_none_pcb(), "NET", [("U1", "1")]),
    ("empty_net_pins", _basic_pcb(), "NET", []),
    (
        "duplicate_net_pins",
        _basic_pcb(),
        "NET",
        [("U1", "1"), ("U1", "1"), ("J1", "2")],
    ),
)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c[0])
def test_wire_path_bit_exact(case):
    _label, pcb, net_name, net_pins = case
    _assert_same(
        f"wire_path[{_label}]",
        lambda: tuple(_terminal_wire(t) for t in ORACLE.extract_net_terminals(pcb, net_name, net_pins)),
        lambda: _wire_path(pcb, net_name, net_pins),
    )


# ---------------------------------------------------------------------------
# Property-based sweep: rotation index x side x position
# ---------------------------------------------------------------------------


@given(
    rotation=st.one_of(st.none(), st.integers(0, 3)),
    side=st.one_of(st.none(), st.integers(0, 1)),
    comp_pos=st.tuples(
        st.floats(-100, 100, allow_nan=False, allow_infinity=False),
        st.floats(-100, 100, allow_nan=False, allow_infinity=False),
    ),
    pin_pos=st.tuples(
        st.floats(-20, 20, allow_nan=False, allow_infinity=False),
        st.floats(-20, 20, allow_nan=False, allow_infinity=False),
    ),
)
@settings(max_examples=200, deadline=30_000)
def test_wire_path_random_sweep(rotation, side, comp_pos, pin_pos):
    u1 = Component(
        "U1", "fp", (2, 2), initial_position=comp_pos, initial_rotation_quadrant=rotation, initial_side=side
    )
    u1.pins = [Pin("1", "1", pin_pos, net="NET", layer="F.Cu")]
    pcb = SimpleNamespace(
        components=[u1],
        stackup=SimpleNamespace(layers=[SimpleNamespace(name="F.Cu", index=0, layer_type="signal")]),
    )
    _assert_same(
        "wire_path[random pin_world_position]",
        lambda: tuple(_terminal_wire(t) for t in ORACLE.extract_net_terminals(pcb, "NET", [("U1", "1")])),
        lambda: _wire_path(pcb, "NET", [("U1", "1")]),
    )


# ---------------------------------------------------------------------------
# Typed-field parity: the wire constructors reproduce the exact values the
# oracle's kernel reads, field for field (the "wire-format trap" the oracle
# docstring documents).
# ---------------------------------------------------------------------------


def _pin_fields(pin):
    return {
        "name": pin.name,
        "number": pin.number,
        "position": tuple(pin.position),
        "is_pth": bool(pin.is_pth),
        "layer": pin.layer,
    }


def test_pin_wire_from_pin_parity():
    wires = _tdb()
    u1 = Component("U1", "fp", (2, 2))
    u1.pins = [Pin("1", "1", (1.5, -2.5), net="NET", layer="B.Cu", is_pth=True)]
    got = wires.PinWire.from_pin(u1.pins[0])
    for field, value in _pin_fields(u1.pins[0]).items():
        assert getattr(got, field) == value, f"PinWire.{field}"


def test_pin_wire_none_layer_parity():
    """pin.layer = None stays None in the wire (the kernel defaults it) —
    exercised through a duck-typed pin because the netlist Pin pyclass
    already defaults layer=None to 'F.Cu' at construction."""
    wires = _tdb()
    pin = SimpleNamespace(name="1", number="1", position=(0, 0), is_pth=False, layer=None)
    got = wires.PinWire.from_pin(pin)
    assert got.layer is None


def test_component_wire_from_component_parity():
    wires = _tdb()
    u1 = Component("U1", "fp", (2, 2), initial_position=(10, 20), initial_rotation_quadrant=1, initial_side=1)
    u1.pins = [Pin("A", "1", (2.0, 3.0), net="NET", layer="F.Cu")]
    got = wires.ComponentWire.from_component(u1)
    assert got.ref == "U1"
    assert got.initial_position == (10.0, 20.0)
    assert got.initial_rotation_quadrant == 1
    assert got.initial_side == 1
    assert [p.name for p in got.pins] == ["A"]
    assert [p.number for p in got.pins] == ["1"]
    assert [p.position for p in got.pins] == [(2.0, 3.0)]
    assert [p.is_pth for p in got.pins] == [False]
    assert [p.layer for p in got.pins] == ["F.Cu"]


def test_component_wire_int_initial_position_coerces_to_float():
    """int position tuples coerce to f64 exactly (pyo3), matching the kernel's
    own Option<(f64, f64)> extraction of the raw component."""
    wires = _tdb()
    u1 = Component("U1", "fp", (2, 2), initial_position=(1, 2))
    u1.pins = [Pin("1", "1", (1, 0), net="NET", layer="F.Cu")]
    got = wires.ComponentWire.from_component(u1)
    assert got.initial_position == (1.0, 2.0)
    assert got.pins[0].position == (1.0, 0.0)


def test_stackup_layer_wire_from_layer_parity():
    wires = _tdb()
    layer = SimpleNamespace(name="F.Cu", index=0, layer_type="signal")
    got = wires.StackupLayerWire.from_layer(layer)
    assert (got.name, got.index, got.layer_type) == ("F.Cu", 0, "signal")


def test_stackup_layer_wire_none_fields():
    wires = _tdb()
    layer = SimpleNamespace(name=None, index=None, layer_type="signal")
    got = wires.StackupLayerWire.from_layer(layer)
    assert got.name is None and got.index is None and got.layer_type == "signal"


def test_wire_types_hashable_and_equal():
    """Frozen dataclass-style value semantics: equal constructions compare
    equal, hash consistently, and field reprs round-trip."""
    wires = _tdb()
    a = wires.PinWire("1", "1", (1.0, 0.0), False, "F.Cu")
    b = wires.PinWire("1", "1", (1.0, 0.0), False, "F.Cu")
    c = wires.PinWire("1", "1", (2.0, 0.0), False, "F.Cu")
    assert a == b
    assert a != c
    assert hash(a) == hash(b)
    assert repr(a).startswith("PinWire(")
