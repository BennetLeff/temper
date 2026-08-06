"""
Tests for Router V6 Quality U2: Via Counting.

Part of temper-7rqf (Stage 6 - Quality Gate)
"""

from __future__ import annotations

from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.quality.via_count import (
    ViaCounts,
    count_signal_vias_from_routing,
)
from temper_placer.router_v6.routing_results import CompiledRoute
from temper_placer.router_v6.via_placement import Via

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_via(net_name, x=0.0, y=0.0):
    return Via((x, y), "F.Cu", "B.Cu", 0.6, 0.3, net_name)


def _make_compiled_route(net_name, vias, width_mm=0.2):
    coords = [(0.0, 0.0), (10.0, 0.0)]
    path = RoutePath(net_name, coords, "F.Cu", 10.0)
    return CompiledRoute(net_name, path, width_mm, vias, None)


def _make_compiled_routes(*routes):
    return {r.net_name: r for r in routes}


# ---------------------------------------------------------------------------
# Tests: count_signal_vias_from_routing
# ---------------------------------------------------------------------------


def test_count_signal_vias_from_routing_all_signal():
    via1 = _make_via("SIGNAL1", x=1.0)
    via2 = _make_via("SIGNAL2", x=2.0)
    via3 = _make_via("SIG_NET", x=3.0)
    route1 = _make_compiled_route("SIGNAL1", [via1])
    route2 = _make_compiled_route("SIGNAL2", [via2])
    route3 = _make_compiled_route("SIG_NET", [via3])
    routes = _make_compiled_routes(route1, route2, route3)

    count, signal, non_signal, all_v = count_signal_vias_from_routing(routes)

    assert count == 3
    assert len(signal) == 3
    assert len(non_signal) == 0
    assert len(all_v) == 3


def test_count_signal_vias_from_routing_all_ground():
    via1 = _make_via("GND", x=1.0)
    via2 = _make_via("PGND", x=2.0)
    route1 = _make_compiled_route("GND", [via1])
    route2 = _make_compiled_route("PGND", [via2])
    routes = _make_compiled_routes(route1, route2)

    count, signal, non_signal, all_v = count_signal_vias_from_routing(routes)

    assert count == 0
    assert len(signal) == 0
    assert len(non_signal) == 2
    assert len(all_v) == 2


def test_count_signal_vias_from_routing_mixed():
    via1 = _make_via("SIGNAL1")
    via2 = _make_via("GND")
    via3 = _make_via("VCC")
    via4 = _make_via("SIGNAL2")
    route1 = _make_compiled_route("SIGNAL1", [via1, via2])
    route2 = _make_compiled_route("SIGNAL2", [via3, via4])
    routes = _make_compiled_routes(route1, route2)

    count, signal, non_signal, all_v = count_signal_vias_from_routing(routes)

    assert count == 2
    assert len(signal) == 2
    assert len(non_signal) == 2
    assert len(all_v) == 4
    assert all(v.net_name == "SIGNAL1" or v.net_name == "SIGNAL2" for v in signal)


def test_count_signal_vias_from_routing_power_vias_not_signal():
    via1 = _make_via("+3V3")
    via2 = _make_via("+5V")
    via3 = _make_via("VDD")
    via4 = _make_via("DC_BUS+")
    route = _make_compiled_route("+3V3", [via1, via2, via3, via4])
    routes = _make_compiled_routes(route)

    count, signal, non_signal, all_v = count_signal_vias_from_routing(routes)

    assert count == 0
    assert len(signal) == 0
    assert len(non_signal) == 4


def test_count_signal_vias_from_routing_empty():
    routes = {}
    count, signal, non_signal, all_v = count_signal_vias_from_routing(routes)

    assert count == 0
    assert len(signal) == 0
    assert len(non_signal) == 0
    assert len(all_v) == 0


def test_count_signal_vias_from_routing_zero_vias():
    route = _make_compiled_route("SIGNAL1", [])
    routes = _make_compiled_routes(route)

    count, signal, non_signal, all_v = count_signal_vias_from_routing(routes)

    assert count == 0
    assert len(signal) == 0
    assert len(non_signal) == 0
    assert len(all_v) == 0


def test_count_signal_vias_from_routing_hv_nets_not_signal():
    via1 = _make_via("DC_BUS+")
    via2 = _make_via("AC_L")
    via3 = _make_via("SW_NODE")
    route = _make_compiled_route("DC_BUS+", [via1, via2, via3])
    routes = _make_compiled_routes(route)

    count, signal, non_signal, all_v = count_signal_vias_from_routing(routes)

    assert count == 0
    assert len(non_signal) == 3


# ---------------------------------------------------------------------------
# Tests: ViaCounts dataclass
# ---------------------------------------------------------------------------


def test_via_counts_dataclass():
    counts = ViaCounts(signal=10, thermal=5, stitching=3, total=18)
    assert counts.signal == 10
    assert counts.thermal == 5
    assert counts.stitching == 3
    assert counts.total == 18


def test_via_counts_zero():
    counts = ViaCounts(signal=0, thermal=0, stitching=0, total=0)
    assert counts.signal == 0


# ---------------------------------------------------------------------------
# Tests: signal via count <= 100 gate (provisional threshold)
# ---------------------------------------------------------------------------


