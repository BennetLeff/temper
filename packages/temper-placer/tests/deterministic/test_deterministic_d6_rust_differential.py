"""R1a behavioural differential of the D6 deterministic validation stages
against the pinned pre-migration oracle.

Rust Orchestration Engine plan 2026-08-09-001, Phase D batch D6: the
run() orchestration of the six validation stages --
`deterministic/stages/{placement_validation,via_validation,drc_sweep,
drc_validation,connectivity_validation,courtyard_check}.py` -- moves to
`temper-orchestration` as `Stage<BoardState>` implementors
(`PlacementValidationStage`, `ViaValidationStage`, `ViaDeduplicationStage`,
`DRCSweepStage`, `TrackDeduplicationStage`, `ShortCircuitDetectionStage`,
`DRCValidationStage`, `ConnectivityValidationStage`, `CourtyardCheckStage`).
The pre-migration implementations are pinned VERBATIM as the oracles
(`tests/deterministic/_*_run_py_oracle.py`, content-hash-pinned below).

Both arms are driven with IDENTICAL BoardState inputs and stage constructor
args; every observable output is compared bit-exactly (floats projected
through `float.hex()`):

- `PlacementValidationStage` -> `state.placement_violations` (tuple of
  `PlacementViolation`) and the `PlacementValidationError` raise (message
  equality on the raise path).
- `ViaValidationStage` / `ViaDeduplicationStage` -> `state.vias` (frozenset
  of Via objects) and the captured stdout (the `print(...)` messages).
- `DRCSweepStage` / `TrackDeduplicationStage` / `ShortCircuitDetectionStage`
  -> `state.routes` + `state.vias` (frozensets) and the captured stdout.
- `DRCValidationStage` -> `state.drc_violations` (tuple) and the
  `DRCValidationError` raise.
- `ConnectivityValidationStage` -> `state.connectivity_violations` (tuple of
  `ConnectivityViolation`) and the `ConnectivityValidationError` raise.
- `CourtyardCheckStage` -> `state.placements` (frozenset of `(ref, (x, y))`)
  bit-exact and the captured stdout; the CPython `random` module is seeded
  IDENTICALLY before each arm (the stage's nudge noise stays single-source
  CPython `random.random()`, driven through FFI by the port), so the two
  trajectories consume the identical noise sequence.

The leaf kernels the stages delegate to (temper_drc_rs / temper-geometry /
temper-io-types) stay single-source and are driven through FFI by the port;
the shapely/GEOS courtyard collision detection, the DRCOracle methods and
`random.random()` stay Python call-backs.

Anti-vacuity: `test_oracle_and_port_are_different_implementations` asserts the
shims resolve to the Rust pyfunctions (their `run` bodies call
`temper_orchestration`), not back onto the oracle. The oracle body digests
below are pinned: a differential whose oracle can be edited to agree with the
port proves nothing.
"""

from __future__ import annotations

import hashlib
import inspect
import random as _random
from dataclasses import replace
from pathlib import Path

import pytest
import temper_orchestration as _to

import tests.deterministic._placement_validation_run_py_oracle as _orc_pv
import tests.deterministic._via_validation_run_py_oracle as _orc_vv
import tests.deterministic._drc_sweep_run_py_oracle as _orc_ds
import tests.deterministic._drc_validation_run_py_oracle as _orc_drv
import tests.deterministic._connectivity_validation_run_py_oracle as _orc_cv
import tests.deterministic._courtyard_check_run_py_oracle as _orc_cc

from temper_placer.core.board import Trace, Via
from temper_placer.core.courtyard import Courtyard
from temper_placer.core.netlist import Component, Netlist, Pin
from temper_placer.deterministic.stages import (
    ConnectivityValidationStage as _shim_cv,
    CourtyardCheckStage as _shim_cc,
    DRCSweepStage as _shim_ds,
    DRCValidationStage as _shim_drv,
    PlacementValidationStage as _shim_pv,
    ShortCircuitDetectionStage as _shim_sc,
    TrackDeduplicationStage as _shim_td,
    ViaDeduplicationStage as _shim_vd,
    ViaValidationStage as _shim_vv,
)
from temper_placer.deterministic.state import BoardState
from temper_placer.router_v6.constraints_geometry import Point

# ---------------------------------------------------------------------------
# Oracle body pinning (G1)
# ---------------------------------------------------------------------------

_PINNED = {
    "_placement_validation_run_py_oracle.py": "1faa542b979894b8eb74697887cdecaf4ac1de8c9eadfedfe7cbc1e267050e57",
    "_via_validation_run_py_oracle.py": "818f78454de32e37482468f5aa389fad9c383f0ea14edea656bab03f7f8916d8",
    "_drc_sweep_run_py_oracle.py": "072ff3d07df9186dcb013fb4047aadf978ef06219b531cc7828a51f9bc4ea3fc",
    "_drc_validation_run_py_oracle.py": "b384e46ca944de80c3a98d66ddc69908ab0406b1e6733865e3bc5681c6feba6b",
    "_connectivity_validation_run_py_oracle.py": "318c7418406d644e9229e9839fd61b2566e973c1cda1e3e2ab7e51757b841dda",
    "_courtyard_check_run_py_oracle.py": "fab02913bc492b2838c8f6d33352c2131254be1c28bc0b841f2ab0170b9a6dec",
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
        _shim_pv.run: "run_placement_validation",
        _shim_vv.run: "run_via_validation",
        _shim_vd.run: "run_via_deduplication",
        _shim_ds.run: "run_drc_sweep",
        _shim_td.run: "run_track_deduplication",
        _shim_sc.run: "run_short_circuit_detection",
        _shim_drv.run: "run_drc_validation",
        _shim_cv.run: "run_connectivity_validation",
        _shim_cc.run: "run_courtyard_check",
    }
    for fn, symbol in expected.items():
        src = inspect.getsource(fn)
        assert symbol in src, f"{fn.__qualname__} does not delegate to {symbol}"
    for symbol in [
        "run_placement_validation",
        "run_via_validation",
        "run_via_deduplication",
        "run_drc_sweep",
        "run_track_deduplication",
        "run_short_circuit_detection",
        "run_drc_validation",
        "run_connectivity_validation",
        "run_courtyard_check",
    ]:
        assert getattr(_to, symbol) is not None


