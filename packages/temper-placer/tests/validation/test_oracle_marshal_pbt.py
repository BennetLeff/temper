"""Property-based tests for the Phase-A U6 oracle marshalers
(Wave-4 discipline contract G4/G5).

Verification unit: the U6 marshal cluster — `temper_drc_rs.OracleInput`
(`_netlist_to_oracle_dict`) and `temper_drc_rs.OracleOutput`
(`_placement_to_oracle_dict`), exercised through the Python shims in
`validation/human_reference_extractor.py` that delegate to the Rust
pyclasses.

Module → property map (G4 note: every module reached by >= 1 property):

  | Module                  | Properties |
  |-------------------------|------------|
  | `OracleInput`           | P1, P3, P4, P5 |
  | `OracleOutput`          | P2, P4, P5, P6 |

Reachability is measured, not assumed: P1/P2 assert the shim output against
the verbatim pinned oracle (imported from the G1 differential file) over
generated netlists/states; P3/P4 pin per-field structure; P5 pins the
cross-marshaler 1:1 ref alignment the extractor's positions rows rely on;
P6 draws a varying board so the dims are genuinely discriminating. Every
property has a `test_pN_fails_for_<mutant>` companion (G4 vacuity guard)
proving a degenerate kernel violates it.

Metamorphic relations (G5, >= 3) are in the labelled section at the bottom.
"""

from __future__ import annotations

import numpy as np
import pytest
import temper_drc_rs as _tdrc  # noqa: F401  (imported for the is-instance checks)
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.core.board import Board  # noqa: E402
from temper_placer.core.netlist import Component, Net, Netlist  # noqa: E402
from temper_placer.core.state import PlacementState  # noqa: E402
from temper_placer.validation import human_reference_extractor as _hr  # noqa: E402

# The verbatim pre-migration marshaler bodies (pinned in the G1 differential
# file) are the oracle reference for the kernel-equivalence properties.
from tests.validation.test_oracle_marshal_rust_differential import (  # noqa: E402, I001
    _float_hex_recursive,
    _oracle_netlist_to_oracle_dict,
    _oracle_placement_to_oracle_dict,
)


# ---------------------------------------------------------------------------
# Input strategies
# ---------------------------------------------------------------------------

_FLOAT = st.floats(0.1, 50.0, allow_nan=False, allow_infinity=False)
_REF = st.text(min_size=1, max_size=6)


@st.composite
def oracle_netlist(draw):
    """A design-bundle Netlist with 0..5 components and 0..3 nets."""
    n_comps = draw(st.integers(min_value=0, max_value=5))
    comps = [
        Component(
            ref=f"C{i}",
            footprint=draw(st.text(min_size=1, max_size=10)),
            bounds=(draw(_FLOAT), draw(_FLOAT)),
        )
        for i in range(n_comps)
    ]
    n_nets = draw(st.integers(min_value=0, max_value=3))
    nets = [
        Net(
            name=f"N{j}",
            pins=[
                (draw(_REF), str(draw(st.integers(1, 20))))
                for _ in range(draw(st.integers(min_value=0, max_value=4)))
            ],
        )
        for j in range(n_nets)
    ]
    return Netlist(components=comps, nets=nets)


@st.composite
def oracle_context(draw):
    """A netlist + aligned PlacementState + board (the full extractor
    input triple)."""
    netlist = draw(oracle_netlist())
    n = len(netlist.components)
    dtype = draw(st.sampled_from([np.float32, np.float64]))
    positions = np.asarray(
        [[draw(_FLOAT), draw(_FLOAT)] for _ in range(n)], dtype=dtype
    )
    state = PlacementState(
        positions=positions,
        rotation_logits=np.zeros((n, 4), dtype=np.float32),
    )
    board = Board(
        width=draw(st.floats(10.0, 200.0, allow_nan=False, allow_infinity=False)),
        height=draw(st.floats(10.0, 200.0, allow_nan=False, allow_infinity=False)),
    )
    return netlist, state, board


# ---------------------------------------------------------------------------
# P1 — netlist dict == pinned oracle (bit-exact)
# ---------------------------------------------------------------------------


