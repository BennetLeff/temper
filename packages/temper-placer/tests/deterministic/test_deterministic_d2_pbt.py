"""Property-based tests (G4) for the D2 deterministic zone stages (Rust
Orchestration Engine plan 2026-08-09-001, Phase D batch D2).

The batch shares one oracle + corpus (the differential in
``test_deterministic_d2_rust_differential.py``); these properties cover the
whole batch unit with >=5 non-vacuous properties, every stage reached by at
least one property:

- P1 (zone_geometry): a state with no board returns ``zones`` unchanged
  (identity-preserving guard).
- P2 (zone_geometry): a board produces exactly the 4 MVP-3 zones
  (HV/Power/Signal/MCU), contiguous, covering the full board extent.
- P3 (zone_geometry): a dict config with ``bounds_ratio`` scales the zone
  bounds exactly as ``ratio[i] * board_dim``.
- P4 (zone_assignment): the map has exactly one entry per netlist
  component, with refs preserved and zones drawn from {HV, Power, Signal,
  MCU}.
- P5 (zone_assignment): a state with no netlist returns
  ``component_zone_map`` unchanged (identity-preserving guard).
- P6 (slot_generation): every zone's slots are strictly inside the zone
  bounds (half-cell anchor ``min + spacing/2 <= coord < max``), and the
  slot-set keys are exactly the zone names.
- P7 (slot_generation): a state with no/empty zones returns ``zone_slots``
  unchanged (identity-preserving guard).

Vacuity guards: every property body is a standalone function taking the
implementation to exercise, so ``test_pN_fails_for_<mutant>`` re-runs the
SAME body against a degenerate stand-in and asserts the body's assertions
trip -- proving each property is non-vacuous (the established U4 PBT
pattern).
"""

from __future__ import annotations

import temper_orchestration as _to
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic.state import BoardState

_ZONES = {"HV", "Power", "Signal", "MCU"}


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

def _board_state(board: Board | None) -> BoardState:
    return BoardState(board=board)


@st.composite
def geometry_input(draw: st.DrawFn) -> tuple[BoardState, list | None]:
    """A (state, config) pair: either a board-only state (no config) or a
    dict-config state."""
    has_config = draw(st.booleans())
    width = draw(st.floats(min_value=10.0, max_value=200.0, allow_nan=False))
    height = draw(st.floats(min_value=10.0, max_value=200.0, allow_nan=False))
    state = BoardState(board=Board(width=width, height=height))
    if not has_config:
        return state, None
    names = draw(
        st.lists(
            st.text(min_size=1, max_size=8, alphabet="ABCDE"),
            min_size=1,
            max_size=3,
            unique=True,
        )
    )
    config = [
        {
            "name": name,
            "bounds_ratio": [
                draw(st.floats(min_value=0.0, max_value=0.5, allow_nan=False)),
                draw(st.floats(min_value=0.0, max_value=0.5, allow_nan=False)),
                draw(st.floats(min_value=0.5, max_value=1.0, allow_nan=False)),
                draw(st.floats(min_value=0.5, max_value=1.0, allow_nan=False)),
            ],
        }
        for name in names
    ]
    return state, config


@st.composite
def assignment_input(draw: st.DrawFn) -> tuple[BoardState, Netlist]:
    """A (state, netlist) pair: a state with a netlist of 1-4 components."""
    refs = draw(
        st.lists(
            st.sampled_from(["Q1", "C1", "U_MCU1", "U2", "R1", "R2"]),
            min_size=1,
            max_size=4,
            unique=True,
        )
    )
    rows = []
    for i, ref in enumerate(refs):
        if ref.startswith("Q"):
            net, net_class = "AC_L", "HighVoltage"
        elif ref.startswith("C"):
            net, net_class = "VBUS", "Power"
        elif ref.startswith("U_MCU"):
            net, net_class = "3V3", "Signal"
        elif ref.startswith("U"):
            net, net_class = "SPI_MOSI", "Signal"
        else:
            net, net_class = "SENSE", "Signal"
        rows.append(
            (
                Component(
                    ref=ref,
                    footprint="FP",
                    bounds=(1.0, 1.0),
                    pins=[Pin(str(i), "1", (0.0, 0.0), net=net)],
                ),
                Net(net, [(ref, "1")], net_class=net_class),
            )
        )
    comps, nets = zip(*rows)
    netlist = Netlist(components=list(comps), nets=list(nets))
    return BoardState(netlist=netlist), netlist


def _zone_class():
    from temper_placer.deterministic.stages.zone_geometry import Zone

    return Zone


