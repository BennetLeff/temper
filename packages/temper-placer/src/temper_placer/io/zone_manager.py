"""
Zone manager for KiCad copper pour generation.

Creates copper pour zones (filled polygons) for power distribution layers.
Supports standard 4-layer stackup: F.Cu (signal) - In1.Cu (GND) - In2.Cu (VCC) - B.Cu (signal)
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence
import math

from kiutils.board import Board as KiBoard
from kiutils.items.zones import Zone, ZonePolygon
from kiutils.items.common import Position


@dataclass
class PlaneConfig:
    """Configuration for a power plane zone."""
    
    layer: str  # e.g., "In1.Cu"
    net_name: str  # e.g., "GND"
    priority: int = 0  # Higher priority zones fill first
    min_thickness: float = 0.25  # Minimum copper width in mm
    clearance: float = 0.3  # Clearance to other nets in mm
    thermal_gap: float = 0.3  # Thermal relief gap in mm
    thermal_bridge_width: float = 0.25  # Thermal spoke width in mm


@dataclass
class ZoneResult:
    """Result of zone generation."""
    
    zones_added: int
    nets_covered: list[str]
    layers_used: list[str]
    warnings: list[str] = field(default_factory=list)


def get_board_outline(board: KiBoard) -> list[tuple[float, float]]:
    """Extract board outline as polygon coordinates.
    
    Args:
        board: KiCad board object
        
    Returns:
        List of (x, y) coordinates forming the board outline
    """
    # Try to find Edge.Cuts layer graphics
    outline_points = []
    
    for item in board.graphicItems:
        if hasattr(item, 'layer') and item.layer == "Edge.Cuts":
            if hasattr(item, 'start') and hasattr(item, 'end'):
                # Line segment
                outline_points.append((item.start.X, item.start.Y))
                outline_points.append((item.end.X, item.end.Y))
    
    if not outline_points:
        # Fallback: default board size
        return [
            (0.0, 0.0),
            (100.0, 0.0),
            (100.0, 130.0),
            (0.0, 130.0),
        ]
    
    # Deduplicate and order points
    unique_points = list(set(outline_points))
    if len(unique_points) < 3:
        return [
            (0.0, 0.0),
            (100.0, 0.0),
            (100.0, 130.0),
            (0.0, 130.0),
        ]
    
    # Sort by angle from centroid for proper polygon ordering
    cx = sum(p[0] for p in unique_points) / len(unique_points)
    cy = sum(p[1] for p in unique_points) / len(unique_points)
    sorted_points = sorted(unique_points, key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
    
    return sorted_points


def get_net_code(board: KiBoard, net_name: str) -> int:
    """Get net code for a net name.
    
    Args:
        board: KiCad board object
        net_name: Name of the net
        
    Returns:
        Net code (integer), 0 if not found
    """
    for net in board.nets:
        if net.name == net_name:
            return net.number
    return 0


def create_zone(
    board: KiBoard,
    config: PlaneConfig,
    outline: list[tuple[float, float]],
) -> Zone:
    """Create a copper pour zone for a power plane.
    
    Args:
        board: KiCad board object
        config: Zone configuration
        outline: Board outline coordinates
        
    Returns:
        Zone object ready to add to board
    """
    net_code = get_net_code(board, config.net_name)
    
    # Create ZonePolygon with Position coordinates
    positions = [Position(x, y) for x, y in outline]
    zone_polygon = ZonePolygon(coordinates=positions)
    
    # Create zone
    zone = Zone()
    zone.net = net_code
    zone.netName = config.net_name
    zone.layers = [config.layer]
    zone.name = f"{config.net_name}_plane"
    zone.priority = config.priority
    zone.connectPads = "thermal_reliefs"
    zone.clearance = config.clearance
    zone.minThickness = config.min_thickness
    zone.polygons = [zone_polygon]  # Use ZonePolygon wrapper!
    
    return zone


def add_power_planes(
    board: KiBoard,
    gnd_nets: Sequence[str] = ("GND",),
    vcc_nets: Sequence[str] = ("+15V", "+5V", "+3V3", "VCC"),
    gnd_layer: str = "In1.Cu",
    vcc_layer: str = "In2.Cu",
) -> ZoneResult:
    """Add power plane zones to a 4-layer board.
    
    Creates copper pour zones on inner layers for power distribution.
    
    Args:
        board: KiCad board object to modify
        gnd_nets: Net names to connect to GND plane
        vcc_nets: Net names to connect to VCC plane
        gnd_layer: Layer for GND plane
        vcc_layer: Layer for VCC plane
        
    Returns:
        ZoneResult with statistics
    """
    outline = get_board_outline(board)
    warnings = []
    zones_added = 0
    nets_covered = []
    layers_used = []
    
    # Create GND plane (Layer 2 - In1.Cu)
    primary_gnd = None
    for net_name in gnd_nets:
        if get_net_code(board, net_name) != 0:
            primary_gnd = net_name
            break
            
    if primary_gnd:
        config = PlaneConfig(
            layer=gnd_layer,
            net_name=primary_gnd,
            priority=0,
            clearance=0.3,
        )
        zone = create_zone(board, config, outline)
        board.zones.append(zone)
        zones_added += 1
        nets_covered.append(primary_gnd)
        if gnd_layer not in layers_used:
            layers_used.append(gnd_layer)
    else:
        warnings.append("No GND nets found, skipping GND plane")
    
    # Create Power plane (Layer 3 - In2.Cu)
    # We prioritize higher voltage or distinct power rails if needed, 
    # but for now we look for the first match in the list.
    primary_vcc = None
    for net_name in vcc_nets:
        if get_net_code(board, net_name) != 0:
            primary_vcc = net_name
            break
    
    if primary_vcc:
        config = PlaneConfig(
            layer=vcc_layer,
            net_name=primary_vcc,
            priority=0,
            clearance=0.3,
        )
        zone = create_zone(board, config, outline)
        board.zones.append(zone)
        zones_added += 1
        nets_covered.append(primary_vcc)
        if vcc_layer not in layers_used:
            layers_used.append(vcc_layer)
    else:
        warnings.append("No VCC nets found, skipping VCC plane")
    
    return ZoneResult(
        zones_added=zones_added,
        nets_covered=nets_covered,
        layers_used=layers_used,
        warnings=warnings,
    )


def add_zones_to_pcb(
    input_pcb: Path,
    output_pcb: Path,
    gnd_nets: Sequence[str] = ("GND",),
    vcc_nets: Sequence[str] = ("+15V", "+5V", "+3V3", "VCC"),
) -> ZoneResult:
    """Add power plane zones to a PCB file.
    
    Args:
        input_pcb: Path to input KiCad PCB file
        output_pcb: Path to output KiCad PCB file
        gnd_nets: Net names for GND plane
        vcc_nets: Net names for VCC plane
        
    Returns:
        ZoneResult with statistics
    """
    board = KiBoard.from_file(str(input_pcb))
    result = add_power_planes(board, gnd_nets, vcc_nets)
    board.to_file(str(output_pcb))
    return result
