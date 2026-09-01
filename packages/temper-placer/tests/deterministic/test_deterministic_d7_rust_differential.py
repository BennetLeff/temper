"""R1a behavioural differential of the D7 deterministic routing-adjacent stages
against the pinned pre-migration oracle.

Rust Orchestration Engine plan 2026-08-09-001, Phase D batch D7 (the FINAL
Phase D batch): the run() orchestration of the five routing-adjacent stages --
`deterministic/stages/{fine_pitch_escape,hv_lv_partition,power_plane,
layer_assignment,apply_placements}.py` -- moves to `temper-orchestration` as
`Stage<BoardState>` implementors (`FinePitchEscapeStage`, `HvLvPartitionStage`,
`PowerPlaneStage`, `LayerAssignmentStage`, `ApplyPlacementsStage`). The
pre-migration implementations are pinned VERBATIM as the oracles
(`tests/deterministic/_*_run_py_oracle.py`, content-hash-pinned below).

Both arms are driven with IDENTICAL BoardState inputs and stage constructor
args; every observable output is compared bit-exactly (floats projected
through `float.hex()`):

- `FinePitchEscapeStage` -> `state.vias` (frozenset of Via) and the captured
  stdout (the fine-pitch detection / layer-distribution `print` messages).
- `HvLvPartitionStage` -> `state.component_domain_map` (frozenset),
  `state.routing_corridors` (tuple) and `state.domain_regions` (tuple of
  shapely polygons, compared by `wkt`) plus the `PartitionError` raise
  (message equality) and the log messages (`caplog`); the skip/guard paths
  preserve identity.
- `PowerPlaneStage` -> `state.layer_assignments` (frozenset of
  `LayerAssignment`).
- `LayerAssignmentStage` -> `state.layer_assignments` (frozenset).
- `ApplyPlacementsStage` -> `state.netlist` (the replaced-component list's
  `initial_position`s).

The leaf kernels the stages delegate to stay single-source and are driven
through FFI by the port: `temper_design_bundle_python.deterministic_leaves`
(`min_pin_pitch_py` / `escape_layer_for_net_py` / `assign_layers` /
`recompute_plane_assignments`) and `temper_design_bundle_python.hv_lv_partition`
(`hv_lv_classify` / `hv_lv_area_check`). The pydantic guard config, the shapely
outline + `compute_guard_strip` GEOS surface and the duck-typed
`_rules_by_net` / `_nets` / `_area` readers stay Python call-backs.

Anti-vacuity: `test_oracle_and_port_are_different_implementations` asserts the
shims resolve to the Rust pyfunctions (their `run` bodies call
`temper_orchestration`), not back onto the oracle. The oracle body digests
below are pinned: a differential whose oracle can be edited to agree with the
port proves nothing.
"""

from __future__ import annotations

import hashlib
import inspect
from pathlib import Path

import pytest
import temper_orchestration as _to
import tests.deterministic._apply_placements_run_py_oracle as _orc_ap
import tests.deterministic._fine_pitch_escape_run_py_oracle as _orc_fpe
import tests.deterministic._hv_lv_partition_run_py_oracle as _orc_hlp
import tests.deterministic._layer_assignment_run_py_oracle as _orc_la
import tests.deterministic._power_plane_run_py_oracle as _orc_pp

from temper_placer.core.board import Via
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic.stages import (
    FinePitchEscapeStage as _shim_fpe,
)
from temper_placer.deterministic.stages import (
    HvLvPartitionStage as _shim_hlp,
)
from temper_placer.deterministic.stages import (
    LayerAssignmentStage as _shim_la,
)
from temper_placer.deterministic.stages import (
    PowerPlaneStage as _shim_pp,
)
from temper_placer.deterministic.state import BoardState

# ---------------------------------------------------------------------------
# Oracle body pinning (G1)
# ---------------------------------------------------------------------------

_PINNED = {
    "_fine_pitch_escape_run_py_oracle.py": "1758a44e7d784f036ee9b6f17eb781c1030c381d370d2b97fbe938acc37f15e6",
    "_hv_lv_partition_run_py_oracle.py": "ad7addd63dcdf8bac365879323262824fbce6d3391456d76d83a590ceaf8cfc1",
    "_power_plane_run_py_oracle.py": "e0950e82be1a9b5c8ee2d495f265c1ea22fb5c2b07d6bf42df644eab3b31eca6",
    "_layer_assignment_run_py_oracle.py": "ab6a89f1ec94c61c89a7bb9006ca3e4f899869b711c003d863491d0d16e99f57",
    "_apply_placements_run_py_oracle.py": "e0c6221464e14b69b62266345c8701c44f14aa08cc038e86b3fd7bd45fa4f215",
}
_BODY_MARKER = "# --- BEGIN PINNED BODY ---\n"