def _make_many_signal_vias(count):
    vias = [_make_via(f"SIG{i}") for i in range(count)]
    routes = {}
    for i, via in enumerate(vias):
        net_name = f"SIG{i}"
        coords = [(float(i), 0.0), (float(i), 10.0)]
        path = RoutePath(net_name, coords, "F.Cu", 10.0)
        routes[net_name] = CompiledRoute(net_name, path, 0.2, [via], None)

    signal_count, _, _, _ = count_signal_vias_from_routing(routes)
    return signal_count


def test_signal_via_count_under_threshold():
    count = _make_many_signal_vias(50)
    assert count == 50
    assert count <= 100


def test_signal_via_count_at_threshold():
    count = _make_many_signal_vias(100)
    assert count == 100


def test_signal_via_count_over_threshold():
    count = _make_many_signal_vias(150)
    assert count == 150
    assert count > 100


# ---------------------------------------------------------------------------
# Tests: classify_vias (requires routed_pcb_path, skipped via direct unit test)
# ---------------------------------------------------------------------------


def test_classify_vias_empty_parse_result():
    """Empty via list returns all zeros."""
    counts = ViaCounts(signal=0, thermal=0, stitching=0, total=0)
    assert counts.signal == 0
    assert counts.thermal == 0
    assert counts.stitching == 0


# ---------------------------------------------------------------------------
# Tests: monotonicity invariants
# ---------------------------------------------------------------------------


def test_signal_via_count_never_exceeds_total():
    """The number of signal vias must never exceed total vias."""

    def _build_and_check(nets):
        vias = [_make_via(n) for n in nets]
        route = _make_compiled_route("test", vias)
        routes = _make_compiled_routes(route)
        signal, _, _, all_v = count_signal_vias_from_routing(routes)
        assert signal <= len(all_v)

    _build_and_check(["SIG1", "SIG2", "GND", "VCC"])
    _build_and_check(["SIG1", "SIG2", "SIG3"])
    _build_and_check(["GND", "PGND", "VCC"])
    _build_and_check(["DC_BUS+", "AC_L", "AC_N"])


def test_classification_is_exhaustive():
    """Every via is either signal or non-signal (ground/power/HV)."""
    nets = ["SIG1", "SIG2", "GND", "PGND", "VCC", "+3V3", "DC_BUS+", "AC_L", "SW_NODE"]
    vias = [_make_via(n) for n in nets]
    route = _make_compiled_route("test", vias)
    routes = _make_compiled_routes(route)
    signal_count, signal, non_signal, all_v = count_signal_vias_from_routing(routes)

    assert signal_count + len(non_signal) == len(all_v)
    assert all(v not in signal for v in non_signal)
    assert all(v not in non_signal for v in signal)


# ---------------------------------------------------------------------------
# Tests: _classify_vias — issue #752 defect 10
#
# `_classify_vias` carried a per-via `signal` accumulator guarded by
# `is_signal_net(...)`, then unconditionally overwrote it two lines later with
# `signal = total - thermal - stitching`. The accumulator was a dead store, and
# it made the function read as though non-signal (power/HV) vias were excluded
# from the signal count when they never were. These tests pin the real,
# residual definition, so removing the dead store cannot change behaviour and
# "fixing" it the other way (deleting the residual line) fails loudly.
# ---------------------------------------------------------------------------


def _parse_result(vias, components=(), board_size=(50.0, 50.0)):
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.io._kicad_types import ParseResult

    return ParseResult(
        netlist=Netlist(components=list(components), nets=[]),
        board=Board(width=board_size[0], height=board_size[1]),
        vias=list(vias),
        traces=[],
        pads=[],
        warnings=[],
    )


def _via_data(net, x, y):
    from temper_placer.io._kicad_types import ViaData

    return ViaData(position=(x, y), diameter=0.6, drill=0.3, net=net, layers=("F.Cu", "B.Cu"))


def test_classify_vias_counts_are_a_partition_of_total():
    from temper_placer.router_v6.quality.via_count import classify_vias_from_parse

    # 25.0 is the board centre: far from every edge, so nothing is stitching,
    # and there is no Q1/Q2 footprint, so nothing is thermal.
    vias = [_via_data(n, 25.0, 25.0) for n in ("SIG1", "GND", "VCC", "DC_BUS+", "AC_L")]
    counts = classify_vias_from_parse(_parse_result(vias))

    assert counts.total == 5
    assert counts.thermal == 0
    assert counts.stitching == 0
    assert counts.signal + counts.thermal + counts.stitching == counts.total


def test_classify_vias_signal_is_the_residual_and_includes_power_nets():
    """A mid-board power via is neither thermal nor stitching, so it is signal.

    This is the assertion the dead `is_signal_net` accumulator implied was
    false. If someone ever "resolves" the dead store by deleting the residual
    `signal = total - thermal - stitching` line instead, this fails.
    """
    from temper_placer.router_v6.quality.via_count import classify_vias_from_parse

    counts = classify_vias_from_parse(_parse_result([_via_data("VCC", 25.0, 25.0)]))
    assert counts == ViaCounts(signal=1, thermal=0, stitching=0, total=1)


def test_classify_vias_edge_ground_via_is_stitching_not_signal():
    from temper_placer.router_v6.quality.via_count import classify_vias_from_parse

    counts = classify_vias_from_parse(_parse_result([_via_data("GND", 1.0, 25.0)]))
    assert counts == ViaCounts(signal=0, thermal=0, stitching=1, total=1)


def test_classify_vias_empty_is_all_zero():
    from temper_placer.router_v6.quality.via_count import classify_vias_from_parse

    assert classify_vias_from_parse(_parse_result([])) == ViaCounts(
        signal=0, thermal=0, stitching=0, total=0
    )
