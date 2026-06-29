"""
Wave 5 / R12 -- net ordering (reverted 2026-06-23)

Verifies the **current** ``_compute_net_order``:

1. Power nets first (GND / VCC / HV / AC_ / + / VBUS).
2. Historically problematic nets next (``astar_pathfinding.PROBLEM_NETS``).
3. Shortest ``total_length`` first as a tie-breaker within each class.

The "high-pin-first" rule (R12) was tried in commit ``99108893``
and REGRESSED closure from 15/24 to 13/24 on ``temper.kicad_pcb``
(deterministic across 3 runs).  Reverted in the same commit; the
8-pin I_SENSE still hits the iter cap even with first claim, and
routing it first blocks the 2-3 pin nets that were succeeding
under the shortest-first order.
"""
from __future__ import annotations

from temper_placer.router_v6.astar_pathfinding import _compute_net_order
from temper_placer.router_v6.channel_mapping import ChannelMapping, ChannelPath


def _make_mapping(net_specs: list[tuple[str, int, float, bool]]) -> ChannelMapping:
    """Build a ChannelMapping from a list of
    (name, pin_count, total_length, is_problem) tuples."""
    paths = {}
    for name, pin_count, total_length, _is_problem in net_specs:
        paths[name] = ChannelPath(
            net_name=name,
            channel_sequence=[f"CH{i}" for i in range(pin_count)],
            waypoints=[(float(i), float(i)) for i in range(pin_count)],
            total_length=total_length,
        )
    return ChannelMapping(channel_paths=paths)


def test_power_nets_route_first():
    """Power nets come before signal nets regardless of pin count."""
    mapping = _make_mapping([
        ("GND", 2, 10.0, False),
        ("VCC", 4, 20.0, False),
        ("SIG_2PIN", 2, 5.0, False),
        ("SIG_8PIN", 8, 80.0, False),
    ])
    order = _compute_net_order(mapping)
    # GND and VCC must come before any signal net
    power_idx = [order.index("GND"), order.index("VCC")]
    sig_idx = [order.index("SIG_2PIN"), order.index("SIG_8PIN")]
    assert max(power_idx) < min(sig_idx), (
        f"Power nets must route before signal nets, got order: {order}"
    )


def test_shortest_path_routes_first_within_signal_class():
    """Post-revert: shortest ``total_length`` wins within the signal
    class.  The earlier "high-pin-first" attempt was reverted because
    it blocked the 2-3 pin nets that were succeeding.  This test
    pins the current (correct) behavior; if a future attempt
    reintroduces high-pin-first, this test will fail.
    """
    mapping = _make_mapping([
        ("SIG_2PIN_A", 2, 5.0, False),
        ("SIG_2PIN_B", 2, 8.0, False),
        ("SIG_3PIN", 3, 15.0, False),
        ("SIG_4PIN", 4, 25.0, False),
        ("SIG_8PIN", 8, 80.0, False),
    ])
    order = _compute_net_order(mapping)
    idx_8 = order.index("SIG_8PIN")
    idx_4 = order.index("SIG_4PIN")
    idx_3 = order.index("SIG_3PIN")
    idx_2a = order.index("SIG_2PIN_A")
    idx_2b = order.index("SIG_2PIN_B")
    # Shortest first: 2-pin (5,8) < 3-pin (15) < 4-pin (25) < 8-pin (80)
    assert idx_2a < idx_2b < idx_3 < idx_4 < idx_8, (
        f"Shortest total_length should route first within the signal "
        f"class; got order {order} (idx_2a={idx_2a}, idx_2b={idx_2b}, "
        f"idx_3={idx_3}, idx_4={idx_4}, idx_8={idx_8})"
    )


def test_shortest_path_is_tiebreaker_within_pin_count():
    """When two signal nets have the same pin count, the shorter
    one routes first (matches the pre-Wave-5 tie-breaker)."""
    mapping = _make_mapping([
        ("SIG_LONG", 3, 50.0, False),
        ("SIG_SHORT", 3, 10.0, False),
    ])
    order = _compute_net_order(mapping)
    assert order.index("SIG_SHORT") < order.index("SIG_LONG"), (
        f"Within same pin count, shortest should route first, got: {order}"
    )


def test_problem_nets_still_get_priority():
    """Historically problematic nets route before other signal
    nets of the same pin count (preserved from pre-Wave-5).
    The fixture name is from astar_pathfinding.PROBLEM_NETS
    (a hardcoded set of legacy fixture names like ``/k02``)."""
    from temper_placer.router_v6.astar_pathfinding import PROBLEM_NETS
    # Pick any name from the actual PROBLEM_NETS set so the
    # ``is_problem`` check is True.
    assert PROBLEM_NETS, "PROBLEM_NETS should be non-empty"
    problem_name = next(iter(PROBLEM_NETS))
    mapping = _make_mapping([
        ("NORMAL_2PIN", 2, 5.0, False),
        (problem_name, 2, 5.0, True),
    ])
    order = _compute_net_order(mapping)
    assert order.index(problem_name) < order.index("NORMAL_2PIN"), (
        f"Problem nets should route before non-problem at same "
        f"pin count, got: {order}"
    )
