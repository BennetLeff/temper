"""Canonical, layer-aware copper connectivity for Router V6.

This is a preflight graph over emitted copper primitives.  It deliberately
does not infer plane or exemption status from a net name: those dispositions
require a typed adapter once the relevant copper has been emitted and checked.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from temper_placer.router_v6.constraints_geometry import (
    LineSegment,
    Point,
    point_to_segment_distance,
    segment_to_segment_distance,
)

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
) -> NetConnectivity:
    """Return the deterministic all-pad connectivity result for one net.

    Tracks join only on a shared layer.  Vias join only the layers in their
    explicit span; pads can be reached only on their declared conductive
    layers.  Consequently, same-XY SMD copper on different layers is never a
    connection by itself.
    """
    ordered_pads = tuple(sorted(pads, key=lambda pad: pad.identity))
    ordered_tracks = tuple(sorted(tracks, key=_track_key))
    ordered_vias = tuple(sorted(vias, key=_via_key))
    net = ordered_pads[0].identity.net if ordered_pads else ""

    items: tuple[object, ...] = (*ordered_pads, *ordered_tracks, *ordered_vias)
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

    for left, track in enumerate(ordered_tracks):
        for right in range(left + 1, len(ordered_tracks)):
            other = ordered_tracks[right]
            if track.layer == other.layer and _tracks_touch(track, other):
                union(track_start + left, track_start + right)
        for pad_index, pad in enumerate(ordered_pads):
            if track.layer in pad.layers and _track_touches_pad(track, pad):
                union(track_start + left, pad_index)
        for via_index, via in enumerate(ordered_vias):
            if track.layer in via.layers and _track_touches_via(track, via):
                union(track_start + left, via_start + via_index)

    for left, pad in enumerate(ordered_pads):
        for right in range(left + 1, len(ordered_pads)):
            other = ordered_pads[right]
            if pad.layers & other.layers and _pads_touch(pad, other):
                union(left, right)

    for left, via in enumerate(ordered_vias):
        for right in range(left + 1, len(ordered_vias)):
            other = ordered_vias[right]
            if via.layers & other.layers and _points_touch(via.center, other.center):
                union(via_start + left, via_start + right)
        for pad_index, pad in enumerate(ordered_pads):
            if via.layers & pad.layers and _via_touches_pad(via, pad):
                union(via_start + left, pad_index)

    pad_components: dict[int, list[PadIdentity]] = {}
    for pad_index, pad in enumerate(ordered_pads):
        pad_components.setdefault(find(pad_index), []).append(pad.identity)
    component_pads = [tuple(sorted(component)) for component in pad_components.values()]
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
    pads: Iterable[CopperPad], tracks: Iterable[CopperTrack], vias: Iterable[CopperVia]
) -> dict[str, NetConnectivity]:
    """Verify each net independently; mixed-net copper is never joined."""
    pad_groups: dict[str, list[CopperPad]] = {}
    track_groups: dict[str, list[CopperTrack]] = {}
    via_groups: dict[str, list[CopperVia]] = {}
    for pad in pads:
        pad_groups.setdefault(pad.identity.net, []).append(pad)
    for track in tracks:
        track_groups.setdefault(track.net, []).append(track)
    for via in vias:
        via_groups.setdefault(via.net, []).append(via)
    net_names = pad_groups.keys() | track_groups.keys() | via_groups.keys()
    return {
        net: verify_net_connectivity(
            pad_groups.get(net, ()), track_groups.get(net, ()), via_groups.get(net, ())
        )
        for net in sorted(net_names)
    }


def _track_key(track: CopperTrack) -> tuple[int, float, float, float, float, float]:
    return (track.layer, track.start.x, track.start.y, track.end.x, track.end.y, track.width)


def _via_key(via: CopperVia) -> tuple[float, float, tuple[int, ...], float]:
    return (via.center.x, via.center.y, tuple(sorted(via.layers)), via.diameter)


def _tracks_touch(left: CopperTrack, right: CopperTrack) -> bool:
    clearance = (left.width + right.width) / 2 + CONTACT_TOLERANCE_MM
    return segment_to_segment_distance(left.segment, right.segment) <= clearance


def _track_touches_via(track: CopperTrack, via: CopperVia) -> bool:
    return point_to_segment_distance(via.center, track.segment) <= (
        track.width / 2 + via.diameter / 2 + CONTACT_TOLERANCE_MM
    )


def _track_touches_pad(track: CopperTrack, pad: CopperPad) -> bool:
    return _segment_touches_pad(track.segment, pad, track.width / 2)


def _via_touches_pad(via: CopperVia, pad: CopperPad) -> bool:
    return _point_in_pad(via.center, pad, via.diameter / 2)


def _pads_touch(left: CopperPad, right: CopperPad) -> bool:
    return _point_in_pad(left.center, right) or _point_in_pad(right.center, left)


def _segment_touches_pad(segment: LineSegment, pad: CopperPad, radius: float) -> bool:
    if pad.shape == "circle":
        return point_to_segment_distance(pad.center, segment) <= pad.size[0] / 2 + radius + CONTACT_TOLERANCE_MM
    start = _to_pad_coordinates(segment.start, pad)
    end = _to_pad_coordinates(segment.end, pad)
    half_x, half_y = pad.size[0] / 2 + radius, pad.size[1] / 2 + radius
    return _segment_intersects_box(start, end, half_x, half_y)


def _point_in_pad(point: Point, pad: CopperPad, radius: float = 0.0) -> bool:
    # Rotation is intentionally handled here rather than with a global
    # coordinate threshold.  Ovals use their bounding ellipse, a conservative
    # representation until the KiCad shape adapter is introduced.
    local_x, local_y = _to_pad_coordinates(point, pad)
    half_x, half_y = pad.size[0] / 2 + radius, pad.size[1] / 2 + radius
    if pad.shape == "circle":
        return local_x * local_x + local_y * local_y <= half_x * half_x + CONTACT_TOLERANCE_MM
    return abs(local_x) <= half_x + CONTACT_TOLERANCE_MM and abs(local_y) <= half_y + CONTACT_TOLERANCE_MM


def _to_pad_coordinates(point: Point, pad: CopperPad) -> tuple[float, float]:
    from math import cos, radians, sin

    angle = radians(-pad.rotation)
    dx, dy = point.x - pad.center.x, point.y - pad.center.y
    return dx * cos(angle) - dy * sin(angle), dx * sin(angle) + dy * cos(angle)


def _segment_intersects_box(start: tuple[float, float], end: tuple[float, float], half_x: float, half_y: float) -> bool:
    """Liang-Barsky clipping against pad-local rectangular copper."""
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


def _points_touch(left: Point, right: Point) -> bool:
    return left.distance_to(right) <= CONTACT_TOLERANCE_MM
