"""
KiCad PCB and schematic parser using kiutils.

This module provides functions to parse KiCad files and convert them to
the internal Netlist representation used by temper-placer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from kiutils.board import Board as KiBoard
from kiutils.schematic import Schematic
from kiutils.footprint import Footprint
from kiutils.symbol import SymbolLib

from temper_placer.core.netlist import Component, Pin, Net, Netlist
from temper_placer.core.board import Board, Zone, MountingHole


@dataclass
class ParseResult:
    """Result of parsing KiCad files."""

    netlist: Netlist
    board: Optional[Board]
    warnings: List[str]

    @property
    def has_warnings(self) -> bool:
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
    """
    warnings: List[str] = []

    # Load the KiCad board
    ki_board = KiBoard.from_file(str(pcb_path))

    # Extract board dimensions
    board = _extract_board_geometry(ki_board, warnings)

    # Extract components (footprints)
    components = _extract_components_from_pcb(ki_board, warnings)

    # Extract nets
    nets = _extract_nets_from_pcb(ki_board, components, warnings)

    netlist = Netlist(components=components, nets=nets)

    return ParseResult(netlist=netlist, board=board, warnings=warnings)


def parse_kicad_schematic(sch_path: Path, recursive: bool = True) -> ParseResult:
    """
    Parse a KiCad schematic file (.kicad_sch) to extract netlist information.

    This is useful for getting the logical netlist before placement, or
    for hierarchical designs where the schematic is the source of truth.

    Args:
        sch_path: Path to the .kicad_sch file.
        recursive: If True, recursively parse hierarchical sub-sheets.

    Returns:
        ParseResult containing netlist and any warnings.
    """
    warnings: List[str] = []

    # Load the schematic
    schematic = Schematic.from_file(str(sch_path))

    # Track all components and nets across sheets
    all_components: List[Component] = []
    all_nets: Dict[str, Net] = {}

    # Parse the main sheet
    _parse_schematic_sheet(
        schematic, sch_path.parent, all_components, all_nets, warnings, recursive=recursive
    )

    netlist = Netlist(components=all_components, nets=list(all_nets.values()))

    return ParseResult(netlist=netlist, board=None, warnings=warnings)


def _extract_board_geometry(ki_board: KiBoard, warnings: List[str]) -> Board:
    """Extract board outline and geometry from KiCad board."""

    # Get board outline from Edge.Cuts layer
    x_min, y_min = float("inf"), float("inf")
    x_max, y_max = float("-inf"), float("-inf")

    for item in ki_board.graphicItems:
        if hasattr(item, "layer") and item.layer == "Edge.Cuts":
            # Handle lines
            if hasattr(item, "start") and hasattr(item, "end"):
                for pt in [item.start, item.end]:
                    x_min = min(x_min, pt.X)
                    y_min = min(y_min, pt.Y)
                    x_max = max(x_max, pt.X)
                    y_max = max(y_max, pt.Y)
            # Handle arcs/circles
            elif hasattr(item, "center"):
                cx, cy = item.center.X, item.center.Y
                r = getattr(item, "radius", 0) or 0
                x_min = min(x_min, cx - r)
                y_min = min(y_min, cy - r)
                x_max = max(x_max, cx + r)
                y_max = max(y_max, cy + r)

    # If no outline found, use default or warn
    if x_min == float("inf"):
        warnings.append("No board outline found in Edge.Cuts layer, using default 100x150mm")
        width, height = 100.0, 150.0
        origin = (0.0, 0.0)
    else:
        width = x_max - x_min
        height = y_max - y_min
        origin = (x_min, y_min)

    # Extract mounting holes (footprints with MountingHole in name or specific patterns)
    mounting_holes: List[MountingHole] = []
    for fp in ki_board.footprints:
        fp_name = fp.libId or ""
        if "MountingHole" in fp_name or "mounting" in fp_name.lower():
            pos = (fp.position.X, fp.position.Y)
            # Try to get hole diameter from pads
            diameter = 3.2  # Default M3
            for pad in fp.pads:
                if hasattr(pad, "drill") and pad.drill:
                    diameter = pad.drill.diameter or diameter
                    break
            mounting_holes.append(MountingHole(pos, diameter, keepout_radius=diameter + 2.0))

    # Extract zones (copper zones for placement constraints)
    zones: List[Zone] = []
    for zone in ki_board.zones:
        if zone.layerName and "Cu" in zone.layerName:
            # Get zone bounds from polygon
            if zone.polygon and zone.polygon.coordinates:
                coords = zone.polygon.coordinates
                zx_min = min(c.X for c in coords)
                zy_min = min(c.Y for c in coords)
                zx_max = max(c.X for c in coords)
                zy_max = max(c.Y for c in coords)

                zone_name = zone.name or f"Zone_{len(zones)}"
                net_class = zone.netName or "Signal"

                zones.append(
                    Zone(
                        name=zone_name,
                        bounds=(zx_min, zy_min, zx_max, zy_max),
                        net_classes=[net_class],
                    )
                )

    return Board(
        width=width,
        height=height,
        origin=origin,
        mounting_holes=mounting_holes,
        zones=zones,
    )