# ---------------------------------------------------------------------------
# Canonicalisers (bit-exact comparison via float.hex)
# ---------------------------------------------------------------------------

def _hx(v):
    return None if v is None else float(v).hex()


def _placement_violations_canon(violations):
    return tuple(
        (
            v.constraint_name,
            v.violation_type,
            v.message,
            v.severity,
            v.component_a,
            v.component_b,
            _hx(v.actual_distance_mm),
            _hx(v.required_distance_mm),
        )
        for v in violations
    )


def _via_canon(v) -> tuple:
    return (
        v.net,
        (float(v.position[0]).hex(), float(v.position[1]).hex()),
        tuple(v.layers),
        bool(getattr(v, "is_diff_pair", False)),
    )


def _vias_canon(vias):
    return frozenset(_via_canon(v) for v in vias)


def _trace_canon(t) -> tuple:
    return (
        t.net,
        t.layer,
        (float(t.start[0]).hex(), float(t.start[1]).hex()),
        (float(t.end[0]).hex(), float(t.end[1]).hex()),
        float(t.width),
    )


def _route_canon(r) -> tuple:
    if isinstance(r, Trace):
        return ("Trace",) + _trace_canon(r)
    if isinstance(r, Via):
        return ("Via",) + _via_canon(r)
    return ("Other", repr(r))


def _routes_canon(routes):
    return frozenset(_route_canon(r) for r in routes)


def _drc_violations_canon(violations):
    return tuple((v.type, str(v)) for v in violations)


def _connectivity_violations_canon(violations):
    return tuple(
        (
            v.type,
            v.net,
            (float(v.location.x).hex(), float(v.location.y).hex()),
            v.description,
        )
        for v in violations
    )


def _placements_canon(placements):
    return {
        ref: (float(x).hex(), float(y).hex())
        for ref, (x, y) in dict(placements).items()
    }


# ---------------------------------------------------------------------------
# placement_validation fixtures
# ---------------------------------------------------------------------------

class _PVComp:
    def __init__(self, ref, x, y):
        self.ref = ref
        self.x = x
        self.y = y


class _PVBoard:
    def __init__(self, components):
        self.components = components


class _Prox:
    def __init__(self, name, from_component, from_pin, to_component, to_pin,
                 max_distance_mm, tier):
        self.name = name
        self.from_component = from_component
        self.from_pin = from_pin
        self.to_component = to_component
        self.to_pin = to_pin
        self.max_distance_mm = max_distance_mm
        self.tier = tier


class _SigHv:
    def __init__(self, name, signal_component, signal_pin, target_component,
                 target_pin, hv_component, hv_pins, required_clearance_mm,
                 max_path_length_mm, tier):
        self.name = name
        self.signal_component = signal_component
        self.signal_pin = signal_pin
        self.target_component = target_component
        self.target_pin = target_pin
        self.hv_component = hv_component
        self.hv_pins = hv_pins
        self.required_clearance_mm = required_clearance_mm
        self.max_path_length_mm = max_path_length_mm
        self.tier = tier


def _pv_state(*, comps=("U1", "Q1", "R1")) -> BoardState:
    positions = {"U1": (5.0, 5.0), "Q1": (30.0, 5.0), "R1": (60.0, 5.0)}
    board = _PVBoard([_PVComp(ref, positions[ref][0], positions[ref][1]) for ref in comps])
    return BoardState(board=board)


def _prox_ok():
    return _Prox("P1", "U1", "15", "Q1", "1", max_distance_mm=30.0, tier="hard")


def _prox_violated():
    # 25mm apart but max 10mm -> violation, hard tier -> error severity.
    return _Prox("P2", "U1", "15", "Q1", "1", max_distance_mm=10.0, tier="hard")


def _prox_violated_soft():
    return _Prox("P3", "U1", "15", "Q1", "1", max_distance_mm=10.0, tier="signal")


def _prox_missing():
    return _Prox("P4", "U1", "15", "NO_SUCH", "1", max_distance_mm=10.0, tier="signal")


def _sig_hv_ok():
    return _SigHv(
        "S1", "U1", "15", "Q1", "1", "Q1", ["2", "3"],
        required_clearance_mm=6.0, max_path_length_mm=50.0, tier="hard",
    )


def _sig_hv_too_long():
    # U1(5,5) -> Q1(30,5) = 25mm path, but max 10mm.
    return _SigHv(
        "S2", "U1", "15", "Q1", "1", "Q1", ["2"],
        required_clearance_mm=6.0, max_path_length_mm=10.0, tier="hard",
    )


def _sig_hv_clearance():
    # Q1's pin 2 sits on the segment U1(5,5)->Q1(30,5): distance 0.
    return _SigHv(
        "S3", "U1", "15", "Q1", "1", "Q1", ["2"],
        required_clearance_mm=6.0, max_path_length_mm=50.0, tier="hard",
    )


def _sig_hv_missing():
    return _SigHv(
        "S4", "U1", "15", "MISSING", "1", "Q1", ["2"],
        required_clearance_mm=6.0, max_path_length_mm=50.0, tier="hard",
    )


def _pv_kwargs(constraints=None, fail_on_hard_violations=True, parsed_pads=None):
    return {
        "constraints": constraints or {},
        "fail_on_hard_violations": fail_on_hard_violations,
        "parsed_pads": parsed_pads or {},
    }


def _run_pv_both(state, **kw):
    args = _pv_kwargs(**kw)
    return (
        _orc_pv.PlacementValidationStage(**args).run(state),
        _shim_pv(**args).run(state),
    )


# ---------------------------------------------------------------------------
# via_validation / drc_sweep fixtures
# ---------------------------------------------------------------------------

