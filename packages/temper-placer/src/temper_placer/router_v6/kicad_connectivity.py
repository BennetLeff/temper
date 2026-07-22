"""Parse emitted KiCad PCB content into connectivity-verifier inputs.

Post-write preflight for U4: without deleting the stitch/plane-MST
workarounds, demote nets whose emitted copper does not constitute a
legal all-pad component.  The verdict is recorded in
``RoutingResults.connectivity`` so U3's truthful completion reporting
inspects it.
"""

from __future__ import annotations

import re

from temper_placer.router_v6.connectivity import (
    CopperPad,
    CopperTrack,
    CopperVia,
    CopperZone,
    NetConnectivity,
    PadIdentity,
    Point,
    verify_net_connectivity,
)

_ZONE_RE = re.compile(
    r'\(zone\s+\(net\s+(\d+)\)\s+\(net_name\s+"([^"]+)"\)'
    r'\s+\(layer\s+"([^"]+)"\)',
)

_SEGMENT_RE = re.compile(
    r"\(segment\s+\(start\s+([-\d.]+)\s+([-\d.]+)\)"
    r"\s+\(end\s+([-\d.]+)\s+([-\d.]+)\)"
    r"\s+\(width\s+([-\d.]+)\)"
    r'\s+\(layer\s+"([^"]+)"\)'
    r"\s+\(net\s+(\d+)\)"
)

_VIA_RE = re.compile(
    r"\(via\s+\(at\s+([-\d.]+)\s+([-\d.]+)\)"
    r"\s+\(size\s+([-\d.]+)\)"
    r"\s+\(drill\s+([-\d.]+)\)"
    r'\s+\(layers\s+"([^"]+)"\s+"([^"]+)"\)'
    r"\s+\(net\s+(\d+)\)"
)

_NET_NAME_RE = re.compile(r'\(net\s+(\d+)\s+"([^"]+)"')


def _build_net_name_map(pcb_content: str) -> dict[int, str]:
    return {int(m.group(1)): m.group(2) for m in _NET_NAME_RE.finditer(pcb_content)}


def _layer_id(layer_name: str) -> int:
    return 0 if layer_name == "F.Cu" else 1  # coarse; full stackup deferred


def _segment_connectivity(pcb_content: str, pad_positions: dict[str, list[tuple[float, float]]]) -> dict[str, NetConnectivity]:
    """Parse emitted content, extract tracks/vias per net, and verify connectivity.

    Pad shape and rotation are NOT available from the writer's
    pad-position map, so ``CopperPad`` objects carry best-effort identity
    and a default 1.0×1.0 mm rectangular shape.  This is sufficient for
    contact detection (track endpoint within pad bounding box) but does
    not model partial overlap.
    """
    net_name_map = _build_net_name_map(pcb_content)
    segments_by_net: dict[int, list[CopperTrack]] = {}
    for m in _SEGMENT_RE.finditer(pcb_content):
        x1, y1, x2, y2, width, layer, net_num = m.groups()
        net_num = int(net_num)
        segments_by_net.setdefault(net_num, []).append(
            CopperTrack(
                net=net_name_map.get(net_num, str(net_num)),
                start=Point(float(x1), float(y1)),
                end=Point(float(x2), float(y2)),
                width=float(width),
                layer=_layer_id(layer),
            )
        )

    # Parse real (via ...) s-expressions emitted by the writer
    # (adapter.py:_write_routes_to_content emits these for compiled routes).
    vias_by_net: dict[int, list[CopperVia]] = {}
    for m in _VIA_RE.finditer(pcb_content):
        x, y, size, drill, layer_from, layer_to, net_num = m.groups()
        net_num = int(net_num)
        vias_by_net.setdefault(net_num, []).append(
            CopperVia(
                net=net_name_map.get(net_num, str(net_num)),
                center=Point(float(x), float(y)),
                diameter=float(size),
                layers=frozenset((_layer_id(layer_from), _layer_id(layer_to))),
            )
        )

    # U5: parse zone/pour polygons from emitted content
    # U5: parse zone/pour polygons from emitted content.
    # Extract xy points from (polygon (pts ...)) blocks, using the
    # surrounding zone context to determine net/layer.
    zones_by_net: dict[int, list[CopperZone]] = {}
    for m in _ZONE_RE.finditer(pcb_content):
        net_num = int(m.group(1))
        layer_name = m.group(3)
        # Find the polygon block: search forward from the zone header
        # for "(polygon", then find the matching "))".
        start = m.end()
        poly_start = pcb_content.find("(polygon", start)
        if poly_start < 0:
            continue
        poly_end = pcb_content.find("))", poly_start)
        if poly_end < 0:
            continue
        poly_block = pcb_content[poly_start:poly_end + 2]
        xy_pts = re.findall(r"\(xy\s+([-\d.]+)\s+([-\d.]+)\)", poly_block)
        if len(xy_pts) < 3:
            continue
        from shapely.geometry import MultiPolygon, Polygon as ShapelyPolygon
        try:
            poly = ShapelyPolygon([(float(x), float(y)) for x, y in xy_pts])
            if not poly.is_valid:
                fixed = poly.buffer(0)
                if isinstance(fixed, MultiPolygon):
                    fixed = max(fixed.geoms, key=lambda g: g.area)
                poly = fixed
        except (ValueError, TypeError):
            continue
        if not isinstance(poly, ShapelyPolygon) or poly.is_empty:
            continue
        zones_by_net.setdefault(net_num, []).append(
            CopperZone(
                polygon=poly,
                layer=_layer_id(layer_name),
                net=net_name_map.get(net_num, str(net_num)),
            )
        )

    results: dict[str, NetConnectivity] = {}
    for net_name, positions in pad_positions.items():
        # Find the net number for this net name
        net_num = next((n for n, name in net_name_map.items() if name == net_name), None)
        tracks = segments_by_net.get(net_num, []) if net_num else []
        via_list = vias_by_net.get(net_num, []) if net_num else []
        zone_list = zones_by_net.get(net_num, []) if net_num else []

        # Best-effort CopperPad: default rect, no rotation.
        # Layer (0, 1) = both F.Cu and B.Cu — the preflight does not
        # know the SMD/PTH status of each pad, so it conservatively
        # treats every pad as reachable on either layer.  This avoids
        # false INCOMPLETE verdicts on legitimate B.Cu connections
        # (PR #237's netclass assignments will route there).
        pads = [
            CopperPad(
                identity=PadIdentity(component_ref="", pad=str(i), net=net_name, x=x, y=y, layers=(0, 1)),
                center=Point(x, y),
                shape="rect",
                size=(1.0, 1.0),
            )
            for i, (x, y) in enumerate(positions)
        ]

        results[net_name] = verify_net_connectivity(
            pads=tuple(pads), tracks=tracks, vias=via_list, zones=tuple(zone_list),
        )

    return results


def connectivity_preflight(
    pcb_content: str,
    pad_positions: dict[str, list[tuple[float, float]]],
) -> dict[str, NetConnectivity]:
    """Post-write connectivity check — demotes incomplete nets without removing
    the stitch/plane-MST workarounds (U4 preflight).

    Returns a dict suitable for ``RoutingResults.connectivity``.
    """
    return _segment_connectivity(pcb_content, pad_positions)
