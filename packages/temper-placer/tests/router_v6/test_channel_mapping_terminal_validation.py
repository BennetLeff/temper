"""Regression tests for the Stage 3 -> 4.1 wrong-pad terminal defect.

Measured on ``pcb/temper.kicad_pcb``
(``docs/evidence/2026-08-08-nlayer-via-astar-spike.md`` Sec 2.4):
``expand_channel_path_terminals`` used to return a 2-pad net's SAT-derived
channel path unchanged even when its endpoint waypoint did not resolve to
either of that net's own two pads. In the measured case (``GATE_HS``), the
endpoint landed exactly on a physically adjacent pad belonging to a
DIFFERENT net (R23's other pin, 2.925mm away) -- see
``docs/evidence/2026-08-08-nlayer-via-astar-spike-terminal-fix.md`` for the
full enumeration this repo's own tooling produced.

Stage 4 A* treats every ``ChannelPath.waypoints`` entry as a required
terminal it must physically reach (``_astar_search.py``: consecutive
waypoint pairs each get their own segment search, and the goal coordinate is
snapped onto the emitted path exactly -- see
``append_exact_terminal_point``), so an unverified endpoint becomes real
copper. On a mains-connected board with an SELV/HV isolation requirement,
copper that bridges the wrong two nets is a safety defect, not merely an
incomplete route.

These tests reconstruct that shape with synthetic coordinates (not the real
board's numbers -- see the real-board regression in
``test_temper_production_board_routing.py`` /
``test_pad_connectivity_audit.py`` for that) and pin the fix: an endpoint
that does not resolve to the routed net's own pad must never survive
``expand_channel_path_terminals`` unchanged.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.channel_mapping import ChannelPath, expand_channel_path_terminals

# This net's own two true pads (the values `_net_pad_positions` would hand
# `expand_channel_path_terminals` in production).
_OWN_PAD_A = (100.0, 50.0)
_OWN_PAD_B = (110.0, 50.0)

# Stand-in for "a physically adjacent pad belonging to a DIFFERENT net" --
# the exact shape measured for GATE_HS/R23 in the evidence doc, at a
# similar few-mm separation from this net's own pad, but a synthetic
# coordinate, not R23's real board position.
_FOREIGN_PAD = (110.0 + 2.925, 50.0)


def test_wrong_pad_terminal_is_corrected_not_trusted():
    """The headline defect: a 2-pad net's SAT-derived endpoint lands on a
    different net's pad. The fixed function must not return it unchanged --
    it must resolve the corrected endpoint to THIS net's own pad."""
    channel_path = ChannelPath(
        net_name="NET_UNDER_TEST",
        channel_sequence=["CH1"],
        waypoints=[_OWN_PAD_A, _FOREIGN_PAD],
        total_length=12.925,
    )

    result = expand_channel_path_terminals(channel_path, [_OWN_PAD_A, _OWN_PAD_B])

    assert result.waypoints[0] == _OWN_PAD_A
    assert result.waypoints[-1] == _OWN_PAD_B
    assert _FOREIGN_PAD not in result.waypoints, (
        "a foreign net's pad must never survive as this net's routing terminal"
    )


def test_wrong_pad_terminal_at_the_start_is_also_corrected():
    """Same defect, opposite end of the path."""
    channel_path = ChannelPath(
        net_name="NET_UNDER_TEST",
        channel_sequence=["CH1"],
        waypoints=[_FOREIGN_PAD, _OWN_PAD_B],
        total_length=2.925,
    )

    result = expand_channel_path_terminals(channel_path, [_OWN_PAD_A, _OWN_PAD_B])

    assert result.waypoints[0] == _OWN_PAD_A
    assert result.waypoints[-1] == _OWN_PAD_B
    assert _FOREIGN_PAD not in result.waypoints


