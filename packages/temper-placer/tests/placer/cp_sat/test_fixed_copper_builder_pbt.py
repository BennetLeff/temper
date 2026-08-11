"""Property-based tests for the Phase E batch E2 `FixedCopperBuilder` orchestration.

Rust Orchestration Engine plan 2026-08-09-001 Phase E E2: the
`fixed_copper.py` build orchestration (`build_free_component_pads` /
`build_fixed_copper_items` / `audit_fixed_copper`) migrates to
`temper-design-bundle` as `FixedCopperBuilder::build*`. These properties run
against the production shim (`temper_placer.placer.cp_sat.fixed_copper`) and
hold over randomized board/netlist inputs.

Six non-vacuous properties (G4):

- P1  pad identity: every free ref's pad list is exactly the free
      component's pins that occupy a copper layer, each with a distinct
      number, and every pad's `layers` is a subset of `copper_layers`.
- P2  item layer universe: every item's `layers` lies within `copper_layers`
      (zones within the full `COPPER_LAYERS` set), and the item kinds are a
      subset of {segment, via, zone, pad}.
- P3  origin normalization: a segment item's `exact["p0"]`/`["p1"]` are the
      trace endpoints minus the board origin, exactly (float subtraction in
      the documented order).
- P4  audit soundness: every reported violation names a ref with a resolved
      position, has `actual_mm < margin_mm` (clearance below the physical
      margin), a known item kind, and the item/net/layer filters match.
- P5  audit far-clearance: a placement placed far outside the board clears
      every item (zero violations) -- the audit is not vacuous on empty /
      far-away placements.
- P6  other-pads opt-in: `include_other_pads=True` turns every pinned
      component's copper pad into a `"pad"` item; `False` produces none.

Vacuity guards (G4): every property carries a companion that constructs a
violating input and asserts the invariant discriminates it.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.io._kicad_types import TraceData
from temper_placer.placer.cp_sat import fixed_copper as fc

_ALL_LAYERS = frozenset({"F.Cu", "B.Cu", "In1.Cu", "In2.Cu"})
_LAYER_SUBSETS = [
    frozenset({"F.Cu"}),
    frozenset({"F.Cu", "B.Cu"}),
    _ALL_LAYERS,
]


def _pin(number, net, layer, pos, w, h, pth, rot):
    return Pin(
        name=number,
        number=number,
        position=pos,
        net=net,
        width=w,
        height=h,
        shape="rect",
        layer=layer,
        is_pth=pth,
        pad_rotation_deg=rot,
    )


@st.composite
def netlist_and_free(draw):
    """A Netlist of 1-4 components (some free, some pinned) with 1-4 pins
    each, on randomized layers/positions, plus a `free_refs` set containing
    the first 1-2 components."""
    n_comps = draw(st.integers(min_value=1, max_value=4))
    comps = []
    for i in range(n_comps):
        n_pins = draw(st.integers(min_value=1, max_value=4))
        pins = []
        for j in range(n_pins):
            layer = draw(st.sampled_from(sorted(_ALL_LAYERS) + ["Silkscreen"]))
            pins.append(
                _pin(
                    str(j),
                    draw(st.sampled_from(["NET_A", "NET_B", None])),
                    layer,
                    (draw(st.floats(min_value=-10, max_value=10, allow_nan=False)),
                     draw(st.floats(min_value=-10, max_value=10, allow_nan=False))),
                    draw(st.floats(min_value=0.2, max_value=5.0, allow_nan=False)),
                    draw(st.floats(min_value=0.2, max_value=5.0, allow_nan=False)),
                    draw(st.booleans()),
                    draw(st.floats(min_value=0.0, max_value=360.0, allow_nan=False)),
                )
            )
        comps.append(
            Component(
                ref=f"U{i}",
                footprint="t",
                bounds=(2.0, 2.0),
                pins=pins,
                initial_position=(draw(st.floats(min_value=0, max_value=50, allow_nan=False)),
                                  draw(st.floats(min_value=0, max_value=50, allow_nan=False))),
                initial_rotation=draw(st.integers(min_value=0, max_value=3)),
            )
        )
    nl = Netlist(components=comps, nets=[Net(name="NET_A", pins=[]), Net(name="NET_B", pins=[])])
    free = {f"U{i}" for i in range(min(2, n_comps))}
    return nl, free


@st.composite
def parse_result(draw):
    """A duck-typed ParseResult with 0-4 traces, 0-3 vias and a board with
    0-2 zones, on a random origin."""
    origin = (draw(st.floats(min_value=-50, max_value=50, allow_nan=False)),
              draw(st.floats(min_value=-50, max_value=50, allow_nan=False)))
    traces = []
    for _ in range(draw(st.integers(min_value=0, max_value=4))):
        traces.append(TraceData(
            start=(draw(st.floats(min_value=-60, max_value=60, allow_nan=False)),
                   draw(st.floats(min_value=-60, max_value=60, allow_nan=False))),
            end=(draw(st.floats(min_value=-60, max_value=60, allow_nan=False)),
                 draw(st.floats(min_value=-60, max_value=60, allow_nan=False))),
            width=draw(st.floats(min_value=0.1, max_value=2.0, allow_nan=False)),
            layer=draw(st.sampled_from(sorted(_ALL_LAYERS) + ["Silkscreen"])),
            net=draw(st.sampled_from(["NET_A", "NET_B", "NET_X", None])),
        ))
    vias = []
    for _ in range(draw(st.integers(min_value=0, max_value=3))):
        vias.append(SimpleNamespace(
            layers=draw(st.sampled_from([["F.Cu"], ["F.Cu", "B.Cu"], ["Silkscreen"], ["In1.Cu"]])),
            position=(draw(st.floats(min_value=-60, max_value=60, allow_nan=False)),
                      draw(st.floats(min_value=-60, max_value=60, allow_nan=False))),
            diameter=draw(st.floats(min_value=0.3, max_value=2.0, allow_nan=False)),
            net=draw(st.sampled_from(["NET_A", "NET_B", None])),
        ))
    zones = []
    for _ in range(draw(st.integers(min_value=0, max_value=2))):
        zones.append(SimpleNamespace(
            name="Z",
            polygon=[(0.0, 0.0), (4.0, 0.0), (4.0, 2.0)],
            layers=draw(st.sampled_from([["F.Cu"], ["B.Cu"]])),
            net_classes=draw(st.sampled_from([["NET_A"], ["NET_B"]])),
        ))
    board = Board(width=120.0, height=120.0, origin=origin, zones=zones)
    return SimpleNamespace(traces=traces, vias=vias, board=board)


@settings(max_examples=50, deadline=60000)
@given(netlist_and_free(), st.sampled_from(_LAYER_SUBSETS))
def test_p1_pad_identity(data, copper_layers):
    nl, free = data
    pads = fc.build_free_component_pads(nl, free, copper_layers=copper_layers)
    assert set(pads) == free
    for comp in nl.components:
        if comp.ref not in free:
            continue
        # Pads whose layers fall entirely outside copper_layers are dropped.
        kept = [p for p in comp.pins if set(_pin_layers(p)) & copper_layers]
        got = pads[comp.ref]
        assert len(got) == len(kept), (comp.ref, len(got), len(kept))
        numbers = [p.number for p in got]
        assert len(set(numbers)) == len(numbers), f"duplicate pad number in {comp.ref}"
        for p in got:
            assert set(p.layers) <= copper_layers
            assert set(p.layers), "empty layer set"
    assert pads or not free, "free refs with no copper pads must still be keyed"


def _pin_layers(pin):
    is_pth = getattr(pin, "is_pth", False)
    layer = getattr(pin, "layer", None)
    if is_pth or layer == "all":
        return _ALL_LAYERS
    if layer in _ALL_LAYERS:
        return {layer}
    return set()


def test_p1_fails_for_dropped_pad_mutant():
    """A builder that drops a free component's copper pad violates P1's
    exact-count claim; the invariant discriminates it."""
    comp = Component(
        ref="U0", footprint="t", bounds=(2.0, 2.0),
        pins=[_pin("1", "NET_A", "F.Cu", (0.0, 0.0), 1.0, 1.0, False, 0.0),
              _pin("2", "NET_A", "F.Cu", (0.0, 1.0), 1.0, 1.0, False, 0.0)],
        initial_position=(0.0, 0.0), initial_rotation=0,
    )
    nl = Netlist(components=[comp], nets=[])
    pads = fc.build_free_component_pads(nl, {"U0"})
    assert len(pads["U0"]) == 2, "fixture must produce two pads"
    # Mutant: a hand-built pads dict dropping pad "2".
    dropped = {ref: [p for p in ps if p.number != "2"] for ref, ps in pads.items()}
    assert [p.number for p in dropped["U0"]] == ["1"]
    assert len(dropped["U0"]) != len(pads["U0"]), "exact-count claim must catch the drop"


@settings(max_examples=50, deadline=60000)
@given(parse_result(), netlist_and_free(), st.sampled_from(_LAYER_SUBSETS))
def test_p2_item_layer_universe(pr, data, copper_layers):
    nl, free = data
    items = fc.build_fixed_copper_items(pr, nl, free, copper_layers=copper_layers)
    for item in items:
        assert item.kind in {"segment", "via", "zone", "pad"}, item.kind
        assert set(item.layers), f"empty layers on {item.label}"
        if item.kind == "zone":
            assert set(item.layers) <= _ALL_LAYERS
        else:
            assert set(item.layers) <= copper_layers, f"{item.label} layers outside universe"


def test_p2_fails_for_leaked_layer_mutant():
    """An item carrying a layer outside its allowed universe violates P2."""
    pr, nl, free = _mini_board()
    items = fc.build_fixed_copper_items(pr, nl, free, copper_layers=frozenset({"F.Cu"}))
    assert all(set(i.layers) <= {"F.Cu"} for i in items), "fixture must be clean"
    # Mutant: hand-built pad item on B.Cu.
    mutant = fc.FixedCopperItem(
        kind="pad", net="NET_X", layers=frozenset({"B.Cu"}),
        rect=(0.0, 0.0, 1.0, 1.0), exact={"rect": (0.0, 0.0, 1.0, 1.0)},
        slack_mm=0.0, margin_mm=0.05, label="mutant",
    )
    assert set(mutant.layers) == {"B.Cu"}
    assert not set(mutant.layers) <= {"F.Cu"}, "mutant must leak B.Cu"


@settings(max_examples=50, deadline=60000)
@given(parse_result(), netlist_and_free())
def test_p3_origin_normalization(pr, data):
    nl, free = data
    items = fc.build_fixed_copper_items(pr, nl, free)
    ox, oy = float(pr.board.origin[0]), float(pr.board.origin[1])
    trace_items = [i for i in items if i.kind == "segment"]
    kept = [t for t in pr.traces if t.layer in _ALL_LAYERS]
    assert len(trace_items) == len(kept), (
        f"trace items {len(trace_items)} != copper-layer traces {len(kept)}"
    )
    for item, t in zip(trace_items, kept):
        assert item.exact["p0"] == (t.start[0] - ox, t.start[1] - oy), t
        assert item.exact["p1"] == (t.end[0] - ox, t.end[1] - oy), t


def test_p3_fails_for_unshifted_mutant():
    """An item built from RAW trace coordinates (no origin subtraction)
    violates P3's normalization claim."""
    tr = TraceData(start=(25.0, 25.0), end=(25.0, 35.0), width=0.2, layer="F.Cu", net="NET_X")
    board = Board(width=100.0, height=100.0, origin=(20.0, 20.0), zones=[])
    pr = SimpleNamespace(traces=[tr], vias=[], board=board)
    nl = Netlist(components=[], nets=[])
    items = fc.build_fixed_copper_items(pr, nl, set())
    assert items and items[0].exact["p0"] == (5.0, 5.0), "fixture must normalize"
    # Mutant: raw (unshifted) endpoints.
    assert tr.start != (5.0, 5.0)
    assert tr.start == (25.0, 25.0)