def _extract_components_from_pcb(ki_board: KiBoard, warnings: List[str]) -> List[Component]:
    """Extract components from KiCad board footprints."""

    components: List[Component] = []

    for fp in ki_board.footprints:
        ref = _get_footprint_reference(fp)
        if not ref:
            warnings.append(f"Footprint missing reference: {fp.libId}")
            continue

        # Get bounds from footprint courtyard or pads
        width, height = _get_footprint_bounds(fp)

        # Get position and rotation
        pos = (fp.position.X, fp.position.Y) if fp.position else None
        rot = int(fp.position.angle / 90) % 4 if fp.position and fp.position.angle else 0

        # Extract pins from pads
        pins: List[Pin] = []
        for pad in fp.pads:
            pad_pos = (pad.position.X, pad.position.Y) if pad.position else (0.0, 0.0)
            pin = Pin(
                name=pad.number or str(len(pins) + 1),
                number=pad.number or str(len(pins) + 1),
                position=pad_pos,
                net=pad.net.name if pad.net else None,
            )
            pins.append(pin)

        # Determine net class from pads
        net_class = "Signal"
        for pad in fp.pads:
            if pad.net and pad.net.name:
                net_name = pad.net.name.upper()
                if "VCC" in net_name or "VDD" in net_name or "PWR" in net_name:
                    net_class = "Power"
                    break
                elif "HV" in net_name or "BUS" in net_name:
                    net_class = "HighVoltage"
                    break

        # Get value/attributes
        attributes = {}
        for prop in getattr(fp, "properties", []):
            if hasattr(prop, "key") and hasattr(prop, "value"):
                attributes[prop.key] = prop.value

        comp = Component(
            ref=ref,
            footprint=fp.libId or "Unknown",
            bounds=(width, height),
            pins=pins,
            net_class=net_class,
            initial_position=pos,
            initial_rotation=rot,
            attributes=attributes,
        )
        components.append(comp)

    return components


def _extract_nets_from_pcb(
    ki_board: KiBoard, components: List[Component], warnings: List[str]
) -> List[Net]:
    """Extract nets from KiCad board."""

    # Build component lookup
    comp_by_ref = {c.ref: c for c in components}

    # Collect nets from pads
    nets_dict: Dict[str, List[Tuple[str, str]]] = {}

    for fp in ki_board.footprints:
        ref = _get_footprint_reference(fp)
        if not ref or ref not in comp_by_ref:
            continue

        for pad in fp.pads:
            if pad.net and pad.net.name:
                net_name = pad.net.name
                if net_name not in nets_dict:
                    nets_dict[net_name] = []
                nets_dict[net_name].append((ref, pad.number or ""))

    # Create Net objects
    nets: List[Net] = []
    for net_name, pins in nets_dict.items():
        if len(pins) < 2:
            continue  # Skip single-pin nets (unconnected)

        # Determine net class
        net_class = "Signal"
        upper_name = net_name.upper()
        if "GND" in upper_name or "VSS" in upper_name:
            net_class = "Power"
        elif (
            "VCC" in upper_name
            or "VDD" in upper_name
            or "+3V3" in upper_name
            or "+5V" in upper_name
        ):
            net_class = "Power"
        elif "HV" in upper_name or "BUS" in upper_name:
            net_class = "HighVoltage"

        # Assign weight (power nets are less critical for wirelength)
        weight = 0.5 if net_class == "Power" else 1.0

        net = Net(
            name=net_name,
            pins=pins,
            net_class=net_class,
            weight=weight,
        )
        nets.append(net)

    return nets