def test_oracle_bodies_match_pinned_digests() -> None:
    for name, expected in _PINNED.items():
        text = (Path(__file__).with_name(name)).read_text(encoding="utf-8")
        assert _BODY_MARKER in text, f"{name} oracle header marker missing"
        body = text.rsplit(_BODY_MARKER, 1)[1]
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        assert digest == expected, (
            f"{name} drifted from its pinned digest; the oracle must be a "
            "verbatim pre-migration snapshot, never edited to agree with the port"
        )


def test_oracle_and_port_are_different_implementations() -> None:
    """The shims must resolve to the Rust pyfunctions, not the oracle."""
    expected = {
        _shim_fpe.run: "run_fine_pitch_escape",
        _shim_hlp.run: "run_hv_lv_partition",
        _shim_pp.run: "run_power_plane",
        _shim_la.run: "run_layer_assignment",
    }
    for fn, symbol in expected.items():
        src = inspect.getsource(fn)
        assert symbol in src, f"{fn.__qualname__} does not delegate to {symbol}"
    # The apply_placements one-line shim module was deleted (shim-debt
    # cleanup 2026-08-19); the production path is the pyfunction directly,
    # and the oracle's class must NOT resolve to it.
    for symbol in [
        "run_fine_pitch_escape",
        "run_hv_lv_partition",
        "run_power_plane",
        "run_layer_assignment",
        "run_apply_placements",
    ]:
        assert getattr(_to, symbol) is not None
    assert (
        "run_apply_placements"
        not in _orc_ap.ApplyPlacementsStage.run.__code__.co_names
    )


# ---------------------------------------------------------------------------
# Canonicalisers (bit-exact comparison via float.hex)
# ---------------------------------------------------------------------------

def _hx(v):
    return None if v is None else float(v).hex()


def _via_canon(v) -> tuple:
    return (
        v.net,
        (float(v.position[0]).hex(), float(v.position[1]).hex()),
        tuple(v.layers),
        _hx(v.drill),
        _hx(v.width),
    )


def _vias_canon(vias):
    return frozenset(_via_canon(v) for v in vias)


def _la_canon(la) -> tuple:
    return (la.net_name, int(la.layer), bool(la.is_plane), bool(la.allow_layer_change))


def _las_canon(assignments):
    return frozenset(_la_canon(la) for la in assignments)


# ---------------------------------------------------------------------------
# Shared component/netlist fixtures
# ---------------------------------------------------------------------------

def _pin(name, position, net=None):
    return Pin(name, name, position, net=net, width=2.0, height=2.0, shape="circle")


def _comp(ref, pins, initial_position=None):
    return Component(
        ref=ref,
        footprint="FP",
        bounds=(2.0, 2.0),
        pins=pins,
        net_class="Signal",
        initial_position=initial_position,
    )


def _netlist(components, net_specs=()):
    """Build a Netlist whose `get_component_nets` is populated. `net_specs`
    is a list of `(name, [(ref, pin_num), ...], net_class)` triples."""
    nets = [Net(name, pins, net_class=nc) for name, pins, nc in net_specs]
    return Netlist(components=components, nets=nets)


def _components_positions(netlist) -> dict:
    return {c.ref: c.initial_position for c in netlist.components}


# ---------------------------------------------------------------------------
# fine_pitch_escape
# ---------------------------------------------------------------------------

def _fpe_state(*, components, placements=None, vias=None) -> BoardState:
    return BoardState(
        netlist=_netlist(components),
        placements=frozenset(placements) if placements else None,
        vias=frozenset(vias) if vias else None,
    )


def test_fpe_no_netlist_guard_identity() -> None:
    """`if not state.netlist: return state` -- identity on both arms."""
    state = BoardState(netlist=None)
    assert _orc_fpe.FinePitchEscapeStage().run(state) is state
    assert _shim_fpe().run(state) is state


