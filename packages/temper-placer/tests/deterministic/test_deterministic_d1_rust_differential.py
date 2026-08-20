"""R1a: behavioural differential of the D1 deterministic setup stages
against the pinned pre-migration oracle.

Rust Orchestration Engine plan 2026-08-09-001, Phase D batch D1: the
orchestration of ``deterministic/stages/{setup,net_ordering,config_attach}.py``
moves to ``temper-orchestration`` as ``Stage<BoardState>`` implementors
(``DrcOracleSetupStage`` + ``NetClassSetupStage`` + ``NetOrderingStage`` +
``ConfigAttachStage``); the Python modules keep their public API and become
thin FFI delegations. The pre-migration implementations are pinned VERBATIM
as the oracles (``tests/deterministic/_*_py_oracle.py``, content-hash-pinned
below).

Both arms are driven with IDENTICAL BoardState inputs and stage constructor
args; every observable field of the resulting BoardState is compared:

- ``config_attach``   -> ``state.config``
- ``net_ordering``    -> ``state.net_order``
- ``drc_oracle_setup``-> the DRCOracle's observable state: the registered
  pads (``geometry.pads`` list of ``Pad`` dataclasses, compared element-wise
  with ``==`` -- Pad is a dataclass over scalar fields) and the ClearanceMatrix
  state (``default_*`` scalars, ``_net_class_rules``, ``_net_to_class``,
  ``_differential_pairs``)
- ``net_class_setup`` -> the netlist's per-net ``net_class`` after the
  in-place mapping

Anti-vacuity: ``test_oracle_and_port_are_different_implementations`` asserts
the shim resolves to the Rust pyfunctions (its ``run`` calls
``temper_orchestration``), not back onto the oracle. The oracle body digests
below are pinned: a differential whose oracle can be edited to agree with the
port proves nothing.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import temper_orchestration as _to
import tests.deterministic._config_attach_py_oracle as _orc_config_attach
import tests.deterministic._net_ordering_py_oracle as _orc_net_ordering
import tests.deterministic._setup_py_oracle as _orc_setup

from temper_placer._constraint_types.clearance import (
    DifferentialPairRule,
    NetClassRule,
)
from temper_placer._constraint_types.config import PlacementConstraints
from temper_placer.core.board import Board
from temper_placer.core.design_rules import create_temper_design_rules
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic.stages import (
    DRCOracleSetupStage as _shim_drc_oracle_setup,
)
from temper_placer.deterministic.stages import (
    NetClassSetupStage as _shim_net_class_setup,
)
from temper_placer.deterministic.stages import NetOrderingStage as _shim_net_ordering
from temper_placer.deterministic.stages import config_attach as _shim_config_attach
from temper_placer.deterministic.state import BoardState
from temper_placer.io._kicad_types import PadData

# ---------------------------------------------------------------------------
# Oracle body pinning (G1)
# ---------------------------------------------------------------------------

_PINNED = {
    "_setup_py_oracle.py": "cf5d0fb35213f815c5f15df45cd2aa31d141e96779f00aa315d1bdce0d644985",
    "_net_ordering_py_oracle.py": "2f2b17055fc2701411044de4c0da56d720f58e5c8a78fbc0046b23e4edd53d96",
    "_config_attach_py_oracle.py": "b1f63ba15a8d09b2a12d4a1cbaf03c000a016fec5dc7640fdc36d6c6f5c82506",
}
_BODY_MARKER = "# --- BEGIN PINNED BODY ---\n"


def test_oracle_bodies_match_pinned_digests() -> None:
    for name, expected in _PINNED.items():
        text = (Path(__file__).with_name(name)).read_text(encoding="utf-8")
        assert _BODY_MARKER in text, f"{name} oracle header marker missing"
        body = text.split(_BODY_MARKER, 1)[1]
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        assert digest == expected, (
            f"{name} oracle body changed; it must stay verbatim "
            f"(expected {expected}, got {digest})"
        )


def test_oracle_and_port_are_different_implementations() -> None:
    """Anti-vacuity: the shims must resolve to the Rust pyfunctions.

    Shim-debt cleanup (2026-08-20): the D1 stage modules were collapsed
    onto the generic ``RustFunctionStage`` adapter -- ``run`` is one shared
    implementation, so the old bytecode-name probe
    (``run.__code__.co_names``) can no longer distinguish per-stage Rust
    calls. Each adapter binds its ``temper-orchestration`` pyfunction as
    ``_fn`` on the instance; identity against the pyfunction is the new
    (stronger) probe.
    """
    assert _shim_drc_oracle_setup is not _orc_setup.DRCOracleSetupStage
    assert _shim_net_class_setup is not _orc_setup.NetClassSetupStage
    assert _shim_net_ordering is not _orc_net_ordering.NetOrderingStage
    assert _shim_config_attach.ConfigAttachStage is not _orc_config_attach.ConfigAttachStage
    # The adapters' instances bind the temper_orchestration pyfunctions --
    # the Rust port -- by identity.
    assert _shim_drc_oracle_setup()._fn is _to.run_drc_oracle_setup
    assert _shim_net_class_setup()._fn is _to.run_net_class_setup
    assert _shim_net_ordering()._fn is _to.run_net_ordering
    assert _shim_config_attach.ConfigAttachStage({})._fn is _to.run_config_attach


# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------

def _netlist(initial_rotation_quadrant: int | None = None, initial_position=(10.0, 10.0)) -> Netlist:
    pin = Pin(
        "1",
        "1",
        (2.0, 0.0),
        net="GND",
        width=1.0,
        height=1.0,
        shape="circle",
        layer="F.Cu",
    )
    comp = Component(
        ref="U1",
        footprint="FP",
        bounds=(5.0, 5.0),
        pins=[pin],
        initial_position=initial_position,
        initial_rotation_quadrant=initial_rotation_quadrant,
    )
    return Netlist(components=[comp], nets=[])


def _netlist_with_nets() -> Netlist:
    p1 = Pin("1", "1", (0.0, 0.0), net="NET_A")
    p2 = Pin("2", "2", (1.0, 0.0), net="NET_B")
    comp = Component(
        ref="U1",
        footprint="FP",
        bounds=(5.0, 5.0),
        pins=[p1, p2],
        initial_position=(10.0, 10.0),
        initial_rotation_quadrant=0,
    )
    return Netlist(
        components=[comp],
        nets=[
            Net(name="NET_A", pins=[("U1", "1")], net_class="Signal"),
            Net(name="NET_B", pins=[("U1", "2")], net_class="Signal"),
        ],
    )


def _net_class_config() -> PlacementConstraints:
    return PlacementConstraints(
        net_class_rules={
            "Signal": NetClassRule(
                name="Signal",
                trace_width_mm=0.2,
                clearance_mm=0.15,
                via_size_mm=0.6,
                via_drill_mm=0.3,
                via_template="Via1x1",
                creepage_mm=0.0,
            )
        },
        net_classes={"N1": "Signal"},
        differential_pairs=[],
    )


def _parsed_pads() -> list[PadData]:
    return [
        PadData(
            position=(10.0, 20.0),
            size=(2.0, 1.0),
            shape="rect",
            drill=0.0,
            rotation=0.0,
            layer="F.Cu",
            number="1",
            net="GND",
            component_ref="R1",
        ),
        PadData(
            position=(15.0, 20.0),
            size=(1.0, 1.0),
            shape="circle",
            drill=0.8,
            rotation=90.0,
            layer="B.Cu",
            number="2",
            net="",
            component_ref="U1",
        ),
        PadData(
            position=(30.0, 5.0),
            size=(1.5, 1.5),
            shape="weird",
            drill=0.0,
            rotation=45.0,
            layer="In1.Cu",
            number="3",
            net="N1",
            component_ref="Q1",
        ),
    ]


def _drc_oracle_canon(state: BoardState):
    """Canonical projection of the observable DRCOracle state."""
    oracle = state.drc_oracle
    rules = oracle.rules
    return (
        rules.default_clearance,
        rules.default_track_width,
        rules.default_via_diameter,
        rules.default_via_drill,
        dict(rules._net_class_rules),
        dict(rules._net_to_class),
        dict(rules._differential_pairs),
        tuple(oracle.geometry.pads),
    )


# ---------------------------------------------------------------------------
# ConfigAttachStage
# ---------------------------------------------------------------------------

def test_config_attach_attaches_when_absent() -> None:
    for config in ({"zones": ["x"]}, None, {"a": 1}):
        state = BoardState()
        oracle_out = _orc_config_attach.ConfigAttachStage(config).run(state)
        shim_out = _shim_config_attach.ConfigAttachStage(config).run(state)
        assert shim_out.config == oracle_out.config
        if config is None:
            assert shim_out.config is None


def test_config_attach_preserves_existing_config() -> None:
    config = {"zones": ["x"]}
    state = BoardState(config={"existing": True})
    oracle_out = _orc_config_attach.ConfigAttachStage(config).run(state)
    shim_out = _shim_config_attach.ConfigAttachStage(config).run(state)
    assert shim_out.config == oracle_out.config == {"existing": True}


# ---------------------------------------------------------------------------
# NetOrderingStage
# ---------------------------------------------------------------------------

def test_net_ordering_with_netlist_and_loops() -> None:
    state = BoardState(netlist=_netlist_with_nets())
    oracle_out = _orc_net_ordering.NetOrderingStage().run(state)
    shim_out = _shim_net_ordering().run(state)
    assert shim_out.net_order == oracle_out.net_order
    assert oracle_out.net_order  # non-empty: the ordering did something


def test_net_ordering_without_netlist_unchanged() -> None:
    state = BoardState()
    oracle_out = _orc_net_ordering.NetOrderingStage().run(state)
    shim_out = _shim_net_ordering().run(state)
    assert shim_out.net_order == oracle_out.net_order == ()


def test_net_ordering_with_priorities() -> None:
    state = BoardState(netlist=_netlist_with_nets())
    priority = {"NET_B": 1}
    oracle_out = _orc_net_ordering.NetOrderingStage(net_priority=priority).run(state)
    shim_out = _shim_net_ordering(net_priority=priority).run(state)
    assert shim_out.net_order == oracle_out.net_order


# ---------------------------------------------------------------------------
# DRCOracleSetupStage
# ---------------------------------------------------------------------------

def test_drc_oracle_setup_default_matrix() -> None:
    state = BoardState()
    oracle_out = _orc_setup.DRCOracleSetupStage().run(state)
    shim_out = _shim_drc_oracle_setup().run(state)
    assert _drc_oracle_canon(shim_out) == _drc_oracle_canon(oracle_out)


def test_drc_oracle_setup_board_parse() -> None:
    board = Board(width=100, height=100)
    state = BoardState(board=board)
    oracle_out = _orc_setup.DRCOracleSetupStage().run(state)
    shim_out = _shim_drc_oracle_setup().run(state)
    assert _drc_oracle_canon(shim_out) == _drc_oracle_canon(oracle_out)


def test_drc_oracle_setup_netlist_fallback() -> None:
    board = Board(width=100, height=100)
    state = BoardState(board=board, netlist=_netlist(initial_rotation_quadrant=1))
    oracle_out = _orc_setup.DRCOracleSetupStage().run(state)
    shim_out = _shim_drc_oracle_setup().run(state)
    assert _drc_oracle_canon(shim_out) == _drc_oracle_canon(oracle_out)
    assert len(shim_out.drc_oracle.geometry.pads) == 1
    pad = shim_out.drc_oracle.geometry.pads[0]
    assert (pad.center.x, pad.center.y) == (10.0, 8.0)  # R(-90) convention
    assert pad.net == "GND"


def test_drc_oracle_setup_netlist_fallback_with_placements() -> None:
    board = Board(width=100, height=100)
    state = BoardState(
        board=board,
        netlist=_netlist(initial_position=None),
        placements=frozenset({("U1", (10.0, 10.0))}),
    )
    oracle_out = _orc_setup.DRCOracleSetupStage().run(state)
    shim_out = _shim_drc_oracle_setup().run(state)
    assert _drc_oracle_canon(shim_out) == _drc_oracle_canon(oracle_out)
    assert len(shim_out.drc_oracle.geometry.pads) == 1


def test_drc_oracle_setup_skips_unplaced_components() -> None:
    board = Board(width=100, height=100)
    state = BoardState(board=board, netlist=_netlist(initial_position=None))
    oracle_out = _orc_setup.DRCOracleSetupStage().run(state)
    shim_out = _shim_drc_oracle_setup().run(state)
    assert _drc_oracle_canon(shim_out) == _drc_oracle_canon(oracle_out)
    assert len(shim_out.drc_oracle.geometry.pads) == 0


def test_drc_oracle_setup_config_duck_typed() -> None:
    config = _net_class_config()
    state = BoardState()
    oracle_out = _orc_setup.DRCOracleSetupStage(design_rules=config).run(state)
    shim_out = _shim_drc_oracle_setup(design_rules=config).run(state)
    assert _drc_oracle_canon(shim_out) == _drc_oracle_canon(oracle_out)


def test_drc_oracle_setup_design_rules_object() -> None:
    dr = create_temper_design_rules()
    state = BoardState()
    oracle_out = _orc_setup.DRCOracleSetupStage(design_rules=dr).run(state)
    shim_out = _shim_drc_oracle_setup(design_rules=dr).run(state)
    assert _drc_oracle_canon(shim_out) == _drc_oracle_canon(oracle_out)
    # The count is the live net-class-set cardinality (grew 11 -> 12 when
    # #1084 added HighVoltageTank) -- pin against the oracle, not a literal.
    assert len(shim_out.drc_oracle.rules._net_class_rules) == len(
        oracle_out.drc_oracle.rules._net_class_rules
    )


def test_drc_oracle_setup_differential_pairs() -> None:
    config = PlacementConstraints(
        net_class_rules={
            "Signal": NetClassRule(
                name="Signal",
                trace_width_mm=0.2,
                clearance_mm=0.15,
                via_size_mm=0.6,
                via_drill_mm=0.3,
                via_template="Via1x1",
                creepage_mm=0.0,
            )
        },
        net_classes={"N1": "Signal"},
        differential_pairs=[
            DifferentialPairRule(net_pos="N1", net_neg="N2", spacing_mm=0.25)
        ],
    )
    state = BoardState()
    oracle_out = _orc_setup.DRCOracleSetupStage(design_rules=config).run(state)
    shim_out = _shim_drc_oracle_setup(design_rules=config).run(state)
    assert _drc_oracle_canon(shim_out) == _drc_oracle_canon(oracle_out)
    assert len(shim_out.drc_oracle.rules._differential_pairs) == 1


def test_drc_oracle_setup_parsed_pads() -> None:
    pads = _parsed_pads()
    state = BoardState()
    oracle_out = _orc_setup.DRCOracleSetupStage(parsed_pads=pads).run(state)
    shim_out = _shim_drc_oracle_setup(parsed_pads=pads).run(state)
    assert _drc_oracle_canon(shim_out) == _drc_oracle_canon(oracle_out)
    assert len(shim_out.drc_oracle.geometry.pads) == 3
    # PTH + layer-mapping semantics pinned: B.Cu -> layer 3, drill>0 -> PTH.
    by_id = {p.id: p for p in shim_out.drc_oracle.geometry.pads}
    assert by_id["U1.2"].is_pth is True
    assert by_id["U1.2"].layer == 3
    assert by_id["U1.2"].net == "__UNCONNECTED__"  # empty net sentinel
    assert by_id["Q1.3"].shape == "rect"  # unknown shape normalized
    assert by_id["Q1.3"].layer == 1  # In1.Cu -> layer 1


# ---------------------------------------------------------------------------
# NetClassSetupStage
# ---------------------------------------------------------------------------

def test_net_class_setup_applies_mapping() -> None:
    state = BoardState(netlist=_netlist_with_nets())
    mapping = {"NET_A": "Power"}
    oracle_out = _orc_setup.NetClassSetupStage(net_classes=mapping).run(state)
    shim_out = _shim_net_class_setup(net_classes=mapping).run(state)
    oracle_nc = {n.name: n.net_class for n in oracle_out.netlist.nets}
    shim_nc = {n.name: n.net_class for n in shim_out.netlist.nets}
    assert shim_nc == oracle_nc
    assert shim_nc["NET_A"] == "Power"
    assert shim_nc["NET_B"] == "Signal"


def test_net_class_setup_noop_without_mapping() -> None:
    state = BoardState(netlist=_netlist_with_nets())
    oracle_out = _orc_setup.NetClassSetupStage(net_classes=None).run(state)
    shim_out = _shim_net_class_setup(net_classes=None).run(state)
    assert oracle_out is state
    assert shim_out is state  # identity preserved on the no-op path


def test_net_class_setup_noop_without_netlist() -> None:
    state = BoardState()
    oracle_out = _orc_setup.NetClassSetupStage(net_classes={"NET_A": "Power"}).run(state)
    shim_out = _shim_net_class_setup(net_classes={"NET_A": "Power"}).run(state)
    assert oracle_out is state
    assert shim_out is state


def test_net_class_setup_empty_mapping_noop() -> None:
    state = BoardState(netlist=_netlist_with_nets())
    oracle_out = _orc_setup.NetClassSetupStage(net_classes={}).run(state)
    shim_out = _shim_net_class_setup(net_classes={}).run(state)
    assert oracle_out is state
    assert shim_out is state
