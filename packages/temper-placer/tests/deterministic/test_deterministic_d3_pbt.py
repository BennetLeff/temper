"""Property-based tests (G4) for the D3 deterministic clearance-grid batch
(Rust Orchestration Engine plan 2026-08-09-001, Phase D batch D3).

The batch shares one oracle + corpus (the differential in
``test_deterministic_d3_rust_differential.py``); these properties cover the
whole batch unit with >=5 non-vacuous properties, every migrated surface
reached by at least one property:

- P1 (ClearanceGridStage): a state with no board returns the state unchanged
  (identity-preserving guard).
- P2 (ClearanceGridStage): an empty netlist produces an empty grid -- zero
  blocked cells and no net registrations.
- P3 (ClearanceGridStage): a pad blocks its own location.
- P4 (ClearanceGridStage): pads are mutually blocking across nets but
  transparent to their own net (``is_available`` with ``net_name=``).
- P5 (ClearanceGridStage): net ids are assigned in pin-first-seen order,
  1..N sequentially, so the registration order is deterministic.
- P6 (hv_pad_set): an explicit ``component_refdes`` zone yields exactly the
  pads of that component.
- P7 (fence perf budget): below the floor is exempt; above the budget is
  reported with an "exceeds budget" message.
- P8 (ClearanceGridStage): the HV creepage expansion strictly increases the
  blocked count on the expanded layer.

Vacuity guards: every property body is a standalone function taking the
implementation to exercise, so ``test_pN_fails_for_<mutant>`` re-runs the
SAME body against a degenerate stand-in and asserts the body's assertions
trip -- proving each property is non-vacuous (the established U4/D2 PBT
pattern).
"""

from __future__ import annotations

import temper_orchestration as _to
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic.state import BoardState
from temper_placer.io.config_loader import HVExclusionZone

_STAGE_DEFAULTS = dict(
    cell_size_mm=0.5,
    layer_count=2,
    pad_sizes={},
    max_clearance_mm=0.2,
    net_class_clearances={"Signal": 0.2},
    net_classes={},
    pth_mask_expansion_mm=0.0,
    smd_mask_expansion_mm=0.0,
    inner_layer_clearance_mm=0.2,
    hv_exclusion_zones=[],
    default_trace_width_mm=0.0,
)


def _run_stage(state, **overrides):
    kw = dict(_STAGE_DEFAULTS)
    kw.update(overrides)
    return _to.run_clearance_grid_stage(
        state,
        kw["cell_size_mm"],
        kw["layer_count"],
        kw["pad_sizes"],
        kw["max_clearance_mm"],
        kw["net_class_clearances"],
        kw["net_classes"],
        kw["pth_mask_expansion_mm"],
        kw["smd_mask_expansion_mm"],
        kw["inner_layer_clearance_mm"],
        kw["hv_exclusion_zones"],
        kw["default_trace_width_mm"],
    )


def _pad_size(width: float, height: float, shape: str = "circle"):
    class _Size:
        def __init__(self, w, h):
            self.X = w
            self.Y = h

    class _Pad:
        def __init__(self, w, h, shape):
            self.size = _Size(w, h)
            self.shape = shape
            self.rotation = 0.0

    return _Pad(width, height, shape)


def _pin(number, net, x, y, shape="circle", layer="F.Cu", width=2.0, height=2.0):
    return Pin(
        name=number,
        number=number,
        position=(x, y),
        net=net,
        shape=shape,
        layer=layer,
        width=width,
        height=height,
    )


@st.composite
def single_pad_state(draw: st.DrawFn):
    """A board + one circle-pad component at a mid-board position."""
    size = draw(st.floats(min_value=30.0, max_value=100.0, allow_nan=False, allow_infinity=False))
    pos = draw(
        st.floats(min_value=10.0, max_value=size - 10.0, allow_nan=False, allow_infinity=False)
    )
    pin = _pin("1", "NET_A", 0.0, 0.0)
    comp = Component(
        ref="Q1",
        footprint="FP",
        bounds=(5.0, 5.0),
        pins=[pin],
        net_class="Signal",
        initial_position=(pos, pos),
    )
    nl = Netlist(components=[comp], nets=[Net("NET_A", [("Q1", "1")], net_class="Signal")])
    return BoardState(board=Board(width=size, height=size), netlist=nl), pos, size