@given(oracle_netlist())
@settings(max_examples=50, deadline=None)
def test_p1_netlist_dict_matches_oracle(netlist):
    """P1: `_netlist_to_oracle_dict(nl)` is bit-identical to the pinned
    pre-migration `_netlist_to_oracle_dict` on every generated netlist. A
    kernel that returns a constant (or skips nets/components) violates it."""
    got = _hr._netlist_to_oracle_dict(netlist)
    assert _float_hex_recursive(got) == _float_hex_recursive(
        _oracle_netlist_to_oracle_dict(netlist)
    )


# ---------------------------------------------------------------------------
# P2 — placement dict == pinned oracle (bit-exact)
# ---------------------------------------------------------------------------


@given(oracle_context())
@settings(max_examples=50, deadline=None)
def test_p2_placement_dict_matches_oracle(ctx):
    """P2: `_placement_to_oracle_dict(state, nl, board)` is bit-identical to
    the pinned oracle over generated states/netlists/boards — including the
    float32→float64 upcast and the row-major reshape order."""
    netlist, state, board = ctx
    got = _hr._placement_to_oracle_dict(state, netlist, board)
    assert _float_hex_recursive(got) == _float_hex_recursive(
        _oracle_placement_to_oracle_dict(state, netlist, board)
    )


# ---------------------------------------------------------------------------
# P3 — per-net pins structure (ref-only, in pin order)
# ---------------------------------------------------------------------------


@given(oracle_netlist())
@settings(max_examples=50, deadline=None)
def test_p3_net_pins_ref_only_in_order(netlist):
    """P3: every net dict's `pins` is exactly `[ref for ref, _ in net.pins]`
    — the pin-number half stripped, duplicates preserved, order kept. A
    kernel that dedups or reorders pins violates it."""
    d = _hr._netlist_to_oracle_dict(netlist)
    for j, net in enumerate(netlist.nets):
        assert d["nets"][j]["name"] == net.name
        assert d["nets"][j]["pins"] == [ref for ref, _ in net.pins]
    assert len(d["nets"]) == len(netlist.nets)


# ---------------------------------------------------------------------------
# P4 — per-component width/height (bounds-derived floats)
# ---------------------------------------------------------------------------


@given(oracle_netlist())
@settings(max_examples=50, deadline=None)
def test_p4_component_bounds_to_float(netlist):
    """P4: every component dict carries `float(bounds[0])` / `float(bounds[1])`
    as width/height, in netlist component order, with no extra keys. A kernel
    that swaps width/height or emits a fixed size violates it."""
    d = _hr._netlist_to_oracle_dict(netlist)
    for i, comp in enumerate(netlist.components):
        cd = d["components"][i]
        assert cd == {
            "ref": comp.ref,
            "footprint": comp.footprint,
            "width": float(comp.bounds[0]),
            "height": float(comp.bounds[1]),
        }


# ---------------------------------------------------------------------------
# P5 — cross-marshaler 1:1 ref alignment (extractor's load-bearing invariant)
# ---------------------------------------------------------------------------


@given(oracle_context())
@settings(max_examples=50, deadline=None)
def test_p5_refs_align_with_positions(ctx):
    """P5: the netlist marshaler's component refs and the placement
    marshaler's `component_refs` are identical (both derive from
    `netlist.components` order), and the flat position list has exactly
    2 entries per ref — the 1:1 positions-row alignment the quality oracle's
    `extract_placement` relies on. A kernel that reorders either list
    violates it."""
    netlist, state, board = ctx
    input_refs = [c["ref"] for c in _hr._netlist_to_oracle_dict(netlist)["components"]]
    placement = _hr._placement_to_oracle_dict(state, netlist, board)
    assert placement["component_refs"] == input_refs
    assert len(placement["positions"]) == 2 * len(placement["component_refs"])


# ---------------------------------------------------------------------------
# P6 — board dims
# ---------------------------------------------------------------------------


@given(oracle_context())
@settings(max_examples=50, deadline=None)
def test_p6_board_dims(ctx):
    """P6: `board_width_mm` / `board_height_mm` equal `float(board.width)` /
    `float(board.height)`. A kernel that hardcodes dims violates it."""
    netlist, state, board = ctx
    d = _hr._placement_to_oracle_dict(state, netlist, board)
    assert d["board_width_mm"] == float(board.width)
    assert d["board_height_mm"] == float(board.height)


# ---------------------------------------------------------------------------
# Concrete inputs for the vacuity guards
# ---------------------------------------------------------------------------


