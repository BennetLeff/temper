"""Parse emitted KiCad PCB content into connectivity-verifier inputs.

Post-write preflight for U4: without deleting the stitch/plane-MST
workarounds, demote nets whose emitted copper does not constitute a
legal all-pad component.  The verdict is recorded in
``RoutingResults.connectivity`` so U3's truthful completion reporting
inspects it.
"""

from __future__ import annotations

import re
from typing import Any

from temper_placer.geometry.pad_world import pad_world_rotation_deg
from temper_placer.router_v6.connectivity import (
    CopperPad,
    CopperTrack,
    CopperVia,
    CopperZone,
    NetConnectivity,
    PadIdentity,
    Point,
    verify_net_connectivity,
    verify_net_route_result,
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

# `(at X Y)` inside a paren-balanced via block (the audit's `_VIA_AT_RE`).
_VIA_AT_RE = re.compile(r"\(at\s+([-\d.]+)\s+([-\d.]+)\)")
# Bare `"name"` tokens inside a layers list (the audit's `_LAYER_NAME_RE`).
_LAYER_NAME_RE = re.compile(r'"([^"]+)"')

_NET_NAME_RE = re.compile(r'\(net\s+(\d+)\s+"([^"]+)"')


def _build_net_name_map(pcb_content: str) -> dict[int, str]:
    return {int(m.group(1)): m.group(2) for m in _NET_NAME_RE.finditer(pcb_content)}


def _layer_id(layer_name: str) -> int:
    return 0 if layer_name == "F.Cu" else 1  # coarse; full stackup deferred


def _segment_connectivity(
    pcb_content: str, pad_positions: dict[str, list[tuple[float, float]]]
) -> dict[str, NetConnectivity]:
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
        poly_block = pcb_content[poly_start : poly_end + 2]
        xy_pts = re.findall(r"\(xy\s+([-\d.]+)\s+([-\d.]+)\)", poly_block)
        if len(xy_pts) < 3:
            continue
        from shapely.geometry import MultiPolygon
        from shapely.geometry import Polygon as ShapelyPolygon

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
                identity=PadIdentity(
                    component_ref="", pad=str(i), net=net_name, x=x, y=y, layers=(0, 1)
                ),
                center=Point(x, y),
                shape="rect",
                size=(1.0, 1.0),
            )
            for i, (x, y) in enumerate(positions)
        ]

        results[net_name] = verify_net_connectivity(
            pads=tuple(pads),
            tracks=tracks,
            vias=via_list,
            zones=tuple(zone_list),
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


def _copper_layer_id_map(pcb_content: str) -> tuple[dict[str, int], set[int]]:
    """Layer name -> KiCad canonical layer id, from the board's own
    ``(layers ...)`` declaration, plus the set of ids whose declared ROLE is
    a copper role (signal/power/mixed/jumper — ``user`` layers such as
    silkscreen/mask/edge-cuts are not copper). The canonical ids (0 for
    F.Cu, 31 for B.Cu, 1..4 for the inner layers) are the SSOT for copper
    identity — the coarse ``_layer_id`` above (F.Cu -> 0, everything else
    -> 1) is only used by the legacy U4 preflight and would silently merge
    In1.Cu / In3.Cu / In4.Cu / B.Cu into one layer on this 6-layer board.
    """

    # `(layers` stands alone on its own line (no trailing space), so the
    # shared `_extract_top_level_blocks` pattern `^\s*\((layers)\s` never
    # matches it. Extract the block locally with a word boundary instead.
    def _layers_blocks() -> list[str]:
        pattern = re.compile(r"^\s*\(layers\b")
        blocks: list[str] = []
        cur: list[str] = []
        depth = 0
        in_block = False
        for line in pcb_content.split("\n"):
            if not in_block and pattern.match(line):
                in_block = True
                depth = 0
                cur = []
            if in_block:
                cur.append(line)
                depth += line.count("(") - line.count(")")
                if depth <= 0:
                    in_block = False
                    blocks.append("\n".join(cur))
        return blocks

    name_to_id: dict[str, int] = {}
    copper_ids: set[int] = set()
    for block in _layers_blocks():
        for m in re.finditer(r'\(\s*(\d+)\s+"([^"]+)"\s+([^)\s]+)', block):
            layer_id, name, role = m.groups()
            name_to_id[name] = int(layer_id)
            if role in ("signal", "power", "mixed", "jumper"):
                copper_ids.add(int(layer_id))
    return name_to_id, copper_ids


def _copper_pads_by_net(
    pcb: Any, layer_id: dict[str, int], copper_ids: set[int]
) -> dict[str, list[CopperPad]]:
    """Real pad geometry (position, shape, size, rotation, conductive
    layers) per net, resolved from the parsed board the same way the router
    itself resolves pad positions (``pin_world_position``). A through-hole
    pad's barrel touches every copper layer the board declares.
    """
    from temper_placer.core.pin_geometry import pin_world_position

    pads: dict[str, list[CopperPad]] = {}
    for comp in pcb.components:
        if not hasattr(comp, "pins"):
            continue
        comp_rot_deg = float(getattr(comp, "initial_rotation_quadrant", 0) or 0) * 90.0
        for pin in comp.pins:
            if not pin.net:
                continue
            raw_layer = getattr(pin, "layer", None) or "F.Cu"
            is_through = bool(getattr(pin, "is_pth", False)) or raw_layer in ("all", "*.Cu")
            if is_through:
                layers = tuple(sorted(copper_ids))
            else:
                layer = layer_id.get(str(raw_layer))
                if layer is None or layer not in copper_ids:
                    continue  # non-copper pin layer — nothing to connect
                layers = (layer,)
            if not layers:
                continue
            world = pin_world_position(pin, comp)
            pad_number = getattr(pin, "number", None) or getattr(pin, "name", "?")
            width = float(getattr(pin, "width", 0.0) or 0.0)
            height = float(getattr(pin, "height", 0.0) or 0.0)
            if width <= 0.0 and height <= 0.0:
                width = height = 1.0  # best-effort default, like the U4 pads
            shape = str(getattr(pin, "shape", "rect") or "rect")
            is_circle = shape in ("circle", "thru_hole")
            rotation = pad_world_rotation_deg(comp_rot_deg, getattr(pin, "pad_rotation_deg", 0.0))
            identity = PadIdentity(
                component_ref=comp.ref,
                pad=str(pad_number),
                net=pin.net,
                x=world[0],
                y=world[1],
                layers=layers,
            )
            pads.setdefault(pin.net, []).append(
                CopperPad(
                    identity=identity,
                    center=Point(world[0], world[1]),
                    shape="circle" if is_circle else "rect",
                    size=(width, height),
                    rotation=rotation,
                )
            )
    return pads


def _zones_by_net(
    pcb_content: str, layer_id: dict[str, int], copper_ids: set[int]
) -> dict[str, tuple[set[int], int]]:
    """Per net: (copper layer ids with any zone block, zone block count)."""
    from temper_placer.router_v6.pad_connectivity_audit import (
        _extract_top_level_blocks,
        net_number_to_name_map,
    )

    num_to_name = net_number_to_name_map(pcb_content)
    out: dict[str, tuple[set[int], int]] = {}
    for block in _extract_top_level_blocks(pcb_content, ("zone",)):
        net_m = re.search(r"\(net\s+(\d+)\)", block)
        if not net_m:
            continue
        name = num_to_name.get(int(net_m.group(1)))
        if not name:
            continue
        layer_m = re.search(r'\(layer\s+"([^"]+)"\)', block)
        if not layer_m:
            continue
        lid = layer_id.get(layer_m.group(1))
        if lid is None or lid not in copper_ids:
            continue  # non-copper layer — not a real pour
        layers, count = out.get(name, (set(), 0))
        layers.add(lid)
        out[name] = (layers, count + 1)
    return out


def net_route_result_preflight(pcb_content: str) -> dict[str, Any]:
    """Rust-verified per-net verdicts over the EMITTED content.

    This is the router-side fake-completion fix: every verdict comes from
    ``NetRouteResult.verify_continuity`` (the Rust union-find over the
    actual emitted copper), whose ``Connected`` variant is unrepresentable
    without that verification. Returns ``{net_name: NetRouteResult
    pyclass}`` for every pad-bearing net — the same universe the PRIMARY
    audit metric (``pad_connectivity_audit.audit_pcb_file``) reports.

    Pads use REAL geometry parsed from the board (world position via the
    canonical ``pin_world_position`` kernel, shape/size/rotation/layers
    from the pin model), not the best-effort 1.0x1.0 both-layer rects the
    legacy U4 preflight uses — so a segment on the wrong layer from a
    pad's own layers is a genuine miss, not a silent union.

    Zones are outlines, never copper: they feed only the ``ZoneDependent``
    classification (see ``connectivity.verify_net_route_result``).
    """
    import tempfile
    from pathlib import Path

    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.router_v6.pad_connectivity_audit import (
        _extract_top_level_blocks,
    )

    layer_id, copper_ids = _copper_layer_id_map(pcb_content)
    net_name_map = _build_net_name_map(pcb_content)

    segments_by_net: dict[str, list[CopperTrack]] = {}
    for m in _SEGMENT_RE.finditer(pcb_content):
        x1, y1, x2, y2, width, layer, net_num = m.groups()
        lid = layer_id.get(layer)
        if lid is None or lid not in copper_ids:
            continue
        name = net_name_map.get(int(net_num))
        if not name:
            continue
        segments_by_net.setdefault(name, []).append(
            CopperTrack(
                net=name,
                start=Point(float(x1), float(y1)),
                end=Point(float(x2), float(y2)),
                width=float(width),
                layer=lid,
            )
        )

    vias_by_net: dict[str, list[CopperVia]] = {}
    for block in _extract_top_level_blocks(pcb_content, ("via",)):
        at_m = _VIA_AT_RE.search(block)
        size_m = re.search(r"\(size\s+([-\d.]+)\)", block)
        net_m = re.search(r"\(net\s+(\d+)\)", block)
        layers_m = re.search(r'\(layers\s+((?:"[^"]+"\s*)+)\)', block)
        if not (at_m and net_m):
            continue
        name = net_name_map.get(int(net_m.group(1)))
        if not name:
            continue
        # KiCad via semantics (the audit's `_parse_segments_and_vias` rule):
        # a via with NO type token (blind/buried/micro) is THROUGH — it
        # pierces every copper layer regardless of the declared layer pair
        # (which is only the stack extent). A typed via connects exactly
        # its declared layer pair.
        is_typed = re.search(r"\(via\s+(blind|buried|micro)\b", block) is not None
        if is_typed:
            if layers_m is None:
                continue
            layer_names = _LAYER_NAME_RE.findall(layers_m.group(1))
            if len(layer_names) < 2:
                continue
            l_from = layer_id.get(layer_names[0])
            l_to = layer_id.get(layer_names[1])
            if l_from is None or l_to is None:
                continue
            via_layers = {l_from, l_to}
        else:
            via_layers = set(copper_ids)
        if not via_layers:
            continue
        vias_by_net.setdefault(name, []).append(
            CopperVia(
                net=name,
                center=Point(float(at_m.group(1)), float(at_m.group(2))),
                diameter=float(size_m.group(1)) if size_m else 0.6,
                layers=frozenset(via_layers),
            )
        )

    zones_by_net = _zones_by_net(pcb_content, layer_id, copper_ids)

    with tempfile.NamedTemporaryFile(
        "w", suffix=".kicad_pcb", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(pcb_content)
        tmp_path = Path(tmp.name)
    try:
        pcb = parse_kicad_pcb_v6(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    pads_by_net = _copper_pads_by_net(pcb, layer_id, copper_ids)

    results: dict[str, Any] = {}
    for net_name, pads in pads_by_net.items():
        zone_layers, zone_count = zones_by_net.get(net_name, (set(), 0))
        results[net_name] = verify_net_route_result(
            pads,
            segments_by_net.get(net_name, []),
            vias_by_net.get(net_name, []),
            zone_layers=zone_layers,
            zone_outline_count=zone_count,
        )
    return results