def _pin(name, position, *, is_pth=False, layer="F.Cu", net=None):
    return Pin(name, name, position, net=net, layer=layer, is_pth=is_pth,
               width=2.0, height=2.0, shape="circle")


def _comp(ref, pins, initial_position=None):
    return Component(
        ref=ref, footprint="FP", bounds=(2.0, 2.0), pins=pins,
        net_class="Signal", initial_position=initial_position,
    )


def _netlist(refs=("Q1",)) -> Netlist:
    return Netlist(components=[_comp("Q1", [_pin("1", (0.0, 0.0))], (20.0, 20.0))], nets=[])


def _trace(start, end, layer="F.Cu", net="A", width=0.25):
    return Trace(start=start, end=end, width=width, layer=layer, net=net)


def _via(position, net="A", layers=("F.Cu", "B.Cu"), is_diff_pair=False):
    return Via(position=position, drill=0.3, width=0.6, layers=layers, net=net,
               is_diff_pair=is_diff_pair)


# ---------------------------------------------------------------------------
# DRC oracle fakes (deterministic, shared by both arms)
# ---------------------------------------------------------------------------

class _SweepOracle:
    """Deterministic routing-oracle fake: a track is valid unless its net is
    "BAD"; a via is valid unless its net is "BADVIA"."""

    def can_place_track_segment(self, *, start, end, layer, net, width):
        if net == "BAD":
            return False, "short to another net"
        return True, ""

    def get_valid_via_sites(self, position, search_radius=0.1, net=""):
        if net == "BADVIA":
            return []
        return [position]


class _DrvViolation:
    def __init__(self, vtype, message="v"):
        self.type = vtype
        self.message = message

    def __str__(self):
        return f"<{self.type}: {self.message}>"


class _DrvOracle:
    """Deterministic validate_all() fake returning the configured violations."""

    def __init__(self, violations):
        self._violations = list(violations)

    def validate_all(self):
        return list(self._violations)


class _Pad:
    def __init__(self, net, x, y, layer=0, size=(1.0, 1.0), rotation=0.0, pid="p"):
        self.net = net
        self.center = Point(x, y)
        self.layer = layer
        self.size = size
        self.rotation = rotation
        self.id = pid


class _Trk:
    def __init__(self, net, sx, sy, ex, ey, layer=0):
        self.net = net
        self.start = Point(sx, sy)
        self.end = Point(ex, ey)
        self.layer = layer


class _V:
    def __init__(self, net, x, y):
        self.net = net
        self.center = Point(x, y)


class _ConnOracle:
    """Deterministic geometry fake: pads/tracks/vias grouped by net."""

    def __init__(self, pads=(), tracks=(), vias=()):
        self.geometry = _Geom(pads, tracks, vias)


class _Geom:
    def __init__(self, pads, tracks, vias):
        self.pads = list(pads)
        self.tracks = list(tracks)
        self.vias = list(vias)


class _LayerAssignment:
    def __init__(self, net_name, is_plane):
        self.net_name = net_name
        self.is_plane = is_plane


# ---------------------------------------------------------------------------
# placement_validation differential
# ---------------------------------------------------------------------------

def test_pv_guard_no_board_identity() -> None:
    """No board: log a warning and return the ORIGINAL state object."""
    state = BoardState()
    orc, port = _run_pv_both(state)
    assert orc is state
    assert port is state


def test_pv_no_violations_writes_empty_tuple() -> None:
    state = _pv_state()
    orc, port = _run_pv_both(
        state,
        constraints={"placement_proximity": [_prox_ok()], "signal_hv_clearances": [_sig_hv_ok()]},
    )
    assert _placement_violations_canon(orc.placement_violations) == ()
    assert _placement_violations_canon(port.placement_violations) == ()
    assert port.placement_violations == ()


def test_pv_proximity_violation_hard_raises() -> None:
    state = _pv_state()
    kw = {"constraints": {"placement_proximity": [_prox_violated()]}}
    with pytest.raises(_orc_pv.PlacementValidationError) as ei:
        _orc_pv.PlacementValidationStage(**_pv_kwargs(**kw)).run(state)
    with pytest.raises(Exception) as ei2:
        _shim_pv(**_pv_kwargs(**kw)).run(state)
    assert ei2.value.__class__.__name__ == "PlacementValidationError"
    assert str(ei.value) == str(ei2.value)
    assert "1 hard placement violations found" in str(ei2.value)


def test_pv_proximity_violation_no_raise() -> None:
    """fail_on_hard_violations=False stores the violation instead of raising."""
    state = _pv_state()
    kw = {
        "constraints": {"placement_proximity": [_prox_violated()]},
        "fail_on_hard_violations": False,
    }
    orc, port = _run_pv_both(state, **kw)
    assert _placement_violations_canon(orc.placement_violations) == _placement_violations_canon(
        port.placement_violations
    )
    assert port.placement_violations[0].severity == "error"
    assert port.placement_violations[0].violation_type == "proximity"
    assert port.placement_violations[0].component_a == "U1"
    assert port.placement_violations[0].actual_distance_mm is not None
    assert port.placement_violations[0].required_distance_mm == 10.0


def test_pv_proximity_violation_soft_warning() -> None:
    state = _pv_state()
    kw = {"constraints": {"placement_proximity": [_prox_violated_soft()]}}
    orc, port = _run_pv_both(state, **kw)
    assert _placement_violations_canon(orc.placement_violations) == _placement_violations_canon(
        port.placement_violations
    )
    assert port.placement_violations[0].severity == "warning"


def test_pv_proximity_missing_component_warning() -> None:
    state = _pv_state()
    kw = {"constraints": {"placement_proximity": [_prox_missing()]}}
    orc, port = _run_pv_both(state, **kw)
    assert _placement_violations_canon(orc.placement_violations) == _placement_violations_canon(
        port.placement_violations
    )
    v = port.placement_violations[0]
    assert v.violation_type == "missing_component"
    assert v.severity == "warning"
    assert v.actual_distance_mm is None
    assert v.required_distance_mm is None


