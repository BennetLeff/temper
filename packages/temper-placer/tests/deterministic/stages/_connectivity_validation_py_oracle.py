"""VERBATIM pre-migration oracle for the connectivity_validation leaf kernel.

Wave 4, Phase 5, batch 2 (deterministic leaf stages). Pinned from the
pre-migration ``deterministic/stages/connectivity_validation.py`` at the
dispatch base (origin/main): the ``ConnectivityValidationStage`` per-net
connectivity algorithm (UnionFind + touch predicates + component
classification + dangling-track scan), with the `run`-level orchestration
(drc_oracle geometry extraction, per-net grouping, plane-net skipping,
logging, ``fail_on_violations`` raising) intentionally omitted.

The helpers are transcribed verbatim from the pre-migration module
(``_tracks_touch`` / ``_track_touches_via`` / ``_track_touches_pad`` /
``_via_touches_pad`` / ``_point_touches_item`` / ``_get_item_location``).

Do NOT edit: this file is the Python arm of the differentials. If it drifts,
the differentials prove nothing.
"""

from dataclasses import dataclass

from temper_placer.core.topology import UnionFind
from temper_placer.router_v6.constraints_geometry import (
    Point,
    point_to_rotated_rect_distance,
)
from temper_placer.router_v6.constraints_spatial_index import Pad, Track, Via


@dataclass
class Violation:
    type: str
    net: str
    location: Point
    description: str


def validate_net(net_name: str, pads, tracks, vias) -> list[Violation]:
    """The ``ConnectivityValidationStage._validate_net_connectivity`` body."""
    all_items = pads + tracks + vias
    if not all_items:
        return []

    item_to_id = {id(item): i for i, item in enumerate(all_items)}
    id_to_item = dict(enumerate(all_items))

    uf = UnionFind()
    for i in range(len(all_items)):
        uf.find(i)

    # 1. Check Track-Track connectivity
    for i, t1 in enumerate(tracks):
        for t2 in tracks[i + 1 :]:
            if tracks_touch(t1, t2):
                uf.union(item_to_id[id(t1)], item_to_id[id(t2)])

    # 2. Check Track-Via connectivity
    for t in tracks:
        for v in vias:
            if track_touches_via(t, v):
                uf.union(item_to_id[id(t)], item_to_id[id(v)])

    # 3. Check Track-Pad connectivity
    for t in tracks:
        for p in pads:
            if track_touches_pad(t, p):
                uf.union(item_to_id[id(t)], item_to_id[id(p)])

    # 4. Check Via-Pad connectivity
    for v in vias:
        for p in pads:
            if via_touches_pad(v, p):
                uf.union(item_to_id[id(v)], item_to_id[id(p)])

    # 5. Check Via-Via connectivity (stacking)
    for i, v1 in enumerate(vias):
        for v2 in vias[i + 1 :]:
            if v1.center == v2.center:
                uf.union(item_to_id[id(v1)], item_to_id[id(v2)])

    violations = []

    components = uf.get_components()
    components_with_pads = {}
    components_without_pads = {}

    for root, members in components.items():
        island_pads = [id_to_item[m] for m in members if isinstance(id_to_item[m], Pad)]
        if island_pads:
            components_with_pads[root] = island_pads
        else:
            components_without_pads[root] = members

    # 1. Report all copper islands with no pads as orphans
    for _root, members in components_without_pads.items():
        rep_item = id_to_item[members[0]]
        loc = get_item_location(rep_item)
        violations.append(
            Violation(
                type="orphan_island",
                net=net_name,
                location=loc,
                description=f"Isolated copper island for net {net_name} with no pads",
            )
        )

    # 2. If there are multiple islands with pads, report them as unconnected
    if len(components_with_pads) > 1:
        sorted_roots = sorted(
            components_with_pads.keys(),
            key=lambda r: (len(components_with_pads[r]), r),
            reverse=True,
        )
        for root in sorted_roots[1:]:
            island_pads = components_with_pads[root]
            loc = island_pads[0].center
            violations.append(
                Violation(
                    type="unconnected_pad",
                    net=net_name,
                    location=loc,
                    description=(
                        f"Pad {island_pads[0].id} and {len(island_pads) - 1} others "
                        f"are not connected to the main group of net {net_name}"
                    ),
                )
            )

    # Check for dangling tracks
    for t in tracks:
        start_connected = False
        end_connected = False

        for other in all_items:
            if other is t:
                continue
            if point_touches_item(t.start, other, exclude_track=t):
                start_connected = True
                break

        for other in all_items:
            if other is t:
                continue
            if point_touches_item(t.end, other, exclude_track=t):
                end_connected = True
                break

        if not start_connected or not end_connected:
            violations.append(
                Violation(
                    type="dangling_track",
                    net=net_name,
                    location=t.start if not start_connected else t.end,
                    description=f"Track segment in net {net_name} has a dangling endpoint",
                )
            )

    return violations


def tracks_touch(t1: Track, t2: Track) -> bool:
    if t1.layer != t2.layer:
        return False
    return t1.start == t2.start or t1.start == t2.end or t1.end == t2.start or t1.end == t2.end


def track_touches_via(t: Track, v: Via) -> bool:
    return t.start == v.center or t.end == v.center


def track_touches_pad(t: Track, p: Pad) -> bool:
    if t.layer != p.layer:
        return False
    return (
        point_to_rotated_rect_distance(t.start, p.rot_rect) <= 1e-4
        or point_to_rotated_rect_distance(t.end, p.rot_rect) <= 1e-4
    )


def via_touches_pad(v: Via, p: Pad) -> bool:
    return point_to_rotated_rect_distance(v.center, p.rot_rect) <= 1e-4


def point_touches_item(pt: Point, item, exclude_track: Track | None = None) -> bool:
    if isinstance(item, Track):
        if exclude_track and item.layer != exclude_track.layer:
            return False
        return pt == item.start or pt == item.end
    if isinstance(item, Via):
        return pt == item.center
    if isinstance(item, Pad):
        if exclude_track and item.layer != exclude_track.layer:
            return False
        return point_to_rotated_rect_distance(pt, item.rot_rect) <= 1e-4
    return False


def get_item_location(item) -> Point:
    if hasattr(item, "center"):
        return item.center
    if hasattr(item, "start"):
        return item.start
    return Point(0, 0)
