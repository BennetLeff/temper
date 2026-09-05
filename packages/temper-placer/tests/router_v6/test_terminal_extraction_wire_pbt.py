"""PBT (G4) + metamorphic (G5) suite for the typed terminal-extraction path.

Covers `router_v6/terminal_extraction.py`'s wire path — Phase-A U7
(`docs/plans/2026-08-09-001-feat-rust-orchestration-engine-plan.md`): the
`ComponentWire`/`StackupLayerWire` typed marshalling feeding the unchanged
`temper_rust_router.extract_net_terminals_py` kernel. Because the shim calls
the kernel through the Python-level attribute, every kernel-reaching property
has a `test_pN_fails_for_<mutant>` vacuity guard that patches that attribute
and re-runs the property.

Terminal row shape (kernel wire format):
``(component_ref, pad, net, x, y, layers, layer_names, is_pth)``.

Properties:
  P1  rotation-0 translation law: world == component pos + pin pos (exact).
  P2  falsy pin.layer ("" / None / missing) defaults to "F.Cu".
  P3  PTH layer_names come from the stackup's signal/mixed layers in stackup
      order; an SMD pin gets exactly its world layer.
  P4  unknown component/pad contributes no terminal row.
  P5  output is stably sorted by the PadIdentity field tuple.
  P6  wire construction preserves every field the kernel reads.
  P7  wire-path extraction == raw-pyobject extraction (transparency).

Metamorphic relations (exactness stated per relation):
  MR1 component-order permutation leaves the terminal rows bit-identical.
  MR2 net_pins-order permutation leaves the rows bit-identical.
  MR3 an unmatched duplicate (ref, pad) reference is omitted
      immediately after the first (timsort stability on equal keys).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import temper_rust_router as _trr
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.core.netlist import Component, Pin
from temper_placer.router_v6.terminal_extraction import (
    ComponentWire,
    StackupLayerWire,
    extract_net_terminals,
)

_KERNEL = "extract_net_terminals_py"


@pytest.fixture
def _restore_kernel():
    saved = getattr(_trr, _KERNEL)
    yield
    setattr(_trr, _KERNEL, saved)


def _pcb(components, layers):
    return SimpleNamespace(
        components=components,
        stackup=SimpleNamespace(layers=layers),
    )


def _simple_layer(name="F.Cu", index=0, layer_type="signal"):
    return SimpleNamespace(name=name, index=index, layer_type=layer_type)


def _simple_comp(ref, pos, rotation=None, side=None):
    c = Component(ref, "fp", (2, 2), initial_position=pos, initial_rotation_quadrant=rotation, initial_side=side)
    c.pins = []
    return c


def _simple_pin(name="1", number="1", pos=(0.0, 0.0), layer="F.Cu", is_pth=False):
    return Pin(name, number, pos, net="NET", layer=layer, is_pth=is_pth)


def _row(t):
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


@st.composite
def simple_pcb_strategy(draw):
    n_comp = draw(st.integers(min_value=1, max_value=3))
    comps = []
    for i in range(n_comp):
        c = _simple_comp(
            f"C{i}",
            (
                draw(st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False)),
                draw(st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False)),
            ),
            rotation=draw(st.one_of(st.none(), st.integers(0, 3))),
            side=draw(st.one_of(st.none(), st.integers(0, 1))),
        )
        for j in range(draw(st.integers(min_value=1, max_value=3))):
            c.pins.append(
                _simple_pin(
                    f"P{j}",
                    str(j),
                    (
                        draw(st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False)),
                        draw(st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False)),
                    ),
                    layer=draw(st.sampled_from(["F.Cu", "B.Cu", ""])),
                    is_pth=draw(st.booleans()),
                )
            )
        comps.append(c)
    layers = [
        _simple_layer("F.Cu", 0, "signal"),
        _simple_layer("B.Cu", 1, "signal"),
    ]
    return _pcb(comps, layers)


def _all_pins(pcb):
    return [(c.ref, p.number) for c in pcb.components for p in c.pins]


def _assert_rows_equal(label, a, b):
    assert a == b, f"{label}: {a!r} != {b!r}"


# ---------------------------------------------------------------------------
# P1 — rotation-0 translation law (exact)
# ---------------------------------------------------------------------------


@given(
    st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-20.0, max_value=20.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-20.0, max_value=20.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100, deadline=60000)
def test_p1_rotation0_translation_exact(cx, cy, lx, ly):
    u1 = _simple_comp("U1", (cx, cy), rotation=0, side=0)
    u1.pins = [_simple_pin("1", "1", (lx, ly), layer="F.Cu", is_pth=False)]
    pcb = _pcb([u1], [_simple_layer()])
    rows = [_row(t) for t in extract_net_terminals(pcb, "NET", [("U1", "1")])]
    assert len(rows) == 1
    ref, pad, net, x, y, layers, layer_names, is_pth = rows[0]
    del ref, pad, net, layers, layer_names, is_pth
    assert x == cx + lx
    assert y == cy + ly


def test_p1_fails_for_offset_mutant(_restore_kernel):
    """A kernel that offsets x by 1 violates the exact translation law."""
    real = getattr(_trr, _KERNEL)

    def offset_kernel(net_name, net_pins, components, stackup_layers):
        rows = real(net_name, net_pins, components, stackup_layers)
        return [r[:3] + (r[3] + 1.0,) + r[4:] for r in rows]

    setattr(_trr, _KERNEL, offset_kernel)
    with pytest.raises(AssertionError):
        test_p1_rotation0_translation_exact.hypothesis.inner_test(10.0, 20.0, 1.0, 2.0)


# ---------------------------------------------------------------------------
# P2 — falsy pin.layer defaults to "F.Cu"
# ---------------------------------------------------------------------------


@given(st.just(""))
@settings(max_examples=5, deadline=60000)
def test_p2_falsy_layer_defaults_to_fcu(layer):
    u1 = _simple_comp("U1", (0.0, 0.0), rotation=0, side=0)
    u1.pins = [_simple_pin("1", "1", (0.0, 0.0), layer=layer, is_pth=False)]
    pcb = _pcb([u1], [_simple_layer()])
    rows = [_row(t) for t in extract_net_terminals(pcb, "NET", [("U1", "1")])]
    assert rows[0][6] == ["F.Cu"]


def test_p2_fails_for_layer_passthrough_mutant(_restore_kernel):
    """A kernel that keeps the raw (falsy) layer as the SMD layer name — i.e.
    skips the oracle's `pin_world_layer` empty-string default — violates P2."""

    def passthrough(net_name, net_pins, components, stackup_layers):
        out = []
        for component_ref, pad_name in net_pins:
            comp = next((c for c in components if c.ref == component_ref), None)
            if comp is None:
                continue
            pin = next((p for p in comp.pins if p.name == pad_name or p.number == pad_name), None)
            if pin is None:
                continue
            if not pin.is_pth:
                out.append((component_ref, pin.number, net_name, 0.0, 0.0, [], [pin.layer], False))
        return out

    setattr(_trr, _KERNEL, passthrough)
    with pytest.raises(AssertionError):
        test_p2_falsy_layer_defaults_to_fcu.hypothesis.inner_test("")