def test_fpe_escape_vias_placed_bit_exact(capsys) -> None:
    """A fine-pitch component (pins 0.5mm apart) gets a via per netted pin;
    a second component sharing the net is NOT fine-pitch itself but its pins
    still get vias (the net touches a fine-pitch component)."""
    u1 = _comp(
        "U1",
        [_pin("1", (0, 0), net="SPI_CLK"), _pin("2", (0, 0.5), net="SPI_CLK")],
        initial_position=(10.0, 10.0),
    )
    r1 = _comp("R1", [_pin("1", (0, 0), net="SPI_CLK")], initial_position=(20.0, 10.0))
    state = _fpe_state(
        components=[u1, r1], placements={("U1", (10.0, 10.0)), ("R1", (20.0, 10.0))}
    )
    orc_out = _orc_fpe.FinePitchEscapeStage().run(state)
    orc_stdout = capsys.readouterr().out
    port_out = _shim_fpe().run(state)
    port_stdout = capsys.readouterr().out
    assert _vias_canon(orc_out.vias) == _vias_canon(port_out.vias)
    # U1's two pins -> 2 vias on In2.Cu (SPI_CLK is a layer-2 net);
    # R1's pin shares the fine-pitch net -> 1 more via.
    assert len(port_out.vias) == 3
    assert orc_stdout == port_stdout


def test_fpe_no_fine_pitch_component(capsys) -> None:
    """No component with min_pitch < threshold: no vias, the no-detection
    message, and the empty-frozenset write."""
    c1 = _comp("C1", [_pin("1", (0, 0), net="A"), _pin("2", (3, 0), net="B")])
    state = _fpe_state(components=[c1])
    orc_out = _orc_fpe.FinePitchEscapeStage().run(state)
    orc_stdout = capsys.readouterr().out
    port_out = _shim_fpe().run(state)
    port_stdout = capsys.readouterr().out
    assert _vias_canon(orc_out.vias) == _vias_canon(port_out.vias)
    assert port_out.vias == frozenset()
    assert orc_stdout == port_stdout
    assert "No fine-pitch components detected" in port_stdout


def test_fpe_layer_distribution(capsys) -> None:
    """EXP-6b/EXP-9 layer precedence: layer3 nets -> B.Cu, layer2 nets ->
    In2.Cu, everything else -> In1.Cu (the escape_layer_for_net_py kernel)."""
    u1 = _comp(
        "U1",
        [
            _pin("1", (0, 0), net="I_SENSE"),  # layer-3
            _pin("2", (0, 0.5), net="GATE_H"),  # layer-2
            _pin("3", (0, 1.0), net="OTHER"),  # layer-1 default
        ],
        initial_position=(0.0, 0.0),
    )
    state = _fpe_state(components=[u1], placements={("U1", (0.0, 0.0))})
    orc_out = _orc_fpe.FinePitchEscapeStage().run(state)
    orc_stdout = capsys.readouterr().out
    port_out = _shim_fpe().run(state)
    port_stdout = capsys.readouterr().out
    assert _vias_canon(orc_out.vias) == _vias_canon(port_out.vias)
    by_net = {v.net: tuple(v.layers) for v in port_out.vias}
    assert by_net["I_SENSE"] == ("F.Cu", "B.Cu")
    assert by_net["GATE_H"] == ("F.Cu", "In2.Cu")
    assert by_net["OTHER"] == ("F.Cu", "In1.Cu")
    assert orc_stdout == port_stdout
    assert "1 to In1.Cu, 1 to In2.Cu, 1 to B.Cu" in port_stdout


def test_fpe_existing_vias_preserved(capsys) -> None:
    """Pre-existing state.vias survive: the stage appends, and the write is
    the union."""
    existing = Via(
        position=(99.0, 99.0), drill=0.3, width=0.6, layers=("F.Cu", "In1.Cu"), net="OLD"
    )
    u1 = _comp(
        "U1",
        [_pin("1", (0, 0), net="GATE_H"), _pin("2", (0, 0.5), net="GATE_H")],
        initial_position=(0.0, 0.0),
    )
    state = _fpe_state(components=[u1], placements={("U1", (0.0, 0.0))}, vias=[existing])
    orc_out = _orc_fpe.FinePitchEscapeStage().run(state)
    orc_stdout = capsys.readouterr().out
    port_out = _shim_fpe().run(state)
    port_stdout = capsys.readouterr().out
    assert _vias_canon(orc_out.vias) == _vias_canon(port_out.vias)
    assert len(port_out.vias) == 3  # 2 escape vias + the pre-existing OLD via
    assert "OLD" in {v.net for v in port_out.vias}
    assert orc_stdout == port_stdout


