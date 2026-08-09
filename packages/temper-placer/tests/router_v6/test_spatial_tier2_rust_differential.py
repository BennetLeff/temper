"""Differential tests: Wave-4 spatial-tier-2 kernels in ``temper-geometry``
vs the pre-migration pure-Python references.

Migration unit "spatial tier 2" (router_v6 spatial/router kernels):

- ``bottleneck_analysis.py`` — the ``_classify_severity`` classification and
  the ``identify_bottlenecks`` capacity/demand aggregation.
- ``layer_capacity.py`` — the ``estimated_traces`` estimate formula inside
  ``calculate_layer_capacity``.
- ``connectivity.py`` — the union-find connectivity kernel plus the ten
  pad/track/via touch predicates (circle pads, rect pads, Liang-Barsky
  box overlap, segment/point distances).  The four ``_zone_*`` shapely
  predicates are JUSTIFIED-KEEP (GEOS ``contains``/``touches``/
  ``intersects`` on ``CopperZone.polygon``); they stay in Python and their
  (i, j) union pairs are fed to the Rust kernel.
- ``obstacle_map.py`` — the two ``Point.buffer(r, quad_segs=8)`` via sites,
  reproduced bit-exactly from GEOS's own circle construction (see
  ``obstacle_map_kernels.rs``).  ``LineString.buffer``, ``poly.buffer(0)``
  and ``unary_union`` are JUSTIFIED-KEEP (measured blockers in
  ``docs/evidence/2026-08-04-geos-polygon-algebra-spike.md`` §4.2/§4.3).
- ``routing_space.py`` — JUSTIFIED-KEEP: its compute surface is the GEOS
  ``difference`` / ``area`` over shapely polygons (spike §3 shows GEOS
  boolean output is not bit-reproducible without vendoring GEOS's noding
  and emission policy; the spike's §5 narrowing is a design change gated on
  the unresolved ``channel_skeleton`` Voronoi gate, out of scope for a
  kernel-migration unit).

All comparisons are bit-exact: floats are compared with ``==`` (identical
bit patterns) and with ``float.hex()`` on every scalar the kernels emit.

The ``_oracle_*`` functions below are VERBATIM copies of the module bodies
as committed before this migration (``f1ffc013``); do not edit them — they
are the reference.  The module's own public functions now delegate to the
Rust kernels; the oracle blocks pin what those kernels must reproduce.
"""

from __future__ import annotations

import random
from types import SimpleNamespace

import temper_geometry as _tg

from temper_placer.geometry.kicad_transform import (
    rotate_world_to_local_deg as _rotate_world_to_local_deg,
)
from temper_placer.router_v6 import bottleneck_analysis as ba
from temper_placer.router_v6 import connectivity as conn
from temper_placer.router_v6 import layer_capacity as lc
from temper_placer.router_v6 import obstacle_map as om
from temper_placer.router_v6.bottleneck_analysis import (
    Bottleneck,
    BottleneckAnalysis,
    BottleneckSeverity,
)
from temper_placer.router_v6.connectivity import (
    CONTACT_TOLERANCE_MM,
    CopperPad,
    CopperTrack,
    CopperVia,
    CopperZone,
    NetConnectivity,
    PadIdentity,
    verify_net_connectivity,
)
from temper_placer.router_v6.constraints_geometry import (
    LineSegment,
    Point,
    point_to_segment_distance,
    segment_to_segment_distance,
)
from temper_placer.router_v6.layer_capacity import LayerCapacity
from temper_placer.router_v6.routing_demand import RoutingDemand

# ---------------------------------------------------------------------------
# Verbatim pre-migration oracles — do not edit; they are the reference.
# ---------------------------------------------------------------------------


def _oracle_classify_severity(capacity: int, demand: int) -> BottleneckSeverity:
    """Severity classification (verbatim ``_classify_severity``)."""
    if capacity == 0:
        if demand > 0:
            return BottleneckSeverity.CRITICAL
        return BottleneckSeverity.NONE

    ratio = capacity / demand if demand > 0 else float("inf")

    if ratio < 0.5:
        return BottleneckSeverity.CRITICAL
    elif ratio < 1.0:
        return BottleneckSeverity.HIGH
    elif ratio < 1.2:
        return BottleneckSeverity.MEDIUM
    elif ratio < 2.0:
        return BottleneckSeverity.LOW
    else:
        return BottleneckSeverity.NONE


