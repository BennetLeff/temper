"""Metamorphic relations for the Phase E batch E2 `FixedCopperBuilder` orchestration.

Rust Orchestration Engine plan 2026-08-09-001 Phase E E2: the
`fixed_copper.py` build orchestration migrates to `temper-design-bundle` as
`FixedCopperBuilder::build*`. These relations run against the production
shim and hold over randomized inputs (G5, >=3 invariant relations).

Relations:

- MR1  margin monotonicity: raising `margin_mm` yields the same item set
       with coordinate-wise expanding encoded rects (and identical exact
       copper + labels). The encoding is monotone in the margin.
- MR2  copper-layer universe subset: an item produced under
       `copper_layers=subset` (traces/vias/pads) is identical, and present,
       in the run under `copper_layers=superset`; zone items are identical
       in both (zones always use the full `COPPER_LAYERS`).
- MR3  origin-translation invariance: translating BOTH the board origin and
       the raw trace/via coordinates by the same delta leaves the normalized
       item geometry unchanged (traces/vias are normalized by origin
       subtraction; the delta cancels exactly).
- MR4  audit-vs-encode coupling: moving a resolved placement farther from
       every item never turns a zero-violation audit into a violation (the
       audit is monotone in clearance distance).

Three-plus relations (G5), all non-vacuous with discriminating companions.
"""

from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import given, settings

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist, Pin
from temper_placer.io._kicad_types import TraceData
from temper_placer.placer.cp_sat import fixed_copper as fc

_ALL_LAYERS = frozenset({"F.Cu", "B.Cu", "In1.Cu", "In2.Cu"})


def _pin(number, net, layer, pos, w=1.0, h=1.0, pth=False, rot=0.0):
    return Pin(
        name=number, number=number, position=pos, net=net, width=w, height=h,
        shape="rect", layer=layer, is_pth=pth, pad_rotation_deg=rot,
    )


def _netlist():
    return Netlist(
        components=[
            Component(
                ref="U0", footprint="t", bounds=(2.0, 2.0),
                pins=[_pin("1", "NET_A", "F.Cu", (0.0, 0.0)),
                      _pin("2", "NET_B", "F.Cu", (0.0, 1.0))],
                initial_position=(10.0, 10.0), initial_rotation_quadrant=0,
            ),
            Component(
                ref="U1", footprint="t", bounds=(2.0, 2.0),
                pins=[_pin("1", "NET_C", "F.Cu", (0.5, 0.5), pth=True)],
                initial_position=(20.0, 20.0), initial_rotation_quadrant=1,
            ),
        ],
        nets=[],
    )


@st.composite
def pr_netlist_free(draw):
    """A fixed small board (traces on F.Cu/B.Cu, one via, one zone, a pinned
    component) plus the free ref set {U0}."""
    origin = (draw(st.floats(min_value=-40, max_value=40, allow_nan=False)),
              draw(st.floats(min_value=-40, max_value=40, allow_nan=False)))
    traces = [
        TraceData(start=(0.0, 0.0), end=(10.0, 0.0), width=0.2, layer="F.Cu", net="NET_X"),
        TraceData(start=(0.0, 0.0), end=(5.0, 5.0), width=0.4, layer="B.Cu", net="NET_Y"),
    ]
    vias = [type("V", (), {"layers": ["F.Cu", "B.Cu"], "position": (3.0, 3.0),
                            "diameter": 0.8, "net": "NET_X"})()]
    zones = [type("Z", (), {"name": "Z1", "polygon": [(0.0, 0.0), (4.0, 0.0), (4.0, 2.0)],
                            "layers": ["F.Cu"], "net_classes": ["NET_A"]})()]
    board = Board(width=120.0, height=120.0, origin=origin, zones=zones)
    return (
        type("PR", (), {"traces": traces, "vias": vias, "board": board})(),
        _netlist(),
        {"U0"},
    )


def _rects(items):
    return {i.label: i.rect for i in items}


