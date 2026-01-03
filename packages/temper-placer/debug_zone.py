#!/usr/bin/env python3
"""
Test ZonePolygon usage for zone creation.
"""
from kiutils.board import Board
from kiutils.items.zones import Zone, ZonePolygon
from kiutils.items.common import Position

# Load the template board
board = Board.from_file("output_temper_with_priority.kicad_pcb")

# Find GND net
gnd_net = None
for net in board.nets:
    if net.name == "GND":
        gnd_net = net
        break

print(f"GND net: {gnd_net}")

# Use fallback rectangle for board outline 
outline = [(0, 0), (100, 0), (100, 130), (0, 130)]
print(f"Board outline: {outline}")

# Create zone
z = Zone()
z.net = gnd_net.number if gnd_net else 0
z.netName = gnd_net.name if gnd_net else "GND"
z.layers = ["In1.Cu"]
z.name = "GND_plane"
z.priority = 0
z.clearance = 0.3
z.minThickness = 0.25
z.connectPads = "thermal_reliefs"

# Create ZonePolygon with Position coordinates
positions = [Position(x, y) for x, y in outline]
zone_polygon = ZonePolygon(coordinates=positions)
z.polygons = [zone_polygon]

print(f"Zone layers: {z.layers}")
print(f"Zone polygons: {len(z.polygons)} ZonePolygon objects")
print(f"First polygon: {z.polygons[0]}")

# Try to serialize
try:
    sexpr = z.to_sexpr()
    print(f"\nSerialization SUCCESS! Length: {len(sexpr)} chars")
    print(f"First 500 chars:\n{sexpr[:500]}")
except Exception as e:
    print(f"\nSerialization FAILED: {e}")
    import traceback
    traceback.print_exc()

# Add to board and save
print("\nAdding zone to board and saving...")
board.zones.append(z)
try:
    board.to_file("output_zone_test.kicad_pcb")
    print("SUCCESS! Saved to output_zone_test.kicad_pcb")
    print("\nOpen in KiCad to verify the zone appears on In1.Cu")
except Exception as e:
    print(f"SAVE FAILED: {e}")
    import traceback
    traceback.print_exc()
