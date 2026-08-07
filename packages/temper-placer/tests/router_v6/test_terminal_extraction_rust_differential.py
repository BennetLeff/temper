"""R1a differential: ``router_v6/terminal_extraction`` vs its pinned oracle.

**THIS SUITE IS DELIBERATELY RED.** Gate G1 (``docs/wave4-discipline-contract.md``)
requires the differential that pins the pre-migration implementation
verbatim to exist and fail *before* the Rust exists; every comparison
resolves its Rust arm through ``tests/router_v6/_pending_rust.rust`` and
fails with a named ``PendingRustError`` until the migration supplies the
pyfunction.

Arms
----
* **oracle** -- ``tests/router_v6/_terminal_extraction_py_oracle.py``, a
  verbatim ``git show`` copy of ``terminal_extraction.py`` at
  ``550cab2a3a0fcfd4a6c29063d30d3a83837ebcb5`` (``origin/main``).
* **rust** -- the ``extract_net_terminals_py`` pyfunction the migration
  adds, bound in the adapter block below.

Comparison is by type-carrying signature (``tests/router_v6/_signature``).
**No tolerance anywhere.** Both arms compare at the wire-tuple level: a
component is ``(ref, initial_position, initial_rotation, initial_side,
pins)`` where each pin is ``(name, number, position, is_pth, layer)``, a
stackup layer is ``(name, index, layer_type)``, and a returned terminal is
``(component_ref, pad, net, x, y, layers, layer_names, is_pth)`` -- see the
oracle module's own docstring for exactly which fields the kernel is
required to read (the "wire-format trap" this program's brief names).

Rotation-index-only note: ``Component.initial_rotation`` is typed ``int |
None`` (``core/netlist.py``'s installed dataclass contract);
``core/pin_geometry._normalize_rotation``'s float-radians branch is
therefore unreachable through the real object model, so the Rust arm here
takes ``Option<i64>``, exactly like ``net_ordering.rs``'s sibling
``pin_world_position`` for the identical reason (see that file's own
docstring, which this test suite's `_ORACLE_NAMES` sibling pin references).
"""

from __future__ import annotations

import ast
import subprocess
from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import tests.router_v6._terminal_extraction_py_oracle as ORACLE
from temper_placer.core.netlist import Component, Pin
from tests.router_v6._pending_rust import missing_symbols, rust
from tests.router_v6._signature import sig

# ===========================================================================
# ADAPTER BLOCK -- the ONLY part of this file that knows the Rust arm exists.
# Phase B binds these; no assertion and no corpus row below changes.
# ===========================================================================

_RUST_MODULE = "temper_rust_router"

REQUIRED_RUST_SYMBOLS: tuple[str, ...] = ("extract_net_terminals_py",)


def _rust(symbol: str):
    return rust(_RUST_MODULE, symbol)


# ===========================================================================
# END ADAPTER BLOCK
# ===========================================================================

_ORACLE_PIN_SHA = "550cab2a3a0fcfd4a6c29063d30d3a83837ebcb5"
_ORACLE_NAMES: tuple[str, ...] = ("ParsedTerminal", "extract_net_terminals")


def _capture(fn):
    try:
        return fn()
    except BaseException as exc:  # noqa: BLE001 - error parity is the point
        return exc


# ---------------------------------------------------------------------------
# Wire marshalling (mirrors the shipped module's planned delegation)
# ---------------------------------------------------------------------------


def _pin_wire(pin) -> tuple:
    return (
        pin.name,
        pin.number,
        tuple(pin.position),
        bool(getattr(pin, "is_pth", False)),
        getattr(pin, "layer", None),
    )


def _component_wire(component) -> tuple:
    pos = component.initial_position
    return (
        component.ref,
        tuple(pos) if pos is not None else None,
        component.initial_rotation,
        component.initial_side,
        [_pin_wire(p) for p in getattr(component, "pins", ())],
    )


def _stackup_layer_wire(layer) -> tuple:
    return (
        getattr(layer, "name", None),
        getattr(layer, "index", None),
        getattr(layer, "layer_type", None),
    )


def _pcb_wire(pcb) -> tuple[list[tuple], list[tuple]]:
    components_wire = [_component_wire(c) for c in getattr(pcb, "components", ())]
    stackup = getattr(pcb, "stackup", None)
    stackup_layers = getattr(stackup, "layers", ()) or ()
    stackup_wire = [_stackup_layer_wire(layer) for layer in stackup_layers]
    return components_wire, stackup_wire


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


def _assert_same(label: str, oracle_fn, symbol: str, rust_fn):
    """The oracle arm runs first, so a broken oracle fails with its own error."""
    a = _capture(oracle_fn)
    fn = _rust(symbol)  # RED until the Rust arm lands
    b = _capture(lambda: rust_fn(fn))
    assert sig(a) == sig(b), f"{label}: oracle={a!r} rust={b!r}"


# ---------------------------------------------------------------------------
# G1 evidence: the oracle is a verbatim pin
# ---------------------------------------------------------------------------