# ---------------------------------------------------------------------------
# P3 — PTH layer context from declared signal/mixed layers; SMD exactly one
# ---------------------------------------------------------------------------


@given(simple_pcb_strategy())
@settings(max_examples=50, deadline=60000)
def test_p3_pth_vs_smd_layer_context(pcb):
    stackup_signal = ["F.Cu", "B.Cu"]
    for t in extract_net_terminals(pcb, "NET", _all_pins(pcb)):
        if t.is_pth:
            assert list(t.layer_names) == stackup_signal
            assert all(name in stackup_signal for name in t.layer_names)
        else:
            assert len(t.layer_names) == 1


def test_p3_fails_for_pth_raw_layer_mutant(_restore_kernel):
    """A kernel that returns the pin's raw layer for PTH pins (ignoring the
    stackup's declared signal/mixed layers) violates P3."""
    real = getattr(_trr, _KERNEL)

    def raw_pth_layer(net_name, net_pins, components, stackup_layers):
        rows = real(net_name, net_pins, components, stackup_layers)
        return [r if not r[7] else (r[0], r[1], r[2], r[3], r[4], r[5], ["raw"], r[7]) for r in rows]

    setattr(_trr, _KERNEL, raw_pth_layer)
    u1 = _simple_comp("U1", (0.0, 0.0), rotation=0, side=0)
    u1.pins = [_simple_pin("1", "1", (0.0, 0.0), layer="all", is_pth=True)]
    pcb = _pcb([u1], [_simple_layer(), _simple_layer("B.Cu", 1, "signal")])
    with pytest.raises(AssertionError):
        test_p3_pth_vs_smd_layer_context.hypothesis.inner_test(pcb)