def test_fpe_duplicate_positions_dedup(capsys) -> None:
    """Two pins rounding to the same (x, y) key produce ONE via."""
    u1 = _comp(
        "U1",
        [
            _pin("1", (0.0004, 0.0), net="GATE_H"),
            _pin("2", (0.0, 0.0002), net="GATE_H"),
            _pin("3", (1.0, 0.0), net="GATE_H"),
        ],
        initial_position=(0.0, 0.0),
    )
    state = _fpe_state(components=[u1], placements={("U1", (0.0, 0.0))})
    orc_out = _orc_fpe.FinePitchEscapeStage().run(state)
    orc_stdout = capsys.readouterr().out
    port_out = _shim_fpe().run(state)
    port_stdout = capsys.readouterr().out
    assert _vias_canon(orc_out.vias) == _vias_canon(port_out.vias)
    assert len(port_out.vias) == 2  # pins 1+2 share the rounded key
    assert orc_stdout == port_stdout


def test_fpe_nc_pins_skipped(capsys) -> None:
    """Pins without a net never get a via (the `if not pin.net` skip)."""
    u1 = _comp(
        "U1",
        [_pin("1", (0, 0), net="GATE_H"), _pin("2", (0, 0.5), net=None)],
        initial_position=(0.0, 0.0),
    )
    state = _fpe_state(components=[u1], placements={("U1", (0.0, 0.0))})
    orc_out = _orc_fpe.FinePitchEscapeStage().run(state)
    orc_stdout = capsys.readouterr().out
    port_out = _shim_fpe().run(state)
    port_stdout = capsys.readouterr().out
    assert _vias_canon(orc_out.vias) == _vias_canon(port_out.vias)
    assert len(port_out.vias) == 1
    assert orc_stdout == port_stdout


# ---------------------------------------------------------------------------
# hv_lv_partition
# ---------------------------------------------------------------------------

class _Rule:
    def __init__(self, safety_category, creepage_mm):
        self.safety_category = safety_category
        self.creepage_mm = creepage_mm


class _DesignRules:
    def __init__(self, net_classes, net_class_assignments=None):
        self.net_classes = net_classes
        self.net_class_assignments = net_class_assignments or {}


class _DrcOracle:
    def __init__(self, design_rules):
        self.design_rules = design_rules


class _FakeBoard:
    def __init__(self, width=100.0, height=100.0, outline_polygon=None):
        self.width = width
        self.height = height
        self.outline_polygon = outline_polygon
        self.layer_stackup = None


_HV_CLASS_RULES = {"HV": _Rule("HV", 6.0), "AC": _Rule("AC", 6.0)}
_LV_CLASS_RULES = {"LV": _Rule("LV", 0.0), "iso": _Rule("iso", 0.0)}


def _all_rules():
    rules = dict(_HV_CLASS_RULES)
    rules.update(_LV_CLASS_RULES)
    return rules


def _hlv_state(*, comps, net_specs, config=None, board=None, rules=None):
    netlist = _netlist(comps, net_specs)
    return BoardState(
        netlist=netlist,
        config=config,
        board=board,
        drc_oracle=_DrcOracle(_DesignRules(net_classes=rules)) if rules is not None else None,
    )


def _run_hlp_both(state):
    return (
        _orc_hlp.HvLvPartitionStage().run(state),
        _shim_hlp().run(state),
    )


def test_hlp_disabled_guard_identity() -> None:
    state = BoardState(config={"hv_lv_guard_strip": {"enabled": False}})
    assert _orc_hlp.HvLvPartitionStage().run(state) is state
    assert _shim_hlp().run(state) is state


def test_hlp_no_board_guard_identity() -> None:
    state = BoardState(netlist=_netlist([_comp("Q1", [_pin("1", (0, 0))])]))
    assert _orc_hlp.HvLvPartitionStage().run(state) is state
    assert _shim_hlp().run(state) is state