def _concrete_netlist() -> Netlist:
    return Netlist(
        components=[Component(ref="C1", footprint="0805", bounds=(2.0, 1.5))],
        nets=[Net(name="VCC", pins=[("C1", "1"), ("C1", "2")])],
    )


def _concrete_context():
    netlist = _concrete_netlist()
    state = PlacementState(
        positions=np.array([[10.0, 20.0]], dtype=np.float32),
        rotation_logits=np.zeros((1, 4), dtype=np.float32),
    )
    return netlist, state, Board(width=100.0, height=80.0)


def _concrete_context_two_components():
    """>= 2 components so an order-mutating kernel is genuinely
    discriminating (reversing a 1-element list is a no-op)."""
    netlist = Netlist(
        components=[
            Component(ref="C1", footprint="0805", bounds=(2.0, 1.5)),
            Component(ref="R1", footprint="0603", bounds=(1.0, 1.0)),
        ],
        nets=[Net(name="VCC", pins=[("C1", "1"), ("R1", "1")])],
    )
    state = PlacementState(
        positions=np.array([[10.0, 20.0], [30.0, 40.0]], dtype=np.float32),
        rotation_logits=np.zeros((2, 4), dtype=np.float32),
    )
    return netlist, state, Board(width=100.0, height=80.0)


# ---------------------------------------------------------------------------
# Vacuity guards — a degenerate kernel must violate its property
# ---------------------------------------------------------------------------


def test_p1_fails_for_empty_constant_kernel(monkeypatch):
    monkeypatch.setattr(
        _hr,
        "_netlist_to_oracle_dict",
        lambda _nl: {"nets": [], "components": []},
    )
    with pytest.raises(AssertionError):
        test_p1_netlist_dict_matches_oracle.hypothesis.inner_test(_concrete_netlist())


def test_p2_fails_for_empty_constant_kernel(monkeypatch):
    monkeypatch.setattr(
        _hr,
        "_placement_to_oracle_dict",
        lambda *_a: {"positions": [], "component_refs": [], "board_width_mm": 0.0, "board_height_mm": 0.0},
    )
    with pytest.raises(AssertionError):
        test_p2_placement_dict_matches_oracle.hypothesis.inner_test(_concrete_context())


def test_p3_fails_for_dedup_kernel(monkeypatch):
    def _dedup(netlist):
        d = _oracle_netlist_to_oracle_dict(netlist)
        d["nets"] = [{"name": n["name"], "pins": list(dict.fromkeys(n["pins"]))} for n in d["nets"]]
        return d

    monkeypatch.setattr(_hr, "_netlist_to_oracle_dict", _dedup)
    with pytest.raises(AssertionError):
        test_p3_net_pins_ref_only_in_order.hypothesis.inner_test(_concrete_netlist())


def test_p4_fails_for_hardcoded_size_kernel(monkeypatch):
    def _fixed_size(netlist):
        d = _oracle_netlist_to_oracle_dict(netlist)
        d["components"] = [dict(c, width=9.9, height=9.9) for c in d["components"]]
        return d

    monkeypatch.setattr(_hr, "_netlist_to_oracle_dict", _fixed_size)
    with pytest.raises(AssertionError):
        test_p4_component_bounds_to_float.hypothesis.inner_test(_concrete_netlist())


def test_p5_fails_for_reordered_refs_kernel(monkeypatch):
    def _reversed_refs(state, netlist, board):
        d = _oracle_placement_to_oracle_dict(state, netlist, board)
        d["component_refs"] = list(reversed(d["component_refs"]))
        return d

    monkeypatch.setattr(_hr, "_placement_to_oracle_dict", _reversed_refs)
    with pytest.raises(AssertionError):
        test_p5_refs_align_with_positions.hypothesis.inner_test(_concrete_context_two_components())


def test_p6_fails_for_hardcoded_board_kernel(monkeypatch):
    def _fixed_board(state, netlist, board):
        d = _oracle_placement_to_oracle_dict(state, netlist, board)
        d["board_width_mm"] = 123.0
        d["board_height_mm"] = 456.0
        return d

    monkeypatch.setattr(_hr, "_placement_to_oracle_dict", _fixed_board)
    with pytest.raises(AssertionError):
        test_p6_board_dims.hypothesis.inner_test(_concrete_context())


# ---------------------------------------------------------------------------
# G5 metamorphic relations (>= 3), each naming its exactness claim
# ---------------------------------------------------------------------------


