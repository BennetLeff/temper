"""Property-based tests (G4) for the D1 deterministic setup stages (Rust
Orchestration Engine plan 2026-08-09-001, Phase D batch D1).

The batch shares one oracle + corpus (the differential in
``test_deterministic_d1_rust_differential.py``); these properties cover the
whole batch unit with >=5 non-vacuous properties, every stage reached by at
least one property:

- P1 (config_attach): a None config leaves ``state.config`` unchanged.
- P2 (config_attach): attaching a config when ``state.config`` is None sets
  exactly that object (identity, not a copy) and preserves other fields.
- P3 (net_ordering): with a netlist present, ``net_order`` is a permutation
  of the netlist's net names (no nets lost, no extras).
- P4 (net_ordering): the no-netlist path preserves ``net_order`` exactly.
- P5 (drc_oracle_setup): with ``parsed_pads`` present, one pad is registered
  per PadData, in input order, with the layer mapping and id convention.
- P6 (net_class_setup): applying a mapping mutates only the nets named in
  the mapping; unrelated nets keep their class.

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

from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic.state import BoardState

_NET_NAMES = st.sampled_from(["NET_A", "NET_B", "NET_C", "NET_D"])


@st.composite
def netlist_state(draw: st.DrawFn) -> BoardState:
    """A BoardState with 1-3 nets, each with a distinct net name."""
    net_names = draw(st.lists(_NET_NAMES, min_size=1, max_size=4, unique=True))
    nets = [Net(name=name, pins=[("U1", "1")], net_class="Signal") for name in net_names]
    comp = Component(
        ref="U1",
        footprint="FP",
        bounds=(5.0, 5.0),
        pins=[Pin("1", "1", (0.0, 0.0), net=net_names[0])],
        initial_position=(10.0, 10.0),
        initial_rotation=0,
    )
    return BoardState(netlist=Netlist(components=[comp], nets=nets))


@st.composite
def config_state(draw: st.DrawFn) -> BoardState:
    """A BoardState whose config may or may not already be populated."""
    has_config = draw(st.booleans())
    return BoardState(config={"pre": 1} if has_config else None)


# ---------------------------------------------------------------------------
# P1 / P2 -- ConfigAttachStage
# ---------------------------------------------------------------------------

def _body_p1(impl, state):
    out = impl(state, None)
    assert out.config == state.config
    if state.config is None:
        assert out.config is None


@given(config_state())
@settings(max_examples=100, deadline=None)
def test_p1_config_attach_none_is_noop(state):
    _body_p1(_to.run_config_attach, state)


def test_p1_fails_for_attach_mutant():
    """Mutant: a None config still attaches a fresh config -> P1 must trip."""

    def mutant(state, config):  # noqa: ARG001
        return BoardState(config={"mutant": True})

    _assert_mutant_detected(_body_p1, mutant, BoardState())


def _body_p2(impl, state, config):
    out = impl(state, config)
    if state.config is None and config is not None:
        assert out.config is config  # identity, not a copy
        assert out.netlist is state.netlist  # other fields preserved
    else:
        assert out.config == state.config


@given(config_state(), st.dictionaries(st.text(min_size=1), st.integers(), max_size=3))
@settings(max_examples=100, deadline=None)
def test_p2_config_attach_sets_identity(state, config):
    _body_p2(_to.run_config_attach, state, config)


def test_p2_fails_for_copy_mutant():
    """Mutant: deep-copies the config instead of holding the object."""

    def mutant(state, config):  # noqa: ARG001
        from copy import deepcopy

        return BoardState(config=deepcopy(config))

    _assert_mutant_detected(_body_p2, mutant, BoardState(), {"z": 1})


# ---------------------------------------------------------------------------
# P3 / P4 -- NetOrderingStage
# ---------------------------------------------------------------------------

def _body_p3(impl, state):
    out = impl(state, None)
    net_names = {n.name for n in state.netlist.nets}
    assert sorted(out.net_order) == sorted(net_names)


@given(netlist_state())
@settings(max_examples=100, deadline=None)
def test_p3_net_ordering_is_permutation(state):
    _body_p3(_to.run_net_ordering, state)


def test_p3_fails_for_drop_net_mutant():
    """Mutant: drops the first net from the ordering -> permutation trips."""

    def mutant(state, net_priority):  # noqa: ARG001
        out = _to.run_net_ordering(state, None)
        return BoardState(netlist=state.netlist, net_order=tuple(out.net_order[1:]))

    state = BoardState(
        netlist=Netlist(
            components=[],
            nets=[
                Net(name="NET_A", pins=[], net_class="Signal"),
                Net(name="NET_B", pins=[], net_class="Signal"),
            ],
        )
    )
    _assert_mutant_detected(_body_p3, mutant, state)


def _body_p4(impl, state):
    out = impl(state, None)
    assert out.net_order == state.net_order


@given(st.just(BoardState(net_order=("X", "Y"))))
@settings(max_examples=1, deadline=None)
def test_p4_net_ordering_no_netlist_unchanged(state):
    _body_p4(_to.run_net_ordering, state)


def test_p4_fails_for_overwrite_mutant():
    """Mutant: overwrites net_order even without a netlist."""

    def mutant(state, net_priority):  # noqa: ARG001
        return BoardState(net_order=("mutant",))

    _assert_mutant_detected(_body_p4, mutant, BoardState())


# ---------------------------------------------------------------------------
# P5 -- DrcOracleSetupStage (parsed_pads)
# ---------------------------------------------------------------------------

def _make_pads(n_pads):
    from temper_placer.io._kicad_types import PadData

    return [
        PadData(
            position=(10.0 * i, 0.0),
            size=(1.0, 1.0),
            shape="rect",
            drill=0.0,
            rotation=0.0,
            layer="F.Cu",
            number=str(i),
            net=f"N{i}",
            component_ref="R1",
        )
        for i in range(n_pads)
    ]


def _body_p5(impl, n_pads):
    pads = _make_pads(n_pads)
    out = impl(BoardState(), None, pads)
    registered = out.drc_oracle.geometry.pads
    assert len(registered) == n_pads
    assert [p.id for p in registered] == [f"R1.{i}" for i in range(n_pads)]
    assert all(p.layer == 0 for p in registered)  # F.Cu -> layer 0


@given(st.integers(min_value=1, max_value=5))
@settings(max_examples=50, deadline=None)
def test_p5_drc_oracle_parsed_pads_preserve_order(n_pads):
    _body_p5(_to.run_drc_oracle_setup, n_pads)


def test_p5_fails_for_reorder_mutant():
    """Mutant: registers pads in reverse order -> the order property trips."""

    def mutant(state, design_rules, parsed_pads):  # noqa: ARG001
        return _to.run_drc_oracle_setup(BoardState(), None, list(reversed(parsed_pads)))

    _assert_mutant_detected(_body_p5, mutant, 3)


# ---------------------------------------------------------------------------
# P6 -- NetClassSetupStage
# ---------------------------------------------------------------------------

def _body_p6(impl, state, new_class):
    named = next(iter(state.netlist.nets)).name
    mapping = {named: new_class}
    out = impl(state, mapping)
    net_classes = {n.name: n.net_class for n in out.netlist.nets}
    assert net_classes[named] == new_class
    for n in state.netlist.nets:
        if n.name != named:
            assert net_classes[n.name] == "Signal"  # untouched


@given(netlist_state(), st.sampled_from(["Power", "GND"]))
@settings(max_examples=100, deadline=None)
def test_p6_net_class_mapping_only_touches_named_nets(state, new_class):
    _body_p6(_to.run_net_class_setup, state, new_class)


def test_p6_fails_for_blanket_mutant():
    """Mutant: applies the mapping to every net -> the untouched-net
    property trips."""

    def mutant(state, net_classes):  # noqa: ARG001
        for n in state.netlist.nets:
            n.net_class = "Power"
        return BoardState(netlist=state.netlist)

    state = BoardState(
        netlist=Netlist(
            components=[],
            nets=[
                Net(name="NET_A", pins=[], net_class="Signal"),
                Net(name="NET_B", pins=[], net_class="Signal"),
            ],
        )
    )
    _assert_mutant_detected(_body_p6, mutant, state, "Power")


# ---------------------------------------------------------------------------
# Vacuity-guard plumbing
# ---------------------------------------------------------------------------

def _assert_mutant_detected(body, mutant, *args) -> None:
    """Run ``body`` against the degenerate mutant; the body's assertions MUST
    trip. If they do not, the property is vacuous -- a hard failure."""
    import pytest

    with pytest.raises(AssertionError):
        body(mutant, *args)
