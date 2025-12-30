
import math
import uuid
from typing import List, Tuple
from kiutils.board import Board
from kiutils.items.common import Position
from kiutils.items.brditems import Via, Segment
from temper_placer.core.netlist import Netlist
# Use "TYPE_CHECKING" or just strict reference if available
# But to avoid runtime import issues with circular deps if drc_oracle imports this:
from typing import Optional, Any 

def fanout_power_nets(
    board: Board,
    netlist: Netlist,
    power_nets: List[str],
    drc_oracle: Any = None,
    via_offset: float = 1.0,
    trace_width: float = 0.5
) -> int:
    """
    Fanout power/ground nets to vias connecting to inner planes.
    
    Args:
        board: KiCad board object.
        netlist: Parsed netlist.
        power_nets: List of net names to fanout.
        drc_oracle: Optional DRCOracle for checking placement.
        via_offset: Distance from pad center to via center (mm).
        trace_width: Width of the fanout trace (mm).
        
    Returns:
        Number of fanouts created.
    """
    fanouts_created = 0
    
    # Map net names to their IDs/Codes in board
    net_map = {net.name: net.number for net in board.nets}
    
    # Iterate over components to find pads connected to power nets
    for comp in board.footprints:
        ref = comp.properties.get("Reference", "")
        
        for pad in comp.pads:
            if pad.net.name in power_nets:
                net_code = net_map.get(pad.net.name, 0)
                if net_code == 0:
                    continue

                # Determine start position (Pad Center)
                start_x, start_y = pad.position.X, pad.position.Y
                
                # Default direction: (1, 1) diagonal
                dx, dy = 1.0, 1.0 
                
                # Infer component center (simplistic)
                comp_x, comp_y = comp.position.X, comp.position.Y
                vec_x = start_x - comp_x
                vec_y = start_y - comp_y
                length = math.sqrt(vec_x**2 + vec_y**2)
                
                if length > 0.001:
                    dx, dy = vec_x / length, vec_y / length
                
                # Calculate via position
                via_x = start_x + dx * via_offset
                via_y = start_y + dy * via_offset
                
                # Check DRC if oracle provided
                if drc_oracle:
                    valid, _ = drc_oracle.can_place_via((via_x, via_y), 0.6, pad.net.name) 
                    if not valid:
                        # Try a few other angles
                        for angle in [45, 90, -45, -90, 135, -135, 180]:
                            rad = math.radians(angle)
                            rx = dx * math.cos(rad) - dy * math.sin(rad)
                            ry = dx * math.sin(rad) + dy * math.cos(rad)
                            tx = start_x + rx * via_offset
                            ty = start_y + ry * via_offset
                            valid, _ = drc_oracle.can_place_via((tx, ty), 0.6, pad.net.name)
                            if valid:
                                via_x, via_y = tx, ty
                                break
                        if not valid:
                             continue

                # Create Track (Segment in KiCad/KiUtils)
                # Determine layer: default to F.Cu unless pad is exclusively bottom
                layer = "F.Cu"
                if pad.layers:
                    if "B.Cu" in pad.layers and "F.Cu" not in pad.layers:
                        layer = "B.Cu"
                    # Else if both or just front, use Front.
                    # Or use pad's layer specifically.
                    # For now F.Cu is safe for SMD on Top.
                
                track = Segment(
                    start=Position(start_x, start_y),
                    end=Position(via_x, via_y),
                    width=trace_width,
                    layer=layer,
                    net=net_code,
                    tstamp=str(uuid.uuid4())
                )
                
                # Create Via
                via = Via(
                    position=Position(via_x, via_y),
                    size=0.6,
                    drill=0.3,
                    layers=["F.Cu", "B.Cu"],
                    net=net_code,
                    tstamp=str(uuid.uuid4())
                )
                
                # Add to board.traceItems (not tracks)
                board.traceItems.append(track)
                board.traceItems.append(via)
                fanouts_created += 1

    return fanouts_created