def _segments_from_source(src: str, names: tuple[str, ...]) -> dict[str, str]:
    tree = ast.parse(src)
    lines = src.splitlines()
    out: dict[str, str] = {}
    for node in tree.body:
        nm = getattr(node, "name", None)
        if nm in names:
            decos = getattr(node, "decorator_list", [])
            start = (min(d.lineno for d in decos) if decos else node.lineno) - 1
            out[nm] = "\n".join(lines[start : node.end_lineno])
    return out


def test_oracle_is_verbatim_copy():
    """Every definition in the oracle is character-identical to the pin."""
    rel = "packages/temper-placer/src/temper_placer/router_v6/terminal_extraction.py"
    try:
        src = subprocess.run(
            ["git", "show", f"{_ORACLE_PIN_SHA}:{rel}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):  # pragma: no cover
        pytest.skip(f"pinned commit {_ORACLE_PIN_SHA} not present in this clone")

    original = _segments_from_source(src, _ORACLE_NAMES)
    with open(ORACLE.__file__, encoding="utf-8") as fh:
        copied = _segments_from_source(fh.read(), _ORACLE_NAMES)

    for name in _ORACLE_NAMES:
        assert name in copied, f"{name} missing from the oracle module"
        assert name in original, f"{name} missing from terminal_extraction.py at the pin"
        assert copied[name] == original[name], (
            f"terminal_extraction.py::{name} in the oracle is NOT verbatim -- "
            f"the pin is broken and the differential proves nothing"
        )


def test_rust_symbols_exist():
    """The migration checklist. RED until every kernel is ported."""
    missing = missing_symbols(_RUST_MODULE, REQUIRED_RUST_SYMBOLS)
    assert not missing, (
        f"{_RUST_MODULE} is missing {len(missing)} of {len(REQUIRED_RUST_SYMBOLS)} "
        f"terminal_extraction kernels: {missing}"
    )


# ---------------------------------------------------------------------------
# Corpus
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
    """initial_rotation=1 (90deg index) and initial_side=1 (bottom mirror)
    on the same component -- exercises the mirror-before-rotate ordering."""
    u1 = Component(
        "U1", "fp", (2, 2), initial_position=(5, 5), initial_rotation=1, initial_side=1
    )
    u1.pins = [Pin("A1", "1", (2.0, 3.0), net="NET", layer="F.Cu")]
    return SimpleNamespace(
        components=[u1],
        stackup=SimpleNamespace(layers=[SimpleNamespace(name="F.Cu", index=0, layer_type="signal")]),
    )


def _defaults_pcb() -> SimpleNamespace:
    """initial_rotation/initial_side/initial_position all None (defaults)."""
    u1 = Component("U1", "fp", (2, 2))
    u1.pins = [Pin("1", "1", (1.5, -2.5), net="NET", layer="F.Cu")]
    return SimpleNamespace(
        components=[u1],
        stackup=SimpleNamespace(layers=[SimpleNamespace(name="F.Cu", index=0, layer_type="signal")]),
    )


def _get_pin_name_vs_number_pcb() -> SimpleNamespace:
    """get_pin matches by NAME or NUMBER, first match in pin-list order.
    First pin's name collides with the second pin's number."""
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
    """pin.layer == "" is falsy in Python -- must default to F.Cu, same as
    pin.layer being None or missing."""
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
    """A PTH pin over a stackup with a 'mixed' layer_type layer (not just
    'signal') -- both count toward pth_layers."""
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
    """A stackup layer with name=None is excluded from layer_indices (the
    filter checks name is not None) but NOT filtered out of pth_layers
    (that comprehension has no such guard) -- a PTH pin's layer_names can
    legitimately contain a None entry."""
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
def test_extract_net_terminals_bit_exact(case):
    _label, pcb, net_name, net_pins = case
    components_wire, stackup_wire = _pcb_wire(pcb)
    _assert_same(
        f"extract_net_terminals[{_label}]",
        lambda: tuple(_terminal_wire(t) for t in ORACLE.extract_net_terminals(pcb, net_name, net_pins)),
        "extract_net_terminals_py",
        lambda fn: tuple(fn(net_name, list(net_pins), components_wire, stackup_wire)),
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
def test_pin_world_position_random_sweep(rotation, side, comp_pos, pin_pos):
    u1 = Component(
        "U1", "fp", (2, 2), initial_position=comp_pos, initial_rotation=rotation, initial_side=side
    )
    u1.pins = [Pin("1", "1", pin_pos, net="NET", layer="F.Cu")]
    pcb = SimpleNamespace(
        components=[u1],
        stackup=SimpleNamespace(layers=[SimpleNamespace(name="F.Cu", index=0, layer_type="signal")]),
    )
    components_wire, stackup_wire = _pcb_wire(pcb)
    _assert_same(
        "extract_net_terminals[random pin_world_position]",
        lambda: tuple(_terminal_wire(t) for t in ORACLE.extract_net_terminals(pcb, "NET", [("U1", "1")])),
        "extract_net_terminals_py",
        lambda fn: tuple(fn("NET", [("U1", "1")], components_wire, stackup_wire)),
    )