def test_pv_signal_hv_path_too_long_raises() -> None:
    state = _pv_state()
    kw = {"constraints": {"signal_hv_clearances": [_sig_hv_too_long()]}}
    with pytest.raises(_orc_pv.PlacementValidationError) as ei:
        _orc_pv.PlacementValidationStage(**_pv_kwargs(**kw)).run(state)
    with pytest.raises(Exception) as ei2:
        _shim_pv(**_pv_kwargs(**kw)).run(state)
    assert str(ei.value) == str(ei2.value)
    assert "1 hard placement violations found" in str(ei2.value)


def test_pv_signal_hv_clearance_violation() -> None:
    state = _pv_state()
    kw = {"constraints": {"signal_hv_clearances": [_sig_hv_clearance()]}, "fail_on_hard_violations": False}
    orc, port = _run_pv_both(state, **kw)
    assert _placement_violations_canon(orc.placement_violations) == _placement_violations_canon(
        port.placement_violations
    )
    v = port.placement_violations[0]
    assert v.violation_type == "hv_clearance"
    assert v.actual_distance_mm == 0.0


def test_pv_signal_hv_missing_component() -> None:
    state = _pv_state()
    kw = {"constraints": {"signal_hv_clearances": [_sig_hv_missing()]}}
    orc, port = _run_pv_both(state, **kw)
    assert _placement_violations_canon(orc.placement_violations) == _placement_violations_canon(
        port.placement_violations
    )
    v = port.placement_violations[0]
    assert v.violation_type == "missing_component"
    assert v.component_a is None
    assert v.actual_distance_mm is None


def test_pv_parsed_pads_offset() -> None:
    """parsed_pads pin offsets shift the resolved position; a violation that
    only materialises with the offset must appear on BOTH arms."""
    state = _pv_state()
    parsed = {"Q1": {"1": {"x": 5.0, "y": 0.0}}}  # Q1 gate sits at (35, 5)
    # U1(5,5) -> Q1 gate(35,5) = 30mm > 10mm -> hard violation.
    kw = {
        "constraints": {"placement_proximity": [_prox_violated()]},
        "parsed_pads": parsed,
        "fail_on_hard_violations": False,
    }
    orc, port = _run_pv_both(state, **kw)
    assert _placement_violations_canon(orc.placement_violations) == _placement_violations_canon(
        port.placement_violations
    )
    assert port.placement_violations
    # Without parsed pads the same constraint gives the same answer (no pads).
    orc2, port2 = _run_pv_both(state, constraints={"placement_proximity": [_prox_violated()]},
                                fail_on_hard_violations=False)
    assert _placement_violations_canon(orc2.placement_violations) == _placement_violations_canon(
        port2.placement_violations
    )


def test_pv_combined_and_multiple() -> None:
    """Multiple constraints of both kinds, mixed pass/fail, ordering pinned."""
    state = _pv_state()
    kw = {
        "constraints": {
            "placement_proximity": [_prox_ok(), _prox_violated()],
            "signal_hv_clearances": [_sig_hv_ok(), _sig_hv_clearance()],
        },
        "fail_on_hard_violations": False,
    }
    orc, port = _run_pv_both(state, **kw)
    assert _placement_violations_canon(orc.placement_violations) == _placement_violations_canon(
        port.placement_violations
    )
    assert len(port.placement_violations) == 2
    assert [v.violation_type for v in port.placement_violations] == ["proximity", "hv_clearance"]


# ---------------------------------------------------------------------------
# via_validation differential
# ---------------------------------------------------------------------------

def _vv_state(vias=(), routes=(), netlist=None, placements=None) -> BoardState:
    return BoardState(
        vias=frozenset(vias),
        routes=frozenset(routes),
        netlist=netlist,
        placements=frozenset(placements or ()),
    )


def test_vv_guard_no_vias_identity() -> None:
    state = BoardState()
    orc = _orc_vv.ViaValidationStage().run(state)
    port = _shim_vv().run(state)
    assert orc is state
    assert port is state


def test_vv_keeps_valid_removes_dangling() -> None:
    vias = [
        _via((1.0, 1.0), net="NET_A"),                       # endpoint on both F.Cu+B.Cu
        _via((30.0, 30.0), net="NET_B"),                     # no connection
    ]
    routes = [
        _trace((1.0, 1.0), (2.0, 1.0), net="NET_A"),
        _trace((1.0, 1.0), (2.0, 1.0), net="NET_A", layer="B.Cu"),
    ]
    state = _vv_state(vias=vias, routes=routes)
    orc = _orc_vv.ViaValidationStage().run(state)
    port = _shim_vv().run(state)
    assert _vias_canon(orc.vias) == _vias_canon(port.vias)
    assert len(port.vias) == 1
    nets_kept = {c[0] for c in _vias_canon(port.vias)}
    assert nets_kept == {"NET_A"}  # the two-layer-connected via survives
    assert "NET_B" not in nets_kept  # the dangling via is removed


def test_vv_plane_net_single_connection_kept() -> None:
    """A GND via with only an F.Cu connection is kept (plane auto-connect)."""
    vias = [_via((5.0, 5.0), net="GND")]
    routes = [_trace((5.0, 5.0), (6.0, 5.0), net="GND")]
    state = _vv_state(vias=vias, routes=routes)
    orc = _orc_vv.ViaValidationStage().run(state)
    port = _shim_vv().run(state)
    assert _vias_canon(orc.vias) == _vias_canon(port.vias)
    assert len(port.vias) == 1


def test_vv_plane_net_no_connection_removed() -> None:
    vias = [_via((7.0, 7.0), net="GND")]
    # A dummy route keeps the state guard from returning early; the GND via
    # has no trace/pin connection on either layer, so it is removed.
    routes = [_trace((50.0, 50.0), (51.0, 50.0), net="DUMMY")]
    state = _vv_state(vias=vias, routes=routes)
    orc = _orc_vv.ViaValidationStage().run(state)
    port = _shim_vv().run(state)
    assert _vias_canon(orc.vias) == _vias_canon(port.vias)
    assert port.vias == frozenset()


