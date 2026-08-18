"""
Tests for gate-drive-loop trace-geometry measurement (U2: gate_drive.py).

Validates the topology walk (``_walk_forward``/``_find_switch``/
``_pick_return_net``) against synthetic ``Netlist``s built from the real
data shapes observed on the production board (see the module docstring
in ``physics/gate_drive.py`` for the full rationale): a direct
driver-to-switch net (matches the real board's low-side loop, U5), a
loop split by a series gate resistor (matches the real board's high-side
loop, U4 + R18), ambiguous/absent cases (fail-closed to ``None``), and
the area/spacing geometry helpers.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from temper_placer.core.netlist import Component, Netlist, Pin
from temper_placer.physics.gate_drive import (
    _find_switch,
    _hull_area,
    _min_spacing,
    _pick_return_net,
    _walk_forward,
    gate_drive_loop_area,
    gate_drive_spacing,
)


@dataclass
class _FakeTrace:
    start: tuple[float, float]
    end: tuple[float, float]
    net: str | None = None


def _pin(name: str, net: str | None, pos: tuple[float, float] = (0.0, 0.0)) -> Pin:
    return Pin(name=name, number=name, position=pos, net=net)


def _switch(ref: str, gate_net: str, other_nets: tuple[str, str], footprint: str = "Package_TO_SOT_THT:TO-247-3_Vertical") -> Component:
    return Component(
        ref=ref,
        footprint=footprint,
        bounds=(5.0, 5.0),
        pins=[
            _pin("1", gate_net),
            _pin("2", other_nets[0]),
            _pin("3", other_nets[1]),
        ],
    )


def _resistor(ref: str, net_a: str, net_b: str) -> Component:
    return Component(
        ref=ref,
        footprint="Resistor_SMD:R_0603_1608Metric",
        bounds=(1.0, 0.5),
        pins=[_pin("1", net_a), _pin("2", net_b)],
    )


def _driver(ref: str, gate_net: str, extra_nets: tuple[str, ...] = ()) -> Component:
    pins = [_pin("1", gate_net)]
    pins += [_pin(str(i + 2), n) for i, n in enumerate(extra_nets)]
    return Component(
        ref=ref,
        footprint="lib:SOIC16W_Isolated",
        bounds=(10.0, 10.0),
        pins=pins,
    )


# ---------------------------------------------------------------------------
# _find_switch
# ---------------------------------------------------------------------------


def test_find_switch_matches_to247_footprint():
    switch = _switch("U4", "GATE_HS", ("+170V_BUS", "SW_NODE"))
    netlist = Netlist(components=[switch])
    found = _find_switch(netlist, {"GATE_HS"})
    assert found is not None
    assert found.ref == "U4"


def test_find_switch_ignores_non_power_footprint():
    driver = _driver("U6", "GATE_HS")
    netlist = Netlist(components=[driver])
    assert _find_switch(netlist, {"GATE_HS"}) is None


def test_find_switch_ambiguous_returns_none():
    a = _switch("U4", "GATE_HS", ("+170V_BUS", "SW_NODE"))
    b = _switch("U9", "GATE_HS", ("+170V_BUS", "OTHER"))
    netlist = Netlist(components=[a, b])
    assert _find_switch(netlist, {"GATE_HS"}) is None


# ---------------------------------------------------------------------------
# _walk_forward -- direct (matches the real board's low-side loop, U5)
# ---------------------------------------------------------------------------


def test_walk_forward_direct_switch_on_gate_net():
    switch = _switch("U5", "GATE_LS", ("SW_NODE", "hb-gnd"))
    netlist = Netlist(components=[switch])
    result = _walk_forward(netlist, "GATE_LS")
    assert result is not None
    forward_nets, found = result
    assert forward_nets == {"GATE_LS"}
    assert found.ref == "U5"


# ---------------------------------------------------------------------------
# _walk_forward -- one resistor hop (matches the real board's high-side
# loop, R18 bridging GATE_HS -> hb.power_loop.q_high-g -> U4)
# ---------------------------------------------------------------------------


def test_walk_forward_through_series_resistor():
    r18 = _resistor("R18", "GATE_HS", "hb.power_loop.q_high-g")
    u4 = _switch("U4", "hb.power_loop.q_high-g", ("+170V_BUS", "SW_NODE"))
    netlist = Netlist(components=[r18, u4])
    result = _walk_forward(netlist, "GATE_HS")
    assert result is not None
    forward_nets, found = result
    assert forward_nets == {"GATE_HS", "hb.power_loop.q_high-g"}
    assert found.ref == "U4"


def test_walk_forward_does_not_cross_a_second_series_resistor_once_switch_found():
    """R19 (gate-net -> SW_NODE) must not be treated as a further forward
    hop once the switch is already found on the same net -- it is the
    return-path pulldown, not part of the "go" chain."""
    r18 = _resistor("R18", "GATE_HS", "hb.power_loop.q_high-g")
    r19 = _resistor("R19", "hb.power_loop.q_high-g", "SW_NODE")
    u4 = _switch("U4", "hb.power_loop.q_high-g", ("+170V_BUS", "SW_NODE"))
    netlist = Netlist(components=[r18, r19, u4])
    result = _walk_forward(netlist, "GATE_HS")
    assert result is not None
    forward_nets, found = result
    assert "SW_NODE" not in forward_nets
    assert found.ref == "U4"


def test_walk_forward_exhausted_returns_none():
    """A gate net with no reachable switch (e.g. a broken/unrouted stub)
    fails closed rather than reporting a fake measurement."""
    netlist = Netlist(components=[])
    assert _walk_forward(netlist, "GATE_HS") is None


def test_walk_forward_stops_extending_at_non_rl_component():
    """A non-R/L 2-pin component must not be treated as a forward hop."""
    diode = Component(
        ref="D1",
        footprint="D_SOD-123",
        bounds=(1.0, 0.5),
        pins=[_pin("1", "GATE_HS"), _pin("2", "SOME_OTHER_NET")],
    )
    netlist = Netlist(components=[diode])
    assert _walk_forward(netlist, "GATE_HS") is None


# ---------------------------------------------------------------------------
# _pick_return_net
# ---------------------------------------------------------------------------


def test_pick_return_net_prefers_gnd_named_net():
    switch = _switch("U5", "GATE_LS", ("SW_NODE", "hb-gnd"))
    assert _pick_return_net(switch, {"GATE_LS"}) == "hb-gnd"


def test_pick_return_net_falls_back_to_non_supply_net():
    switch = _switch("U4", "hb.power_loop.q_high-g", ("+170V_BUS", "SW_NODE"))
    assert _pick_return_net(switch, {"GATE_HS", "hb.power_loop.q_high-g"}) == "SW_NODE"


def test_pick_return_net_ambiguous_two_gnd_like_nets_returns_none():
    switch = _switch("U9", "GATE_X", ("hb-gnd", "DC_BUS_RTN"))
    assert _pick_return_net(switch, {"GATE_X"}) is None


def test_pick_return_net_ambiguous_two_non_supply_nets_returns_none():
    switch = _switch("U9", "GATE_X", ("SW_NODE", "OTHER_SIGNAL"))
    assert _pick_return_net(switch, {"GATE_X"}) is None


def test_pick_return_net_no_remaining_nets_returns_none():
    switch = Component(
        ref="U9",
        footprint="Package_TO_SOT_THT:TO-247-3_Vertical",
        bounds=(5.0, 5.0),
        pins=[_pin("1", "GATE_X")],
    )
    assert _pick_return_net(switch, {"GATE_X"}) is None


# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------


def test_hull_area_needs_at_least_three_points():
    go = [_FakeTrace((0.0, 0.0), (1.0, 0.0), net="GATE_HS")]
    ret = [_FakeTrace((0.0, 0.0), (1.0, 0.0), net="SW_NODE")]
    assert _hull_area(go, ret) is None


def test_hull_area_rectangle():
    go = [_FakeTrace((0.0, 0.0), (10.0, 0.0), net="GATE_HS")]
    ret = [_FakeTrace((0.0, 5.0), (10.0, 5.0), net="SW_NODE")]
    area = _hull_area(go, ret)
    assert area is not None
    assert area == pytest.approx(50.0, rel=1e-3)


def test_min_spacing_basic():
    go = [_FakeTrace((0.0, 0.0), (10.0, 0.0), net="GATE_HS")]
    ret = [_FakeTrace((0.0, 3.0), (10.0, 3.0), net="SW_NODE")]
    spacing = _min_spacing(go, ret)
    assert spacing is not None
    assert spacing == pytest.approx(3.0, rel=1e-3)


def test_min_spacing_empty_arm_returns_none():
    go = [_FakeTrace((0.0, 0.0), (10.0, 0.0), net="GATE_HS")]
    assert _min_spacing(go, []) is None


# ---------------------------------------------------------------------------
# public entry points -- fail-closed on missing/unparseable pcb
# ---------------------------------------------------------------------------


def test_gate_drive_loop_area_nonexistent_pcb():
    from pathlib import Path

    assert gate_drive_loop_area(Path("/nonexistent/x.kicad_pcb"), "GATE_HS") is None


def test_gate_drive_spacing_nonexistent_pcb():
    from pathlib import Path

    assert gate_drive_spacing(Path("/nonexistent/x.kicad_pcb"), "GATE_HS") is None