def test_hlp_skip_empty_identity() -> None:
    """All-LV (or all-HV) buckets -> skip_empty; state returned unchanged."""
    comps = [_comp("R1", [_pin("1", (0, 0))], initial_position=(0, 0))]
    state = _hlv_state(
        comps=comps,
        net_specs=[("+3V3", [("R1", "1")], "LV")],
        rules=_LV_CLASS_RULES,
        board=_FakeBoard(),
    )
    orc_out, port_out = _run_hlp_both(state)
    assert orc_out is state
    assert port_out is state


def test_hlp_skip_zero_identity() -> None:
    """width_mm=0 -> skip_zero (the `width_mm == 0` CPython equality)."""
    comps = [_comp("Q1", [_pin("1", (0, 0))], initial_position=(0, 0))]
    state = _hlv_state(
        comps=comps,
        net_specs=[("DC_BUS+", [("Q1", "1")], "HV")],
        rules=_HV_CLASS_RULES,
        board=_FakeBoard(),
        config={"hv_lv_guard_strip": {"width_mm": 0}},
    )
    orc_out, port_out = _run_hlp_both(state)
    assert orc_out is state
    assert port_out is state


def test_hlp_ok_write_bit_exact(caplog) -> None:
    """ok decision writes component_domain_map / routing_corridors /
    domain_regions; both arms identical."""
    q1 = _comp("Q1", [_pin("1", (0, 0))], initial_position=(0, 0))
    r1 = _comp("R1", [_pin("1", (0, 0))], initial_position=(0, 0))
    state = _hlv_state(
        comps=[q1, r1],
        net_specs=[("DC_BUS+", [("Q1", "1")], "HV"), ("+3V3", [("R1", "1")], "LV")],
        rules=_all_rules(),
        board=_FakeBoard(),
    )
    with caplog.at_level("INFO"):
        orc_out, port_out = _run_hlp_both(state)
    assert orc_out.component_domain_map == port_out.component_domain_map
    assert orc_out.component_domain_map == frozenset({("Q1", "HV_edge"), ("R1", "LV_interior")})
    assert len(orc_out.routing_corridors) == len(port_out.routing_corridors) == 1
    assert orc_out.routing_corridors[0].wkt == port_out.routing_corridors[0].wkt
    assert len(orc_out.domain_regions) == len(port_out.domain_regions) == 2
    for a, b in zip(orc_out.domain_regions, port_out.domain_regions):
        assert a.wkt == b.wkt


def test_hlp_width_below_creepage_warning(caplog) -> None:
    """A width_mm override below the creepage logs the warning and the width
    is clamped up to the creepage (the design-bundle kernel)."""
    q1 = _comp("Q1", [_pin("1", (0, 0))], initial_position=(0, 0))
    r1 = _comp("R1", [_pin("1", (0, 0))], initial_position=(0, 0))
    state = _hlv_state(
        comps=[q1, r1],
        net_specs=[("DC_BUS+", [("Q1", "1")], "HV"), ("+3V3", [("R1", "1")], "LV")],
        rules=_all_rules(),
        board=_FakeBoard(),
        config={"hv_lv_guard_strip": {"width_mm": 2.0}},
    )
    with caplog.at_level("WARNING"):
        orc_out, port_out = _run_hlp_both(state)
    msgs = [r.message for r in caplog.records if "below creepage" in str(r.message)]
    assert len(msgs) == 2, "both arms log the below-creepage warning"
    assert msgs[0] == msgs[1]
    assert orc_out.component_domain_map == port_out.component_domain_map
    assert orc_out.routing_corridors[0].wkt == port_out.routing_corridors[0].wkt


def test_hlp_fallback_identity(caplog) -> None:
    """Insufficient bucket area with fallback_to_unconstrained -> warning +
    identity return."""
    big = _comp("Q1", [_pin("1", (0, 0))], initial_position=(0, 0))
    r1 = _comp("R1", [_pin("1", (0, 0))], initial_position=(0, 0))
    big.bounds = (40.0, 40.0)
    state = _hlv_state(
        comps=[big, r1],
        net_specs=[("DC_BUS+", [("Q1", "1")], "HV"), ("+3V3", [("R1", "1")], "LV")],
        rules=_all_rules(),
        board=_FakeBoard(width=2.0, height=2.0),
        config={"hv_lv_guard_strip": {"fallback_to_unconstrained": True}},
    )
    with caplog.at_level("WARNING"):
        orc_out, port_out = _run_hlp_both(state)
    assert orc_out is state
    assert port_out is state
    msgs = [str(r.message) for r in caplog.records if "insufficient" in str(r.message)]
    assert len(msgs) == 2
    assert msgs[0] == msgs[1]