def test_vv_diff_pair_always_kept() -> None:
    vias = [_via((9.0, 9.0), net="DP", is_diff_pair=True)]
    state = _vv_state(vias=vias)
    orc = _orc_vv.ViaValidationStage().run(state)
    port = _shim_vv().run(state)
    assert _vias_canon(orc.vias) == _vias_canon(port.vias)
    assert len(port.vias) == 1


def test_vv_pin_connection_and_pth_layers() -> None:
    """A via on a PTH pin's F.Cu position is connected via the pin index; a
    PTH pin registers on every STANDARD_LAYER_ORDER layer."""
    comp = _comp(
        "U1",
        [_pin("1", (0.0, 0.0), is_pth=True)],
        initial_position=(10.0, 10.0),
    )
    netlist = Netlist(components=[comp], nets=[])
    # Via at the pin's F.Cu world position (10, 10): connected on F.Cu.
    vias = [_via((10.0, 10.0), net="NET_X")]
    state = _vv_state(vias=vias, netlist=netlist)
    orc = _orc_vv.ViaValidationStage().run(state)
    port = _shim_vv().run(state)
    assert _vias_canon(orc.vias) == _vias_canon(port.vias)
    assert len(port.vias) == 1


def test_vv_stdout_messages(capsys) -> None:
    vias = [
        _via((1.0, 1.0), net="NET_A"),
        _via((30.0, 30.0), net="NET_B"),
        _via((31.0, 31.0), net="NET_B"),
    ]
    routes = [_trace((1.0, 1.0), (2.0, 1.0), net="NET_A")]
    state = _vv_state(vias=vias, routes=routes)
    _orc_vv.ViaValidationStage().run(state)
    orc_out = capsys.readouterr().out
    port = _shim_vv().run(state)
    port_out = capsys.readouterr().out
    assert orc_out == port_out
    # All three vias connect on at most one layer (require_both_layers=True).
    assert "Removed 3 dangling vias" in port_out
    assert "Affected nets: NET_A, NET_B" in port_out


def test_vv_plane_vias_removed_stdout(capsys) -> None:
    """The plane-vias debug block: a GND via with no connection is removed and
    the 'Removed plane vias' lines print net/pos/layers/connected."""
    vias = [_via((7.0, 7.0), net="GND")]
    routes = [_trace((50.0, 50.0), (51.0, 50.0), net="DUMMY")]
    state = _vv_state(vias=vias, routes=routes)
    _orc_vv.ViaValidationStage().run(state)
    orc_out = capsys.readouterr().out
    _shim_vv().run(state)
    port_out = capsys.readouterr().out
    assert orc_out == port_out
    assert "Plane vias: 0/1 kept" in port_out
    assert "Removed plane vias (first 5):" in port_out
    assert "GND at (7.0, 7.0) layers=('F.Cu', 'B.Cu') connected=0" in port_out


def test_vv_plane_vias_kept_stdout(capsys) -> None:
    """A GND via with one F.Cu connection survives via the plane special case."""
    vias = [_via((5.0, 5.0), net="GND")]
    routes = [_trace((5.0, 5.0), (6.0, 5.0), net="GND"), _trace((5.0, 5.0), (6.0, 5.0), net="GND", layer="B.Cu")]
    state = _vv_state(vias=vias, routes=routes)
    _orc_vv.ViaValidationStage().run(state)
    orc_out = capsys.readouterr().out
    port = _shim_vv().run(state)
    port_out = capsys.readouterr().out
    assert orc_out == port_out
    assert "Plane vias: 1/1 kept" in port_out
    assert len(port.vias) == 1


def test_vvd_dedup_removes_duplicates() -> None:
    vias = [
        _via((1.0, 1.0), net="A"),
        _via((1.0, 1.0), net="A"),   # exact duplicate
        _via((1.01, 1.0), net="A"),  # within 0.05 tolerance
        _via((5.0, 5.0), net="B"),
    ]
    state = _vv_state(vias=vias)
    orc = _orc_vv.ViaDeduplicationStage().run(state)
    port = _shim_vd().run(state)
    assert _vias_canon(orc.vias) == _vias_canon(port.vias)
    assert len(port.vias) == 2


def test_vvd_guard_no_vias_identity() -> None:
    state = BoardState()
    orc = _orc_vv.ViaDeduplicationStage().run(state)
    port = _shim_vd().run(state)
    assert orc is state
    assert port is state


def test_vvd_stdout_message(capsys) -> None:
    vias = [_via((1.0, 1.0)), _via((1.01, 1.0))]
    state = _vv_state(vias=vias)
    _orc_vv.ViaDeduplicationStage().run(state)
    orc_out = capsys.readouterr().out
    _shim_vd().run(state)
    port_out = capsys.readouterr().out
    assert orc_out == port_out
    assert "Removed 1 duplicate vias" in port_out


# ---------------------------------------------------------------------------
# drc_sweep differential
# ---------------------------------------------------------------------------

def _ds_state(oracle=None, routes=(), vias=()) -> BoardState:
    return BoardState(
        drc_oracle=oracle,
        routes=frozenset(routes),
        vias=frozenset(vias),
    )


def test_ds_guard_no_oracle_identity() -> None:
    state = BoardState()
    orc = _orc_ds.DRCSweepStage().run(state)
    port = _shim_ds().run(state)
    assert orc is state
    assert port is state