@st.composite
def slots_state(draw: st.DrawFn) -> BoardState:
    """A state with 1-3 zones of generous extent (guaranteeing non-empty
    slot grids at the tested spacings)."""
    Zone = _zone_class()
    n = draw(st.integers(min_value=1, max_value=3))
    zones = set()
    for i in range(n):
        name = draw(st.sampled_from(["HV", "P", "S"]))
        while name in {z.name for z in zones}:
            name += "_"
        x0 = draw(st.floats(min_value=0.0, max_value=50.0, allow_nan=False))
        y0 = draw(st.floats(min_value=0.0, max_value=50.0, allow_nan=False))
        # Extent >= 20mm, so even spacing=5.0 yields a non-empty grid
        # (needs extent > spacing/2; 20 >> 2.5).
        x1 = x0 + draw(st.floats(min_value=20.0, max_value=50.0, allow_nan=False))
        y1 = y0 + draw(st.floats(min_value=20.0, max_value=50.0, allow_nan=False))
        zones.add(Zone(name=name, bounds=((x0, y0), (x1, y1))))
    return BoardState(zones=frozenset(zones))


# ---------------------------------------------------------------------------
# P1 / P2 / P3 -- ZoneGeometryStage
# ---------------------------------------------------------------------------

def _body_p1(impl, state):
    out = impl(state, None)
    assert out is state  # identity-preserving guard
    assert out.zones == state.zones == frozenset()


@given(st.just(BoardState()))
@settings(max_examples=1, deadline=None)
def test_p1_zone_geometry_no_board_noop(state):
    _body_p1(_to.run_zone_geometry, state)


def test_p1_fails_for_attach_mutant():
    """Mutant: attaches zones even without a board -> P1 must trip."""

    def mutant(state, zone_config):  # noqa: ARG001
        return BoardState(zones=frozenset())

    _assert_mutant_detected(_body_p1, mutant, BoardState())


def _body_p2(impl, state):
    out = impl(state, None)
    zones = out.zones
    assert len(zones) == 4
    assert {z.name for z in zones} == _ZONES
    w = state.board.width
    h = state.board.height
    by_name = {z.name: z for z in zones}
    for z in by_name.values():
        (x_min, y_min), (x_max, y_max) = z.bounds
        assert y_min == 0
        assert y_max == h
        assert x_min < x_max
    # Contiguous left-to-right coverage of [0, w].
    ordered = sorted(zones, key=lambda z: z.bounds[0][0])
    assert ordered[0].bounds[0][0] == 0
    assert ordered[-1].bounds[1][0] == w
    for i in range(len(ordered) - 1):
        assert ordered[i].bounds[1][0] == ordered[i + 1].bounds[0][0]


@given(geometry_input())
@settings(max_examples=100, deadline=None)
def test_p2_zone_geometry_four_zone_layout(inp):
    state, config = inp
    if config is not None:
        return  # P2 is the no-config branch
    _body_p2(_to.run_zone_geometry, state)


def test_p2_fails_for_drop_zone_mutant():
    """Mutant: drops a zone -> the 4-zone property trips."""

    def mutant(state, zone_config):  # noqa: ARG001
        out = _to.run_zone_geometry(state, None)
        names = [z.name for z in out.zones]
        kept = frozenset(z for z in out.zones if z.name != names[0])
        return BoardState(board=state.board, zones=kept)

    state = BoardState(board=Board(width=100.0, height=100.0))
    _assert_mutant_detected(_body_p2, mutant, state)


def _body_p3(impl, state, config):
    out = impl(state, config)
    zones = {z.name: z for z in out.zones}
    w = state.board.width
    h = state.board.height
    for entry in config:
        z = zones[entry["name"]]
        r0, r1, r2, r3 = entry["bounds_ratio"]
        assert z.bounds == ((r0 * w, r1 * h), (r2 * w, r3 * h))


@given(geometry_input())
@settings(max_examples=100, deadline=None)
def test_p3_zone_geometry_dict_config_scales(inp):
    state, config = inp
    if config is None:
        return  # P3 is the config branch
    _body_p3(_to.run_zone_geometry, state, config)


def test_p3_fails_for_wrong_scale_mutant():
    """Mutant: scales by the board dims swapped -> P3 trips."""

    def mutant(state, config):
        out = _to.run_zone_geometry(state, None)
        w = state.board.width
        h = state.board.height
        zones = []
        for entry in config:
            r0, r1, r2, r3 = entry["bounds_ratio"]
            zones.append(
                __import__(
                    "temper_placer.deterministic.stages.zone_geometry", fromlist=["Zone"]
                ).Zone(
                    name=entry["name"],
                    bounds=((r0 * h, r1 * w), (r2 * h, r3 * w)),
                )
            )
        return BoardState(board=state.board, zones=frozenset(zones))

    state = BoardState(board=Board(width=100.0, height=50.0))
    config = [{"name": "X", "bounds_ratio": [0.1, 0.2, 0.6, 0.9]}]
    _assert_mutant_detected(_body_p3, mutant, state, config)


# ---------------------------------------------------------------------------
# P4 / P5 -- ZoneAssignmentStage
# ---------------------------------------------------------------------------

def _body_p4(impl, state, netlist):
    out = impl(state)
    zone_map = dict(out.component_zone_map)
    assert set(zone_map) == {c.ref for c in netlist.components}
    assert all(zone in {"HV", "Power", "Signal", "MCU"} for zone in zone_map.values())


@given(assignment_input())
@settings(max_examples=100, deadline=None)
def test_p4_zone_assignment_covers_components(inp):
    state, netlist = inp
    _body_p4(_to.run_zone_assignment, state, netlist)