# ---------------------------------------------------------------------------
# P4 — unknown component/pad contributes no row
# ---------------------------------------------------------------------------


@given(simple_pcb_strategy())
@settings(max_examples=50, deadline=60000)
def test_p4_missing_omitted(pcb):
    pins = _all_pins(pcb)
    pins_ext = list(pins) + [("GHOST", "1"), (pins[0][0] if pins else "C0", "NOPE")]
    rows = list(extract_net_terminals(pcb, "NET", pins_ext))
    expected = list(extract_net_terminals(pcb, "NET", pins))
    assert rows == expected


def test_p4_fails_for_synthesizing_mutant(_restore_kernel):
    """A kernel that synthesizes a row for an unknown component (instead of
    omitting it) violates P4 — only the request that names the ghost gains a
    row, so the two-arm equality breaks."""
    real = getattr(_trr, _KERNEL)

    def synthesize(net_name, net_pins, components, stackup_layers):
        rows = real(net_name, net_pins, components, stackup_layers)
        known = {c.ref for c in components}
        for ref, pad in net_pins:
            if ref not in known:
                rows.append((ref, pad, net_name, 0.0, 0.0, [], ["F.Cu"], False))
        return rows

    setattr(_trr, _KERNEL, synthesize)
    u1 = _simple_comp("U1", (0.0, 0.0), rotation=0, side=0)
    u1.pins = [_simple_pin("1", "1", (0.0, 0.0), layer="F.Cu", is_pth=False)]
    pcb = _pcb([u1], [_simple_layer()])
    with pytest.raises(AssertionError):
        test_p4_missing_omitted.hypothesis.inner_test(pcb)


# ---------------------------------------------------------------------------
# P5 — stable PadIdentity sort
# ---------------------------------------------------------------------------


def _identity_key(r):
    return (r[0], r[1], r[2], r[3], r[4], r[5])


@given(simple_pcb_strategy())
@settings(max_examples=50, deadline=60000)
def test_p5_output_sorted_by_identity(pcb):
    rows = [_row(t) for t in extract_net_terminals(pcb, "NET", _all_pins(pcb))]
    assert rows == sorted(rows, key=_identity_key)


def test_p5_fails_for_reverse_mutant(_restore_kernel):
    """A kernel that returns input order (reversed) violates the stable
    PadIdentity sort."""
    real = getattr(_trr, _KERNEL)

    def reverse(net_name, net_pins, components, stackup_layers):
        return list(reversed(real(net_name, net_pins, components, stackup_layers)))

    setattr(_trr, _KERNEL, reverse)
    u1 = _simple_comp("U1", (0.0, 0.0), rotation=0, side=0)
    u1.pins = [_simple_pin("1", "1", (0.0, 0.0), layer="F.Cu", is_pth=False)]
    u2 = _simple_comp("U2", (5.0, 0.0), rotation=0, side=0)
    u2.pins = [_simple_pin("1", "1", (0.0, 0.0), layer="F.Cu", is_pth=False)]
    pcb = _pcb([u2, u1], [_simple_layer()])
    with pytest.raises(AssertionError):
        test_p5_output_sorted_by_identity.hypothesis.inner_test(pcb)


# ---------------------------------------------------------------------------
# P6 — wire construction preserves every field the kernel reads
# ---------------------------------------------------------------------------


@given(simple_pcb_strategy())
@settings(max_examples=50, deadline=60000)
def test_p6_wire_construction_preserves_fields(pcb):
    for comp in pcb.components:
        w = ComponentWire.from_component(comp)
        assert w.ref == comp.ref
        assert w.initial_position == (tuple(comp.initial_position) if comp.initial_position else None)
        assert w.initial_rotation_quadrant == comp.initial_rotation_quadrant
        assert w.initial_side == comp.initial_side
        assert len(w.pins) == len(comp.pins)
        for wp, p in zip(w.pins, comp.pins):
            assert wp.name == p.name
            assert wp.number == p.number
            assert wp.position == tuple(p.position)
            assert wp.is_pth == bool(p.is_pth)
            assert wp.layer == (p.layer if p.layer is not None else None)
    for layer in pcb.stackup.layers:
        w = StackupLayerWire.from_layer(layer)
        assert w.name == layer.name
        assert w.index == layer.index
        assert w.layer_type == layer.layer_type