def test_hlp_raise_partition_error() -> None:
    """fallback_to_unconstrained=False + insufficient area -> PartitionError
    on BOTH arms with identical message."""
    big = _comp("Q1", [_pin("1", (0, 0))], initial_position=(0, 0))
    r1 = _comp("R1", [_pin("1", (0, 0))], initial_position=(0, 0))
    big.bounds = (40.0, 40.0)
    state = _hlv_state(
        comps=[big, r1],
        net_specs=[("DC_BUS+", [("Q1", "1")], "HV"), ("+3V3", [("R1", "1")], "LV")],
        rules=_all_rules(),
        board=_FakeBoard(width=2.0, height=2.0),
        config={"hv_lv_guard_strip": {"fallback_to_unconstrained": False}},
    )
    with pytest.raises(Exception) as orc_exc:
        _orc_hlp.HvLvPartitionStage().run(state)
    with pytest.raises(Exception) as port_exc:
        _shim_hlp().run(state)
    assert type(orc_exc.value).__name__ == type(port_exc.value).__name__ == "PartitionError"
    assert str(orc_exc.value) == str(port_exc.value)
    assert str(port_exc.value).startswith("PartitionError: HV cannot fit Q1 (")


def test_hlp_dual_domain_warning(caplog) -> None:
    """A dual-domain component (HV+LV nets) goes to the LV bucket with the
    `dual-domain ... -> LV bucket` warning."""
    q1 = _comp("Q1", [_pin("1", (0, 0))], initial_position=(0, 0))
    bridge = _comp(
        "U_BRIDGE",
        [_pin("1", (0, 0), net="DC_BUS+"), _pin("2", (0, 1), net="SPI_CLK")],
        initial_position=(0, 0),
    )
    r1 = _comp("R1", [_pin("1", (0, 0))], initial_position=(0, 0))
    state = _hlv_state(
        comps=[q1, bridge, r1],
        net_specs=[
            ("DC_BUS+", [("Q1", "1"), ("U_BRIDGE", "1")], "HV"),
            ("SPI_CLK", [("U_BRIDGE", "2")], "LV"),
            ("+3V3", [("R1", "1")], "LV"),
        ],
        rules=_all_rules(),
        board=_FakeBoard(),
    )
    with caplog.at_level("WARNING"):
        orc_out, port_out = _run_hlp_both(state)
    assert orc_out.component_domain_map == port_out.component_domain_map
    domain = dict(port_out.component_domain_map)
    assert domain["U_BRIDGE"] == "LV_interior"  # dual -> LV
    msgs = [str(r.message) for r in caplog.records if "dual-domain" in str(r.message)]
    assert len(msgs) == 2
    assert msgs[0] == msgs[1] == "dual-domain U_BRIDGE -> LV bucket"


# ---------------------------------------------------------------------------
# power_plane
# ---------------------------------------------------------------------------

def _run_pp_both(state, **kw):
    return (
        _orc_pp.PowerPlaneStage(**kw).run(state),
        _shim_pp(**kw).run(state),
    )


def test_pp_no_netlist_guard_identity() -> None:
    state = BoardState(netlist=None)
    assert _orc_pp.PowerPlaneStage().run(state) is state
    assert _shim_pp().run(state) is state


def test_pp_plane_nets_assigned_bit_exact() -> None:
    """Default tables: DC_BUS+ -> F.Cu plane (upgraded in place), SIG_A ->
    F.Cu non-plane."""
    q1 = _comp("Q1", [_pin("1", (0, 0), net="DC_BUS+")], initial_position=(0, 0))
    r1 = _comp("R1", [_pin("1", (0, 0), net="SIG_A")], initial_position=(0, 0))
    state = BoardState(
        netlist=_netlist(
            [q1, r1],
            [("DC_BUS+", [("Q1", "1")], "HV"), ("SIG_A", [("R1", "1")], "Signal")],
        ),
        layer_assignments=frozenset(),
    )
    orc_out, port_out = _run_pp_both(state)
    assert _las_canon(orc_out.layer_assignments) == _las_canon(port_out.layer_assignments)
    by_net = {la.net_name: la for la in port_out.layer_assignments}
    assert (by_net["DC_BUS+"].layer, by_net["DC_BUS+"].is_plane) == (0, True)
    assert (by_net["SIG_A"].layer, by_net["SIG_A"].is_plane) == (0, False)