def _oracle_identify_bottlenecks(
    layer_capacities: dict[str, LayerCapacity] | None,
    demand: RoutingDemand | None,
) -> BottleneckAnalysis:
    """Verbatum ``identify_bottlenecks`` (pre-migration)."""
    if layer_capacities is None or demand is None:
        return BottleneckAnalysis(
            bottlenecks=[],
            total_capacity=0,
            total_demand=0,
        )

    bottlenecks = []
    total_capacity = 0

    # Distribute demand across layers (simplified - assume even distribution)
    num_layers = len(layer_capacities)
    demand_per_layer = demand.routable_nets // num_layers if num_layers > 0 else 0

    # Analyze each layer
    for layer_name, capacity in layer_capacities.items():
        total_capacity += capacity.estimated_traces

        # Calculate utilization
        if capacity.estimated_traces > 0:
            utilization = demand_per_layer / capacity.estimated_traces
        else:
            utilization = float("inf")

        # Determine severity
        severity = _oracle_classify_severity(capacity.estimated_traces, demand_per_layer)

        bottlenecks.append(
            Bottleneck(
                layer_name=layer_name,
                severity=severity,
                capacity=capacity.estimated_traces,
                demand=demand_per_layer,
                utilization=utilization,
            )
        )

    return BottleneckAnalysis(
        bottlenecks=bottlenecks,
        total_capacity=total_capacity,
        total_demand=demand.routable_nets,
    )


def _oracle_calculate_layer_capacity(
    grid: object,
    widths: object,
    min_trace_width: float = 0.127,  # 5mil
    min_clearance: float = 0.127,  # 5mil
) -> LayerCapacity:
    """Verbatim ``calculate_layer_capacity`` (pre-migration)."""
    # Get basic grid statistics
    total_cells = grid.width_cells * grid.height_cells
    free_cells = grid.free_cell_count
    blocked_cells = grid.blocked_cell_count

    # Get channel width statistics
    min_channel_width = widths.min_width
    avg_channel_width = widths.avg_width

    # Estimate trace capacity
    # Each trace needs: trace_width + 2*clearance for isolation
    trace_pitch = min_trace_width + 2 * min_clearance

    # Estimate number of traces that can fit in average channel
    if avg_channel_width > 0 and trace_pitch > 0:
        traces_per_channel = int(avg_channel_width / trace_pitch)

        # Estimate total trace capacity (conservative)
        # Use free cells as a proxy for routing area
        estimated_traces = max(1, int(free_cells * 0.01 * traces_per_channel))
    else:
        estimated_traces = 0

    return LayerCapacity(
        layer_name=grid.layer_name,
        total_cells=total_cells,
        free_cells=free_cells,
        blocked_cells=blocked_cells,
        min_channel_width=min_channel_width,
        avg_channel_width=avg_channel_width,
        estimated_traces=estimated_traces,
    )


def _oracle__track_key(track: CopperTrack) -> tuple[int, float, float, float, float, float]:
    return (track.layer, track.start.x, track.start.y, track.end.x, track.end.y, track.width)


def _oracle__via_key(via: CopperVia) -> tuple[float, float, tuple[int, ...], float]:
    return (via.center.x, via.center.y, tuple(sorted(via.layers)), via.diameter)


def _oracle__tracks_touch(left: CopperTrack, right: CopperTrack) -> bool:
    clearance = (left.width + right.width) / 2 + CONTACT_TOLERANCE_MM
    return segment_to_segment_distance(left.segment, right.segment) <= clearance


def _oracle__track_touches_via(track: CopperTrack, via: CopperVia) -> bool:
    return point_to_segment_distance(via.center, track.segment) <= (
        track.width / 2 + via.diameter / 2 + CONTACT_TOLERANCE_MM
    )


def _oracle__track_touches_pad(track: CopperTrack, pad: CopperPad) -> bool:
    return _oracle__segment_touches_pad(track.segment, pad, track.width / 2)


def _oracle__via_touches_pad(via: CopperVia, pad: CopperPad) -> bool:
    return _oracle__point_in_pad(via.center, pad, via.diameter / 2)


def _oracle__pads_touch(left: CopperPad, right: CopperPad) -> bool:
    return _oracle__point_in_pad(left.center, right) or _oracle__point_in_pad(right.center, left)


def _oracle__segment_touches_pad(segment: LineSegment, pad: CopperPad, radius: float) -> bool:
    if pad.shape == "circle":
        return (
            point_to_segment_distance(pad.center, segment)
            <= pad.size[0] / 2 + radius + CONTACT_TOLERANCE_MM
        )
    start = _oracle__to_pad_coordinates(segment.start, pad)
    end = _oracle__to_pad_coordinates(segment.end, pad)
    half_x, half_y = pad.size[0] / 2 + radius, pad.size[1] / 2 + radius
    return _oracle__segment_intersects_box(start, end, half_x, half_y)