def test_ds_removes_bad_track_and_via() -> None:
    routes = [
        _trace((0.0, 0.0), (10.0, 0.0), net="GOOD"),
        _trace((0.0, 5.0), (10.0, 5.0), net="BAD"),
    ]
    vias = [
        _via((1.0, 1.0), net="GOODVIA"),
        _via((2.0, 2.0), net="BADVIA"),
    ]
    state = _ds_state(oracle=_SweepOracle(), routes=routes, vias=vias)
    orc = _orc_ds.DRCSweepStage().run(state)
    port = _shim_ds().run(state)
    assert _routes_canon(orc.routes) == _routes_canon(port.routes)
    assert _vias_canon(orc.vias) == _vias_canon(port.vias)
    assert len(port.routes) == 1
    assert len(port.vias) == 1


def test_ds_stdout(capsys) -> None:
    routes = [
        _trace((0.0, 0.0), (10.0, 0.0), net="GOOD"),
        _trace((0.0, 5.0), (10.0, 5.0), net="BAD"),
    ]
    vias = [_via((2.0, 2.0), net="BADVIA")]
    state = _ds_state(oracle=_SweepOracle(), routes=routes, vias=vias)
    _orc_ds.DRCSweepStage().run(state)
    orc_out = capsys.readouterr().out
    _shim_ds().run(state)
    port_out = capsys.readouterr().out
    assert orc_out == port_out
    assert "Removed 1 tracks, 1 vias" in port_out


def test_ds_non_trace_route_entries_pass_through() -> None:
    """Non-Trace route entries (e.g. a Via in routes) pass through unchanged."""
    via_in_routes = _via((50.0, 50.0), net="VIAINROUTES")
    routes = [_trace((0.0, 0.0), (10.0, 0.0), net="BAD"), via_in_routes]
    state = _ds_state(oracle=_SweepOracle(), routes=routes)
    orc = _orc_ds.DRCSweepStage().run(state)
    port = _shim_ds().run(state)
    assert _routes_canon(orc.routes) == _routes_canon(port.routes)
    canon = _routes_canon(port.routes)
    assert ("Via", "VIAINROUTES") in [c[:2] for c in canon]


def test_td_guard_no_routes_identity() -> None:
    state = BoardState()
    orc = _orc_ds.TrackDeduplicationStage().run(state)
    port = _shim_td().run(state)
    assert orc is state
    assert port is state


def test_td_removes_reversed_duplicate() -> None:
    routes = [
        _trace((0.0, 0.0), (10.0, 0.0), net="A"),
        _trace((10.0, 0.0), (0.0, 0.0), net="A"),  # reversed duplicate
        _trace((0.0, 5.0), (10.0, 5.0), net="A"),  # distinct
        _trace((0.0, 0.0), (10.0, 0.0), net="B"),  # distinct net
    ]
    state = _ds_state(routes=routes)
    orc = _orc_ds.TrackDeduplicationStage().run(state)
    port = _shim_td().run(state)
    assert _routes_canon(orc.routes) == _routes_canon(port.routes)
    assert len(port.routes) == 3


def test_td_non_trace_pass_through_and_stdout(capsys) -> None:
    via_in_routes = _via((50.0, 50.0), net="VIA")
    routes = [_trace((0.0, 0.0), (10.0, 0.0), net="A"),
              _trace((10.0, 0.0), (0.0, 0.0), net="A"),
              via_in_routes]
    state = _ds_state(routes=routes)
    orc = _orc_ds.TrackDeduplicationStage().run(state)
    orc_out = capsys.readouterr().out
    port = _shim_td().run(state)
    port_out = capsys.readouterr().out
    assert orc_out == port_out
    assert _routes_canon(orc.routes) == _routes_canon(port.routes)
    assert ("Via", "VIA") in [c[:2] for c in _routes_canon(port.routes)]
    assert "Removed 1 duplicate segments" in port_out


def test_sc_guard_no_netlist_or_routes_identity() -> None:
    state = BoardState()
    orc = _orc_ds.ShortCircuitDetectionStage().run(state)
    port = _shim_sc().run(state)
    assert orc is state
    assert port is state


def _sc_state(comps, nets, routes, placements=()) -> BoardState:
    return BoardState(
        netlist=Netlist(components=comps, nets=nets),
        routes=frozenset(routes),
        placements=frozenset(placements),
    )


def test_sc_removes_shorting_track() -> None:
    """A track on net A whose endpoint touches a net-B pin is removed."""
    comp = _comp("U1", [_pin("1", (0.0, 0.0), net="NET_B")], (10.0, 10.0))
    nets = [type("_Net", (), {"pins": [("U1", "1")], "name": "NET_B"})()]
    routes = [
        _trace((10.0, 10.0), (30.0, 10.0), net="NET_A"),  # endpoint on B pin -> short
        _trace((20.0, 20.0), (40.0, 20.0), net="NET_A"),  # clear
    ]
    state = _sc_state([comp], nets, routes)
    orc = _orc_ds.ShortCircuitDetectionStage().run(state)
    port = _shim_sc().run(state)
    assert _routes_canon(orc.routes) == _routes_canon(port.routes)
    assert len(port.routes) == 1


def test_sc_same_net_not_short() -> None:
    comp = _comp("U1", [_pin("1", (0.0, 0.0), net="NET_A")], (10.0, 10.0))
    nets = [type("_Net", (), {"pins": [("U1", "1")], "name": "NET_A"})()]
    routes = [_trace((10.0, 10.0), (30.0, 10.0), net="NET_A")]
    state = _sc_state([comp], nets, routes)
    orc = _orc_ds.ShortCircuitDetectionStage().run(state)
    port = _shim_sc().run(state)
    assert _routes_canon(orc.routes) == _routes_canon(port.routes)
    assert len(port.routes) == 1


def test_sc_pth_pin_registers_all_layers() -> None:
    """A PTH pin on the wrong net on any standard layer registers as a short
    candidate; a track on In1.Cu whose endpoint coincides is removed."""
    comp = _comp("U1", [_pin("1", (0.0, 0.0), net="NET_B", is_pth=True)], (10.0, 10.0))
    nets = [type("_Net", (), {"pins": [("U1", "1")], "name": "NET_B"})()]
    routes = [
        _trace((10.0, 10.0), (30.0, 10.0), net="NET_A", layer="In1.Cu"),
    ]
    state = _sc_state([comp], nets, routes)
    orc = _orc_ds.ShortCircuitDetectionStage().run(state)
    port = _shim_sc().run(state)
    assert _routes_canon(orc.routes) == _routes_canon(port.routes)
    assert port.routes == frozenset()