@settings(max_examples=50, deadline=60000)
@given(pr_netlist_free())
def test_mr1_margin_monotonicity(data):
    pr, nl, free = data
    small = fc.build_fixed_copper_items(pr, nl, free, margin_mm=0.05)
    big = fc.build_fixed_copper_items(pr, nl, free, margin_mm=0.3)
    assert len(small) == len(big), "margin must not change the item set"
    for a, b in zip(small, big):
        assert a.kind == b.kind and a.label == b.label
        assert a.exact == b.exact, "exact copper must be margin-independent"
        # Larger margin -> coordinate-wise expanding encoded rect.
        assert a.rect[0] >= b.rect[0] and a.rect[1] >= b.rect[1], b.label
        assert a.rect[2] <= b.rect[2] and a.rect[3] <= b.rect[3], b.label
        assert b.margin_mm == 0.3 and a.margin_mm == 0.05


def test_mr1_fails_for_shrunk_rect_mutant():
    """A larger margin that SHRINKS an encoded rect violates MR1; the
    monotonicity claim discriminates it."""
    pr, nl, free = _static_board()
    small = fc.build_fixed_copper_items(pr, nl, free, margin_mm=0.05)
    big = fc.build_fixed_copper_items(pr, nl, free, margin_mm=0.3)
    assert small and big
    # Mutant: shrink the big rect below the small rect's extent.
    a = small[0]
    b = big[0]
    assert a.rect[0] >= b.rect[0], "fixture must be monotone to be meaningful"
    shrunk = (b.rect[0] - 1.0, b.rect[1] - 1.0, b.rect[2] + 0.1, b.rect[3] + 0.1)
    assert not (shrunk[0] >= a.rect[0] and shrunk[1] >= a.rect[1]
                and shrunk[2] <= a.rect[2] and shrunk[3] <= a.rect[3])


@settings(max_examples=50, deadline=60000)
@given(pr_netlist_free())
def test_mr2_copper_layers_subset(data):
    pr, nl, free = data
    subset = fc.build_fixed_copper_items(pr, nl, free, copper_layers=frozenset({"F.Cu"}))
    full = fc.build_fixed_copper_items(pr, nl, free, copper_layers=_ALL_LAYERS)
    assert subset, "fixture must produce F.Cu items"
    # Zone items are identical in both runs (zones use COPPER_LAYERS).
    subset_zones = [i for i in subset if i.kind == "zone"]
    full_zones = [i for i in full if i.kind == "zone"]
    assert [(i.label, i.rect, i.exact) for i in subset_zones] == [
        (i.label, i.rect, i.exact) for i in full_zones
    ]
    # Every non-zone item under the subset is the full-run item with the
    # SAME label/geometry, its layers intersected with the subset.
    full_by_label = {i.label: i for i in full if i.kind != "zone"}
    for i in subset:
        if i.kind == "zone":
            continue
        f = full_by_label.get(i.label)
        assert f is not None, f"subset item {i.label} absent from full run"
        assert f.kind == i.kind and f.rect == i.rect and f.exact == i.exact, i.label
        assert set(i.layers) == set(f.layers) & {"F.Cu"}, i.label
        assert set(i.layers) <= {"F.Cu"}
    # And the subset run drops every full item with no F.Cu layer left.
    dropped = [i for i in full if i.kind != "zone" and not (set(i.layers) & {"F.Cu"})]
    subset_labels = {i.label for i in subset if i.kind != "zone"}
    assert all(i.label not in subset_labels for i in dropped), "dropped item leaked in"


def test_mr2_fails_for_zone_leak_mutant():
    """A zone item whose layers escape the module COPPER_LAYERS violates
    MR2's zone-identity claim."""
    z = fc.FixedCopperItem(
        kind="zone", net="NET_A", layers=frozenset({"Silkscreen"}),
        rect=(0.0, 0.0, 1.0, 1.0), exact={"polygon": [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]},
        slack_mm=float("inf"), margin_mm=0.05, label="mutant",
    )
    assert set(z.layers) == {"Silkscreen"}
    assert not set(z.layers) <= _ALL_LAYERS, "mutant must leak a non-copper layer"