def test_p4_fails_for_drop_component_mutant():
    """Mutant: drops a component's mapping -> P4 trips."""

    def mutant(state):
        out = _to.run_zone_assignment(state)
        entries = sorted(out.component_zone_map)
        return BoardState(netlist=state.netlist, component_zone_map=frozenset(entries[1:]))

    state, netlist = _p4_mutant_state()
    _assert_mutant_detected(_body_p4, mutant, state, netlist)


# hypothesis's `.example()` is not allowed inside other strategies; build a
# fixed netlist for the P4 mutant so it does not depend on the draw budget.
def _p4_mutant_state() -> tuple[BoardState, Netlist]:
    comps = [
        Component(
            ref="Q1",
            footprint="FP",
            bounds=(1.0, 1.0),
            pins=[Pin("1", "1", (0.0, 0.0), net="AC_L")],
        ),
        Component(
            ref="R1",
            footprint="FP",
            bounds=(1.0, 1.0),
            pins=[Pin("2", "1", (0.0, 0.0), net="SENSE")],
        ),
    ]
    netlist = Netlist(
        components=comps,
        nets=[
            Net("AC_L", [("Q1", "1")], net_class="HighVoltage"),
            Net("SENSE", [("R1", "1")], net_class="Signal"),
        ],
    )
    return BoardState(netlist=netlist), netlist


def _body_p5(impl, state):
    out = impl(state)
    assert out is state  # identity-preserving guard
    assert out.component_zone_map == frozenset()


@given(st.just(BoardState()))
@settings(max_examples=1, deadline=None)
def test_p5_zone_assignment_no_netlist_noop(state):
    _body_p5(_to.run_zone_assignment, state)


def test_p5_fails_for_attach_mutant():
    """Mutant: writes a map even without a netlist -> P5 trips."""

    def mutant(state):  # noqa: ARG001
        return BoardState(component_zone_map=frozenset({("R1", "Signal")}))

    _assert_mutant_detected(_body_p5, mutant, BoardState())


# ---------------------------------------------------------------------------
# P6 / P7 -- SlotGenerationStage
# ---------------------------------------------------------------------------

def _body_p6(impl, state, spacing):
    out = impl(state, spacing)
    zone_slots = dict(out.zone_slots)
    zones_by_name = {z.name: z for z in state.zones}
    assert set(zone_slots) == set(zones_by_name)
    for name, slots in zone_slots.items():
        (x_min, y_min), (x_max, y_max) = zones_by_name[name].bounds
        assert len(slots) > 0, f"{name} must have a non-empty grid at this spacing"
        for x, y in slots:
            assert x >= x_min + spacing / 2.0
            assert y >= y_min + spacing / 2.0
            assert x < x_max
            assert y < y_max


@given(slots_state(), st.floats(min_value=1.0, max_value=5.0, allow_nan=False))
@settings(max_examples=100, deadline=None)
def test_p6_slot_generation_grids_inside_bounds(state, spacing):
    _body_p6(_to.run_slot_generation, state, spacing)


def test_p6_fails_for_out_of_bounds_mutant():
    """Mutant: emits a slot exactly at the zone's max edge -> P6 trips."""
    Zone = _zone_class()
    state = BoardState(
        zones=frozenset({Zone(name="Z", bounds=((0.0, 0.0), (30.0, 30.0)))})
    )

    def mutant(state, spacing):
        corrupt = set()
        for z in state.zones:
            (x_min, _y_min), (_x_max, y_max) = z.bounds
            corrupt.add((z.name, ((x_min + spacing / 2.0, y_max),)))
        return BoardState(zones=state.zones, zone_slots=frozenset(corrupt))

    _assert_mutant_detected(_body_p6, mutant, state, 5.0)


def _body_p7(impl, state, spacing):
    out = impl(state, spacing)
    assert out is state  # identity-preserving guard
    assert out.zone_slots == state.zone_slots


@given(st.just(BoardState(zones=frozenset(), zone_slots=frozenset({("old", ())}))))
@settings(max_examples=1, deadline=None)
def test_p7_slot_generation_no_zones_noop(state):
    _body_p7(_to.run_slot_generation, state, 5.0)


def test_p7_fails_for_attach_mutant():
    """Mutant: writes slots even with no zones -> P7 trips."""

    def mutant(state, spacing):  # noqa: ARG001
        return BoardState(zones=state.zones, zone_slots=frozenset({("HV", ())}))

    state = BoardState(zones=frozenset(), zone_slots=frozenset({("old", ())}))
    _assert_mutant_detected(_body_p7, mutant, state, 5.0)


# ---------------------------------------------------------------------------
# Vacuity-guard plumbing
# ---------------------------------------------------------------------------

def _assert_mutant_detected(body, mutant, *args) -> None:
    """Run ``body`` against the degenerate mutant; the body's assertions MUST
    trip. If they do not, the property is vacuous -- a hard failure."""
    import pytest

    with pytest.raises(AssertionError):
        body(mutant, *args)