def _parse_schematic_sheet(
    schematic: Schematic,
    base_path: Path,
    all_components: List[Component],
    all_nets: Dict[str, Net],
    warnings: List[str],
    recursive: bool = True,
    sheet_prefix: str = "",
) -> None:
    """Parse a schematic sheet and its sub-sheets recursively."""

    # Extract symbols (components) from this sheet
    for symbol in schematic.schematicSymbols:
        ref = None
        value = None
        footprint = None

        # Get properties
        for prop in symbol.properties:
            if prop.key == "Reference":
                ref = prop.value
            elif prop.key == "Value":
                value = prop.value
            elif prop.key == "Footprint":
                footprint = prop.value

        if not ref or ref.startswith("#"):  # Skip power symbols
            continue

        # Apply sheet prefix for hierarchical refs
        full_ref = f"{sheet_prefix}{ref}" if sheet_prefix else ref

        # Get pins from symbol (need to map to footprint later)
        pins: List[Pin] = []
        for pin in getattr(symbol, "pins", []):
            pin_name = getattr(pin, "name", "") or str(len(pins) + 1)
            pin_num = getattr(pin, "number", "") or pin_name
            pins.append(
                Pin(
                    name=pin_name,
                    number=pin_num,
                    position=(0.0, 0.0),  # Will be set from footprint
                    net=None,  # Will be set from net connections
                )
            )

        comp = Component(
            ref=full_ref,
            footprint=footprint or "Unknown",
            bounds=(5.0, 5.0),  # Default, will be updated from footprint
            pins=pins,
            attributes={"Value": value} if value else {},
        )
        all_components.append(comp)

    # Extract nets from wires and labels
    # This is simplified - full net extraction requires tracking wire connections
    for label in getattr(schematic, "labels", []):
        label_text = getattr(label, "text", None)
        if label_text and label_text not in all_nets:
            all_nets[label_text] = Net(
                name=label_text,
                pins=[],  # Will be populated from component connections
                net_class="Signal",
            )

    # Recursively parse sub-sheets
    if recursive:
        for sheet in schematic.sheets:
            sheet_file = None
            sheet_name = None

            for prop in sheet.properties:
                if prop.key == "Sheetfile":
                    sheet_file = prop.value
                elif prop.key == "Sheetname":
                    sheet_name = prop.value

            if sheet_file:
                sub_path = base_path / sheet_file
                if sub_path.exists():
                    try:
                        sub_sch = Schematic.from_file(str(sub_path))
                        sub_prefix = f"{sheet_name}." if sheet_name else ""
                        _parse_schematic_sheet(
                            sub_sch,
                            base_path,
                            all_components,
                            all_nets,
                            warnings,
                            recursive=True,
                            sheet_prefix=f"{sheet_prefix}{sub_prefix}",
                        )
                    except Exception as e:
                        warnings.append(f"Failed to parse sub-sheet {sheet_file}: {e}")
                else:
                    warnings.append(f"Sub-sheet file not found: {sub_path}")


def _get_footprint_reference(fp: Footprint) -> Optional[str]:
    """Extract reference designator from footprint."""
    # Try properties first
    for prop in getattr(fp, "properties", []):
        if hasattr(prop, "key") and prop.key == "Reference":
            return prop.value

    # Try graphicItems (text items)
    for item in getattr(fp, "graphicItems", []):
        if hasattr(item, "type") and item.type == "reference":
            return getattr(item, "text", None)

    return None


def _get_footprint_bounds(fp: Footprint) -> Tuple[float, float]:
    """Get footprint bounding box from courtyard or pads."""

    x_min, y_min = float("inf"), float("inf")
    x_max, y_max = float("-inf"), float("-inf")

    # Try courtyard first (most accurate)
    for item in getattr(fp, "graphicItems", []):
        layer = getattr(item, "layer", "")
        if "CrtYd" in layer or "Courtyard" in layer:
            if hasattr(item, "start") and hasattr(item, "end"):
                for pt in [item.start, item.end]:
                    x_min = min(x_min, pt.X)
                    y_min = min(y_min, pt.Y)
                    x_max = max(x_max, pt.X)
                    y_max = max(y_max, pt.Y)

    # Fall back to pads
    if x_min == float("inf"):
        for pad in fp.pads:
            if pad.position:
                px, py = pad.position.X, pad.position.Y
                # Estimate pad size
                pw = getattr(pad.size, "X", 1.0) if hasattr(pad, "size") else 1.0
                ph = getattr(pad.size, "Y", 1.0) if hasattr(pad, "size") else 1.0
                x_min = min(x_min, px - pw / 2)
                y_min = min(y_min, py - ph / 2)
                x_max = max(x_max, px + pw / 2)
                y_max = max(y_max, py + ph / 2)

    # Default if nothing found
    if x_min == float("inf"):
        return (5.0, 5.0)

    width = x_max - x_min
    height = y_max - y_min

    # Add small margin
    return (max(width, 1.0), max(height, 1.0))