def _oracle__point_in_pad(point: Point, pad: CopperPad, radius: float = 0.0) -> bool:
    # Rotation is intentionally handled here rather than with a global
    # coordinate threshold.  Ovals use their bounding ellipse, a conservative
    # representation until the KiCad shape adapter is introduced.
    local_x, local_y = _oracle__to_pad_coordinates(point, pad)
    half_x, half_y = pad.size[0] / 2 + radius, pad.size[1] / 2 + radius
    if pad.shape == "circle":
        return local_x * local_x + local_y * local_y <= half_x * half_x + CONTACT_TOLERANCE_MM
    return (
        abs(local_x) <= half_x + CONTACT_TOLERANCE_MM
        and abs(local_y) <= half_y + CONTACT_TOLERANCE_MM
    )


def _oracle__to_pad_coordinates(point: Point, pad: CopperPad) -> tuple[float, float]:
    """World point -> pad-local frame, undoing the pad's own rotation.

    Verbatim ``_to_pad_coordinates`` — the inverse of KiCad's
    footprint-child rotation convention R(-theta) is R(+theta), applied
    directly to ``pad.rotation``.
    """
    dx, dy = point.x - pad.center.x, point.y - pad.center.y
    return _rotate_world_to_local_deg(dx, dy, pad.rotation)