def test_sc_stdout(capsys) -> None:
    comp = _comp("U1", [_pin("1", (0.0, 0.0), net="NET_B")], (10.0, 10.0))
    nets = [type("_Net", (), {"pins": [("U1", "1")], "name": "NET_B"})()]
    routes = [_trace((10.0, 10.0), (30.0, 10.0), net="NET_A")]
    state = _sc_state([comp], nets, routes)
    _orc_ds.ShortCircuitDetectionStage().run(state)
    orc_out = capsys.readouterr().out
    _shim_sc().run(state)
    port_out = capsys.readouterr().out
    assert orc_out == port_out
    assert "Removed 1 shorting tracks" in port_out


# ---------------------------------------------------------------------------
# drc_validation differential
# ---------------------------------------------------------------------------

def test_drv_guard_no_oracle_identity() -> None:
    state = BoardState()
    orc = _orc_drv.DRCValidationStage().run(state)
    port = _shim_drv().run(state)
    assert orc is state
    assert port is state


def test_drv_clean_board() -> None:
    state = BoardState(drc_oracle=_DrvOracle([]))
    orc = _orc_drv.DRCValidationStage().run(state)
    port = _shim_drv().run(state)
    assert _drc_violations_canon(orc.drc_violations) == _drc_violations_canon(
        port.drc_violations
    )
    assert port.drc_violations == ()


def test_drv_violations_stored() -> None:
    oracle = _DrvOracle([_DrvViolation("track_clearance"), _DrvViolation("via_dangling")])
    state = BoardState(drc_oracle=oracle)
    orc = _orc_drv.DRCValidationStage().run(state)
    port = _shim_drv().run(state)
    assert _drc_violations_canon(orc.drc_violations) == _drc_violations_canon(
        port.drc_violations
    )
    assert [v.type for v in port.drc_violations] == ["track_clearance", "via_dangling"]


def test_drv_fail_on_violations_raises() -> None:
    state = BoardState(drc_oracle=_DrvOracle([_DrvViolation("track_clearance")]))
    with pytest.raises(_orc_drv.DRCValidationError) as ei:
        _orc_drv.DRCValidationStage(fail_on_violations=True).run(state)
    with pytest.raises(Exception) as ei2:
        _shim_drv(fail_on_violations=True).run(state)
    assert ei2.value.__class__.__name__ == "DRCValidationError"
    assert str(ei.value) == str(ei2.value)
    assert str(ei2.value) == "1 DRC violations found"


def test_drv_max_violations_threshold() -> None:
    """max_violations uses strict >: count == max passes, count > max raises."""
    two = _DrvOracle([_DrvViolation("a"), _DrvViolation("b")])
    state2 = BoardState(drc_oracle=two)
    port_pass = _shim_drv(max_violations=2).run(state2)
    assert _drc_violations_canon(port_pass.drc_violations) == _drc_violations_canon(
        _orc_drv.DRCValidationStage(max_violations=2).run(state2).drc_violations
    )
    three = _DrvOracle([_DrvViolation("a"), _DrvViolation("b"), _DrvViolation("c")])
    state3 = BoardState(drc_oracle=three)
    with pytest.raises(_orc_drv.DRCValidationError) as ei:
        _orc_drv.DRCValidationStage(max_violations=2).run(state3)
    with pytest.raises(Exception) as ei2:
        _shim_drv(max_violations=2).run(state3)
    assert str(ei.value) == str(ei2.value)
    assert str(ei2.value) == "3 violations exceeds max 2"


# ---------------------------------------------------------------------------
# connectivity_validation differential
# ---------------------------------------------------------------------------

def _cv_state(oracle=None, layer_assignments=()) -> BoardState:
    return BoardState(
        drc_oracle=oracle,
        layer_assignments=frozenset(layer_assignments),
    )


def test_cv_guard_no_oracle_identity() -> None:
    state = BoardState()
    orc = _orc_cv.ConnectivityValidationStage().run(state)
    port = _shim_cv().run(state)
    assert orc is state
    assert port is state


def test_cv_clean_net_no_violations() -> None:
    oracle = _ConnOracle(pads=[_Pad("NET_A", 10.0, 10.0)])
    state = _cv_state(oracle=oracle)
    orc = _orc_cv.ConnectivityValidationStage().run(state)
    port = _shim_cv().run(state)
    assert _connectivity_violations_canon(orc.connectivity_violations) == \
        _connectivity_violations_canon(port.connectivity_violations)
    assert port.connectivity_violations == ()


def test_cv_dangling_track() -> None:
    oracle = _ConnOracle(
        pads=[_Pad("NET_A", 0.0, 0.0)],
        tracks=[_Trk("NET_A", 0.0, 0.0, 10.0, 10.0)],
    )
    state = _cv_state(oracle=oracle)
    orc = _orc_cv.ConnectivityValidationStage().run(state)
    port = _shim_cv().run(state)
    assert _connectivity_violations_canon(orc.connectivity_violations) == \
        _connectivity_violations_canon(port.connectivity_violations)
    assert any(v.type == "dangling_track" for v in port.connectivity_violations)


def test_cv_plane_nets_skipped() -> None:
    """A plane net is skipped entirely (assumed connected via inner pours)."""
    oracle = _ConnOracle(
        pads=[_Pad("GND", 0.0, 0.0)],
        tracks=[_Trk("GND", 0.0, 0.0, 10.0, 10.0)],
    )
    state = _cv_state(oracle=oracle, layer_assignments=[_LayerAssignment("GND", True)])
    orc = _orc_cv.ConnectivityValidationStage().run(state)
    port = _shim_cv().run(state)
    assert _connectivity_violations_canon(orc.connectivity_violations) == \
        _connectivity_violations_canon(port.connectivity_violations)
    assert port.connectivity_violations == ()