def test_pp_new_plane_nets_and_remaining() -> None:
    """Plane nets with no existing assignment get appended (plane_nets
    iteration order); remaining netlist nets follow at layer 0 non-plane."""
    q1 = _comp("Q1", [_pin("1", (0, 0), net="DC_BUS+")], initial_position=(0, 0))
    state = BoardState(
        netlist=_netlist(
            [q1],
            [("DC_BUS+", [("Q1", "1")], "HV"), ("GND", [("Q1", "1")], "Ground"),
             ("SIG_A", [("Q1", "1")], "Signal")],
        ),
        layer_assignments=None,
    )
    orc_out, port_out = _run_pp_both(state)
    assert _las_canon(orc_out.layer_assignments) == _las_canon(port_out.layer_assignments)
    by_net = {la.net_name: la for la in port_out.layer_assignments}
    assert (by_net["DC_BUS+"].layer, by_net["DC_BUS+"].is_plane) == (0, True)
    assert (by_net["GND"].layer, by_net["GND"].is_plane) == (1, True)
    assert (by_net["SIG_A"].layer, by_net["SIG_A"].is_plane) == (0, False)


def test_pp_custom_tables() -> None:
    """Custom plane_nets/plane_layers override the defaults."""
    q1 = _comp("Q1", [_pin("1", (0, 0), net="CUSTOM_PWR")], initial_position=(0, 0))
    state = BoardState(
        netlist=_netlist(
            [q1],
            [("CUSTOM_PWR", [("Q1", "1")], "Power"), ("OTHER", [("Q1", "1")], "Signal")],
        ),
        layer_assignments=None,
    )
    orc_out, port_out = _run_pp_both(
        state,
        plane_nets=frozenset({"CUSTOM_PWR"}),
        plane_layers={"CUSTOM_PWR": 2},
    )
    assert _las_canon(orc_out.layer_assignments) == _las_canon(port_out.layer_assignments)
    by_net = {la.net_name: la for la in port_out.layer_assignments}
    assert (by_net["CUSTOM_PWR"].layer, by_net["CUSTOM_PWR"].is_plane) == (2, True)


# ---------------------------------------------------------------------------
# layer_assignment
# ---------------------------------------------------------------------------

def _run_la_both(state, **kw):
    return (
        _orc_la.LayerAssignmentStage(**kw).run(state),
        _shim_la(**kw).run(state),
    )


def test_la_no_netlist_guard_identity() -> None:
    state = BoardState(netlist=None)
    assert _orc_la.LayerAssignmentStage().run(state) is state
    assert _shim_la().run(state) is state


def test_la_by_net_class_bit_exact() -> None:
    """Net-class mapping: HighVoltage -> 0 non-plane, Ground -> 1 plane,
    Power -> 2 plane, Signal -> 0 non-plane."""
    q1 = _comp("Q1", [_pin("1", (0, 0), net="AC_L")], initial_position=(0, 0))
    c1 = _comp("C1", [_pin("1", (0, 0), net="GND")], initial_position=(0, 0))
    u1 = _comp("U1", [_pin("1", (0, 0), net="+3V3")], initial_position=(0, 0))
    r1 = _comp("R1", [_pin("1", (0, 0), net="SPI_CLK")], initial_position=(0, 0))
    state = BoardState(
        netlist=_netlist(
            [q1, c1, u1, r1],
            [
                ("AC_L", [("Q1", "1")], "HighVoltage"),
                ("GND", [("C1", "1")], "Ground"),
                ("+3V3", [("U1", "1")], "Power"),
                ("SPI_CLK", [("R1", "1")], "Signal"),
            ],
        ),
        layer_assignments=None,
    )
    orc_out, port_out = _run_la_both(state)
    assert _las_canon(orc_out.layer_assignments) == _las_canon(port_out.layer_assignments)
    by_net = {la.net_name: la for la in port_out.layer_assignments}
    assert (by_net["AC_L"].layer, by_net["AC_L"].is_plane) == (0, False)
    assert (by_net["GND"].layer, by_net["GND"].is_plane) == (1, True)
    assert (by_net["+3V3"].layer, by_net["+3V3"].is_plane) == (2, True)
    assert (by_net["SPI_CLK"].layer, by_net["SPI_CLK"].is_plane) == (0, False)