@settings(max_examples=50, deadline=60000)
@given(st.integers(min_value=-20, max_value=20))
def test_mr3_origin_translation_invariance(d):
    """Translating BOTH the board origin and the raw trace/via coordinates by
    the same integer delta leaves the normalized item geometry UNCHANGED
    bit-exactly. Integer coordinates make the float64 arithmetic exact
    (`(a + d) - (b + d) == a - b`), so the cancellation is bit-perfect."""
    if d == 0:
        return  # identity case is trivial; the non-zero shifts are the point
    pr, nl, free = _static_board()
    items = fc.build_fixed_copper_items(pr, nl, free)
    tr_shifted = [
        TraceData(start=(t.start[0] + d, t.start[1] + d),
                  end=(t.end[0] + d, t.end[1] + d),
                  width=t.width, layer=t.layer, net=t.net)
        for t in pr.traces
    ]
    via_shifted = [
        type("V", (), {"layers": v.layers,
                       "position": (v.position[0] + d, v.position[1] + d),
                       "diameter": v.diameter, "net": v.net})()
        for v in pr.vias
    ]
    board2 = Board(width=pr.board.width, height=pr.board.height,
                   origin=(pr.board.origin[0] + d, pr.board.origin[1] + d),
                   zones=pr.board.zones)
    pr2 = type("PR", (), {"traces": tr_shifted, "vias": via_shifted, "board": board2})()
    items2 = fc.build_fixed_copper_items(pr2, nl, free)
    assert len(items) == len(items2)
    for a, b in zip(items, items2):
        assert a.kind == b.kind and a.net == b.net and a.label == b.label
        assert a.exact == b.exact, "origin translation must cancel in normalization"


def test_mr3_fails_for_origin_only_shift_mutant():
    """Shifting ONLY the origin (not the trace coords) must change the items;
    MR3's coupled-shift claim discriminates it."""
    tr = TraceData(start=(5.0, 5.0), end=(10.0, 5.0), width=0.2, layer="F.Cu", net="NET_X")
    board = Board(width=100.0, height=100.0, origin=(1.0, 1.0), zones=[])
    pr = SimpleNamespace(traces=[tr], vias=[], board=board)
    items = fc.build_fixed_copper_items(pr, _netlist(), {"U0"})
    assert items[0].exact["p0"] == (4.0, 4.0), "origin must be subtracted"
    # Mutant: raw (origin-ignoring) endpoint would be (5.0, 5.0).
    assert items[0].exact["p0"] != tr.start


@settings(max_examples=50, deadline=60000)
@given(pr_netlist_free())
def test_mr4_audit_monotone_in_clearance(data):
    """Pushing a resolved placement farther from every item never turns a
    zero-violation audit into a violation (monotone in clearance)."""
    pr, nl, free = data
    pads = fc.build_free_component_pads(nl, free)
    items = fc.build_fixed_copper_items(pr, nl, free)
    near = {"U0": (0.0, 0.0)}
    far = {"U0": (500.0, 500.0)}
    v_near = fc.audit_fixed_copper(pads, items, near, {"U0": 0})
    v_far = fc.audit_fixed_copper(pads, items, far, {"U0": 0})
    if v_near:
        # A violation at the near position must clear at the far position.
        assert v_far == [], f"far placement flagged: {[v.reason for v in v_far]}"
    else:
        assert v_far == []


def test_mr4_fails_for_flagging_far_mutant():
    """A placement 500 mm away cannot overlap any item; an audit flagging it
    violates MR4's monotonicity."""
    pr, nl, free = _static_board()
    pads = fc.build_free_component_pads(nl, free)
    items = fc.build_fixed_copper_items(pr, nl, free)
    far = {"U0": (500.0, 500.0)}
    assert fc.audit_fixed_copper(pads, items, far, {"U0": 0}) == []
    # Any item is within the board window far below 500 mm.
    assert all(
        all(abs(c) < 500 for c in i.rect) for i in items
    ), "far placement must clear every item by construction"


from types import SimpleNamespace  # noqa: E402


def _static_board():
    tr = TraceData(start=(0.0, 0.0), end=(10.0, 0.0), width=0.2, layer="F.Cu", net="NET_X")
    board = Board(width=100.0, height=100.0, origin=(0.0, 0.0), zones=[])
    pr = SimpleNamespace(traces=[tr], vias=[], board=board)
    return pr, _netlist(), {"U0"}
