"""
KiCad PCB and schematic parser using kiutils.

This module provides functions to parse KiCad files and convert them to
the internal Netlist representation used by temper-placer.
"""

from __future__ import annotations

import contextlib
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from kiutils.board import Board as KiBoard
from kiutils.footprint import Footprint
from kiutils.schematic import Schematic

from temper_placer.core.board import STANDARD_LAYER_ORDER, Board, MountingHole, Zone
from temper_placer.core.netlist import Component, Net, Netlist, Pin

if TYPE_CHECKING:
    from temper_placer.router_v6.stage0_data import DesignRules, ParsedPCB, StackupInfo


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


def parse_kicad_pcb(pcb_path: Path, normalize: bool = True) -> ParseResult:
    """
    Parse a KiCad PCB file (.kicad_pcb) to extract component placement and netlist.

    Args:
        pcb_path: Path to the .kicad_pcb file.
        normalize: If True, subtract board origin from component positions.

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

    # Guard: empty footprints — return result with empty netlist and warning
    if not ki_board.footprints:
        warnings.append("No footprints found in PCB.")
        board = _extract_board_geometry(ki_board, warnings)
        return ParseResult(
            netlist=Netlist(components=[], nets=[]),
            board=board,
            warnings=warnings,
            traces=[],
            vias=[],
            pads=[],
        )

    # Extract board dimensions first (needed for coordinate normalization)
    board = _extract_board_geometry(ki_board, warnings)

    # Extract components (footprints) with origin-relative positions
    origin_to_use = board.origin if normalize else (0.0, 0.0)
    components = _extract_components_from_pcb(ki_board, warnings, board_origin=origin_to_use)

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

    # Root _sheet
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
            pts = (
                getattr(poly, "points", None)
                or getattr(poly, "pts", None)
                or getattr(poly, "coordinates", [])
            )
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
    _warnings: list[str],
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

        # Determine side (0=Top, 1=Bottom)
        side = 1 if fp.layer in ["B.Cu", "Back", "Bottom"] else 0

        # Extract pins and calculate bounding box center offset
        # Note: In kiutils, pad.position is in footprint-local coordinates (relative to origin)
        # But our internal representation expects pin positions relative to BOUNDING BOX CENTER
        raw_pins = []
        for pad in fp.pads:
            local_x = pad.position.X
            local_y = pad.position.Y

            # Determine if pad is through-hole (connects all copper layers)
            # THT pads have "*.Cu" in their layers list
            pad_layers = pad.layers if hasattr(pad, "layers") and pad.layers else ["F.Cu"]
            is_through_hole = any("*.Cu" in layer or layer == "*.Cu" for layer in pad_layers)

            # Set layer: "all" for THT pads, first copper layer for SMD
            if is_through_hole:
                layer = "all"
            else:
                # Find first copper layer
                copper_layers = [ly for ly in pad_layers if ".Cu" in ly and "*" not in ly]
                layer = copper_layers[0] if copper_layers else "F.Cu"

            # Get pad size
            pad_width = pad.size.X if hasattr(pad, "size") and pad.size else 1.0
            pad_height = pad.size.Y if hasattr(pad, "size") and pad.size else 1.0
            pad_drill = getattr(pad, "drill", 0.0) or 0.0

            # Get pad shape (normalize thru_hole to indicate THT for DSN export)
            pad_shape = pad.shape or "rect"
            if is_through_hole and pad_shape == "circle":
                pad_shape = "thru_hole"

            raw_pins.append(
                {
                    "name": pad.number or "",
                    "number": pad.number or "",
                    "position": (local_x, local_y),
                    "net": pad.net.name
                    if pad.net and hasattr(pad.net, "name")
                    else str(pad.net)
                    if pad.net
                    else None,
                    "width": pad_width,
                    "height": pad_height,
                    "shape": pad_shape,
                    "layer": layer,
                    "drill": pad_drill,
                    "is_pth": is_through_hole,
                }
            )

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
                    position=(
                        p["position"][0] - center_offset_x,
                        p["position"][1] - center_offset_y,
                    ),
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
        # If on bottom side, mirror X center offset before rotation (to match netlist logic)
        cx_to_rotate = -center_offset_x if side == 1 else center_offset_x
        rot_rad = math.radians(rot_deg)
        rotated_cx = cx_to_rotate * math.cos(rot_rad) - center_offset_y * math.sin(rot_rad)
        rotated_cy = cx_to_rotate * math.sin(rot_rad) + center_offset_y * math.cos(rot_rad)

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
            initial_side=side,
            attributes={
                "_center_offset_x": str(center_offset_x),
                "_center_offset_y": str(center_offset_y),
            },
        )

        components.append(comp)

    return components


def _extract_nets_from_pcb(
    _ki_board: KiBoard,
    components: list[Component],
    _warnings: list[str],
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
    ki_board: KiBoard, _warnings: list[str], net_map: dict[str, str] | None = None
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
    ki_board: KiBoard, _warnings: list[str], net_map: dict[str, str] | None = None
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
                    net_id = (
                        str(track.net.number) if hasattr(track.net, "number") else str(track.net)
                    )
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


def _extract_pads_from_pcb(ki_board: KiBoard, _warnings: list[str]) -> list[PadData]:
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
                    drill=getattr(pad, "drill", 0.0) or 0.0,
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
    _sheet: Schematic,
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


def extract_footprint_positions(content: str) -> dict[str, dict]:
    """
    Extract component positions from raw KiCad PCB content without kiutils.

    This is a lightweight parser for extracting footprint positions from
    raw KiCad PCB file content (S-expression format). Useful for:
    - Benchmarking against snippet test cases
    - Quick position extraction without full file parsing

    Args:
        content: Raw KiCad PCB file content as string.

    Returns:
        Dict mapping component reference to position info:
        {
            "U1": {"x": 50.5, "y": 75.25, "rotation": 90.0},
            "R1": {"x": 10.0, "y": 20.0, "rotation": 0.0},
        }
    """
    positions = {}

    # Two-pass approach: first find footprint block boundaries, then extract fields
    # Pass 1: Find all footprint block start positions
    footprint_starts = []
    for match in re.finditer(r'\(footprint\s+"[^"]+"\s+\(layer', content):
        footprint_starts.append(match.start())

    # Pass 2: For each footprint block, extract position and reference
    for i, start in enumerate(footprint_starts):
        # Determine end of this footprint block (start of next, or end of content)
        end = footprint_starts[i + 1] if i + 1 < len(footprint_starts) else len(content)
        block = content[start:end]

        # Extract (at X Y [ANGLE]) - first occurrence in this block
        at_match = re.search(r"\(at\s+([\d.-]+)\s+([\d.-]+)(?:\s+([\d.-]+))?\)", block)
        if not at_match:
            continue

        x = float(at_match.group(1))
        y = float(at_match.group(2))
        rotation = float(at_match.group(3)) if at_match.group(3) else 0.0

        # Extract (property "Reference" "REF" ...) - reference designator
        ref_match = re.search(r'\(property\s+"Reference"\s+"([^"]+)"', block)
        if not ref_match:
            continue

        ref = ref_match.group(1)

        positions[ref] = {
            "x": x,
            "y": y,
            "rotation": rotation,
        }

    return positions


def extract_net_classes(content: str) -> dict:
    """
    Extract net class definitions from raw KiCad PCB content.

    Returns:
        Dict mapping class name to dict of rules:
        {
            "Name": {
                "clearance": 0.2,
                "trace_width": 0.25,
                "via_dia": 0.8,
                "via_drill": 0.4,
                "nets": ["GND", "VCC"]
            }
        }
    """
    classes = {}

    # Iterate over all (net_class ...) blocks
    # We use a simple counter to find the matching closing parenthesis
    start_indices = [m.start() for m in re.finditer(r"\(net_class\b", content)]

    for start in start_indices:
        balance = 0
        end = start
        found_start = False

        for i in range(start, len(content)):
            char = content[i]
            if char == "(":
                balance += 1
                found_start = True
            elif char == ")":
                balance -= 1

            if found_start and balance == 0:
                end = i + 1
                break

        block = content[start:end]

        # Extract name
        # (net_class "Name" "Description" ...)
        name_match = re.search(r'^\(net_class\s+"([^"]+)"', block)
        if not name_match:
            continue

        name = name_match.group(1)

        # Extract params
        rules: dict[str, Any] = {"nets": []}

        # Helper to extract float
        def get_float(pattern, _block=block):
            m = re.search(pattern, _block)
            return float(m.group(1)) if m else None

        rules["clearance"] = get_float(r"\(clearance\s+([\d.]+)\)")
        rules["trace_width"] = get_float(r"\(track_width\s+([\d.]+)\)") or get_float(
            r"\(trace_width\s+([\d.]+)\)"
        )
        rules["via_dia"] = get_float(r"\(via_dia\s+([\d.]+)\)")
        rules["via_drill"] = get_float(r"\(via_drill\s+([\d.]+)\)")
        rules["diff_pair_gap"] = get_float(r"\(diff_pair_gap\s+([\d.]+)\)")
        rules["diff_pair_width"] = get_float(r"\(diff_pair_width\s+([\d.]+)\)")

        # Extract nets
        # (add_net "NetName")
        rules["nets"] = re.findall(r'\(add_net\s+"([^"]+)"\)', block)

        classes[name] = rules

    return classes


def parse_kicad_pcb_v6(pcb_path: Path) -> ParsedPCB:
    """
    Parse KiCad PCB for Router V6 Stage 0.1: Load KiCad PCB File.

    Extracts complete ParsedPCB structure including:
    - Components, nets, zones (from existing parser)
    - Design rules: net classes, clearances, via sizes
    - Stackup: layer count, types, thicknesses, plane assignments

    Args:
        pcb_path: Path to .kicad_pcb file.

    Returns:
        ParsedPCB with all required data for Router V6.

    Example:
        >>> pcb = parse_kicad_pcb_v6(Path("temper.kicad_pcb"))
        >>> errors = pcb.validate_placement()
        >>> assert len(errors) == 0, f"PCB validation failed: {errors}"
    """
    from temper_placer.router_v6.stage0_data import (
        ParsedPCB,
    )

    warnings: list[str] = []

    # Load KiCad board
    ki_board = KiBoard.from_file(str(pcb_path))

    # Guard: empty footprints — skip to early return via parse_kicad_pcb
    # The existing parser now handles empty footprints gracefully

    # Read raw content for manual parsing (net classes)
    try:
        pcb_content = pcb_path.read_text(encoding="utf-8")
    except Exception as e:
        warnings.append(f"Failed to read PCB file content: {e}")
        pcb_content = ""

    # Use existing parser for components, nets, zones, board geometry
    # NOTE: Set normalize=False for Router V6 to work in absolute coordinates
    legacy_result = parse_kicad_pcb(pcb_path, normalize=False)
    warnings.extend(legacy_result.warnings)

    # Extract design rules
    design_rules = _extract_design_rules(ki_board, warnings, pcb_content)

    # Extract stackup
    stackup = _extract_stackup(ki_board, warnings)

    return ParsedPCB(
        components=legacy_result.netlist.components,
        nets=legacy_result.netlist.nets,
        zones=legacy_result.board.zones if legacy_result.board else [],
        board=legacy_result.board or Board.temper_default(),
        design_rules=design_rules,
        stackup=stackup,
        source_path=pcb_path,
        tracks=legacy_result.traces,
        warnings=warnings,
    )


def _extract_design_rules(
    ki_board: KiBoard, _warnings: list[str], pcb_content: str | None = None
) -> DesignRules:
    """
    Extract KiCad design rules from board setup.

    Args:
        ki_board: Parsed KiCad board.
        warnings: List to append warnings.
        pcb_content: Raw PCB file content (optional, for manual net class parsing).

    Returns:
        DesignRules with net classes and assignments.
    """
    from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules

    net_classes = {}
    net_class_assignments = {}

    # Default values (KiCad 6 defaults)
    default_clearance = 0.2  # mm
    default_trace_width = 0.25  # mm
    default_via_diameter = 0.8  # mm
    default_via_drill = 0.4  # mm

    # Extract global design rules from setup
    if hasattr(ki_board, "setup") and ki_board.setup:
        setup = ki_board.setup
        if hasattr(setup, "pcbPlotParams"):
            # KiCad 6+ stores some params in pcbPlotParams
            pass

        # Try to find default rules
        if hasattr(setup, "defaults"):
            defaults = setup.defaults
            if hasattr(defaults, "clearance"):
                default_clearance = float(defaults.clearance)
            if hasattr(defaults, "trackWidth") or hasattr(defaults, "trace_width"):
                default_trace_width = float(
                    getattr(defaults, "trackWidth", getattr(defaults, "trace_width", 0.25))
                )
            if hasattr(defaults, "viaDiameter") or hasattr(defaults, "via_dia"):
                default_via_diameter = float(
                    getattr(defaults, "viaDiameter", getattr(defaults, "via_dia", 0.8))
                )
            if hasattr(defaults, "viaDrill") or hasattr(defaults, "via_drill"):
                default_via_drill = float(
                    getattr(defaults, "viaDrill", getattr(defaults, "via_drill", 0.4))
                )

    # Extract net classes - Try Manual Parsing First
    manual_classes = {}
    if pcb_content:
        manual_classes = extract_net_classes(pcb_content)

    if manual_classes:
        for class_name, rules in manual_classes.items():
            # Use rules or fallback to defaults
            clearance = rules.get("clearance")
            if clearance is None:
                clearance = default_clearance

            trace_width = rules.get("trace_width")
            if trace_width is None:
                trace_width = default_trace_width

            via_diameter = rules.get("via_dia")
            if via_diameter is None:
                via_diameter = default_via_diameter

            via_drill = rules.get("via_drill")
            if via_drill is None:
                via_drill = default_via_drill

            # Try to infer current rating from class name
            current_rating = None
            if (
                "_" in class_name
                and class_name.split("_")[-1].replace("A", "").replace(".", "").isdigit()
            ):
                with contextlib.suppress(ValueError):
                    current_rating = float(class_name.split("_")[-1].replace("A", ""))

            net_classes[class_name] = NetClassRules(
                name=class_name,
                clearance_mm=clearance,
                trace_width_mm=trace_width,
                via_diameter_mm=via_diameter,
                via_drill_mm=via_drill,
                diff_pair_gap_mm=rules.get("diff_pair_gap"),
                diff_pair_width_mm=rules.get("diff_pair_width"),
                current_rating_amps=current_rating,
            )

            # Extract member net assignments
            for net_name in rules.get("nets", []):
                net_class_assignments[net_name] = class_name

    # Fallback to Kiutils if manual parsing failed (or wasn't used)
    elif hasattr(ki_board, "netClasses") and ki_board.netClasses:
        for nc in ki_board.netClasses:
            class_name = nc.name if hasattr(nc, "name") else "Signal"

            # Extract rules
            clearance = float(getattr(nc, "clearance", default_clearance))
            trace_width = float(
                getattr(nc, "trackWidth", getattr(nc, "trace_width", default_trace_width))
            )
            via_diameter = float(
                getattr(nc, "viaDiameter", getattr(nc, "via_dia", default_via_diameter))
            )
            via_drill = float(getattr(nc, "viaDrill", getattr(nc, "via_drill", default_via_drill)))
            diff_pair_gap = (
                float(getattr(nc, "diffPairGap", 0)) if hasattr(nc, "diffPairGap") else None
            )
            diff_pair_width = (
                float(getattr(nc, "diffPairWidth", 0)) if hasattr(nc, "diffPairWidth") else None
            )

            # Try to infer current rating from class name
            current_rating = None
            if (
                "_" in class_name
                and class_name.split("_")[-1].replace("A", "").replace(".", "").isdigit()
            ):
                with contextlib.suppress(ValueError):
                    current_rating = float(class_name.split("_")[-1].replace("A", ""))

            net_classes[class_name] = NetClassRules(
                name=class_name,
                clearance_mm=clearance,
                trace_width_mm=trace_width,
                via_diameter_mm=via_diameter,
                via_drill_mm=via_drill,
                diff_pair_gap_mm=diff_pair_gap,
                diff_pair_width_mm=diff_pair_width,
                current_rating_amps=current_rating,
            )

            # Extract member net assignments
            if hasattr(nc, "nets") and nc.nets:
                for net_name in nc.nets:
                    net_class_assignments[net_name] = class_name

    # Add default class if not present
    if "Signal" not in net_classes:
        net_classes["Signal"] = NetClassRules(
            name="Signal",
            clearance_mm=default_clearance,
            trace_width_mm=default_trace_width,
            via_diameter_mm=default_via_diameter,
            via_drill_mm=default_via_drill,
        )

    return DesignRules(
        net_classes=net_classes,
        net_class_assignments=net_class_assignments,
        default_clearance_mm=default_clearance,
        default_trace_width_mm=default_trace_width,
        default_via_diameter_mm=default_via_diameter,
        default_via_drill_mm=default_via_drill,
    )


def _extract_stackup(ki_board: KiBoard, warnings: list[str]) -> StackupInfo:
    """
    Extract PCB layer stackup from KiCad board.

    Args:
        ki_board: Parsed KiCad board.
        warnings: List to append warnings.

    Returns:
        StackupInfo with layer definitions.
    """
    from temper_placer.router_v6.stage0_data import (
        DielectricInfo,
        LayerInfo,
        StackupInfo,
    )

    layers = []
    parsed_dielectrics = []

    # Helper to find plane assignments from zones (common for both methods)
    plane_assignments = {}
    if hasattr(ki_board, "zones"):
        for zone in ki_board.zones:
            if (
                hasattr(zone, "layers")
                and zone.layers
                and hasattr(zone, "netName")
                and zone.netName
            ):
                # Check if zone covers most of the layer (indicates plane)
                for layer in zone.layers:
                    # Simple heuristic: if net is GND/VCC/Power, it's likely a plane
                    is_power = (
                        "GND" in zone.netName
                        or "VCC" in zone.netName
                        or "+" in zone.netName
                        or "PWR" in zone.netName
                    )
                    if is_power and ".Cu" in layer:
                        plane_assignments[layer] = zone.netName

    # Try to extract from board setup stackup first
    setup_stackup = None
    if hasattr(ki_board, "setup") and hasattr(ki_board.setup, "stackup") and ki_board.setup.stackup:
        setup_stackup = ki_board.setup.stackup

    if setup_stackup and hasattr(setup_stackup, "layers") and setup_stackup.layers:
        # ---------------------------------------------------------------------
        # Method 1: Use KiCad Stackup Table
        # ---------------------------------------------------------------------

        # Calculate total thickness (sum of all layers + mask)
        total_thickness = 0.0

        # Extract copper layers and dielectrics
        copper_layers = []
        raw_dielectrics = []

        for layer in setup_stackup.layers:
            # Add to total thickness if available
            if hasattr(layer, "thickness") and layer.thickness is not None:
                total_thickness += layer.thickness

            if layer.type == "copper":
                copper_layers.append(layer)
            elif layer.type in ["core", "prepreg", "dielectric"] or "dielectric" in layer.type:
                raw_dielectrics.append(layer)

        layer_count = len(copper_layers)

        # Process Copper Layers
        for i, layer in enumerate(copper_layers):
            name = layer.name

            # Determine layer type
            if name in plane_assignments:
                layer_type = "plane"
                plane_net = plane_assignments[name]
            elif i == 0 or i == layer_count - 1:
                layer_type = "signal"
                plane_net = None
            else:
                # Inner layers without plane assignment -> mixed
                layer_type = "mixed"
                plane_net = None

            # Thickness in um (convert from mm)
            thickness_um = (
                (layer.thickness * 1000.0) if (hasattr(layer, "thickness") and layer.thickness) else 35.0
            )

            layers.append(
                LayerInfo(
                    index=i,
                    name=name,
                    layer_type=layer_type,
                    thickness_um=thickness_um,
                    plane_net=plane_net,
                )
            )

        # Process Dielectric Layers
        for d in raw_dielectrics:
            # kiutils StackupLayer uses camelCase for epsilonR and lossTangent
            # but we should check both just in case
            epsilon_r = getattr(d, "epsilonR", None)
            if epsilon_r is None:
                epsilon_r = getattr(d, "epsilon_r", 4.5)

            loss_tangent = getattr(d, "lossTangent", None)
            if loss_tangent is None:
                loss_tangent = getattr(d, "loss_tangent", 0.02)

            parsed_dielectrics.append(
                DielectricInfo(
                    name=d.name,
                    material=getattr(d, "material", "FR4") or "FR4",
                    thickness_mm=d.thickness if hasattr(d, "thickness") and d.thickness else 0.0,
                    epsilon_r=epsilon_r or 4.5,
                    loss_tangent=loss_tangent or 0.02,
                )
            )

    else:
        # ---------------------------------------------------------------------
        # Method 2: Heuristic / Legacy Fallback
        # ---------------------------------------------------------------------

        # Determine layer count from board
        layer_count = 2  # Default to 2-layer
        if hasattr(ki_board, "layers") and ki_board.layers:
            # Count copper layers
            copper_layers = [ly for ly in ki_board.layers if ".Cu" in getattr(ly, "name", "")]
            layer_count = len(copper_layers)

        # Standard layer names for 2/4/6-layer boards
        if layer_count == 2:
            layer_names = ["F.Cu", "B.Cu"]
        elif layer_count == 4:
            layer_names = [str(idx) for idx in STANDARD_LAYER_ORDER]
        elif layer_count == 6:
            layer_names = ["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu"]
        else:
            warnings.append(f"Unusual layer count: {layer_count}. Using generic naming.")
            layer_names = ["F.Cu"] + [f"In{i}.Cu" for i in range(1, layer_count - 1)] + ["B.Cu"]

        # Create layer info
        for i, name in enumerate(layer_names):
            # Determine layer type
            if name in plane_assignments:
                layer_type = "plane"
                plane_net = plane_assignments[name]
            elif i == 0 or i == layer_count - 1:
                layer_type = "signal"  # Outer layers are signal
                plane_net = None
            else:
                # Inner layers: default to mixed (can be signal or plane)
                layer_type = "mixed"
                plane_net = None

            # Standard copper thickness: 35µm (1oz)
            thickness_um = 35.0
            if i == 0 or i == layer_count - 1:
                # Outer layers sometimes thicker
                thickness_um = 35.0

            layers.append(
                LayerInfo(
                    index=i,
                    name=name,
                    layer_type=layer_type,
                    thickness_um=thickness_um,
                    plane_net=plane_net,
                )
            )

        # Total thickness: 1.6mm standard, 0.8mm for 2-layer, 1.6mm for 4+ layer
        total_thickness = 1.6 if layer_count >= 4 else 0.8

        # Check if general.thickness is set (override heuristic)
        if (
            hasattr(ki_board, "general")
            and hasattr(ki_board.general, "thickness")
            and ki_board.general.thickness
        ):
            total_thickness = ki_board.general.thickness

    return StackupInfo(
        layers=layers,
        total_thickness_mm=total_thickness,
        layer_count=layer_count,
        dielectrics=parsed_dielectrics,
    )
