"""Canonical, layer-aware copper connectivity for Router V6.

This is a preflight graph over emitted copper primitives.  It deliberately
does not infer plane or exemption status from a net name: those dispositions
require a typed adapter once the relevant copper has been emitted and checked.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

import temper_geometry as _tg
from shapely.geometry import LineString as ShapelyLineString
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry import Polygon as ShapelyPolygon

from temper_placer.router_v6.constraints_geometry import LineSegment, Point

CONTACT_TOLERANCE_MM = 1e-4


class NetDisposition(StrEnum):
    ROUTED = "routed"
    INCOMPLETE = "incomplete"
    PLANE_CONNECTED = "plane_connected"
    EXEMPT = "exempt"
    FAILED = "failed"


@dataclass(frozen=True, order=True)
class PadIdentity:
    """Stable identity used in output diagnostics, independent of object IDs."""

    component_ref: str
    pad: str
    net: str
    x: float
    y: float
    layers: tuple[int, ...]


@dataclass(frozen=True)
class CopperPad:
    identity: PadIdentity
    center: Point
    shape: str
    size: tuple[float, float]
    rotation: float = 0.0

    @property
    def layers(self) -> frozenset[int]:
        return frozenset(self.identity.layers)


def _to_pad_coordinates(point: Point, pad: CopperPad) -> tuple[float, float]:
    """World point -> pad-local frame.

    Verbatim pre-migration implementation (kept Python, test-only helper):
    the Rust `connectivity_kernels.rs::to_pad_coordinates` uses the opposite
    rotation sign (R(+theta) internally, pinned by the connectivity
    differential), which does not match this helper's `R(-rotation)`
    convention. This function has no production callers -- it exists for the
    rotation-convention test oracle -- so it stays Python verbatim rather
    than delegating to a sign-divergent kernel.
    """
    from math import cos, radians, sin

    angle = radians(-pad.rotation)
    dx, dy = point.x - pad.center.x, point.y - pad.center.y
    return dx * cos(angle) - dy * sin(angle), dx * sin(angle) + dy * cos(angle)


@dataclass(frozen=True)
class CopperTrack:
    start: Point
    end: Point
    layer: int
    width: float = 0.0
    net: str = ""

    @property
    def segment(self) -> LineSegment:
        return LineSegment(self.start, self.end)


@dataclass(frozen=True)
class CopperVia:
    center: Point
    layers: frozenset[int]
    diameter: float = 0.0
    net: str = ""


@dataclass(frozen=True)
class CopperZone:
    """A copper pour/zone polygon for connectivity verification (U5)."""

    polygon: ShapelyPolygon
    layer: int
    net: str = ""


@dataclass(frozen=True)
class ConnectivityComponent:
    """One connected copper component, represented by its required pads."""

    pads: tuple[PadIdentity, ...]


@dataclass(frozen=True)
class NetConnectivity:
    net: str
    disposition: NetDisposition
    connected_pad_count: int
    total_required_pad_count: int
    components: tuple[ConnectivityComponent, ...]
    unresolved_islands: tuple[tuple[PadIdentity, ...], ...]
    reason: str | None = None

    @property
    def connected_pad_ids(self) -> tuple[PadIdentity, ...]:
        return self.components[0].pads if self.components else ()


def verify_net_connectivity(
    pads: Iterable[CopperPad],
    tracks: Iterable[CopperTrack],
    vias: Iterable[CopperVia],
    zones: Iterable[CopperZone] = (),
) -> NetConnectivity:
    """Return the deterministic all-pad connectivity result for one net.

    Tracks join only on a shared layer.  Vias join only the layers in their
    explicit span; pads can be reached only on their declared conductive
    layers; zones connect to pads/tracks/vias/zones they touch (U5).

    Wave 4 migration note: the union-find kernel and the ten
    pad/track/via touch predicates run in ``temper-geometry``'s
    ``connectivity_kernels`` (bit-exact — the predicates reuse the same
    ``drc_constraints_geometry`` / ``primitives`` kernels the pre-migration
    reference called through ``constraints_geometry`` / ``Point.distance_to``).
    The four ``_zone_*`` predicates are JUSTIFIED-KEEP: they are GEOS
    ``contains``/``touches``/``intersects`` calls on ``CopperZone.polygon``
    (see ``docs/evidence/2026-08-04-geos-polygon-algebra-spike.md``), so
    this shim still evaluates them and feeds the resulting (i, j) union
    pairs to the Rust kernel — the final connected-component partition is
    union-order independent, so parity is exact.  Pinned by
    ``test_spatial_tier2_rust_differential.py``.
    """
    ordered_pads = tuple(sorted(pads, key=lambda pad: pad.identity))
    ordered_tracks = tuple(sorted(tracks, key=_track_key))
    ordered_vias = tuple(sorted(vias, key=_via_key))
    ordered_zones = tuple(sorted(zones, key=lambda z: (z.layer, z.net)))
    net = ordered_pads[0].identity.net if ordered_pads else ""

    pad_count = len(ordered_pads)
    track_start = pad_count
    via_start = track_start + len(ordered_tracks)
    zone_start = via_start + len(ordered_vias)

    pad_flat: list[float] = []
    pad_shapes: list[int] = []
    pad_layers: list[list[int]] = []
    for pad in ordered_pads:
        pad_flat.extend([pad.center.x, pad.center.y, pad.rotation, pad.size[0], pad.size[1]])
        pad_shapes.append(1 if pad.shape == "circle" else 0)
        pad_layers.append(list(pad.layers))

    track_flat: list[float] = []
    track_layers: list[int] = []
    for track in ordered_tracks:
        track_flat.extend([track.start.x, track.start.y, track.end.x, track.end.y, track.width])
        track_layers.append(int(track.layer))

    via_flat: list[float] = []
    via_layers: list[list[int]] = []
    for via in ordered_vias:
        via_flat.extend([via.center.x, via.center.y, via.diameter])
        via_layers.append(list(via.layers))

    zone_pairs = _zone_union_pairs(
        ordered_zones,
        ordered_pads,
        ordered_tracks,
        ordered_vias,
        track_start,
        via_start,
        zone_start,
    )
    total_items = zone_start + len(ordered_zones)

    component_pad_lists = _tg.connectivity_components_py(
        pad_flat,
        pad_shapes,
        pad_layers,
        track_flat,
        track_layers,
        via_flat,
        via_layers,
        [(int(i), int(j)) for i, j in zone_pairs],
        int(total_items),
    )

    component_pads = [
        tuple(ordered_pads[pad_index].identity for pad_index in group)
        for group in component_pad_lists
    ]
    component_pads.sort(key=lambda component: (-len(component), component))
    components = tuple(ConnectivityComponent(component) for component in component_pads)
    primary = component_pads[0] if component_pads else ()
    disposition = (
        NetDisposition.ROUTED
        if len(component_pads) == 1 and len(primary) >= 2
        else NetDisposition.INCOMPLETE
    )
    return NetConnectivity(
        net=net,
        disposition=disposition,
        connected_pad_count=len(primary),
        total_required_pad_count=len(ordered_pads),
        components=components,
        unresolved_islands=tuple(component_pads[1:]),
        reason=None if disposition is NetDisposition.ROUTED else "disconnected_required_pads",
    )


def verify_connectivity_by_net(
    pads: Iterable[CopperPad],
    tracks: Iterable[CopperTrack],
    vias: Iterable[CopperVia],
    zones: Iterable[CopperZone] = (),
) -> dict[str, NetConnectivity]:
    """Verify each net independently; mixed-net copper is never joined."""
    pad_groups: dict[str, list[CopperPad]] = {}
    track_groups: dict[str, list[CopperTrack]] = {}
    via_groups: dict[str, list[CopperVia]] = {}
    zone_groups: dict[str, list[CopperZone]] = {}
    for pad in pads:
        pad_groups.setdefault(pad.identity.net, []).append(pad)
    for track in tracks:
        track_groups.setdefault(track.net, []).append(track)
    for via in vias:
        via_groups.setdefault(via.net, []).append(via)
    for zone in zones:
        zone_groups.setdefault(zone.net, []).append(zone)
    net_names = pad_groups.keys() | track_groups.keys() | via_groups.keys() | zone_groups.keys()
    return {
        net: verify_net_connectivity(
            pad_groups.get(net, ()),
            track_groups.get(net, ()),
            via_groups.get(net, ()),
            zone_groups.get(net, ()),
        )
        for net in sorted(net_names)
    }


def _track_key(track: CopperTrack) -> tuple[int, float, float, float, float, float]:
    return (track.layer, track.start.x, track.start.y, track.end.x, track.end.y, track.width)


def _via_key(via: CopperVia) -> tuple[float, float, tuple[int, ...], float]:
    return (via.center.x, via.center.y, tuple(sorted(via.layers)), via.diameter)


# --- U5: zone/pour touch predicates (JUSTIFIED-KEEP, shapely/GEOS) ---
#
# The four ``_zone_*`` predicates are GEOS calls on ``CopperZone.polygon``
# (``contains``/``touches``/``intersects``).  Bit-exact reproduction of
# GEOS predicate output is a "vendor GEOS" bar
# (docs/evidence/2026-08-04-geos-polygon-algebra-spike.md), so they stay in
# Python; ``_zone_union_pairs`` turns their results into (i, j) union pairs
# that ``connectivity_components_py`` applies inside the Rust kernel.  The
# pad/track/via touch predicates that used to sit between here and the
# union-find are migrated (``connectivity_kernels.rs``).


def _zone_touches_pad(zone: CopperZone, pad: CopperPad) -> bool:
    """Pad center or bounding box overlaps zone polygon."""
    if zone.layer not in pad.layers:
        return False
    pt = ShapelyPoint(pad.center.x, pad.center.y)
    return zone.polygon.contains(pt) or zone.polygon.touches(pt)


def _zone_touches_track(zone: CopperZone, track: CopperTrack) -> bool:
    """Track segment intersects or is contained by zone polygon."""
    if zone.layer != track.layer:
        return False
    seg = ShapelyLineString(
        [
            (track.start.x, track.start.y),
            (track.end.x, track.end.y),
        ]
    )
    return zone.polygon.intersects(seg)


def _zones_touch(left: CopperZone, right: CopperZone) -> bool:
    """Two zone polygons overlap."""
    if left.layer != right.layer:
        return False
    return left.polygon.intersects(right.polygon) and not left.polygon.touches(right.polygon)


def _zone_touches_via(zone: CopperZone, via: CopperVia) -> bool:
    """Via center is inside zone polygon."""
    if zone.layer not in via.layers:
        return False
    pt = ShapelyPoint(via.center.x, via.center.y)
    return zone.polygon.contains(pt) or zone.polygon.touches(pt)


def _zone_union_pairs(
    ordered_zones: tuple[CopperZone, ...],
    ordered_pads: tuple[CopperPad, ...],
    ordered_tracks: tuple[CopperTrack, ...],
    ordered_vias: tuple[CopperVia, ...],
    track_start: int,
    via_start: int,
    zone_start: int,
) -> list[tuple[int, int]]:
    """Zone-connectivity union pairs in the reference's emission order.

    Mirrors the reference's zone loops in ``verify_net_connectivity``:
    zone-zone, zone-pad, zone-track and zone-via unions, with the same
    layer guards, expressed as absolute item indices.  The union-find
    partition is independent of application order, so handing these pairs
    to the Rust kernel is exact.
    """
    pairs: list[tuple[int, int]] = []
    for left, zone in enumerate(ordered_zones):
        for right in range(left + 1, len(ordered_zones)):
            if _zones_touch(zone, ordered_zones[right]):
                pairs.append((zone_start + left, zone_start + right))
        for pad_index, pad in enumerate(ordered_pads):
            if _zone_touches_pad(zone, pad):
                pairs.append((zone_start + left, pad_index))
        for track_index, track in enumerate(ordered_tracks):
            if _zone_touches_track(zone, track):
                pairs.append((zone_start + left, track_start + track_index))
        for via_index, via in enumerate(ordered_vias):
            if zone.layer in via.layers and _zone_touches_via(zone, via):
                pairs.append((zone_start + left, via_start + via_index))
    return pairs
