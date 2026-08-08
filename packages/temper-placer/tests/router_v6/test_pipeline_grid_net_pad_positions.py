"""Regression test for _pipeline_grid._net_pad_positions' rotation handling.

Measured on ``pcb/temper.kicad_pcb``: 148 of 169 components (87.6%) have a
nonzero ``initial_rotation``. ``_net_pad_positions`` used to compute a pin's
world position as ``comp.initial_position + pin.position`` directly --
``pin.position`` is the pad's LOCAL, pre-rotation offset (see
``parse_engine.rs``: stored pad-centroid-relative, rotation applied
separately), so this was only correct for a component at rotation index 0.

This is the actual, empirically-confirmed live mechanism behind the
wrong-pad-terminal defect under the production ``--net-batching``
configuration: ``fallback_channel_path`` sets a 2-pad net's
``waypoints = pads`` directly, and ``pads`` came from this function. A
direct scan of every 2-pad net on the real board found 28 of 49 whose
pre-fix pad position landed exactly on a DIFFERENT net's real pad --
``GATE_HS``/R23 among them, the exact shape
docs/evidence/2026-08-08-nlayer-via-astar-spike.md cites.
"""

from __future__ import annotations

from temper_placer.core.netlist import Component, Net, Pin
from temper_placer.router_v6._pipeline_grid import _net_pad_positions


def _rotated_two_pin_component(ref: str, position: tuple[float, float], rotation_index: int) -> Component:
    """A 2-pin component (like a resistor) with pins on its local X axis,
    at the given board position and rotation index (0-3 -> 0/90/180/270deg)."""
    pins = [
        Pin(
            name="1",
            number="1",
            position=(-2.5, 0.0),
            net=f"{ref}_NET_A",
            width=1.0,
            height=1.0,
            shape="rect",
            layer="F.Cu",
        ),
        Pin(
            name="2",
            number="2",
            position=(2.5, 0.0),
            net=f"{ref}_NET_B",
            width=1.0,
            height=1.0,
            shape="rect",
            layer="F.Cu",
        ),
    ]
    return Component(
        ref=ref,
        footprint="R_0805",
        bounds=(2.0, 1.25),
        pins=pins,
        initial_position=position,
        initial_rotation=rotation_index,
    )


def test_net_pad_positions_applies_component_rotation():
    """A component rotated 90 degrees must have its pin offset rotated too --
    not left on the component's local X axis, which becomes the board's Y
    axis once the component is turned 90 degrees."""
    comp = _rotated_two_pin_component("R1", (50.0, 50.0), rotation_index=1)
    comp_by_ref = {"R1": comp}
    net = Net(name="R1_NET_B", pins=[("R1", "2")])

    positions = _net_pad_positions(net, comp_by_ref)

    assert len(positions) == 1
    x, y = positions[0]
    # Rotated 90 degrees: the pin's local +2.5mm-on-X offset becomes a
    # +/-2.5mm-on-Y offset from the component center, NOT an X offset.
    assert abs(x - 50.0) < 1e-6, f"pin must stay on the component's X center once rotated, got x={x}"
    assert abs(abs(y - 50.0) - 2.5) < 1e-6, f"pin must move along Y once rotated 90deg, got y={y}"


def test_net_pad_positions_unrotated_component_is_unaffected():
    """Sanity: rotation index 0 (the common case the pre-fix bug happened to
    get right) must still work after the fix."""
    comp = _rotated_two_pin_component("R2", (10.0, 10.0), rotation_index=0)
    comp_by_ref = {"R2": comp}
    net = Net(name="R2_NET_A", pins=[("R2", "1")])

    positions = _net_pad_positions(net, comp_by_ref)

    assert positions == [(7.5, 10.0)]


def test_net_pad_positions_never_lands_on_a_different_nets_true_pad():
    """The headline defect, reproduced directly: two adjacent rotated
    components, A and B. Resolving one of A's own pads must never coincide
    with any of B's real pads -- if it does, a router that trusts this
    function's output (fallback_channel_path's `waypoints = pads` for a
    2-pad net) would target the wrong net's copper."""
    # A 90-degree-rotated resistor at (50, 50) -- its pin '2' is really at
    # (50, 52.5) once rotation is applied (see the first test above). Place
    # a second, unrelated component's pad exactly where the PRE-FIX (naive,
    # unrotated) computation would have wrongly put it instead: (52.5, 50).
    comp_a = _rotated_two_pin_component("RA", (50.0, 50.0), rotation_index=1)
    comp_b = Component(
        ref="RB",
        footprint="R_0805",
        bounds=(2.0, 1.25),
        pins=[
            Pin(
                name="1",
                number="1",
                position=(0.0, 0.0),
                net="UNRELATED_NET",
                width=1.0,
                height=1.0,
                shape="rect",
                layer="F.Cu",
            )
        ],
        initial_position=(52.5, 50.0),
        initial_rotation=0,
    )
    comp_by_ref = {"RA": comp_a, "RB": comp_b}

    net_a = Net(name="RA_NET_B", pins=[("RA", "2")])
    resolved = _net_pad_positions(net_a, comp_by_ref)[0]

    b_true_position = _net_pad_positions(Net(name="UNRELATED_NET", pins=[("RB", "1")]), comp_by_ref)[0]

    assert resolved != b_true_position, (
        "RA's own pad must not resolve to RB's real pad position -- this is "
        "exactly the GATE_HS/R23 shape (docs/evidence/"
        "2026-08-08-nlayer-via-astar-spike.md)"
    )
