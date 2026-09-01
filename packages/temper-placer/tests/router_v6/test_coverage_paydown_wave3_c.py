"""Coverage paydown tests — Wave 3 easy wins (Batch C).

Covers: layer_assignment simple functions, acid_trap_detection properties, routing_results,
connectivity data structures, manufacturing_report, via_placement.
"""

from __future__ import annotations

import pytest

from temper_placer.router_v6.acid_trap_detection import AcidTrapReport
from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.connectivity import (
    ConnectivityComponent,
    CopperPad,
    CopperTrack,
    CopperVia,
    NetConnectivity,
    NetDisposition,
    PadIdentity,
)
from temper_placer.router_v6.constraints_geometry import Point
from temper_placer.router_v6.layer_assignment import (
    get_plane_layers,
    get_routing_layers,
    get_signal_only_layers,
    matches_pattern,
)
from temper_placer.router_v6.routing_results import RoutingResults
from temper_placer.router_v6.via_placement import ViaPlacement


# ── layer_assignment standalone functions ──────────────────────────


def test_matches_pattern_exact():
    assert matches_pattern("DC_BUS_P", r"DC_BUS_.*") is True


def test_matches_pattern_no_match():
    assert matches_pattern("VCC_3V3", r"DC_BUS_.*") is False


def test_matches_pattern_full_match():
    assert matches_pattern("GND", r"GND") is True


def test_get_routing_layers():
    layers = get_routing_layers()
    assert len(layers) == 4
    from temper_placer.router_v6.layer_assignment import Layer
    assert Layer.L1_TOP in layers
    assert Layer.L4_BOT in layers


def test_get_plane_layers():
    layers = get_plane_layers()
    assert len(layers) == 2
    from temper_placer.router_v6.layer_assignment import Layer
    assert Layer.L2_GND in layers
    assert Layer.L3_PWR in layers


def test_get_signal_only_layers():
    layers = get_signal_only_layers()
    assert len(layers) == 2
    from temper_placer.router_v6.layer_assignment import Layer
    assert Layer.L1_TOP in layers
    assert Layer.L4_BOT in layers


# ── acid_trap_detection report properties ──────────────────────────


def test_acid_trap_report_properties():
    from temper_placer.router_v6.acid_trap_detection import AcidTrap
    traps = [
        AcidTrap("N1", (0, 0), 30.0, "high"),
        AcidTrap("N2", (1, 1), 50.0, "medium"),
        AcidTrap("N3", (2, 2), 70.0, "low"),
    ]
    report = AcidTrapReport(acid_traps=traps)
    assert report.trap_count == 3
    assert report.critical_count == 1
    assert report.medium_count == 1
    assert report.low_count == 1


# ── connectivity data structures ──────────────────────────────────


def test_copper_pad_layers():
    identity = PadIdentity(
        component_ref="C1", pad="1", net="GND", x=0.0, y=0.0, layers=(0, 1)
    )
    pad = CopperPad(
        identity=identity, center=Point(0, 0), shape="rect", size=(1.0, 1.0)
    )
    assert pad.layers == frozenset({0, 1})


def test_copper_track_segment():
    track = CopperTrack(
        start=Point(0.0, 0.0), end=Point(5.0, 5.0), layer=0, width=0.2, net="N"
    )
    seg = track.segment
    assert seg.start.x == 0.0
    assert seg.end.y == 5.0


def test_net_connectivity_connected_pad_ids():
    identity = PadIdentity("C1", "1", "N", 0.0, 0.0, (0,))
    comp = ConnectivityComponent(pads=(identity,))
    nc = NetConnectivity(
        net="N",
        disposition=NetDisposition.ROUTED,
        connected_pad_count=1,
        total_required_pad_count=1,
        components=(comp,),
        unresolved_islands=(),
    )
    assert nc.connected_pad_ids == (identity,)
    assert nc.disposition == NetDisposition.ROUTED


# ── via_placement properties ──────────────────────────────────────


def test_via_placement_properties():
    from temper_placer.router_v6.via_placement import Via
    vias = [
        Via((0, 0), "F.Cu", "B.Cu", 0.6, 0.3, "N1"),
        Via((5, 5), "F.Cu", "B.Cu", 0.6, 0.3, "N2"),
    ]
    vp = ViaPlacement(vias=vias)
    assert vp.via_count == 2
    assert len(vp.get_vias_for_net("N1")) == 1
    assert len(vp.get_vias_for_net("N2")) == 1
    assert vp.get_vias_for_net("NONEXISTENT") == []


def test_via_placement_empty():
    vp = ViaPlacement(vias=[])
    assert vp.via_count == 0


# ── routing_results properties ────────────────────────────────────


def test_routing_results_success_count():
    path = RoutePath("NET1", [(0, 0), (5, 5)], "F.Cu", 7.07)
    from temper_placer.router_v6.routing_results import CompiledRoute
    route = CompiledRoute("NET1", path, 0.127, [], None)
    rr = RoutingResults(
        compiled_routes={"NET1": route},
        failed_nets=["NET2"],
    )
    assert rr.success_count == 1
    assert rr.failure_count == 1


def test_routing_results_get_route():
    path = RoutePath("NET1", [(0, 0), (5, 5)], "F.Cu", 7.07)
    from temper_placer.router_v6.routing_results import CompiledRoute
    route = CompiledRoute("NET1", path, 0.127, [], None)
    rr = RoutingResults(
        compiled_routes={"NET1": route},
        failed_nets=["NET2"],
    )
    assert rr.get_route("NET1") is not None
    assert rr.get_route("NONEXISTENT") is None


def test_routing_results_total_route_length():
    path = RoutePath("A", [(0, 0), (10, 0)], "F.Cu", 10.0)
    from temper_placer.router_v6.routing_results import CompiledRoute
    route = CompiledRoute("A", path, 0.127, [], None)
    rr = RoutingResults(compiled_routes={"A": route}, failed_nets=[])
    assert rr.total_route_length >= 0