@st.composite
def two_pad_state(draw: st.DrawFn):
    """A board + two circle-pad components at distinct positions."""
    size = draw(st.floats(min_value=60.0, max_value=120.0, allow_nan=False, allow_infinity=False))
    a = draw(st.floats(min_value=10.0, max_value=25.0, allow_nan=False, allow_infinity=False))
    b = draw(st.floats(min_value=size - 25.0, max_value=size - 10.0, allow_nan=False, allow_infinity=False))
    comp_a = Component(
        ref="Q1",
        footprint="FP",
        bounds=(5.0, 5.0),
        pins=[_pin("1", "NET_A", 0.0, 0.0)],
        net_class="Signal",
        initial_position=(a, a),
    )
    comp_b = Component(
        ref="R1",
        footprint="FP",
        bounds=(5.0, 5.0),
        pins=[_pin("1", "NET_B", 0.0, 0.0)],
        net_class="Signal",
        initial_position=(b, b),
    )
    nl = Netlist(
        components=[comp_a, comp_b],
        nets=[
            Net("NET_A", [("Q1", "1")], net_class="Signal"),
            Net("NET_B", [("R1", "1")], net_class="Signal"),
        ],
    )
    return BoardState(board=Board(width=size, height=size), netlist=nl), a, b


def _zone(name, center, size, refdes=None, excluded_nets=()):
    return HVExclusionZone(
        name=name,
        center=center,
        size=size,
        clearance_mm=6.0,
        component_refdes=refdes,
        excluded_nets=list(excluded_nets),
    )


# ---------------------------------------------------------------------------
# P1 / P2 -- guards and empty grids
# ---------------------------------------------------------------------------

def _body_p1(impl, state):
    out = impl(state)
    assert out is state  # identity-preserving guard
    assert out.grid is None


@given(st.just(BoardState()))
@settings(max_examples=1, deadline=None)
def test_p1_no_board_noop(state):
    _body_p1(_run_stage, state)


def test_p1_fails_for_attach_mutant():
    """Mutant: attaches a grid even without a board -> P1 must trip."""

    def mutant(state):
        return BoardState()

    import pytest

    with pytest.raises(AssertionError):
        _body_p1(mutant, BoardState())


def _body_p2(impl, state):
    out = impl(state)
    grid = out.grid
    assert grid is not None
    assert grid.blocked_count == 0
    assert dict(grid._net_to_id) == {}


@given(st.just(BoardState(board=Board(width=50.0, height=50.0), netlist=Netlist([], []))))
@settings(max_examples=1, deadline=None)
def test_p2_empty_netlist_empty_grid(state):
    _body_p2(_run_stage, state)


def test_p2_fails_for_preblock_mutant():
    """Mutant: blocks a cell even with no pads -> P2 must trip."""

    def mutant(state):
        out = _run_stage(state)
        grid = out.grid
        grid.block_circle(center=(25.0, 25.0), radius_mm=1.0, clearance_mm=0.0)
        return out

    import pytest

    with pytest.raises(AssertionError):
        _body_p2(mutant, BoardState(board=Board(width=50.0, height=50.0), netlist=Netlist([], [])))


# ---------------------------------------------------------------------------
# P3 / P4 -- pad blocking semantics
# ---------------------------------------------------------------------------

def _body_p3(impl, inp):
    state, pos, _size = inp
    out = impl(state, pad_sizes={("Q1", "1"): _pad_size(2.0, 2.0, "circle")})
    grid = out.grid
    assert grid is not None
    # A 1.0mm-radius pad at (pos, pos) with clearance 0.2 blocks its center.
    assert grid.is_available(pos, pos, layer=0) is False
    assert grid.is_available(pos + 3.0, pos, layer=0) is True


@given(two_pad_state())
@settings(max_examples=40, deadline=None)
def test_p3_pad_blocks_its_location(inp):
    _body_p3(_run_stage, inp)


def test_p3_fails_for_skip_blocking_mutant():
    """Mutant: never blocks pads -> P3 must trip."""

    def mutant(state, **kwargs):  # noqa: ARG001
        return BoardState(board=state.board, netlist=state.netlist)

    import pytest

    with pytest.raises(AssertionError):
        _body_p3(mutant, (BoardState(board=Board(width=50.0, height=50.0)), 25.0, 50.0))


def _body_p4(impl, inp):
    state, a, b = inp
    out = impl(state, pad_sizes={})
    grid = out.grid
    # Each pad blocks the OTHER net's view of its own cell, but its own
    # net can route to it: `is_available(x, y, net_name=...)`.
    assert grid.is_available(a, a, layer=0, net_name="NET_A") is True
    assert grid.is_available(a, a, layer=0, net_name="NET_B") is False
    assert grid.is_available(b, b, layer=0, net_name="NET_B") is True
    assert grid.is_available(b, b, layer=0, net_name="NET_A") is False