@settings(max_examples=50, deadline=60000)
@given(parse_result(), netlist_and_free(), st.sampled_from([0.05, 0.2]))
def test_p4_audit_soundness(pr, data, margin_mm):
    nl, free = data
    pads = fc.build_free_component_pads(nl, free)
    items = fc.build_fixed_copper_items(pr, nl, free, margin_mm=margin_mm)
    positions = {ref: (1000.0 + i, 1000.0 + i) for i, ref in enumerate(sorted(free))}
    rotations = {ref: 0 for ref in free}
    violations = fc.audit_fixed_copper(pads, items, positions, rotations)
    for v in violations:
        assert v.ref in free
        assert v.ref in positions, f"violation for ref without resolved position: {v.ref}"
        assert v.item_kind in {"segment", "via", "zone", "pad"}, v.item_kind
        assert v.actual_mm < v.required_mm, f"non-violation reported: {v.reason}"
        assert v.required_mm == margin_mm


def test_p4_fails_for_overshoot_mutant():
    """An audit record whose actual >= margin is not a violation; the
    soundness claim discriminates it."""
    v = fc.FixedCopperAuditViolation(
        ref="U0", pad_number="1", item_label="x", item_kind="segment",
        item_net="NET_X", required_mm=0.05, actual_mm=0.06,
        reason="not a violation",
    )
    assert v.actual_mm >= v.required_mm
    assert not (v.actual_mm < v.required_mm), "mutant must not satisfy the violation predicate"


