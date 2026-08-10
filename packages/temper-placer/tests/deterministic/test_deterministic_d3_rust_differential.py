"""R1a: behavioural differential of the D3 deterministic clearance-grid
stages against the pinned pre-migration oracle.

Rust Orchestration Engine plan 2026-08-09-001, Phase D batch D3: the
orchestration of ``deterministic/stages/_grid_stage.py`` (the
``ClearanceGridStage`` run: pad collection, per-net blocking, the
pre-route HV creepage-expansion pass, the fence invocation and the HV
exclusion-zone blocking) moves to ``temper-orchestration`` as a
``Stage<BoardState>`` implementor (``ClearanceGridStage``). The
``_grid_hv.hv_pad_set`` and ``_grid_fence`` checks become thin FFI
delegations to Rust kernels (``run_hv_pad_set`` / ``run_grid_fence_check``
/ ``run_grid_perf_budget``); the ``ClearanceGrid`` data type
(``_grid_core.py``), the exception classes and the module-level
``_EXPANSION_LOG`` stay Python. The pre-migration implementations are
pinned VERBATIM as the oracles (``tests/deterministic/_*_py_oracle.py``,
content-hash-pinned below).

Both arms are driven with IDENTICAL BoardState inputs and stage constructor
args; the resulting ``state.grid`` is compared by full internal state -- the
trace and pad net-id arrays (via ``numpy.ndarray.tolist()``), the net
registration maps and the grid dimensions -- so the comparison is bit-exact
(``int32`` array cells and the net-id assignment ORDER, which the oracle and
port must both reproduce). The ``_grid_fence._EXPANSION_LOG`` side effect is
compared entry-for-entry between the arms, and every exclusion-zone /
fence warning printed text is captured and compared.

Error parity is covered for both stage-level error paths reachable from a
plain BoardState: ``ConfigError`` (an HV zone whose ``component_refdes`` is
absent, and the spatial fallback with no in-zone component) and
``FenceViolation`` (via a patched fence on BOTH arms -- the real fence only
fires on a genuinely non-conservative expansion, which the stage's own
expansion is not).

Anti-vacuity: ``test_oracle_and_port_are_different_implementations`` asserts
the shims resolve to the Rust pyfunctions (their ``run`` calls
``temper_orchestration``), not back onto the oracle. The oracle body digests
below are pinned: a differential whose oracle can be edited to agree with the
port proves nothing.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages import _grid_fence as _shim_fence
from temper_placer.deterministic.stages import _grid_hv as _shim_hv
from temper_placer.deterministic.stages import _grid_stage as _shim_grid_stage
from temper_placer.io.config_loader import HVExclusionZone

import tests.deterministic._grid_fence_py_oracle as _orc_fence
import tests.deterministic._grid_hv_py_oracle as _orc_hv
import tests.deterministic._grid_stage_py_oracle as _orc_grid_stage

# ---------------------------------------------------------------------------
# Oracle body pinning (G1)
# ---------------------------------------------------------------------------

_PINNED = {
    "_grid_core_py_oracle.py": "b92f58ee866ae92de07580a7311564fc2f20ef99e7f94fd8c34cc3f415127ed5",
    "_grid_hv_py_oracle.py": "f0e4621cd9dc81a056179465ab410e52a923d09eeadb36ba9d9742f185713197",
    "_grid_fence_py_oracle.py": "ab22dc57c2129d04f08e62b0fbdc79a74fa8d792532452c26bba003f970a8673",
    "_grid_stage_py_oracle.py": "60a346a3cccff402908b6b5385c6eb3b9c6a64fc11a70b913adf65b862c22531",
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
    """Anti-vacuity: the shims must delegate to the Rust pyfunctions."""
    assert _shim_grid_stage.ClearanceGridStage is not _orc_grid_stage.ClearanceGridStage
    assert _shim_hv.hv_pad_set is not _orc_hv.hv_pad_set
    assert _shim_fence.check_clearance_grid_conservatism is not _orc_fence.check_clearance_grid_conservatism
    assert _shim_fence.check_clearance_grid_perf_budget is not _orc_fence.check_clearance_grid_perf_budget
    # The shims' run()/function bodies call the temper_orchestration
    # pyfunctions -- the Rust port -- by bytecode name.
    assert "run_clearance_grid_stage" in _shim_grid_stage.ClearanceGridStage.run.__code__.co_names
    assert "run_hv_pad_set" in _shim_hv.hv_pad_set.__code__.co_names
    assert "run_grid_fence_check" in _shim_fence.check_clearance_grid_conservatism.__code__.co_names
    assert "run_grid_perf_budget" in _shim_fence.check_clearance_grid_perf_budget.__code__.co_names


# ---------------------------------------------------------------------------
# Bit-exact comparison canon
# ---------------------------------------------------------------------------

def _grid_canon(grid):
    """Project a ClearanceGrid onto its full internal state. The oracle's
    and the port's grids are different classes (``_grid_core_py_oracle`` vs
    the real ``_grid_core``), so attribute `==` cannot compare them; the
    canon extracts the int32 arrays (via ``tolist``), the dimensions and the
    net registration maps. The net-id map ALSO pins the registration order,
    which both arms must reproduce."""
    return (
        grid.width_mm,
        grid.height_mm,
        grid.cell_size_mm,
        grid.layer_count,
        grid.cols,
        grid.rows,
        tuple(grid._trace_net_ids[layer].tolist() for layer in range(grid.layer_count)),
        tuple(grid._pad_net_ids[layer].tolist() for layer in range(grid.layer_count)),
        tuple(sorted(dict(grid._net_to_id).items())),
        tuple(sorted(dict(grid._id_to_net).items())),
    )


def _fence_canon(violations) -> tuple:
    """Project fence violation dicts onto (ref, pin_name, layer, xy, reason)
    with floats carried bit-exactly via ``float.hex()``."""
    out = []
    for v in violations:
        x, y = v["xy"]
        out.append(
            (
                v["ref"],
                v["pin_name"],
                v["layer"],
                (x.hex(), y.hex()),
                v["reason"],
            )
        )
    return tuple(out)


# ---------------------------------------------------------------------------
# Corpus builders
# ---------------------------------------------------------------------------

def _make_pad_size(width: float, height: float, shape: str = "circle", rotation: float = 0.0):
    class _Size:
        def __init__(self, w, h):
            self.X = w
            self.Y = h

    class _Pad:
        def __init__(self, w, h, shape, rotation):
            self.size = _Size(w, h)
            self.shape = shape
            self.rotation = rotation

    return _Pad(width, height, shape, rotation)


def _pin(
    number="1",
    net="NET",
    shape="circle",
    layer="F.Cu",
    width=1.0,
    height=1.0,
    is_pth=False,
):
    return Pin(
        name=number,
        number=number,
        position=(0.0, 0.0),
        net=net,
        shape=shape,
        layer=layer,
        width=width,
        height=height,
        is_pth=is_pth,
    )


def _component(ref, *pins, initial_position=(10.0, 10.0), net_class="Signal"):
    return Component(
        ref=ref,
        footprint="FP",
        bounds=(5.0, 5.0),
        pins=list(pins),
        net_class=net_class,
        initial_position=initial_position,
    )


def _state(*components, board=Board(width=50.0, height=50.0), placements=frozenset()):
    nets = []
    for comp in components:
        for pin in comp.pins:
            if pin.net and not any(n.name == pin.net for n in nets):
                nets.append(
                    Net(
                        pin.net,
                        [(comp.ref, pin.name)],
                        net_class=comp.net_class or "Signal",
                    )
                )
    return BoardState(
        board=board,
        netlist=Netlist(components=list(components), nets=nets),
        placements=placements,
    )


def _run_both(stage_kwargs, state, capsys=None):
    """Run the oracle and the port stage with identical args; return
    (oracle_state, port_state) after comparing stdout."""
    orc = _orc_grid_stage.ClearanceGridStage(**stage_kwargs).run(state)
    orc_out = capsys.readouterr().out if capsys else ""
    port = _shim_grid_stage.ClearanceGridStage(**stage_kwargs).run(state)
    port_out = capsys.readouterr().out if capsys else ""
    if capsys:
        assert orc_out == port_out
    return orc, port


# ---------------------------------------------------------------------------
# ClearanceGridStage -- guards and trivial paths
# ---------------------------------------------------------------------------

def test_no_board_guard_identity() -> None:
    state = BoardState()
    orc = _orc_grid_stage.ClearanceGridStage().run(state)
    port = _shim_grid_stage.ClearanceGridStage().run(state)
    assert orc is state
    assert port is state
    assert orc.grid is None and port.grid is None


def test_board_without_netlist_produces_empty_grid() -> None:
    state = BoardState(board=Board(width=50.0, height=50.0))
    orc = _orc_grid_stage.ClearanceGridStage(cell_size_mm=0.5, layer_count=2).run(state)
    port = _shim_grid_stage.ClearanceGridStage(cell_size_mm=0.5, layer_count=2).run(state)
    assert _grid_canon(orc.grid) == _grid_canon(port.grid)
    assert port.grid.blocked_count == 0
    assert orc.grid.cols == port.grid.cols == 100


def test_empty_netlist() -> None:
    state = BoardState(board=Board(width=50.0, height=50.0), netlist=Netlist(components=[], nets=[]))
    orc = _orc_grid_stage.ClearanceGridStage().run(state)
    port = _shim_grid_stage.ClearanceGridStage().run(state)
    assert _grid_canon(orc.grid) == _grid_canon(port.grid)
    assert port.grid.blocked_count == 0


# ---------------------------------------------------------------------------
# ClearanceGridStage -- pad blocking
# ---------------------------------------------------------------------------

def test_circle_pad_blocking_with_pad_size() -> None:
    pin = _pin(net="HV", shape="circle", width=2.0, height=2.0)
    comp = _component("Q1", pin, initial_position=(25.0, 25.0), net_class="HighVoltage")
    state = _state(*((comp,)))
    kwargs = dict(
        cell_size_mm=0.5,
        layer_count=2,
        max_clearance_mm=0.2,
        net_class_clearances={"Signal": 0.2, "HighVoltage": 0.2},
        net_classes={"HV": "HighVoltage"},
        pth_mask_expansion_mm=0.0,
        smd_mask_expansion_mm=0.0,
        inner_layer_clearance_mm=0.2,
        default_trace_width_mm=0.0,
        pad_sizes={("Q1", "1"): _make_pad_size(2.0, 2.0, "circle")},
    )
    orc, port = _run_both(kwargs, state)
    assert _grid_canon(orc.grid) == _grid_canon(port.grid)
    assert port.grid.blocked_count > 0
    assert dict(port.grid._net_to_id) == {"HV": 1}


def test_rect_pad_blocking_rotation_0_and_90() -> None:
    pin0 = _pin(number="1", net="NET_A", shape="rect", layer="F.Cu", width=3.0, height=1.0)
    pin1 = _pin(number="2", net="NET_B", shape="rect", layer="B.Cu", width=1.0, height=3.0)
    comp = _component("U1", pin0, pin1, initial_position=(25.0, 25.0))
    nl = Netlist(
        components=[comp],
        nets=[
            Net("NET_A", [("U1", "1")], net_class="Signal"),
            Net("NET_B", [("U1", "2")], net_class="Signal"),
        ],
    )
    state = BoardState(board=Board(width=50.0, height=50.0), netlist=nl)

    kwargs = dict(
        cell_size_mm=0.5,
        layer_count=2,
        net_class_clearances={"Signal": 0.2},
        net_classes={},
        pth_mask_expansion_mm=0.0,
        smd_mask_expansion_mm=0.0,
        inner_layer_clearance_mm=0.2,
        default_trace_width_mm=0.0,
        pad_sizes={
            ("U1", "1"): _make_pad_size(3.0, 1.0, "rect", rotation=90.0),
            ("U1", "2"): _make_pad_size(1.0, 3.0, "rect"),
        },
    )
    orc, port = _run_both(kwargs, state)
    assert _grid_canon(orc.grid) == _grid_canon(port.grid)
    # 90-degree rotation swaps the rect dims for U1.1 (3x1 -> 1x3).
    assert port.grid.blocked_count > 0


def test_pth_pad_all_layers_and_mechanical_no_net() -> None:
    pth = _pin(number="1", net="NET_A", shape="circle", layer="F.Cu", width=2.0, height=2.0, is_pth=True)
    mech = _pin(number="2", net="", shape="circle", layer="F.Cu", width=1.0, height=1.0)
    comp = _component("U1", pth, mech, initial_position=(25.0, 25.0))
    nl = Netlist(
        components=[comp],
        nets=[Net("NET_A", [("U1", "1")], net_class="Signal")],
    )
    state = BoardState(board=Board(width=50.0, height=50.0), netlist=nl)
    kwargs = dict(
        cell_size_mm=0.5,
        layer_count=4,
        net_class_clearances={"Signal": 0.2},
        net_classes={},
        pth_mask_expansion_mm=0.15,
        smd_mask_expansion_mm=0.10,
        inner_layer_clearance_mm=0.5,
        default_trace_width_mm=0.25,
        pad_sizes={},
    )
    orc, port = _run_both(kwargs, state)
    assert _grid_canon(orc.grid) == _grid_canon(port.grid)
    # PTH pad blocked on all 4 layers; mechanical (empty-net) pad blocked
    # with zero clearance on F.Cu only.
    assert port.grid.blocked_count_on_layer(0) > 0
    assert port.grid.blocked_count_on_layer(1) > 0
    assert port.grid.blocked_count_on_layer(3) > 0


def test_placements_gate_which_components_are_processed() -> None:
    """The stage's `pos = placements_dict.get(component.ref, component.initial_position)`
    only gates whether a component's pads are processed at all; the pad
    position itself comes from `pin_world_position` (component.initial_position).
    A component absent from placements with `initial_position=None` is skipped;
    one present in placements with `initial_position=None` is NOT skipped."""
    pin_a = _pin(net="NET_A", shape="circle", layer="F.Cu", width=2.0, height=2.0)
    pin_b = _pin(net="NET_B", shape="circle", layer="F.Cu", width=2.0, height=2.0)
    comp_a = _component("U1", pin_a, initial_position=None)
    comp_b = _component("U2", pin_b, initial_position=None)
    nl = Netlist(
        components=[comp_a, comp_b],
        nets=[
            Net("NET_A", [("U1", "1")], net_class="Signal"),
            Net("NET_B", [("U2", "1")], net_class="Signal"),
        ],
    )
    state = BoardState(
        board=Board(width=50.0, height=50.0),
        netlist=nl,
        placements=frozenset({("U1", (40.0, 40.0))}),
    )
    kwargs = dict(
        cell_size_mm=0.5,
        layer_count=2,
        net_class_clearances={"Signal": 0.2},
        net_classes={},
        pth_mask_expansion_mm=0.0,
        smd_mask_expansion_mm=0.0,
        inner_layer_clearance_mm=0.2,
        default_trace_width_mm=0.0,
        pad_sizes={},
    )
    orc, port = _run_both(kwargs, state)
    assert _grid_canon(orc.grid) == _grid_canon(port.grid)
    # U1 is processed (pad at the origin fallback); U2 is skipped entirely.
    assert port.grid.blocked_count > 0
    assert port.grid.is_available(0.25, 0.25, layer=0) is False
    assert dict(port.grid._net_to_id) == {"NET_A": 1}


# ---------------------------------------------------------------------------
# ClearanceGridStage -- HV creepage expansion pass + fence
# ---------------------------------------------------------------------------

def test_hv_expansion_circle_pad_with_explicit_refdes() -> None:
    pin = _pin(net="HV", shape="circle", width=2.0, height=2.0)
    comp = _component("Q1", pin, initial_position=(25.0, 25.0), net_class="HighVoltage")
    nl = Netlist(components=[comp], nets=[Net("HV", [("Q1", "1")], net_class="HighVoltage")])
    state = BoardState(board=Board(width=50.0, height=50.0), netlist=nl)
    kwargs = dict(
        cell_size_mm=0.5,
        layer_count=2,
        max_clearance_mm=0.2,
        net_class_clearances={"Signal": 0.2, "HighVoltage": 0.2},
        net_classes={},
        pth_mask_expansion_mm=0.0,
        smd_mask_expansion_mm=0.0,
        inner_layer_clearance_mm=0.2,
        default_trace_width_mm=0.0,
        pad_sizes={("Q1", "1"): _make_pad_size(2.0, 2.0, "circle")},
        hv_exclusion_zones=[
            HVExclusionZone(
                name="q1_zone",
                center=(25.0, 25.0),
                size=(10.0, 10.0),
                clearance_mm=6.0,
                component_refdes="Q1",
            )
        ],
    )
    orc, port = _run_both(kwargs, state)
    assert _grid_canon(orc.grid) == _grid_canon(port.grid)
    # Expansion: blocked radius is pad_radius + 6.0 = 7.0 (not 1.2).
    assert port.grid.is_available(25.0 + 5.0, 25.0, layer=0) is False
    # The expansion log carries exactly one entry for the HV pad on layer 0.
    assert len(list(_shim_fence._EXPANSION_LOG)) == 1
    assert _shim_fence._EXPANSION_LOG == _orc_fence._EXPANSION_LOG
    entry = _shim_fence._EXPANSION_LOG[0]
    assert entry[0] == "Q1" and entry[1] == "1" and entry[2] == 0
    assert len(entry) == 9


def test_hv_expansion_spatial_fallback_and_inner_layer() -> None:
    """A zone without component_refdes resolves to the closest in-zone
    component; the HV pad on an inner layer gets the reduced creepage
    factor (6.0 * 0.30 = 1.8)."""
    pin = _pin(net="HV", shape="circle", layer="In1.Cu", width=2.0, height=2.0)
    comp = _component("Q1", pin, initial_position=(25.0, 25.0), net_class="HighVoltage")
    nl = Netlist(components=[comp], nets=[Net("HV", [("Q1", "1")], net_class="HighVoltage")])
    state = BoardState(board=Board(width=50.0, height=50.0), netlist=nl)
    kwargs = dict(
        cell_size_mm=0.5,
        layer_count=4,
        max_clearance_mm=0.2,
        net_class_clearances={"Signal": 0.2, "HighVoltage": 0.2},
        net_classes={},
        pth_mask_expansion_mm=0.0,
        smd_mask_expansion_mm=0.0,
        inner_layer_clearance_mm=0.5,
        default_trace_width_mm=0.0,
        pad_sizes={("Q1", "1"): _make_pad_size(2.0, 2.0, "circle")},
        hv_exclusion_zones=[
            HVExclusionZone(
                name="q1_zone",
                center=(25.0, 25.0),
                size=(10.0, 10.0),
                clearance_mm=6.0,
            )
        ],
    )
    orc, port = _run_both(kwargs, state)
    assert _grid_canon(orc.grid) == _grid_canon(port.grid)
    assert _shim_fence._EXPANSION_LOG == _orc_fence._EXPANSION_LOG
    # Inner layer: threshold = 1.0 + 1.8 = 2.8; layer 0 untouched.
    assert port.grid.is_available(25.0 + 2.5, 25.0, layer=1) is False
    assert port.grid.is_available(25.0 + 2.5, 25.0, layer=0) is True
    assert _shim_fence._EXPANSION_LOG[0][7] == pytest.approx(1.8)


def test_hv_expansion_rect_pad() -> None:
    pin = _pin(net="HV", shape="rect", width=2.0, height=1.0)
    comp = _component("U1", pin, initial_position=(25.0, 25.0), net_class="HighVoltage")
    nl = Netlist(components=[comp], nets=[Net("HV", [("U1", "1")], net_class="HighVoltage")])
    state = BoardState(board=Board(width=50.0, height=50.0), netlist=nl)
    kwargs = dict(
        cell_size_mm=0.5,
        layer_count=2,
        max_clearance_mm=0.2,
        net_class_clearances={"Signal": 0.2, "HighVoltage": 0.2},
        net_classes={},
        pth_mask_expansion_mm=0.0,
        smd_mask_expansion_mm=0.0,
        inner_layer_clearance_mm=0.2,
        default_trace_width_mm=0.0,
        pad_sizes={("U1", "1"): _make_pad_size(2.0, 1.0, "rect")},
        hv_exclusion_zones=[
            HVExclusionZone(
                name="u1_zone",
                center=(25.0, 25.0),
                size=(10.0, 10.0),
                clearance_mm=6.0,
                component_refdes="U1",
            )
        ],
    )
    orc, port = _run_both(kwargs, state)
    assert _grid_canon(orc.grid) == _grid_canon(port.grid)
    assert _shim_fence._EXPANSION_LOG == _orc_fence._EXPANSION_LOG
    assert _shim_fence._EXPANSION_LOG[0][4] == "rect"


# ---------------------------------------------------------------------------
# ClearanceGridStage -- HV exclusion zones (EXP-13)
# ---------------------------------------------------------------------------

def test_exclusion_zones_block_net_ids_with_prints(capsys) -> None:
    pin = _pin(net="GATE_H", shape="circle", layer="F.Cu", width=1.0, height=1.0)
    comp = _component("Q1", pin, initial_position=(25.0, 25.0), net_class="Signal")
    nl = Netlist(components=[comp], nets=[Net("GATE_H", [("Q1", "1")], net_class="Signal")])
    state = BoardState(board=Board(width=50.0, height=50.0), netlist=nl)
    kwargs = dict(
        cell_size_mm=0.5,
        layer_count=2,
        net_class_clearances={"Signal": 0.2},
        net_classes={},
        pth_mask_expansion_mm=0.0,
        smd_mask_expansion_mm=0.0,
        inner_layer_clearance_mm=0.2,
        default_trace_width_mm=0.0,
        pad_sizes={},
        hv_exclusion_zones=[
            HVExclusionZone(
                name="hv_z",
                center=(10.0, 10.0),
                size=(8.0, 6.0),
                clearance_mm=6.0,
                excluded_nets=["GATE_H"],
                component_refdes="Q1",
            )
        ],
    )
    orc, port = _run_both(kwargs, state, capsys=capsys)
    assert _grid_canon(orc.grid) == _grid_canon(port.grid)
    # The exclusion zone registers GATE_H in the net map (in zone order).
    assert dict(port.grid._net_to_id) == {"GATE_H": 1}
    # The zone (centered 10,10, 8x6) is blocked with net_id -2 inside.
    assert port.grid.is_available(10.0, 10.0, layer=0) is False
    # And far away the cell is free (only the pad block at 25,25).
    assert port.grid.is_available(35.0, 35.0, layer=0) is True


# ---------------------------------------------------------------------------
# ClearanceGridStage -- error parity
# ---------------------------------------------------------------------------

def test_config_error_unknown_refdes_parity() -> None:
    pin = _pin(net="HV", shape="circle", width=2.0, height=2.0)
    comp = _component("Q1", pin, initial_position=(25.0, 25.0), net_class="HighVoltage")
    nl = Netlist(components=[comp], nets=[Net("HV", [("Q1", "1")], net_class="HighVoltage")])
    state = BoardState(board=Board(width=50.0, height=50.0), netlist=nl)
    kwargs = dict(
        cell_size_mm=0.5,
        layer_count=2,
        net_class_clearances={"Signal": 0.2, "HighVoltage": 0.2},
        net_classes={},
        pth_mask_expansion_mm=0.0,
        smd_mask_expansion_mm=0.0,
        inner_layer_clearance_mm=0.2,
        default_trace_width_mm=0.0,
        pad_sizes={},
        hv_exclusion_zones=[
            HVExclusionZone(
                name="bad_zone",
                center=(25.0, 25.0),
                size=(10.0, 10.0),
                clearance_mm=6.0,
                component_refdes="Q99",
            )
        ],
    )
    with pytest.raises(Exception) as orc_exc:
        _orc_grid_stage.ClearanceGridStage(**kwargs).run(state)
    with pytest.raises(Exception) as port_exc:
        _shim_grid_stage.ClearanceGridStage(**kwargs).run(state)
    assert type(orc_exc.value).__name__ == type(port_exc.value).__name__ == "ConfigError"
    assert str(orc_exc.value) == str(port_exc.value)
    assert "Q99" in str(port_exc.value)


def test_config_error_spatial_fallback_no_component_parity() -> None:
    pin = _pin(net="HV", shape="circle", width=2.0, height=2.0)
    comp = _component("Q1", pin, initial_position=(25.0, 25.0), net_class="HighVoltage")
    nl = Netlist(components=[comp], nets=[Net("HV", [("Q1", "1")], net_class="HighVoltage")])
    state = BoardState(board=Board(width=50.0, height=50.0), netlist=nl)
    kwargs = dict(
        cell_size_mm=0.5,
        layer_count=2,
        net_class_clearances={"Signal": 0.2, "HighVoltage": 0.2},
        net_classes={},
        pth_mask_expansion_mm=0.0,
        smd_mask_expansion_mm=0.0,
        inner_layer_clearance_mm=0.2,
        default_trace_width_mm=0.0,
        pad_sizes={},
        hv_exclusion_zones=[
            HVExclusionZone(
                name="orphan",
                center=(100.0, 100.0),
                size=(5.0, 5.0),
                clearance_mm=6.0,
            )
        ],
    )
    with pytest.raises(Exception) as orc_exc:
        _orc_grid_stage.ClearanceGridStage(**kwargs).run(state)
    with pytest.raises(Exception) as port_exc:
        _shim_grid_stage.ClearanceGridStage(**kwargs).run(state)
    assert type(orc_exc.value).__name__ == type(port_exc.value).__name__ == "ConfigError"
    assert str(orc_exc.value) == str(port_exc.value)
    assert "orphan" in str(port_exc.value)


def test_fence_violation_parity(monkeypatch) -> None:
    """Both arms raise FenceViolation with the identical message when the
    fence reports a violation (patched on BOTH arms: the oracle calls the
    oracle module's function, the port calls the real ``_grid_fence``
    module's function at runtime)."""
    pin = _pin(net="HV", shape="circle", width=2.0, height=2.0)
    comp = _component("Q1", pin, initial_position=(25.0, 25.0), net_class="HighVoltage")
    nl = Netlist(components=[comp], nets=[Net("HV", [("Q1", "1")], net_class="HighVoltage")])
    state = BoardState(board=Board(width=50.0, height=50.0), netlist=nl)
    kwargs = dict(
        cell_size_mm=0.5,
        layer_count=2,
        net_class_clearances={"Signal": 0.2, "HighVoltage": 0.2},
        net_classes={},
        pth_mask_expansion_mm=0.0,
        smd_mask_expansion_mm=0.0,
        inner_layer_clearance_mm=0.2,
        default_trace_width_mm=0.0,
        pad_sizes={},
        hv_exclusion_zones=[
            HVExclusionZone(
                name="q1_zone",
                center=(25.0, 25.0),
                size=(10.0, 10.0),
                clearance_mm=6.0,
                component_refdes="Q1",
            )
        ],
    )

    def _always_violate(_grid, _log):
        return [
            {
                "ref": "Q1",
                "pin_name": "1",
                "layer": 0,
                "xy": (31.75, 25.0),
                "reason": "cell at (31.750, 25.000) on layer 0 is unblocked but "
                "should be inside the expanded creepage boundary for "
                "pad Q1.1",
            }
        ]

    monkeypatch.setattr(_shim_fence, "check_clearance_grid_conservatism", _always_violate)
    monkeypatch.setattr(_orc_fence, "check_clearance_grid_conservatism", _always_violate)

    with pytest.raises(Exception) as orc_exc:
        _orc_grid_stage.ClearanceGridStage(**kwargs).run(state)
    with pytest.raises(Exception) as port_exc:
        _shim_grid_stage.ClearanceGridStage(**kwargs).run(state)
    assert type(orc_exc.value).__name__ == type(port_exc.value).__name__ == "FenceViolation"
    assert str(orc_exc.value) == str(port_exc.value)
    assert "Q1" in str(port_exc.value) and "layer 0" in str(port_exc.value)


# ---------------------------------------------------------------------------
# _grid_hv.hv_pad_set (thin FFI delegation)
# ---------------------------------------------------------------------------

def test_hv_pad_set_explicit_refdes_differential() -> None:
    pads = [
        {"ref": "Q1", "name": "G"},
        {"ref": "Q1", "name": "D"},
        {"ref": "R1", "name": "1"},
    ]
    zones = [
        type(
            "Z",
            (),
            {"component_refdes": "Q1", "center": (0.0, 0.0), "size": (1.0, 1.0), "name": "z"},
        )()
    ]
    positions = {"Q1": (10.0, 10.0), "R1": (20.0, 20.0)}
    assert _shim_hv.hv_pad_set(pads, zones, positions) == _orc_hv.hv_pad_set(pads, zones, positions)
    assert _shim_hv.hv_pad_set(pads, zones, positions) == {("Q1", "G"), ("Q1", "D")}


def test_hv_pad_set_spatial_fallback_differential() -> None:
    pads = [
        {"ref": "Q1", "name": "G"},
        {"ref": "Q1", "name": "D"},
        {"ref": "R1", "name": "1"},
    ]
    zones = [
        type(
            "Z",
            (),
            {"component_refdes": None, "center": (10.0, 10.0), "size": (6.0, 6.0), "name": "z"},
        )()
    ]
    positions = {"Q1": (10.0, 10.0), "R1": (40.0, 40.0)}
    assert _shim_hv.hv_pad_set(pads, zones, positions) == _orc_hv.hv_pad_set(pads, zones, positions)
    assert _shim_hv.hv_pad_set(pads, zones, positions) == {("Q1", "G"), ("Q1", "D")}


def test_hv_pad_set_config_error_parity() -> None:
    pads = [{"ref": "Q1", "name": "G"}]
    zones = [
        type(
            "Z",
            (),
            {"component_refdes": "Q99", "center": (0.0, 0.0), "size": (1.0, 1.0), "name": "z"},
        )()
    ]
    with pytest.raises(Exception) as orc_exc:
        _orc_hv.hv_pad_set(pads, zones, {"Q1": (10.0, 10.0)})
    with pytest.raises(Exception) as port_exc:
        _shim_hv.hv_pad_set(pads, zones, {"Q1": (10.0, 10.0)})
    assert type(orc_exc.value).__name__ == type(port_exc.value).__name__ == "ConfigError"
    assert str(orc_exc.value) == str(port_exc.value)


# ---------------------------------------------------------------------------
# _grid_fence checks (thin FFI delegations)
# ---------------------------------------------------------------------------

def _build_same_grid_pair():
    """Run both arms' stages on the same HV-circle input and return the
    (oracle_grid, oracle_log, port_grid, port_log) four-tuple."""
    pin = _pin(net="HV", shape="circle", width=2.0, height=2.0)
    comp = _component("Q1", pin, initial_position=(25.0, 25.0), net_class="HighVoltage")
    nl = Netlist(components=[comp], nets=[Net("HV", [("Q1", "1")], net_class="HighVoltage")])
    state = BoardState(board=Board(width=50.0, height=50.0), netlist=nl)
    kwargs = dict(
        cell_size_mm=0.5,
        layer_count=2,
        max_clearance_mm=0.2,
        net_class_clearances={"Signal": 0.2, "HighVoltage": 0.2},
        net_classes={},
        pth_mask_expansion_mm=0.0,
        smd_mask_expansion_mm=0.0,
        inner_layer_clearance_mm=0.2,
        default_trace_width_mm=0.0,
        pad_sizes={("Q1", "1"): _make_pad_size(2.0, 2.0, "circle")},
        hv_exclusion_zones=[
            HVExclusionZone(
                name="q1_zone",
                center=(25.0, 25.0),
                size=(10.0, 10.0),
                clearance_mm=6.0,
                component_refdes="Q1",
            )
        ],
    )
    orc = _orc_grid_stage.ClearanceGridStage(**kwargs).run(state)
    port = _shim_grid_stage.ClearanceGridStage(**kwargs).run(state)
    return orc.grid, list(_orc_fence._EXPANSION_LOG), port.grid, list(_shim_fence._EXPANSION_LOG)


def test_fence_passes_on_built_grid_both_arms() -> None:
    orc_grid, orc_log, port_grid, port_log = _build_same_grid_pair()
    assert _shim_fence.check_clearance_grid_conservatism(port_grid) == []
    assert _orc_fence.check_clearance_grid_conservatism(orc_grid) == []
    assert len(orc_log) == len(port_log) == 1


def test_fence_violation_differential_with_poked_hole() -> None:
    """Poke the same sample cell in both grids; the violation dicts
    (including the ``:.3f`` reason strings) must match bit-exactly."""
    orc_grid, orc_log, port_grid, port_log = _build_same_grid_pair()
    assert len(orc_log) == 1 and len(port_log) == 1
    entry = orc_log[0]
    (_ref, _pin, layer_idx, pos, _shape, pad_radius, _size, eff_creep, _cells) = entry
    cell = orc_grid.cell_size_mm
    sample_x = pos[0] + pad_radius + eff_creep - cell / 2.0
    sample_y = pos[1]
    row = int(sample_y / cell)
    col = int(sample_x / cell)
    for grid, log in ((orc_grid, orc_log), (port_grid, port_log)):
        grid._trace_net_ids[layer_idx][row, col] = 0
        grid._invalidate_cache()

    orc_violations = _orc_fence.check_clearance_grid_conservatism(orc_grid, orc_log)
    port_violations = _shim_fence.check_clearance_grid_conservatism(port_grid, port_log)
    assert orc_violations, "poked cell must be reported by the oracle fence"
    assert port_violations, "poked cell must be reported by the port fence"
    assert _fence_canon(orc_violations) == _fence_canon(port_violations)


def test_perf_budget_differential() -> None:
    cases = [
        (20.0, 50.0, 20.0, 50.0),   # over budget: 40% > 20%, above floor
        (5.0, 100.0, 20.0, 50.0),   # within budget
        (10.0, 20.0, 20.0, 50.0),   # below floor -> exempt
        (0.0, 0.0, 20.0, 50.0),     # zero/zero, below floor
        (60.0, 100.0, 50.0, 10.0),  # 60% > 50%, floor low
    ]
    for fence, stage, budget, floor in cases:
        orc = _orc_fence.check_clearance_grid_perf_budget(
            fence_elapsed_ms=fence, stage_elapsed_ms=stage, budget_pct=budget, floor_ms=floor
        )
        port = _shim_fence.check_clearance_grid_perf_budget(
            fence_elapsed_ms=fence, stage_elapsed_ms=stage, budget_pct=budget, floor_ms=floor
        )
        assert port == orc, f"mismatch for ({fence}, {stage}, {budget}, {floor})"
    # A message-bearing case pins the `:.1f` formatting bit-exactly.
    orc = _orc_fence.check_clearance_grid_perf_budget(
        fence_elapsed_ms=33.333, stage_elapsed_ms=100.0, budget_pct=20.0, floor_ms=1.0
    )
    port = _shim_fence.check_clearance_grid_perf_budget(
        fence_elapsed_ms=33.333, stage_elapsed_ms=100.0, budget_pct=20.0, floor_ms=1.0
    )
    assert port == orc
    assert orc == (True, "fence overhead 33.3% exceeds budget 20.0% "
                         "(fence=33.3ms, stage=100.0ms)")


# ---------------------------------------------------------------------------
# Pipeline chain
# ---------------------------------------------------------------------------

def test_grid_stage_chain_identical() -> None:
    """zone_geometry -> zone_assignment -> slot_generation -> clearance_grid
    on both arms; the chained state matches field-for-field and the grids
    match bit-exactly."""
    from temper_placer.deterministic.stages import (
        slot_generation as _shim_slot_generation,
    )
    from temper_placer.deterministic.stages import (
        zone_assignment as _shim_zone_assignment,
    )
    from temper_placer.deterministic.stages import (
        zone_geometry as _shim_zone_geometry,
    )

    import tests.deterministic._slot_generation_py_oracle as _orc_slot_generation
    import tests.deterministic._zone_assignment_py_oracle as _orc_zone_assignment
    import tests.deterministic._zone_geometry_py_oracle as _orc_zone_geometry

    board = Board(width=120.5, height=80.0)
    refs = ("Q1", "C1", "U_MCU1", "R1")

    comps, nets = [], []
    for i, ref in enumerate(refs):
        net = {"Q1": "AC_L", "C1": "VBUS", "U_MCU1": "3V3", "R1": "SENSE"}[ref]
        nc = {"Q1": "HighVoltage", "C1": "Power", "U_MCU1": "Signal", "R1": "Signal"}[ref]
        pin = Pin("1", "1", (0.0, 0.0), net=net, width=2.0, height=2.0, shape="circle")
        comps.append(
            Component(
                ref=ref,
                footprint="FP",
                bounds=(2.0, 2.0),
                pins=[pin],
                net_class=nc,
                initial_position=(15.0 * i + 10.0, 40.0),
            )
        )
        nets.append(Net(net, [(ref, "1")], net_class=nc))
    netlist = Netlist(components=comps, nets=nets)

    def chain(shim_zg, shim_za, shim_sg, shim_cg):
        state = shim_zg.ZoneGeometryStage().run(BoardState(board=board, netlist=netlist))
        state = shim_za.ZoneAssignmentStage().run(state)
        state = shim_sg.SlotGenerationStage(slot_spacing_mm=7.5).run(state)
        return shim_cg.ClearanceGridStage(
            cell_size_mm=0.5,
            layer_count=2,
            net_class_clearances={"Signal": 0.2, "HighVoltage": 0.2, "Power": 0.2},
            net_classes={},
            pth_mask_expansion_mm=0.0,
            smd_mask_expansion_mm=0.0,
            inner_layer_clearance_mm=0.2,
            default_trace_width_mm=0.0,
            pad_sizes={},
        ).run(state)

    orc_state = chain(_orc_zone_geometry, _orc_zone_assignment, _orc_slot_generation, _orc_grid_stage)
    port_state = chain(_shim_zone_geometry, _shim_zone_assignment, _shim_slot_generation, _shim_grid_stage)
    assert {z.name for z in port_state.zones} == {"HV", "Power", "Signal", "MCU"}
    assert _grid_canon(orc_state.grid) == _grid_canon(port_state.grid)