@given(two_pad_state())
@settings(max_examples=40, deadline=None)
def test_p4_cross_net_mutual_blocking(inp):
    _body_p4(_run_stage, inp)


def test_p4_fails_for_obstacle_mutant():
    """Mutant: blocks pads as obstacles (net_name=None, id -2) so a pad's
    OWN net cannot route to it -> P4 must trip."""

    def mutant(state, **kwargs):
        kw = dict(kwargs)
        kw["net_classes"] = {}
        out = _to.run_clearance_grid_stage(
            state, kw.get("cell_size_mm", 0.5), kw.get("layer_count", 2), kw.get("pad_sizes", {}),
            kw.get("max_clearance_mm", 0.2), kw.get("net_class_clearances", {"Signal": 0.2}),
            kw.get("net_classes", {}), 0.0, 0.0, 0.2, [], 0.0,
        )
        # Re-block every pad cell as an obstacle so own-net availability dies.
        grid = out.grid
        for comp in state.netlist.components:
            for pin in comp.pins:
                if pin.net:
                    grid.block_circle(
                        center=(comp.initial_position[0] + pin.position[0],
                                comp.initial_position[1] + pin.position[1]),
                        radius_mm=0.5, clearance_mm=0.0, net_name=None,
                    )
        return BoardState(board=state.board, netlist=state.netlist, grid=grid)

    import pytest

    with pytest.raises(AssertionError):
        _body_p4(mutant, (BoardState(board=Board(width=50.0, height=50.0)), 10.0, 40.0))


# ---------------------------------------------------------------------------
# P5 -- net registration order
# ---------------------------------------------------------------------------

def _body_p5(impl, state):
    out = impl(state, pad_sizes={})
    grid = out.grid
    ids = dict(grid._net_to_id)
    assert list(ids) == ["NET_A", "NET_B", "NET_C"]  # pin-first-seen order
    assert list(ids.values()) == [1, 2, 3]  # sequential from 1


@given(st.just(
    BoardState(
        board=Board(width=50.0, height=50.0),
        netlist=Netlist(
            components=[
                Component(
                    ref="U1",
                    footprint="FP",
                    bounds=(5.0, 5.0),
                    pins=[
                        _pin("1", "NET_A", 0.0, 0.0),
                        _pin("2", "NET_B", 1.0, 0.0),
                        _pin("3", "NET_C", 2.0, 0.0),
                    ],
                    initial_position=(25.0, 25.0),
                )
            ],
            nets=[
                Net("NET_A", [("U1", "1")], net_class="Signal"),
                Net("NET_B", [("U1", "2")], net_class="Signal"),
                Net("NET_C", [("U1", "3")], net_class="Signal"),
            ],
        ),
    )
))
@settings(max_examples=1, deadline=None)
def test_p5_net_ids_in_pin_order(state):
    _body_p5(_run_stage, state)


def test_p5_fails_for_reverse_registration_mutant():
    """Mutant: registers nets in reverse pin order -> P5 must trip."""

    def mutant(state, **kwargs):
        out = _run_stage(state, **kwargs)
        grid = out.grid
        # Corrupt the net map after the fact: reverse the ids.
        ids = dict(grid._net_to_id)
        rev = {name: 4 - idx for name, idx in ids.items()}
        grid._net_to_id.clear()
        grid._net_to_id.update(rev)
        return out

    import pytest

    state = BoardState(
        board=Board(width=50.0, height=50.0),
        netlist=Netlist(
            components=[
                Component(
                    ref="U1",
                    footprint="FP",
                    bounds=(5.0, 5.0),
                    pins=[
                        _pin("1", "NET_A", 0.0, 0.0),
                        _pin("2", "NET_B", 1.0, 0.0),
                        _pin("3", "NET_C", 2.0, 0.0),
                    ],
                    initial_position=(25.0, 25.0),
                )
            ],
            nets=[
                Net("NET_A", [("U1", "1")], net_class="Signal"),
                Net("NET_B", [("U1", "2")], net_class="Signal"),
                Net("NET_C", [("U1", "3")], net_class="Signal"),
            ],
        ),
    )
    with pytest.raises(AssertionError):
        _body_p5(mutant, state)


# ---------------------------------------------------------------------------
# P6 -- hv_pad_set explicit refdes
# ---------------------------------------------------------------------------

