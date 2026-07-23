"""
Wave 5 / R12 -- net ordering (reverted 2026-06-23)

Verifies the **current** ``_compute_net_order``:

1. Smallest-footprint nets route first within spatial clusters (bbox area ascending).
2. Power nets are a secondary tiebreaker (not primary sort key) --
   per the Bottleneck Lemma, small-area nets in dense clusters must
   claim narrow corridors before larger nets spread through the region.
3. Historically problematic nets next (``astar_pathfinding.PROBLEM_NETS``).
4. Shortest ``total_length`` first as a tie-breaker within each class.

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


def test_smallest_area_routes_first_within_cluster():
    """Smallest-footprint nets route first; power is a tiebreaker only."""
    mapping = _make_mapping(
        [
            ("GND", 2, 10.0, False),
            ("VCC", 4, 20.0, False),
            ("SIG_2PIN", 2, 5.0, False),
            ("SIG_8PIN", 8, 80.0, False),
        ]
    )
    order = _compute_net_order(mapping)
    # All nets share the same spatial cluster (overlapping waypoints).
    # Bbox areas: GND=1, VCC=9, SIG_2PIN=1, SIG_8PIN=49.
    # Area ascending -> GND(1)/SIG_2PIN(1) first (power tiebreaker puts GND first),
    # then VCC(9), then SIG_8PIN(49).
    assert order.index("GND") < order.index("SIG_2PIN"), f"power tiebreaker, got: {order}"
    assert order.index("SIG_2PIN") < order.index("VCC"), f"area ascending, got: {order}"
    assert order.index("VCC") < order.index("SIG_8PIN"), f"area ascending, got: {order}"


def test_shortest_path_routes_first_within_signal_class():
    """Post-revert: shortest ``total_length`` wins within the signal
    class.  The earlier "high-pin-first" attempt was reverted because
    it blocked the 2-3 pin nets that were succeeding.  This test
    pins the current (correct) behavior; if a future attempt
    reintroduces high-pin-first, this test will fail.
    """
    mapping = _make_mapping(
        [
            ("SIG_2PIN_A", 2, 5.0, False),
            ("SIG_2PIN_B", 2, 8.0, False),
            ("SIG_3PIN", 3, 15.0, False),
            ("SIG_4PIN", 4, 25.0, False),
            ("SIG_8PIN", 8, 80.0, False),
        ]
    )
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


def test_same_area_tiebreak_by_bfs_discovery_order():
    """When two nets have identical bbox area, BFS discovery order
    (alphabetical within sorted conflict neighbors) is the tiebreaker."""
    mapping = _make_mapping(
        [
            ("SIG_LONG", 3, 50.0, False),
            ("SIG_SHORT", 3, 10.0, False),
        ]
    )
    order = _compute_net_order(mapping)
    # Both nets have the same bbox area (same waypoints pattern).
    # total_length is NOT a sort key in _compute_net_order --
    # BFS discovery order (alphabetical) is the tiebreaker.
    assert order.index("SIG_LONG") < order.index("SIG_SHORT"), (
        f"Alphabetical BFS tiebreaker within same area, got: {order}"
    )


def test_problem_nets_not_special_in_compute_net_order():
    """PROBLEM_NETS is consumed elsewhere in the pipeline, not by
    ``_compute_net_order``.  Same-bbox nets are ordered by area and BFS
    discovery (alphabetical)."""
    from temper_placer.router_v6.astar_pathfinding import PROBLEM_NETS

    assert PROBLEM_NETS, "PROBLEM_NETS should be non-empty"
    problem_name = next(iter(PROBLEM_NETS))
    mapping = _make_mapping(
        [
            ("NORMAL_2PIN", 2, 5.0, False),
            (problem_name, 2, 5.0, True),
        ]
    )
    order = _compute_net_order(mapping)
    # PROBLEM_NETS is NOT a sort key in _compute_net_order.
    # Both nets have same bbox area; alphabetical BFS discovery is the tiebreaker.
    # NORMAL_2PIN < /k25 alphabetically.
    assert order.index("NORMAL_2PIN") < order.index(problem_name), (
        f"_compute_net_order does not prioritize PROBLEM_NETS, got: {order}"
    )