def test_cv_empty_and_nonet_skipped() -> None:
    oracle = _ConnOracle(pads=[_Pad("", 0.0, 0.0), _Pad("NoNet", 1.0, 1.0)])
    state = _cv_state(oracle=oracle)
    orc = _orc_cv.ConnectivityValidationStage().run(state)
    port = _shim_cv().run(state)
    assert _connectivity_violations_canon(orc.connectivity_violations) == \
        _connectivity_violations_canon(port.connectivity_violations)
    assert port.connectivity_violations == ()


def test_cv_fail_on_violations_raises() -> None:
    oracle = _ConnOracle(
        pads=[_Pad("NET_A", 0.0, 0.0)],
        tracks=[_Trk("NET_A", 0.0, 0.0, 10.0, 10.0)],
    )
    state = _cv_state(oracle=oracle)
    with pytest.raises(_orc_cv.ConnectivityValidationError) as ei:
        _orc_cv.ConnectivityValidationStage(fail_on_violations=True).run(state)
    with pytest.raises(Exception) as ei2:
        _shim_cv(fail_on_violations=True).run(state)
    assert ei2.value.__class__.__name__ == "ConnectivityValidationError"
    assert str(ei.value) == str(ei2.value)
    assert str(ei2.value) == "1 connectivity violations found"


# ---------------------------------------------------------------------------
# courtyard_check differential
# ---------------------------------------------------------------------------

def _square_courtyard(ref: str, half_size: float = 2.0) -> Courtyard:
    return Courtyard(
        component_ref=ref,
        points=[
            (-half_size, -half_size),
            (half_size, -half_size),
            (half_size, half_size),
            (-half_size, half_size),
        ],
    )


def _cc_state(placements=()) -> BoardState:
    return BoardState(placements=frozenset(placements))


def _cc_kwargs(courtyards=None, **extra):
    kw = {
        "courtyards": courtyards or {},
        "board_width": 100.0,
        "board_height": 100.0,
        "margin": 5.0,
        "max_iterations": 200,
        "nudge_step": 0.2,
    }
    kw.update(extra)
    return kw


def _run_cc_both(state, **kw) -> tuple[BoardState, BoardState]:
    args = _cc_kwargs(**kw)
    _random.seed(20260810)
    orc = _orc_cc.CourtyardCheckStage(**args).run(state)
    _random.seed(20260810)
    port = _shim_cc(**args).run(state)
    return orc, port


def test_cc_guard_no_placements_identity() -> None:
    state = BoardState()
    args = _cc_kwargs()
    orc = _orc_cc.CourtyardCheckStage(**args).run(state)
    port = _shim_cc(**args).run(state)
    assert orc is state
    assert port is state


def test_cc_no_collisions_passthrough() -> None:
    courtyards = {"R1": _square_courtyard("R1"), "R2": _square_courtyard("R2")}
    state = _cc_state({"R1": (10.0, 10.0), "R2": (50.0, 50.0)}.items())
    orc, port = _run_cc_both(state, courtyards=courtyards, max_iterations=50)
    assert _placements_canon(orc.placements) == _placements_canon(port.placements)
    assert port.placements == state.placements  # untouched, bit-identical


def test_cc_resolves_overlap_bit_exact(capsys) -> None:
    """A genuinely overlapping pair is nudged apart; the whole trajectory is
    bit-identical because the random noise sequence is identical."""
    courtyards = {"R1": _square_courtyard("R1"), "R2": _square_courtyard("R2")}
    state = _cc_state({"R1": (10.0, 10.0), "R2": (13.0, 10.0)}.items())
    args = _cc_kwargs(courtyards=courtyards, max_iterations=200)
    _random.seed(42)
    _orc_cc.CourtyardCheckStage(**args).run(state)
    orc_out = capsys.readouterr().out
    _random.seed(42)
    port = _shim_cc(**args).run(state)
    port_out = capsys.readouterr().out
    assert orc_out == port_out
    final = _shim_cc(**args)._find_collisions(dict(port.placements))
    assert final == [], f"left unresolved collisions: {final!r}"


def test_cc_overlapping_centers_nudge() -> None:
    """Coincident centers hit the dist < 1e-6 branch (dx,dy = 1,0; dist = 1)."""
    courtyards = {"R1": _square_courtyard("R1"), "R2": _square_courtyard("R2")}
    state = _cc_state({"R1": (10.0, 10.0), "R2": (10.0, 10.0)}.items())
    orc, port = _run_cc_both(state, courtyards=courtyards, max_iterations=60)
    assert _placements_canon(orc.placements) == _placements_canon(port.placements)


def test_cc_clamp_to_board_bounds() -> None:
    """Nudges near the board edge clamp to [margin, dim - margin]."""
    courtyards = {"R1": _square_courtyard("R1"), "R2": _square_courtyard("R2")}
    state = _cc_state({"R1": (6.0, 6.0), "R2": (9.0, 6.0)}.items())
    orc, port = _run_cc_both(state, courtyards=courtyards, max_iterations=100)
    assert _placements_canon(orc.placements) == _placements_canon(port.placements)
    for ref, (x, y) in dict(port.placements).items():
        assert 5.0 <= x <= 95.0 and 5.0 <= y <= 95.0


def test_cc_stdout_messages(capsys) -> None:
    courtyards = {"R1": _square_courtyard("R1"), "R2": _square_courtyard("R2")}
    state = _cc_state({"R1": (10.0, 10.0), "R2": (13.0, 10.0)}.items())
    args = _cc_kwargs(courtyards=courtyards, max_iterations=5)
    _random.seed(7)
    _orc_cc.CourtyardCheckStage(**args).run(state)
    orc_out = capsys.readouterr().out
    _random.seed(7)
    _shim_cc(**args).run(state)
    port_out = capsys.readouterr().out
    assert orc_out == port_out
    assert "overlapping pairs" in port_out