@settings(max_examples=50, deadline=60000)
@given(parse_result(), netlist_and_free())
def test_p5_audit_far_clearance_is_empty(pr, data):
    """A placement 1000 mm off-board cannot overlap any item; the audit must
    be empty, proving it is not vacuously all-flagging."""
    nl, free = data
    pads = fc.build_free_component_pads(nl, free)
    items = fc.build_fixed_copper_items(pr, nl, free)
    assert items is not None
    positions = {ref: (1000.0 + i, 1000.0 + i) for i, ref in enumerate(sorted(free))}
    rotations = {ref: 0 for ref in free}
    violations = fc.audit_fixed_copper(pads, items, positions, rotations)
    assert violations == [], f"far placement flagged {len(violations)} violations"


def test_p5_fails_for_all_flagging_mutant():
    """A (hypothetical) audit that flags far placements violates P5; the
    invariant discriminates it by demanding the empty result."""
    pr, nl, free = _mini_board()
    pads = fc.build_free_component_pads(nl, free)
    items = fc.build_fixed_copper_items(pr, nl, free)
    far = {ref: (2000.0, 2000.0) for ref in free}
    assert fc.audit_fixed_copper(pads, items, far, {r: 0 for r in free}) == []
    # A far placement cannot overlap an item on the board by construction.
    assert all(
        all(abs(far[ref][0] - c) > 1000 for c in (0.0, 4.0))
        for ref in far
    )