def _make_netlist(comps, nets):
    return Netlist(components=comps, nets=nets)


def _state_for(positions):
    return PlacementState(
        positions=np.asarray(positions, dtype=np.float32),
        rotation_logits=np.zeros((len(positions), 4), dtype=np.float32),
    )


def test_mr1_component_order_preserved():
    """MR1 (exact): prepending a component to the netlist prepends its ref to
    `component_refs` and its position pair to the flat `positions` list —
    the marshaler is strictly order-preserving (the extractor's positions
    rows line up 1:1 with the refs)."""
    board = Board(width=100.0, height=80.0)
    comps = [Component(ref="A", footprint="0805", bounds=(2.0, 1.5)),
             Component(ref="B", footprint="0603", bounds=(1.0, 1.0))]
    netlist = _make_netlist(comps, [])
    state = _state_for([[10.0, 20.0], [30.0, 40.0]])

    front = _make_netlist([Component(ref="X", footprint="0402", bounds=(0.5, 0.5))] + comps, [])
    front_state = _state_for([[0.0, 0.0], [10.0, 20.0], [30.0, 40.0]])

    before = _hr._placement_to_oracle_dict(state, netlist, board)
    after = _hr._placement_to_oracle_dict(front_state, front, board)

    assert after["component_refs"] == ["X"] + before["component_refs"]
    assert after["positions"] == [0.0, 0.0] + before["positions"]


def test_mr2_input_output_ref_consistency():
    """MR2 (exact): for any netlist, the netlist marshaler's component refs
    and the placement marshaler's `component_refs` are the same sequence —
    the two dicts are built from the same `netlist.components` order, so a
    mutation of one must never desynchronise the other."""
    comps = [Component(ref="C1", footprint="0805", bounds=(2.0, 1.5)),
             Component(ref="R1", footprint="0603", bounds=(1.0, 1.0)),
             Component(ref="U1", footprint="QFN-32", bounds=(5.0, 5.0))]
    netlist = _make_netlist(comps, [Net(name="VCC", pins=[("C1", "1"), ("R1", "1")])])
    state = _state_for([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
    board = Board(width=50.0, height=40.0)

    input_refs = [c["ref"] for c in _hr._netlist_to_oracle_dict(netlist)["components"]]
    output_refs = _hr._placement_to_oracle_dict(state, netlist, board)["component_refs"]
    assert input_refs == output_refs == ["C1", "R1", "U1"]


def test_mr3_power_of_two_scale():
    """MR3 (exact for powers of two): scaling every position and the board by
    2.0 scales the flattened `positions` and the board-dict dims by exactly
    2.0 — 2.0 is a power of two, so the multiply is bit-exact in IEEE, and
    the float32→float64 upcast commutes with it."""
    board = Board(width=100.0, height=80.0)
    netlist = _make_netlist([Component(ref="C1", footprint="0805", bounds=(2.0, 1.5))], [])
    base = _state_for([[10.0, 20.0]])
    scaled = _state_for([[20.0, 40.0]])
    scaled_board = Board(width=200.0, height=160.0)

    d1 = _hr._placement_to_oracle_dict(base, netlist, board)
    d2 = _hr._placement_to_oracle_dict(scaled, netlist, scaled_board)

    assert d2["positions"] == [2.0 * p for p in d1["positions"]]
    assert d2["board_width_mm"] == 2.0 * d1["board_width_mm"]
    assert d2["board_height_mm"] == 2.0 * d1["board_height_mm"]


def test_mr4_duplicate_pin_refs_preserved():
    """MR4 (exact): appending a duplicate pin ref to a net appends a
    duplicate ref to the dict's `pins` — the marshaler is a pass-through,
    never a set/dedup (unlike the DRC `nets_from_list`)."""
    comp = Component(ref="C1", footprint="0805", bounds=(2.0, 1.5))
    single = _make_netlist([comp], [Net(name="VCC", pins=[("C1", "1")])])
    dup = _make_netlist([comp], [Net(name="VCC", pins=[("C1", "1"), ("C1", "2"), ("C1", "1")])])

    d1 = _hr._netlist_to_oracle_dict(single)["nets"][0]["pins"]
    d2 = _hr._netlist_to_oracle_dict(dup)["nets"][0]["pins"]
    assert d1 == ["C1"]
    assert d2 == ["C1", "C1", "C1"]
