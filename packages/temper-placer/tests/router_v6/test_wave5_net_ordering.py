"""
Wave 5 / R12 -- net ordering with high-pin-first

Verifies that the new ``_compute_net_order`` ranks high-pin-count
nets first within each class (power > problem > high-pin > short).

Pre-Wave-5 behavior routed 2-pin nets before 3-pin before 4-pin
within the signal class.  Post-Wave-5 inverts that within-class
order; the 8-pin I_SENSE on temper.kicad_pcb now routes before
2-pin signal nets so it can claim channel space before short
nets crowd it.
"""
from __future__ import annotations

from temper_placer.router_v6.astar_pathfinding import _compute_net_order
from temper_placer.router_v6.channel_mapping import ChannelMapping, ChannelPath


def _make_mapping(net_specs: list[tuple[str, int, float, bool]]) -> ChannelMapping:
    """Build a ChannelMapping from a list of
    (name, pin_count, total_length, is_problem) tuples."""
    paths = {}
    for name, pin_count, total_length, is_problem in net_specs:
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


def test_high_pin_signal_nets_route_before_low_pin():
    """Wave 5 / R12: 8-pin signal nets must come before 2-pin
    signal nets within the signal class."""
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
    assert idx_8 < idx_4 < idx_3, (
        f"8-pin should route before 4-pin before 3-pin, got: {order}"
    )
    assert idx_8 < idx_2a and idx_8 < idx_2b, (
        f"8-pin should route before 2-pin nets, got: {order}"
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