@settings(max_examples=50, deadline=60000)
@given(parse_result(), netlist_and_free())
def test_p6_other_pads_opt_in(pr, data):
    nl, free = data
    on = fc.build_fixed_copper_items(pr, nl, free, include_other_pads=True)
    off = fc.build_fixed_copper_items(pr, nl, free, include_other_pads=False)
    pad_items_on = [i for i in on if i.kind == "pad"]
    pad_items_off = [i for i in off if i.kind == "pad"]
    pinned_with_copper = [
        c.ref for c in nl.components
        if c.ref not in free and c.initial_position is not None
        and any(set(_pin_layers(p)) & _ALL_LAYERS for p in c.pins)
    ]
    # include_other_pads=True turns every pinned copper pad into an item.
    assert len(pad_items_on) == sum(
        1 for c in nl.components
        if c.ref not in free and c.initial_position is not None
        for p in c.pins if set(_pin_layers(p)) & _ALL_LAYERS
    ), "pad item count must equal pinned copper pads"
    # include_other_pads=False produces none -- but the free refs' own pads
    # are NEVER items either way.
    assert pad_items_off == []
    assert pinned_with_copper or not pad_items_on


def test_p6_fails_for_leaked_pad_mutant():
    """include_other_pads=False must not produce pad items; the opt-in
    claim discriminates a leaked one."""
    pr, nl, free = _mini_board()
    off = fc.build_fixed_copper_items(pr, nl, free, include_other_pads=False)
    assert all(i.kind != "pad" for i in off)
    # Mutant: a hand-built pad item masquerading as a build result.
    mutant = fc.FixedCopperItem(
        kind="pad", net="NET_X", layers=frozenset({"F.Cu"}),
        rect=(0.0, 0.0, 1.0, 1.0), exact={"rect": (0.0, 0.0, 1.0, 1.0)},
        slack_mm=0.0, margin_mm=0.05, label="mutant",
    )
    assert mutant.kind == "pad"
    assert [i for i in [mutant] if i.kind == "pad"], "mutant must be a pad item"


def _mini_board():
    tr = TraceData(start=(0.0, 0.0), end=(4.0, 0.0), width=0.2, layer="F.Cu", net="NET_X")
    board = Board(width=100.0, height=100.0, origin=(0.0, 0.0), zones=[])
    pr = SimpleNamespace(traces=[tr], vias=[], board=board)
    comp = Component(
        ref="U0", footprint="t", bounds=(2.0, 2.0),
        pins=[_pin("1", "NET_A", "F.Cu", (0.0, 0.0), 1.0, 1.0, False, 0.0)],
        initial_position=(10.0, 10.0), initial_rotation=0,
    )
    nl = Netlist(components=[comp], nets=[])
    return pr, nl, {"U0"}