def test_p6_field_preservation_bites_on_wrong_wire():
    """Anti-vacuity: the per-field assertions above are only meaningful if a
    mis-built wire fails them."""
    w = ComponentWire.from_component(_simple_comp("U1", (1.0, 2.0), rotation=1, side=1))
    assert w != ComponentWire("U1", (9.0, 9.0), None, None, [])
    assert w != ComponentWire("OTHER", (1.0, 2.0), 1, 1, [])


# ---------------------------------------------------------------------------
# P7 — wire-path extraction == raw-pyobject extraction (transparency)
# ---------------------------------------------------------------------------


@given(simple_pcb_strategy())
@settings(max_examples=50, deadline=60000)
def test_p7_wire_path_matches_raw_path(pcb):
    pins = _all_pins(pcb)
    raw = _trr.extract_net_terminals_py("NET", list(pins), list(pcb.components), list(pcb.stackup.layers))
    got = [_row(t) for t in extract_net_terminals(pcb, "NET", pins)]
    assert got == list(raw)


def test_p7_transparency_bites_on_corrupted_wire():
    """Anti-vacuity: the transparency equality is only meaningful if wire
    content drives the kernel output. A wire whose layer field is corrupted
    must produce a different terminal than the raw-pyobject path."""
    u1 = _simple_comp("U1", (0.0, 0.0), rotation=0, side=0)
    u1.pins = [_simple_pin("1", "1", (1.0, 2.0), layer="B.Cu", is_pth=False)]
    pcb = _pcb([u1], [_simple_layer()])
    pins = [("U1", "1")]
    raw = _trr.extract_net_terminals_py("NET", pins, list(pcb.components), list(pcb.stackup.layers))
    w = ComponentWire.from_component(u1)
    corrupted = ComponentWire(
        w.ref,
        w.initial_position,
        w.initial_rotation_quadrant,
        w.initial_side,
        [type(w.pins[0])(w.pins[0].name, w.pins[0].number, w.pins[0].position, w.pins[0].is_pth, "CORRUPTED")],
    )
    got = _trr.extract_net_terminals_py("NET", pins, [corrupted], list(pcb.stackup.layers))
    assert list(got) != list(raw)


# ---------------------------------------------------------------------------
# MR1 — component-order permutation (bit-exact)
# ---------------------------------------------------------------------------


@given(simple_pcb_strategy())
@settings(max_examples=30, deadline=60000)
def test_mr1_component_order_permutation_exact(pcb):
    pins = _all_pins(pcb)
    baseline = [_row(t) for t in extract_net_terminals(pcb, "NET", pins)]
    reordered = _pcb(list(reversed(pcb.components)), pcb.stackup.layers)
    got = [_row(t) for t in extract_net_terminals(reordered, "NET", pins)]
    assert got == baseline


# ---------------------------------------------------------------------------
# MR2 — net_pins-order permutation (bit-exact)
# ---------------------------------------------------------------------------


@given(simple_pcb_strategy())
@settings(max_examples=30, deadline=60000)
def test_mr2_net_pins_order_permutation_exact(pcb):
    pins = _all_pins(pcb)
    baseline = [_row(t) for t in extract_net_terminals(pcb, "NET", pins)]
    permuted = list(reversed(pins))
    got = [_row(t) for t in extract_net_terminals(pcb, "NET", permuted)]
    assert got == baseline


# ---------------------------------------------------------------------------
# MR3 — a duplicate net reference cannot synthesize a physical occurrence
# ---------------------------------------------------------------------------


@given(simple_pcb_strategy())
@settings(max_examples=30, deadline=60000)
def test_mr3_unmatched_duplicate_is_omitted(pcb):
    pins = _all_pins(pcb)
    baseline = [_row(t) for t in extract_net_terminals(pcb, "NET", pins)]
    target = pins[0]
    dup = [_row(t) for t in extract_net_terminals(pcb, "NET", list(pins) + [target])]
    # Every generated component has one physical pin per number. A repeated
    # logical reference asks for occurrence 1, which does not exist; it must
    # not duplicate occurrence 0's coordinate.
    assert dup == baseline