def _body_p6(impl, pads, zones, positions, ref):
    result = impl(pads, zones, positions)
    assert result == {(p["ref"], p["name"]) for p in pads if p["ref"] == ref}


@given(st.just((
    [
        {"ref": "Q1", "name": "G"},
        {"ref": "Q1", "name": "D"},
        {"ref": "R1", "name": "1"},
        {"ref": "R1", "name": "2"},
    ],
    [{"name": "z", "component_refdes": "Q1"}],
    {"Q1": (10.0, 10.0), "R1": (40.0, 40.0)},
    "Q1",
)))
@settings(max_examples=1, deadline=None)
def test_p6_hv_pad_set_explicit_refdes(inp):
    pads, zones, positions, ref = inp
    z = type(
        "Z",
        (),
        {"component_refdes": zones[0]["component_refdes"], "center": (0, 0), "size": (1, 1), "name": "z"},
    )()
    _body_p6(_to.run_hv_pad_set, pads, [z], positions, ref)


def test_p6_fails_for_all_pads_mutant():
    """Mutant: returns every pad regardless of the zone -> P6 must trip."""

    def mutant(pads, zones, positions):  # noqa: ARG001
        return set((p["ref"], p["name"]) for p in pads)

    import pytest

    pads = [{"ref": "Q1", "name": "G"}, {"ref": "R1", "name": "1"}]
    z = type("Z", (), {"component_refdes": "Q1", "center": (0, 0), "size": (1, 1), "name": "z"})()
    with pytest.raises(AssertionError):
        _body_p6(mutant, pads, [z], {"Q1": (10.0, 10.0), "R1": (40.0, 40.0)}, "Q1")


# ---------------------------------------------------------------------------
# P7 -- fence perf budget
# ---------------------------------------------------------------------------

def _body_p7(impl):
    # Below the floor -> exempt.
    over, msg = impl(10.0, 20.0, 20.0, 50.0)
    assert over is False and msg is None
    # Above the budget (above the floor) -> reported with the message.
    over, msg = impl(40.0, 100.0, 20.0, 50.0)
    assert over is True
    assert msg is not None and "exceeds budget" in msg


@given(st.just(0))
@settings(max_examples=1, deadline=None)
def test_p7_perf_budget_floor_and_overrun(_):
    _body_p7(_to.run_grid_perf_budget)


def test_p7_fails_for_never_over_budget_mutant():
    """Mutant: always returns under-budget -> P7 must trip."""

    def mutant(fence, stage, budget, floor):  # noqa: ARG001
        return (False, None)

    import pytest

    with pytest.raises(AssertionError):
        _body_p7(mutant)


# ---------------------------------------------------------------------------
# P8 -- HV creepage expansion grows blocking
# ---------------------------------------------------------------------------

def _hv_expansion_state():
    pin = _pin("1", "HV", 0.0, 0.0)
    comp = Component(
        ref="Q1",
        footprint="FP",
        bounds=(5.0, 5.0),
        pins=[pin],
        net_class="HighVoltage",
        initial_position=(25.0, 25.0),
    )
    nl = Netlist(components=[comp], nets=[Net("HV", [("Q1", "1")], net_class="HighVoltage")])
    return BoardState(board=Board(width=50.0, height=50.0), netlist=nl)


def _body_p8(impl, state):
    base_kwargs = dict(
        net_class_clearances={"Signal": 0.2, "HighVoltage": 0.2},
        pad_sizes={("Q1", "1"): _pad_size(2.0, 2.0, "circle")},
    )
    without = impl(state, **base_kwargs).grid
    zone = _zone("q1_zone", (25.0, 25.0), (10.0, 10.0), refdes="Q1")
    with_hv = impl(state, **base_kwargs, hv_exclusion_zones=[zone]).grid
    # The expansion strictly grows the layer-0 blocked count.
    assert with_hv.blocked_count_on_layer(0) > without.blocked_count_on_layer(0)


@given(st.just(_hv_expansion_state()))
@settings(max_examples=1, deadline=None)
def test_p8_hv_expansion_grows_blocking(state):
    _body_p8(_run_stage, state)


def test_p8_fails_for_skip_expansion_mutant():
    """Mutant: ignores hv_exclusion_zones (no expansion pass) -> P8 must trip."""

    def mutant(state, **kwargs):
        kw = dict(kwargs)
        kw["hv_exclusion_zones"] = []
        return _run_stage(state, **kw)

    import pytest

    with pytest.raises(AssertionError):
        _body_p8(mutant, _hv_expansion_state())