def test_la_manual_and_net_class_overrides() -> None:
    """Manual assignments win; net_classes override the parsed net_class."""
    r1 = _comp("R1", [_pin("1", (0, 0), net="TEST_NET")], initial_position=(0, 0))
    state = BoardState(
        netlist=_netlist([r1], [("TEST_NET", [("R1", "1")], "Signal")]),
        layer_assignments=None,
    )
    orc_out, port_out = _run_la_both(
        state,
        layer_assignments={"TEST_NET": 3},
        net_classes={"TEST_NET": "HighVoltage"},
    )
    assert _las_canon(orc_out.layer_assignments) == _las_canon(port_out.layer_assignments)
    by_net = {la.net_name: la for la in port_out.layer_assignments}
    assert (by_net["TEST_NET"].layer, by_net["TEST_NET"].is_plane) == (3, False)


def test_la_empty_net_class_fallback_to_signal() -> None:
    """An empty net_class falls back to \"Signal\" (the `or \"Signal\"`
    fallback)."""
    r1 = _comp("R1", [_pin("1", (0, 0), net="N1")], initial_position=(0, 0))
    state = BoardState(
        netlist=_netlist([r1], [("N1", [("R1", "1")], "")]),
        layer_assignments=None,
    )
    orc_out, port_out = _run_la_both(state)
    assert _las_canon(orc_out.layer_assignments) == _las_canon(port_out.layer_assignments)
    assert len(port_out.layer_assignments) == 1
    assert next(iter(port_out.layer_assignments)).layer == 0


# ---------------------------------------------------------------------------
# apply_placements
# ---------------------------------------------------------------------------

def _run_ap_both(state):
    return (
        _orc_ap.ApplyPlacementsStage().run(state),
        # Shim-debt cleanup 2026-08-19: the one-line shim module
        # stages/apply_placements.py was deleted; the port arm is the
        # temper-orchestration pyfunction directly.
        _to.run_apply_placements(state),
    )


def test_ap_no_netlist_guard_identity() -> None:
    state = BoardState(netlist=None, placements=frozenset({("R1", (1.0, 1.0))}))
    assert _orc_ap.ApplyPlacementsStage().run(state) is state
    assert _to.run_apply_placements(state) is state


def test_ap_no_placements_guard_identity() -> None:
    r1 = _comp("R1", [_pin("1", (0, 0))], initial_position=(1.0, 1.0))
    state = BoardState(netlist=_netlist([r1]), placements=None)
    assert _orc_ap.ApplyPlacementsStage().run(state) is state
    assert _to.run_apply_placements(state) is state


def test_ap_placements_applied_bit_exact() -> None:
    """Components in placements get their initial_position replaced; others
    keep theirs; the netlist write is a NEW object."""
    r1 = _comp("R1", [_pin("1", (0, 0))], initial_position=(1.0, 1.0))
    c1 = _comp("C1", [_pin("1", (0, 0))], initial_position=(2.0, 2.0))
    u1 = _comp("U1", [_pin("1", (0, 0))], initial_position=(3.0, 3.0))
    state = BoardState(
        netlist=_netlist([r1, c1, u1]),
        placements=frozenset({("R1", (10.5, 20.25)), ("C1", (30.0, 40.0))}),
    )
    orc_out, port_out = _run_ap_both(state)
    assert _components_positions(orc_out.netlist) == _components_positions(port_out.netlist)
    pos = _components_positions(port_out.netlist)
    assert pos["R1"] == (10.5, 20.25)
    assert pos["C1"] == (30.0, 40.0)
    assert pos["U1"] == (3.0, 3.0)  # untouched
    assert port_out.netlist is not state.netlist  # new netlist written
    assert port_out.netlist.components[0] is not r1  # component replaced


def test_ap_unchanged_components_preserved() -> None:
    """Components not in placements keep their ORIGINAL object identity."""
    r1 = _comp("R1", [_pin("1", (0, 0))], initial_position=(1.0, 1.0))
    c1 = _comp("C1", [_pin("1", (0, 0))], initial_position=(2.0, 2.0))
    state = BoardState(
        netlist=_netlist([r1, c1]), placements=frozenset({("R1", (9.0, 9.0))})
    )
    orc_out, port_out = _run_ap_both(state)
    assert _components_positions(orc_out.netlist) == _components_positions(port_out.netlist)
    assert port_out.netlist.components[1] is c1  # untouched component reused