def test_correct_two_pad_path_is_returned_unchanged():
    """No false positives: a 2-pad path whose endpoints already ARE this
    net's own pads must be returned as the identical object (no wasted
    reallocation, no accidental reordering)."""
    channel_path = ChannelPath(
        net_name="NET_UNDER_TEST",
        channel_sequence=["CH1"],
        waypoints=[_OWN_PAD_A, _OWN_PAD_B],
        total_length=10.0,
    )

    result = expand_channel_path_terminals(channel_path, [_OWN_PAD_A, _OWN_PAD_B])

    assert result is channel_path


def test_reversed_pad_order_is_recognized_as_correct():
    """Endpoints matching this net's own pads in the OPPOSITE order to
    `pads` are still correct -- order between the two pads is not itself a
    defect, only landing on the wrong net's pad is."""
    channel_path = ChannelPath(
        net_name="NET_UNDER_TEST",
        channel_sequence=["CH1"],
        waypoints=[_OWN_PAD_B, _OWN_PAD_A],
        total_length=10.0,
    )

    result = expand_channel_path_terminals(channel_path, [_OWN_PAD_A, _OWN_PAD_B])

    assert result is channel_path


def test_interior_channel_guidance_waypoints_are_preserved():
    """Only the terminal endpoints are validated/corrected -- interior
    channel-skeleton routing guidance points are left untouched."""
    interior = (105.0, 55.0)
    channel_path = ChannelPath(
        net_name="NET_UNDER_TEST",
        channel_sequence=["CH1", "CH2"],
        waypoints=[_OWN_PAD_A, interior, _FOREIGN_PAD],
        total_length=20.0,
    )

    result = expand_channel_path_terminals(channel_path, [_OWN_PAD_A, _OWN_PAD_B])

    assert result.waypoints == [_OWN_PAD_A, interior, _OWN_PAD_B]


def test_degenerate_short_path_falls_back_to_true_pads():
    """A path with 0 or 1 waypoints has no real geometry to preserve; the
    only truthful terminals available are this net's own two pads."""
    empty_path = ChannelPath(
        net_name="NET_UNDER_TEST", channel_sequence=[], waypoints=[], total_length=0.0
    )
    single_point_path = ChannelPath(
        net_name="NET_UNDER_TEST",
        channel_sequence=["CH1"],
        waypoints=[_FOREIGN_PAD],
        total_length=0.0,
    )

    for path in (empty_path, single_point_path):
        result = expand_channel_path_terminals(path, [_OWN_PAD_A, _OWN_PAD_B])
        assert result.waypoints == [_OWN_PAD_A, _OWN_PAD_B]


@given(
    pad_a=st.tuples(
        st.floats(min_value=-500, max_value=500, allow_nan=False, allow_infinity=False),
        st.floats(min_value=-500, max_value=500, allow_nan=False, allow_infinity=False),
    ),
    pad_b=st.tuples(
        st.floats(min_value=-500, max_value=500, allow_nan=False, allow_infinity=False),
        st.floats(min_value=-500, max_value=500, allow_nan=False, allow_infinity=False),
    ),
    foreign=st.tuples(
        st.floats(min_value=-500, max_value=500, allow_nan=False, allow_infinity=False),
        st.floats(min_value=-500, max_value=500, allow_nan=False, allow_infinity=False),
    ),
)
@settings(max_examples=200, deadline=None)
def test_terminal_endpoints_always_resolve_to_this_nets_own_pads(pad_a, pad_b, foreign):
    """Property: no matter what garbage coordinate Stage 3 hands us as an
    endpoint, `expand_channel_path_terminals` must never let it survive --
    the first and last waypoint of a 2-pad net's path must always be a
    member of that net's own `pads`. This is the exact invariant whose
    violation is the safety-relevant defect this module exists to close."""
    if pad_a == pad_b:
        return  # degenerate net, not the scenario under test

    channel_path = ChannelPath(
        net_name="NET_UNDER_TEST",
        channel_sequence=["CH1"],
        waypoints=[pad_a, foreign],
        total_length=0.0,
    )

    result = expand_channel_path_terminals(channel_path, [pad_a, pad_b])

    own_pads = {pad_a, pad_b}
    assert result.waypoints[0] in own_pads
    assert result.waypoints[-1] in own_pads