def _oracle__segment_intersects_box(
    start: tuple[float, float], end: tuple[float, float], half_x: float, half_y: float
) -> bool:
    """Liang-Barsky clipping against pad-local rectangular copper (verbatim)."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    lower, upper = 0.0, 1.0
    for position, delta, bound in ((start[0], dx, half_x), (start[1], dy, half_y)):
        bound += CONTACT_TOLERANCE_MM
        if delta == 0:
            if abs(position) > bound:
                return False
            continue
        entry, exit = (-bound - position) / delta, (bound - position) / delta
        lower, upper = max(lower, min(entry, exit)), min(upper, max(entry, exit))
    return lower <= upper and lower <= 1.0 and upper >= 0.0


def _oracle__points_touch(left: Point, right: Point) -> bool:
    return left.distance_to(right) <= CONTACT_TOLERANCE_MM


def _oracle__zone_touches_pad(zone: CopperZone, pad: CopperPad) -> bool:
    """Pad center or bounding box overlaps zone polygon (verbatim)."""
    from shapely.geometry import Point as _SPoint

    if zone.layer not in pad.layers:
        return False
    pt = _SPoint(pad.center.x, pad.center.y)
    return zone.polygon.contains(pt) or zone.polygon.touches(pt)


def _oracle__zone_touches_track(zone: CopperZone, track: CopperTrack) -> bool:
    """Track segment intersects or is contained by zone polygon (verbatim)."""
    from shapely.geometry import LineString as _SLineString

    if zone.layer != track.layer:
        return False
    seg = _SLineString(
        [
            (track.start.x, track.start.y),
            (track.end.x, track.end.y),
        ]
    )
    return zone.polygon.intersects(seg)


def _oracle__zones_touch(left: CopperZone, right: CopperZone) -> bool:
    """Two zone polygons overlap (verbatim)."""
    if left.layer != right.layer:
        return False
    return left.polygon.intersects(right.polygon) and not left.polygon.touches(right.polygon)


def _oracle__zone_touches_via(zone: CopperZone, via: CopperVia) -> bool:
    """Via center is inside zone polygon (verbatim)."""
    from shapely.geometry import Point as _SPoint

    if zone.layer not in via.layers:
        return False
    pt = _SPoint(via.center.x, via.center.y)
    return zone.polygon.contains(pt) or zone.polygon.touches(pt)


def _oracle_verify_net_connectivity(
    pads: list[CopperPad],
    tracks: list[CopperTrack],
    vias: list[CopperVia],
    zones: list[CopperZone] = (),
) -> NetConnectivity:
    """Verbatim ``verify_net_connectivity`` (pre-migration)."""
    ordered_pads = tuple(sorted(pads, key=lambda pad: pad.identity))
    ordered_tracks = tuple(sorted(tracks, key=_oracle__track_key))
    ordered_vias = tuple(sorted(vias, key=_oracle__via_key))
    ordered_zones = tuple(sorted(zones, key=lambda z: (z.layer, z.net)))
    net = ordered_pads[0].identity.net if ordered_pads else ""

    items: tuple[object, ...] = (
        *ordered_pads,
        *ordered_tracks,
        *ordered_vias,
        *ordered_zones,
    )
    parent = list(range(len(items)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    pad_count = len(ordered_pads)
    track_start = pad_count
    via_start = track_start + len(ordered_tracks)
    zone_start = via_start + len(ordered_vias)

    for left, track in enumerate(ordered_tracks):
        for right in range(left + 1, len(ordered_tracks)):
            other = ordered_tracks[right]
            if track.layer == other.layer and _oracle__tracks_touch(track, other):
                union(track_start + left, track_start + right)
        for pad_index, pad in enumerate(ordered_pads):
            if track.layer in pad.layers and _oracle__track_touches_pad(track, pad):
                union(track_start + left, pad_index)
        for via_index, via in enumerate(ordered_vias):
            if track.layer in via.layers and _oracle__track_touches_via(track, via):
                union(track_start + left, via_start + via_index)

    for left, pad in enumerate(ordered_pads):
        for right in range(left + 1, len(ordered_pads)):
            other_pad = ordered_pads[right]
            if pad.layers & other_pad.layers and _oracle__pads_touch(pad, other_pad):
                union(left, right)

    for left, via in enumerate(ordered_vias):
        for right in range(left + 1, len(ordered_vias)):
            other_via = ordered_vias[right]
            if via.layers & other_via.layers and _oracle__points_touch(via.center, other_via.center):
                union(via_start + left, via_start + right)
        for pad_index, pad in enumerate(ordered_pads):
            if via.layers & pad.layers and _oracle__via_touches_pad(via, pad):
                union(via_start + left, pad_index)

    # U5: zone/pour touch predicates — connect zones to pads, tracks,
    # vias, and other zones they touch on the same layer.
    for left, zone in enumerate(ordered_zones):
        for right in range(left + 1, len(ordered_zones)):
            if _oracle__zones_touch(zone, ordered_zones[right]):
                union(zone_start + left, zone_start + right)
        for pad_index, pad in enumerate(ordered_pads):
            if _oracle__zone_touches_pad(zone, pad):
                union(zone_start + left, pad_index)
        for track_index, track in enumerate(ordered_tracks):
            if _oracle__zone_touches_track(zone, track):
                union(zone_start + left, track_start + track_index)
        for via_index, via in enumerate(ordered_vias):
            if zone.layer in via.layers and _oracle__zone_touches_via(zone, via):
                union(zone_start + left, via_start + via_index)

    pad_components: dict[int, list[PadIdentity]] = {}
    for pad_index, pad in enumerate(ordered_pads):
        pad_components.setdefault(find(pad_index), []).append(pad.identity)
    component_pads = [tuple(sorted(component)) for component in pad_components.values()]
    component_pads.sort(key=lambda component: (-len(component), component))
    components = tuple(conn.ConnectivityComponent(component) for component in component_pads)
    primary = component_pads[0] if component_pads else ()
    disposition = (
        conn.NetDisposition.ROUTED
        if len(component_pads) == 1 and len(primary) >= 2
        else conn.NetDisposition.INCOMPLETE
    )
    return NetConnectivity(
        net=net,
        disposition=disposition,
        connected_pad_count=len(primary),
        total_required_pad_count=len(ordered_pads),
        components=components,
        unresolved_islands=tuple(component_pads[1:]),
        reason=None if disposition is conn.NetDisposition.ROUTED else "disconnected_required_pads",
    )


def _oracle_circle_buffer_ring(
    cx: float, cy: float, radius: float, quad_segs: int
) -> list[tuple[float, float]]:
    """Verbatim pre-migration behavior: ``Point(x, y).buffer(r, quad_segs=q)``
    exterior ring (closed)."""
    from shapely.geometry import Point as _SPoint

    if radius <= 0:
        return []
    return list(_SPoint(cx, cy).buffer(radius, quad_segs=quad_segs).exterior.coords)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _assert_bottleneck_equal(actual: Bottleneck, expected: Bottleneck) -> None:
    assert actual.layer_name == expected.layer_name
    assert actual.severity == expected.severity
    assert actual.capacity == expected.capacity
    assert actual.demand == expected.demand
    assert actual.utilization == expected.utilization
    assert actual.utilization.hex() == expected.utilization.hex()


def _stub_grid(rng: random.Random) -> SimpleNamespace:
    w = rng.choice([1, 2, 5, 13, 40])
    h = rng.choice([1, 2, 6, 17, 33])
    total = w * h
    free = rng.randint(0, total)
    return SimpleNamespace(
        layer_name=f"L{rng.randrange(4)}",
        width_cells=w,
        height_cells=h,
        free_cell_count=free,
        blocked_cell_count=total - free,
    )


def _stub_widths(rng: random.Random) -> SimpleNamespace:
    return SimpleNamespace(
        min_width=rng.choice([0.0, 0.1, 0.127, 0.25, 1.5]),
        avg_width=rng.choice([0.0, 0.05, 0.2, 0.5, 1.0, 2.0, 5.0]),
    )


# ---------------------------------------------------------------------------
# bottleneck_analysis kernels
# ---------------------------------------------------------------------------


def test_classify_severity_kernel_matches_reference_on_randomized_inputs() -> None:
    rng = random.Random(20260808)
    for _ in range(2000):
        capacity = rng.randint(0, 200)
        demand = rng.randint(0, 300)
        rust = ba._classify_severity(capacity, demand)
        ref = _oracle_classify_severity(capacity, demand)
        assert rust == ref, (capacity, demand, rust, ref)


def test_classify_severity_kernel_edge_matrix() -> None:
    cases = [
        (0, 0, BottleneckSeverity.NONE),
        (0, 1, BottleneckSeverity.CRITICAL),
        (0, 300, BottleneckSeverity.CRITICAL),
        (1, 1, BottleneckSeverity.MEDIUM),  # ratio 1.0 -> 1.0 < 1.2 -> MEDIUM
        (5, 10, BottleneckSeverity.HIGH),  # ratio 0.5 -> 0.5 < 0.5 false, 0.5 < 1.0 true -> HIGH
        (6, 10, BottleneckSeverity.HIGH),  # 0.6
        (10, 10, BottleneckSeverity.MEDIUM),  # 1.0
        (11, 10, BottleneckSeverity.MEDIUM),  # 1.1
        (12, 10, BottleneckSeverity.LOW),  # 1.2 -> 1.2 < 1.2 false -> LOW (1.2 < 2.0)
        (19, 10, BottleneckSeverity.LOW),  # 1.9
        (20, 10, BottleneckSeverity.NONE),  # 2.0
        (100, 1, BottleneckSeverity.NONE),
        (100, 0, BottleneckSeverity.NONE),  # inf ratio
    ]
    for capacity, demand, expected in cases:
        assert ba._classify_severity(capacity, demand) == expected, (capacity, demand)


def test_identify_bottlenecks_matches_reference_on_randomized_inputs() -> None:
    rng = random.Random(20260809)
    for _ in range(200):
        capacities = {}
        for i in range(rng.randint(0, 5)):
            capacities[f"L{i}"] = LayerCapacity(
                layer_name=f"L{i}",
                total_cells=10000,
                free_cells=rng.randint(0, 10000),
                blocked_cells=rng.randint(0, 10000),
                min_channel_width=float(rng.randint(0, 20)) / 10,
                avg_channel_width=float(rng.randint(0, 100)) / 10,
                estimated_traces=rng.randint(0, 300),
            )
        demand = RoutingDemand(
            total_nets=rng.randint(0, 400),
            routable_nets=rng.randint(0, 400),
            total_pins=rng.randint(0, 2000),
            signal_nets=0,
            power_nets=0,
            diff_pair_nets=0,
            avg_pins_per_net=0.0,
            max_pins_per_net=0,
        )
        rust = ba.identify_bottlenecks(capacities, demand)
        ref = _oracle_identify_bottlenecks(capacities, demand)
        assert rust.total_capacity == ref.total_capacity
        assert rust.total_demand == ref.total_demand
        assert len(rust.bottlenecks) == len(ref.bottlenecks)
        for a, b in zip(rust.bottlenecks, ref.bottlenecks):
            _assert_bottleneck_equal(a, b)


def test_identify_bottlenecks_none_short_circuits_match() -> None:
    assert ba.identify_bottlenecks(None, None) == _oracle_identify_bottlenecks(None, None)
    assert ba.identify_bottlenecks({}, None) == _oracle_identify_bottlenecks({}, None)
    assert ba.identify_bottlenecks(None, SimpleNamespace(routable_nets=5)) == _oracle_identify_bottlenecks(
        None, SimpleNamespace(routable_nets=5)
    )


def test_identify_bottlenecks_empty_dict_with_demand() -> None:
    dem = RoutingDemand(0, 120, 0, 0, 0, 0, 0.0, 0)
    rust = ba.identify_bottlenecks({}, dem)
    ref = _oracle_identify_bottlenecks({}, dem)
    assert rust == ref
    assert rust.bottlenecks == []
    assert rust.total_capacity == 0
    assert rust.total_demand == 120


# ---------------------------------------------------------------------------
# layer_capacity kernel
# ---------------------------------------------------------------------------


def test_calculate_layer_capacity_matches_reference_on_randomized_inputs() -> None:
    rng = random.Random(314159)
    for _ in range(400):
        grid = _stub_grid(rng)
        widths = _stub_widths(rng)
        mtw = rng.choice([0.0, 0.1, 0.127, 0.25])
        mc = rng.choice([0.0, 0.1, 0.127, 0.3])
        rust = lc.calculate_layer_capacity(grid, widths, mtw, mc)
        ref = _oracle_calculate_layer_capacity(grid, widths, mtw, mc)
        assert rust == ref, (grid, widths, mtw, mc)
        assert rust.estimated_traces == ref.estimated_traces


def test_calculate_layer_capacity_zero_edges() -> None:
    # avg width 0 -> no estimate
    grid = SimpleNamespace(layer_name="F.Cu", width_cells=10, height_cells=10,
                           free_cell_count=50, blocked_cell_count=50)
    widths = SimpleNamespace(min_width=0.0, avg_width=0.0)
    rust = lc.calculate_layer_capacity(grid, widths)
    ref = _oracle_calculate_layer_capacity(grid, widths)
    assert rust == ref
    assert rust.estimated_traces == 0

    # zero trace pitch -> no estimate
    widths2 = SimpleNamespace(min_width=1.0, avg_width=2.0)
    rust2 = lc.calculate_layer_capacity(grid, widths2, min_trace_width=0.0, min_clearance=0.0)
    ref2 = _oracle_calculate_layer_capacity(grid, widths2, min_trace_width=0.0, min_clearance=0.0)
    assert rust2 == ref2
    assert rust2.estimated_traces == 0

    # exact-fit pitch: traces_per_channel == 1 -> estimated >= 1
    widths3 = SimpleNamespace(min_width=0.5, avg_width=0.5)
    rust3 = lc.calculate_layer_capacity(grid, widths3, min_trace_width=0.1, min_clearance=0.2)
    ref3 = _oracle_calculate_layer_capacity(grid, widths3, min_trace_width=0.1, min_clearance=0.2)
    assert rust3 == ref3


# ---------------------------------------------------------------------------
# connectivity kernel
# ---------------------------------------------------------------------------

_LAYERSETS = [(0,), (1,), (0, 1), (2,), (0, 2)]


def _rand_pad(rng: random.Random, net: str, idx: int) -> CopperPad:
    layers = list(rng.choice(_LAYERSETS))
    shape = rng.choice(["circle", "rect", "oval", "roundrect"])
    w = rng.choice([0.5, 1.0, 1.5, 2.0])
    h = rng.choice([0.5, 1.0, 1.5, 2.0])
    return CopperPad(
        identity=PadIdentity(
            component_ref=f"C{idx}",
            pad=f"P{idx}",
            net=net,
            x=float(idx),
            y=float(idx * 7 % 13),
            layers=tuple(layers),
        ),
        center=Point(rng.uniform(-5, 5), rng.uniform(-5, 5)),
        shape=shape,
        size=(w, h),
        rotation=float(rng.choice([0, 30, 45, 90, 135, 270])),
    )


def _rand_track(rng: random.Random, net: str) -> CopperTrack:
    return CopperTrack(
        start=Point(rng.uniform(-5, 5), rng.uniform(-5, 5)),
        end=Point(rng.uniform(-5, 5), rng.uniform(-5, 5)),
        layer=rng.choice([0, 1, 2]),
        width=rng.choice([0.2, 0.5, 1.0]),
        net=net,
    )


def _rand_via(rng: random.Random, net: str) -> CopperVia:
    layers = frozenset(rng.choice(_LAYERSETS))
    return CopperVia(
        center=Point(rng.uniform(-5, 5), rng.uniform(-5, 5)),
        layers=layers,
        diameter=rng.choice([0.4, 0.6, 1.0]),
        net=net,
    )


def _rand_zone(rng: random.Random, net: str) -> CopperZone:
    from shapely.geometry import Polygon as _SPolygon

    cx = rng.uniform(-4, 4)
    cy = rng.uniform(-4, 4)
    s = rng.uniform(0.5, 2.0)
    return CopperZone(
        polygon=_SPolygon([(cx - s, cy - s), (cx + s, cy - s), (cx + s, cy + s), (cx - s, cy + s)]),
        layer=rng.choice([0, 1]),
        net=net,
    )


def _assert_connectivity_equal(actual: NetConnectivity, expected: NetConnectivity) -> None:
    assert actual == expected
    assert actual.connected_pad_count == expected.connected_pad_count
    assert actual.total_required_pad_count == expected.total_required_pad_count
    assert actual.disposition == expected.disposition
    assert actual.unresolved_islands == expected.unresolved_islands
    assert [c.pads for c in actual.components] == [c.pads for c in expected.components]


def test_verify_net_connectivity_matches_reference_on_randomized_inputs() -> None:
    rng = random.Random(271828)
    for trial in range(300):
        net = f"NET_{trial}"
        pads = [_rand_pad(rng, net, i) for i in range(rng.randint(0, 4))]
        tracks = [_rand_track(rng, net) for _ in range(rng.randint(0, 4))]
        vias = [_rand_via(rng, net) for _ in range(rng.randint(0, 3))]
        zones = [_rand_zone(rng, net) for _ in range(rng.randint(0, 2))]
        rust = verify_net_connectivity(pads, tracks, vias, zones)
        ref = _oracle_verify_net_connectivity(pads, tracks, vias, zones)
        _assert_connectivity_equal(rust, ref)


def test_verify_net_connectivity_crafted_predicates() -> None:
    # Two tracks whose midpoint distance is inside CONTACT_TOLERANCE of the
    # (w1+w2)/2 clearance -> touch.
    t1 = CopperTrack(start=Point(0, 0), end=Point(2, 0), layer=0, width=0.5, net="N")
    t2 = CopperTrack(start=Point(2.0, 0), end=Point(4, 0), layer=0, width=0.5, net="N")
    # t1 endpoint (2,0) == t2 endpoint (2,0): distance 0 <= clearance
    rust = verify_net_connectivity([], [t1, t2], [])
    ref = _oracle_verify_net_connectivity([], [t1, t2], [])
    _assert_connectivity_equal(rust, ref)

    # Two circle pads whose centers are 0.5 apart (w=1.0 -> half=0.5), so
    # each center lies exactly on the other's contact circle boundary.
    p1 = CopperPad(PadIdentity("C1", "P1", "N", 0.0, 0.0, (0,)), Point(0, 0), "circle", (1.0, 1.0))
    p2 = CopperPad(PadIdentity("C2", "P2", "N", 1.0, 0.0, (0,)), Point(0.5, 0.0), "circle", (1.0, 1.0))
    rust2 = verify_net_connectivity([p1, p2], [], [])
    ref2 = _oracle_verify_net_connectivity([p1, p2], [], [])
    _assert_connectivity_equal(rust2, ref2)
    assert rust2.disposition == conn.NetDisposition.ROUTED

    # Same point via-via -> points_touch on shared layer.
    v1 = CopperVia(Point(3, 3), frozenset((0, 1)), 0.6, "N")
    v2 = CopperVia(Point(3, 3), frozenset((0, 1)), 0.6, "N")
    rust3 = verify_net_connectivity([], [], [v1, v2])
    ref3 = _oracle_verify_net_connectivity([], [], [v1, v2])
    _assert_connectivity_equal(rust3, ref3)

    # Rotated rect pad: a track crossing the rotated box at 45 deg.
    pr = CopperPad(PadIdentity("C9", "P9", "N", 0.0, 0.0, (0,)), Point(0, 0), "rect", (2.0, 2.0),
                   rotation=45.0)
    tr = CopperTrack(start=Point(-3, 3), end=Point(3, -3), layer=0, width=0.2, net="N")
    rust4 = verify_net_connectivity([pr], [tr], [])
    ref4 = _oracle_verify_net_connectivity([pr], [tr], [])
    _assert_connectivity_equal(rust4, ref4)

    # Zone-pad containment (shapely predicates stay in Python): two pads
    # inside the same zone polygon -> joined via the zone -> ROUTED.
    from shapely.geometry import Polygon as _SPolygon

    zone = CopperZone(_SPolygon([(0, 0), (4, 0), (4, 4), (0, 4)]), 0, "N")
    pz = CopperPad(PadIdentity("C5", "P5", "N", 0.0, 0.0, (0,)), Point(2, 2), "circle", (0.5, 0.5))
    pz2 = CopperPad(PadIdentity("C6", "P6", "N", 1.0, 1.0, (0,)), Point(3, 2), "circle", (0.5, 0.5))
    rust5 = verify_net_connectivity([pz, pz2], [], [], [zone])
    ref5 = _oracle_verify_net_connectivity([pz, pz2], [], [], [zone])
    _assert_connectivity_equal(rust5, ref5)
    assert rust5.disposition == conn.NetDisposition.ROUTED


def test_verify_connectivity_by_net_never_joins_different_nets() -> None:
    """``verify_connectivity_by_net`` groups by net before verifying, so two
    different-net pads at the same position stay in separate results."""
    p_a = CopperPad(PadIdentity("C1", "P1", "A", 0.0, 0.0, (0,)), Point(0, 0), "circle", (1.0, 1.0))
    p_b = CopperPad(PadIdentity("C2", "P2", "B", 0.0, 0.0, (0,)), Point(0, 0), "circle", (1.0, 1.0))
    by_net = conn.verify_connectivity_by_net([p_a, p_b], [], [])
    assert set(by_net) == {"A", "B"}
    for result in by_net.values():
        assert result.total_required_pad_count == 1
        assert result.disposition == conn.NetDisposition.INCOMPLETE
        assert len(result.components) == 1


def test_connectivity_empty_inputs() -> None:
    rust = verify_net_connectivity([], [], [])
    ref = _oracle_verify_net_connectivity([], [], [])
    _assert_connectivity_equal(rust, ref)
    assert rust.net == ""
    assert rust.total_required_pad_count == 0


# ---------------------------------------------------------------------------
# obstacle_map circle-buffer kernel
# ---------------------------------------------------------------------------


def test_circle_buffer_kernel_matches_reference_on_randomized_inputs() -> None:
    rng = random.Random(161803)
    for _ in range(300):
        cx = rng.uniform(-100, 100)
        cy = rng.uniform(-100, 100)
        r = rng.uniform(1e-3, 20.0)
        rust_ring = om._circle_buffer_ring(cx, cy, r, 8)
        ref_ring = _oracle_circle_buffer_ring(cx, cy, r, 8)
        assert rust_ring == ref_ring
        for (ax, ay), (bx, by) in zip(rust_ring, ref_ring):
            assert ax.hex() == bx.hex() and ay.hex() == by.hex()


def test_circle_buffer_kernel_cardinal_points_snap() -> None:
    # The cardinal points must be exactly 0.0 (GEOS sinCosSnap), not the
    # libm residual ~1e-17.
    ring = om._circle_buffer_ring(0.0, 0.0, 0.125, 8)
    ref = _oracle_circle_buffer_ring(0.0, 0.0, 0.125, 8)
    assert ring == ref
    assert len(ring) == 33  # 32 distinct + closure
    # k=0 -> (+r, 0); k=8 -> (0, -r); k=16 -> (-r, 0); k=24 -> (0, +r)
    assert ring[0] == (0.125, 0.0)
    assert ring[8] == (0.0, -0.125)
    assert ring[16] == (-0.125, 0.0)
    assert ring[24] == (0.0, 0.125)
    assert ring[-1] == ring[0]


def test_circle_buffer_kernel_nonpositive_radius_is_empty() -> None:
    assert om._circle_buffer_ring(1.0, 2.0, 0.0, 8) == []
    assert om._circle_buffer_ring(1.0, 2.0, -0.5, 8) == []
    assert om._circle_buffer_ring(1.0, 2.0, -0.0, 8) == []


def test_build_obstacle_map_via_circles_match_reference() -> None:
    """End-to-end: escape vias land in the obstacle map with the same ring
    coordinates as the pre-migration ``Point.buffer``."""
    from shapely.geometry import Point as _SPoint

    rng = random.Random(20260810)
    for _ in range(40):
        x = rng.uniform(-50, 50)
        y = rng.uniform(-50, 50)
        d = rng.uniform(0.2, 3.0)
        ring = om._circle_buffer_ring(x, y, d / 2.0, 8)
        ref_ring = list(_SPoint(x, y).buffer(d / 2.0, quad_segs=8).exterior.coords)
        assert ring == ref_ring


def test_kernels_are_registered() -> None:
    """Smoke check that this unit's kernels are live in the loaded
    ``temper_geometry`` extension (the shims fail loudly with
    AttributeError otherwise, but this pins the five names together)."""
    for name in (
        "classify_severity_py",
        "identify_bottlenecks_py",
        "estimate_traces_py",
        "connectivity_components_py",
        "circle_buffer_ring_py",
    ):
        assert hasattr(_tg, name), f"temper_geometry missing {name}"
