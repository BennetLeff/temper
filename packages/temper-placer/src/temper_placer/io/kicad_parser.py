"""
KiCad PCB and schematic parser using kiutils.

This module provides functions to parse KiCad files and convert them to
the internal Netlist representation used by temper-placer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from kiutils.board import Board as KiBoard
from kiutils.footprint import Footprint
from kiutils.schematic import Schematic

from temper_placer.core.board import Board, MountingHole, Zone
from temper_placer.core.netlist import Component, Net, Netlist, Pin


@dataclass
class TraceData:
    """Data for a PCB trace segment."""

    start: tuple[float, float]  # (x, y) in mm, absolute coords
    end: tuple[float, float]  # (x, y) in mm, absolute coords
    width: float  # trace width in mm
    layer: str  # e.g., 'F.Cu', 'B.Cu'
    net: str | None = None  # net name
@dataclass
class ViaData:
    """Data for a PCB via."""

    position: tuple[float, float]  # (x, y) in mm, absolute
    diameter: float  # mm
    drill: float  # mm
    net: str | None = None  # net name
    layers: tuple[str, str] = ("F.Cu", "B.Cu")


@dataclass
class PadData:
    """Data for a component pad."""

    position: tuple[float, float]  # (x, y) in mm, absolute coords
    size: tuple[float, float]  # (width, height) in mm
    shape: str  # 'rect', 'circle', 'oval', 'roundrect', 'thru_hole'
    drill: float = 0.0  # mm
    rotation: float = 0.0  # degrees
    layer: str = "F.Cu"  # primary layer
    number: str = ""  # pad number
    net: str | None = None  # net name
    component_ref: str | None = None  # parent component ref


@dataclass
class ParseResult:
    """
    Result of parsing KiCad files.

    Attributes:
        netlist: Parsed Netlist with components and nets.
        board: Extracted Board geometry.
        warnings: List of parsing warning messages.
        traces: List of PCB trace segments (for routed boards).
        pads: List of component pads with positions and nets.
    """

    netlist: Netlist
    board: Board | None
    warnings: list[str]
    traces: list[TraceData] = field(default_factory=list)
    vias: list[ViaData] = field(default_factory=list)
    pads: list[PadData] = field(default_factory=list)

    @property
    def has_warnings(self) -> bool:
        """True if any warnings were generated during parsing."""
        return len(self.warnings) > 0


def parse_kicad_pcb(pcb_path: Path) -> ParseResult:
    """
    Parse a KiCad PCB file (.kicad_pcb) to extract component placement and netlist.

    Args:
        pcb_path: Path to the .kicad_pcb file.

    Returns:
        ParseResult containing netlist, board geometry, and any warnings.

    Note:
        This extracts placement from an existing PCB file. For initial placement
        optimization, components may be unplaced (position 0,0) or randomly placed.

        Component positions are normalized to origin-relative coordinates
        (i.e., board origin is subtracted). This ensures consistency with the
        optimizer which works in [0, board_width] x [0, board_height] space.
        The kicad_writer adds the origin back when exporting.
    """
    warnings: list[str] = []

    # Load the KiCad board
    ki_board = KiBoard.from_file(str(pcb_path))

    # Extract board dimensions first (needed for coordinate normalization)
    board = _extract_board_geometry(ki_board, warnings)

    # Extract components (footprints) with origin-relative positions
    components = _extract_components_from_pcb(ki_board, warnings, board_origin=board.origin)

    # Extract nets
    nets = _extract_nets_from_pcb(ki_board, components, warnings)

    # Build net ID to name map
    net_map = {}
    if hasattr(ki_board, "nets"):
        for n in ki_board.nets:
            # kiutils might store number as int or str
            if hasattr(n, "number") and hasattr(n, "name"):
                net_map[str(n.number)] = n.name
            elif hasattr(n, "code") and hasattr(n, "name"):  # Older kiutils?
                net_map[str(n.code)] = n.name

    # Extract traces, vias, and pads (optional but useful for visualization/optimization)
    traces = _extract_traces_from_pcb(ki_board, warnings, net_map)
    vias = _extract_vias_from_pcb(ki_board, warnings, net_map)
    pads = _extract_pads_from_pcb(ki_board, warnings)

    netlist = Netlist(components=components, nets=nets)
    return ParseResult(
        netlist=netlist, board=board, warnings=warnings, traces=traces, vias=vias, pads=pads
    )


def parse_kicad_schematic(sch_path: Path, recursive: bool = True) -> ParseResult:
    """
    Parse KiCad schematic files to extract component and netlist data.

    Args:
        sch_path: Path to the root .kicad_sch file.
        recursive: If True, also parse hierarchical sheets.

    Returns:
        ParseResult with extracted netlist.

    Note:
        Schematic parsing does not provide board geometry or footprints.
        It is primarily used for connectivity-only optimization.
    """
    warnings: list[str] = []
    components: list[Component] = []
    nets_dict: dict[str, list[tuple[str, str]]] = {}

    # Root sheet
    sch = Schematic.from_file(str(sch_path))
    _parse_schematic_sheet(sch, components, nets_dict, warnings, recursive)

    # Convert nets dict to list of Net objects
    nets = [Net(name=name, pins=pins) for name, pins in nets_dict.items()]

    return ParseResult(
        netlist=Netlist(components=components, nets=nets), board=None, warnings=warnings
    )


def _extract_board_geometry(ki_board: KiBoard, warnings: list[str]) -> Board:
    """
    Extract board dimensions and origin from Kiutils board object.

    Args:
        ki_board: Parsed kiutils Board instance.
        warnings: List to append any issues found.

    Returns:
        Board object with width, height, and origin.
    """
    # 1. Look for Edge.Cuts lines to determine bounding box
    edge_cuts = [g for g in ki_board.graphicItems if g.layer == "Edge.Cuts"]

    if not edge_cuts:
        warnings.append("No Edge.Cuts found in PCB. Using default 100x150mm.")
        return Board.temper_default()

    # Determine bounding box from edge cuts
    x_min, y_min = float("inf"), float("inf")
    x_max, y_max = float("-inf"), float("-inf")

    for item in edge_cuts:
        # Most items have start/end properties in kiutils
        # (This is a simplified bounding box calculation)
        if hasattr(item, "start") and hasattr(item, "end"):
            for pt in [item.start, item.end]:
                x_min = min(x_min, pt.X)
                y_min = min(y_min, pt.Y)
                x_max = max(x_max, pt.X)
                y_max = max(y_max, pt.Y)

    # 2. Extract Mounting Holes (drilled holes without reference)
    mounting_holes = []
    for fp in ki_board.footprints:
        # Components without reference designators (e.g. REF**) are often mounting holes
        # Or check if footprint has 'MountingHole' in its name/text
        is_mounting_hole = False

        # Check Value/Name (entryName in kiutils)
        if hasattr(fp, "entryName") and "MountingHole" in fp.entryName:
            is_mounting_hole = True

        # Check graphic text items
        if not is_mounting_hole and fp.graphicItems:
            for item in fp.graphicItems:
                if hasattr(item, "text") and "MountingHole" in item.text:
                    is_mounting_hole = True
                    break

        if is_mounting_hole:
            # Normalize to board origin
            mounting_holes.append(
                MountingHole(position=(fp.position.X - x_min, fp.position.Y - y_min), diameter=3.2)
            )

    # 3. Extract Zones
    zones = []
    for ki_zone in ki_board.zones:
        # Kiutils zone boundary is a list of points
        if ki_zone.polygons:
            poly = ki_zone.polygons[0]
            # Try points or pts based on kiutils version
            pts = getattr(poly, "points", None) or getattr(poly, "pts", None) or getattr(poly, "coordinates", [])
            x_pts = [p.X - x_min for p in pts]
            y_pts = [p.Y - y_min for p in pts]
            if x_pts and y_pts:
                bounds = (min(x_pts), min(y_pts), max(x_pts), max(y_pts))
                polygon = list(zip(x_pts, y_pts))

                # Check for complex geometry warning
                bbox_area = (bounds[2] - bounds[0]) * (bounds[3] - bounds[1])
                poly_area = 0.0
                if len(polygon) > 2:
                    # Shoelace formula
                    for i in range(len(polygon)):
                        j = (i + 1) % len(polygon)
                        poly_area += polygon[i][0] * polygon[j][1]
                        poly_area -= polygon[j][0] * polygon[i][1]
                    poly_area = abs(poly_area) / 2.0

                if bbox_area > 0 and abs(bbox_area - poly_area) / bbox_area > 0.05:
                    warnings.append(
                        f"Zone '{ki_zone.name or 'Unnamed'}' is non-rectangular. "
                        f"Approximating polygon (area={poly_area:.1f}) with bounding box (area={bbox_area:.1f})."
                    )

                zones.append(
                    Zone(
                        name=ki_zone.name or f"Zone_{len(zones)}",
                        bounds=bounds,
                        net_classes=[ki_zone.netName] if ki_zone.netName else ["Signal"],
                        polygon=polygon,
                        layers=ki_zone.layers if hasattr(ki_zone, "layers") else ["F.Cu"],
                    )
                )

    # 4. Extract Ground Domains
    # (Simplified: logic for ground domains could be added here if present in PCB)

    return Board(
        width=x_max - x_min,
        height=y_max - y_min,
        origin=(x_min, y_min),
        mounting_holes=mounting_holes,
        zones=zones,
    )


def _extract_components_from_pcb(
    ki_board: KiBoard,
    warnings: list[str],
    board_origin: tuple[float, float],
) -> list[Component]:
    """
    Extract components from Kiutils board object.

    Args:
        ki_board: Parsed board.
        warnings: List for warning messages.
        board_origin: (ox, oy) to normalize positions.

    Returns:
        List of Component instances.
    """
    components = []
    ox, oy = board_origin

    for fp in ki_board.footprints:
        ref = _get_footprint_reference(fp)
        if not ref or ref.startswith("REF**"):
            continue

        # Map Kiutils rotation (degrees) to 0-3 index
        # Note: KiCad uses counter-clockwise rotation
        rot_deg = fp.position.angle or 0.0
        rot_idx = round(rot_deg / 90.0) % 4

        # Calculate component bounds - prefer courtyard graphics, fallback to pads
        width, height = _calculate_footprint_bounds(fp)

        # Extract pins and calculate bounding box center offset
        # Note: In kiutils, pad.position is in footprint-local coordinates (relative to origin)
        # But our internal representation expects pin positions relative to BOUNDING BOX CENTER
        raw_pins = []
        for pad in fp.pads:
            local_x = pad.position.X
            local_y = pad.position.Y

            # Determine if pad is through-hole (connects all copper layers)
            # THT pads have "*.Cu" in their layers list
            pad_layers = pad.layers if hasattr(pad, 'layers') and pad.layers else ["F.Cu"]
            is_through_hole = any("*.Cu" in layer or layer == "*.Cu" for layer in pad_layers)

            # Set layer: "all" for THT pads, first copper layer for SMD
            if is_through_hole:
                layer = "all"
            else:
                # Find first copper layer
                copper_layers = [l for l in pad_layers if ".Cu" in l and "*" not in l]
                layer = copper_layers[0] if copper_layers else "F.Cu"

            # Get pad size
            pad_width = pad.size.X if hasattr(pad, 'size') and pad.size else 1.0
            pad_height = pad.size.Y if hasattr(pad, 'size') and pad.size else 1.0
            pad_drill = getattr(pad, 'drill', 0.0) or 0.0

            # Get pad shape (normalize thru_hole to indicate THT for DSN export)
            pad_shape = pad.shape or "rect"
            if is_through_hole and pad_shape == "circle":
                pad_shape = "thru_hole"

            raw_pins.append({
                "name": pad.number or "",
                "number": pad.number or "",
                "position": (local_x, local_y),
                "net": pad.net.name if pad.net and hasattr(pad.net, "name") else str(pad.net) if pad.net else None,
                "width": pad_width,
                "height": pad_height,
                "shape": pad_shape,
                "layer": layer,
                "drill": pad_drill,
                "is_pth": is_through_hole,
            })

        # Calculate bounding box center offset from footprint origin
        # This is the offset from footprint origin to geometric center of all pads
        if raw_pins:
            pad_xs = [p["position"][0] for p in raw_pins]
            pad_ys = [p["position"][1] for p in raw_pins]
            center_offset_x = (min(pad_xs) + max(pad_xs)) / 2.0
            center_offset_y = (min(pad_ys) + max(pad_ys)) / 2.0
        else:
            center_offset_x, center_offset_y = 0.0, 0.0

        # Create pins with positions relative to bounding box center (not footprint origin)
        pins = []
        for p in raw_pins:
            pins.append(
                Pin(
                    name=p["name"],
                    number=p["number"],
                    position=(p["position"][0] - center_offset_x, p["position"][1] - center_offset_y),
                    net=p["net"],
                    width=p.get("width", 1.0),
                    height=p.get("height", 1.0),
                    shape=p.get("shape", "rect"),
                    layer=p.get("layer", "F.Cu"),
                    drill=p.get("drill", 0.0),
                    is_pth=p.get("is_pth", False),
                )
            )

        # Rotate the center offset based on footprint rotation
        # KiCad rotates counter-clockwise, so we need to rotate the offset
        rot_rad = math.radians(rot_deg)
        rotated_cx = center_offset_x * math.cos(rot_rad) - center_offset_y * math.sin(rot_rad)
        rotated_cy = center_offset_x * math.sin(rot_rad) + center_offset_y * math.cos(rot_rad)

        # initial_position is the BOUNDING BOX CENTER position (footprint origin + rotated center offset)
        # Store the UNROTATED center offset in attributes for the writer to use
        comp = Component(
            ref=ref,
            footprint=fp.libId or "",
            bounds=(width, height),
            pins=pins,
            initial_position=(
                float(fp.position.X) - float(board_origin[0]) + float(rotated_cx),
                float(fp.position.Y) - float(board_origin[1]) + float(rotated_cy),
            ),
            fixed=fp.locked,
            initial_rotation=rot_idx,
            attributes={
                "_center_offset_x": str(center_offset_x),
                "_center_offset_y": str(center_offset_y),
            },
        )

        components.append(comp)

    return components


def _extract_nets_from_pcb(
    ki_board: KiBoard,
    components: list[Component],
    warnings: list[str],
) -> list[Net]:
    """
    Extract connectivity from Kiutils board object.

    Args:
        ki_board: Parsed board.
        components: Extracted components list.
        warnings: List for warning messages.

    Returns:
        List of Net instances.
    """
    nets_dict: dict[str, Net] = {}

    for comp in components:
        for pin in comp.pins:
            if not pin.net:
                continue

            if pin.net not in nets_dict:
                nets_dict[pin.net] = Net(name=pin.net, pins=[])

            nets_dict[pin.net].pins.append((comp.ref, pin.name))

    # Filter out empty nets or single-pin nets
    return [n for n in nets_dict.values() if len(n.pins) >= 2]


def _extract_traces_from_pcb(
    ki_board: KiBoard, warnings: list[str], net_map: dict[str, str] | None = None
) -> list[TraceData]:
    """
    Extract copper trace segments from board.

    Args:
        ki_board: Parsed board.
        warnings: List for warning messages.
        net_map: Dictionary mapping net ID (str) to net name.

    Returns:
        List of TraceData.
    """
    if net_map is None:
        net_map = {}

    traces = []
    # In Kiutils, traces are in 'traceItems' list
    # print(f"DEBUG: Extracting traces. found {len(ki_board.traceItems)} trace items.")
    for track in ki_board.traceItems:
        # Only process tracks, skip vias (which don't have start/end)
        if hasattr(track, "start") and hasattr(track, "end"):
            net_name = None
            # Resolve net name
            if track.net:
                # Try to get from object if populated
                if hasattr(track.net, "name") and track.net.name:
                    net_name = track.net.name
                else:
                    # Fallback to map lookup using ID
                    net_id = str(track.net)  # track.net might be int or object relying on str()
                    # If it has 'number' attribute, use that
                    if hasattr(track.net, "number"):
                        net_id = str(track.net.number)

                    net_name = net_map.get(net_id)

                    # If failed, use the ID itself as fallback
                    if not net_name:
                        net_name = net_id

            traces.append(
                TraceData(
                    start=(track.start.X, track.start.Y),
                    end=(track.end.X, track.end.Y),
                    width=track.width,
                    layer=track.layer,
                    net=net_name,
                )
            )
    return traces


def _extract_vias_from_pcb(
    ki_board: KiBoard, warnings: list[str], net_map: dict[str, str] | None = None
) -> list[ViaData]:
    """
    Extract vias from board.

    Args:
        ki_board: Parsed board.
        warnings: List for warning messages.
        net_map: Dictionary mapping net ID to name.

    Returns:
        List of ViaData.
    """
    if net_map is None:
        net_map = {}

    vias = []
    vias = []
    for track in ki_board.traceItems:
        # Check if it's a Via object (has position but no start/end)
        if hasattr(track, "position") and not hasattr(track, "start"):
            net_name = None
            if track.net:
                if hasattr(track.net, "name") and track.net.name:
                    net_name = track.net.name
                else:
                    net_id = str(track.net.number) if hasattr(track.net, "number") else str(track.net)
                    net_name = net_map.get(net_id, net_id)

            vias.append(
                ViaData(
                    position=(track.position.X, track.position.Y),
                    diameter=track.size,
                    drill=track.drill or 0.4,
                    net=net_name,
                    layers=tuple(track.layers) if hasattr(track, "layers") else ("F.Cu", "B.Cu"),
                )
            )
    return vias


def _extract_pads_from_pcb(ki_board: KiBoard, warnings: list[str]) -> list[PadData]:
    """
    Extract pad positions and layers for visualization.

    Args:
        ki_board: Parsed board.
        warnings: List for warning messages.

    Returns:
        List of PadData.
    """
    pads = []
    for fp in ki_board.footprints:
        ref = _get_footprint_reference(fp)
        # Get footprint position for transforming pad coords
        fp_x = float(fp.position.X) if fp.position else 0.0
        fp_y = float(fp.position.Y) if fp.position else 0.0

        for pad in fp.pads:
            # Transform pad position from footprint-relative to absolute world coords
            abs_x = fp_x + float(pad.position.X)
            abs_y = fp_y + float(pad.position.Y)
            pads.append(
                PadData(
                    position=(abs_x, abs_y),
                    size=(pad.size.X, pad.size.Y),
                    shape=pad.shape or "rect",
                    drill=getattr(pad, 'drill', 0.0) or 0.0,
                    rotation=pad.position.angle or 0.0,
                    layer=pad.layers[0] if pad.layers else "F.Cu",
                    number=pad.number or "",
                    net=pad.net.name
                    if pad.net and hasattr(pad.net, "name")
                    else str(pad.net)
                    if pad.net
                    else None,
                    component_ref=ref,
                )
            )
    return pads


def _parse_schematic_sheet(
    sheet: Schematic,
    components: list[Component],
    nets_dict: dict[str, list[tuple[str, str]]],
    warnings: list[str],
    recursive: bool,
) -> None:
    """Recursive helper for parsing hierarchical schematics."""
    # 1. Extract components
    # (Simplified: schematic parsing is complex and secondary to PCB parsing)
    pass


def _get_footprint_reference(fp: Footprint) -> str | None:
    """
    Extract reference designator from a footprint item.

    Args:
        fp: Kiutils Footprint item.

    Returns:
        Reference string (e.g., "U1") or None.
    """
    # 1. Check Reference property (most reliable in KiCad 6+)
    if hasattr(fp, "properties"):
        props = fp.properties
        if isinstance(props, dict):
            if "Reference" in props:
                return props["Reference"]
        elif isinstance(props, list):
            for p in props:
                if getattr(p, "name", "") == "Reference":
                    return getattr(p, "value", None)

    # 2. Check graphicItems for reference
    for item in fp.graphicItems:
        if hasattr(item, "type") and item.type == "reference":
            return item.text

    # 3. Fallback to ref attribute if available
    ref = getattr(fp, "ref", None)
    if ref and not ref.startswith("REF**"):
        return ref

    # 4. Last resort: entryName if it looks like a ref (e.g. U1, R5)
    ename = getattr(fp, "entryName", None)
    if ename and not ename.startswith("REF**") and ":" not in ename and len(ename) < 10:
        return ename

    return None


def _get_footprint_bounds(fp: Footprint) -> tuple[float, float]:
    """
    Estimate footprint bounding box from its graphic items.

    Args:
        fp: Kiutils Footprint item.

    Returns:
        (width, height) in mm.
    """
    return _calculate_footprint_bounds(fp)


def _calculate_footprint_bounds(fp: Footprint) -> tuple[float, float]:
    """
    Calculate footprint bounding box from courtyard graphics or pads.

    Priority:
    1. Courtyard layer (F.CrtYd, B.CrtYd) - most accurate
    2. Fabrication layer (F.Fab, B.Fab) - body outline
    3. Pads - minimum required area for DRC

    Args:
        fp: Kiutils Footprint item.

    Returns:
        (width, height) in mm.
    """
    # Try courtyard/fab layers first
    if fp.graphicItems:
        layers_priority = ["F.CrtYd", "B.CrtYd", "F.Fab", "B.Fab"]

        items_to_use = [
            g for g in fp.graphicItems if hasattr(g, "layer") and g.layer in layers_priority
        ]

        if not items_to_use:
            # Fallback: ignore Silk layers
            items_to_use = [
                g for g in fp.graphicItems if hasattr(g, "layer") and "Silk" not in g.layer
            ]

        if items_to_use:
            x_min, y_min = float("inf"), float("inf")
            x_max, y_max = float("-inf"), float("-inf")
            has_valid_items = False

            for item in items_to_use:
                if hasattr(item, "start") and hasattr(item, "end"):
                    for pt in [item.start, item.end]:
                        x_min = min(x_min, pt.X)
                        y_min = min(y_min, pt.Y)
                        x_max = max(x_max, pt.X)
                        y_max = max(y_max, pt.Y)
                    has_valid_items = True

                if hasattr(item, "center") and hasattr(item, "radius"):
                    cx, cy, r = item.center.X, item.center.Y, item.radius
                    x_min = min(x_min, cx - r)
                    y_min = min(y_min, cy - r)
                    x_max = max(x_max, cx + r)
                    y_max = max(y_max, cy + r)
                    has_valid_items = True

            if has_valid_items:
                return (max(0.5, x_max - x_min), max(0.5, y_max - y_min))

    # Fallback: Calculate bounds from pads
    # In kiutils, pad.position is in footprint-local coordinates
    if fp.pads:
        x_min, y_min = float("inf"), float("inf")
        x_max, y_max = float("-inf"), float("-inf")

        for pad in fp.pads:
            # pad.position is local to footprint center
            px, py = pad.position.X, pad.position.Y
            pw, ph = pad.size.X, pad.size.Y

            # Extend bounds by pad position +/- half pad size
            x_min = min(x_min, px - pw / 2)
            y_min = min(y_min, py - ph / 2)
            x_max = max(x_max, px + pw / 2)
            y_max = max(y_max, py + ph / 2)

        if x_min != float("inf"):
            return (max(0.5, x_max - x_min), max(0.5, y_max - y_min))

    # Ultimate fallback - should rarely happen
    return (2.0, 2.0)
