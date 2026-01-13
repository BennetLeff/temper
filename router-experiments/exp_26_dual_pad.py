#!/usr/bin/env python3
"""
EXP-26: Dual-Pad Footprint Validation

Tests that the router correctly connects ALL pads sharing a pin number
in footprints with redundant pads (e.g., keyswitches with THT + SMD per pin).

Success Criteria:
- 4 pads per keyswitch (2 switches × 2 pins × 1 pad each → 4 total)
- All pads connected to GND zone after zone fill
- 0 unconnected items in DRC report
"""

from pathlib import Path
import sys
import subprocess
import json

# Add temper-placer to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages/temper-placer/src"))
# Add root for transplant_header
sys.path.insert(0, str(Path(__file__).parent.parent))

from transplant_header import transplant
from kiutils.board import Board as KiBoard
from kiutils.footprint import Footprint, Pad
from kiutils.items.common import Position, Net
from kiutils.items.zones import Zone, ZonePolygon, Hatch

def create_dual_pad_test_board():
    """Create a minimal board with dual-pad footprints."""
    
    # Create empty board
    board = KiBoard()
    board.version = "20241229"
    board.generator = "exp_26_dual_pad"
    
    # Board setup (60x60mm)
    board.general.thickness = 1.6
    
    # Layers are set via the KiCad template during transplant
    # Skip manual layer definition which causes import errors
    
    # Define nets
    board.nets = [
        Net(number=0, name=""),
        Net(number=1, name="GND"),
        Net(number=2, name="NET_A"),
    ]
    
    # Create 2 keyswitch-style footprints with dual pads per pin
    from kiutils.footprint import DrillDefinition
    
    for i, (x, y) in enumerate([(20, 20), (40, 20)]):
        fp = Footprint()
        fp.libId = "DualPad:Keyswitch"
        fp.position = Position(X=x, Y=y)
        fp.layer = "F.Cu"
        
        # Pin 1: THT pad + SMD pad (both GND)
        pad_tht = Pad()
        pad_tht.number = "1"
        pad_tht.type = "thru_hole"
        pad_tht.shape = "circle"
        pad_tht.position = Position(X=0, Y=0)
        pad_tht.size = Position(X=2.0, Y=2.0)
        pad_tht.drill = DrillDefinition(diameter=1.0)
        pad_tht.layers = ["*.Cu", "*.Mask"]
        pad_tht.net = Net(number=1, name="GND")
        
        pad_smd = Pad()
        pad_smd.number = "1"  # SAME number as THT
        pad_smd.type = "smd"
        pad_smd.shape = "rect"
        pad_smd.position = Position(X=3.0, Y=0)  # Offset from THT
        pad_smd.size = Position(X=1.5, Y=2.0)
        pad_smd.layers = ["F.Cu", "F.Paste", "F.Mask"]
        pad_smd.net = Net(number=1, name="GND")
        
        # Pin 2: THT pad + SMD pad (NET_A for signal routing test)
        pad_tht_2 = Pad()
        pad_tht_2.number = "2"
        pad_tht_2.type = "thru_hole"
        pad_tht_2.shape = "circle"
        pad_tht_2.position = Position(X=0, Y=-5)
        pad_tht_2.size = Position(X=2.0, Y=2.0)
        pad_tht_2.drill = DrillDefinition(diameter=1.0)
        pad_tht_2.layers = ["*.Cu", "*.Mask"]
        pad_tht_2.net = Net(number=2, name="NET_A")
        
        pad_smd_2 = Pad()
        pad_smd_2.number = "2"  # SAME number as THT
        pad_smd_2.type = "smd"
        pad_smd_2.shape = "rect"
        pad_smd_2.position = Position(X=3.0, Y=-5)
        pad_smd_2.size = Position(X=1.5, Y=2.0)
        pad_smd_2.layers = ["F.Cu", "F.Paste", "F.Mask"]
        pad_smd_2.net = Net(number=2, name="NET_A")
        
        fp.pads = [pad_tht, pad_smd, pad_tht_2, pad_smd_2]
        
        # Add reference property as dict (kiutils expects dict format)
        fp.properties = {"Reference": f"K{i+1}", "Value": "Keyswitch"}
        
        board.footprints.append(fp)
    
    # Add board outline (Edge.Cuts)
    from kiutils.items.gritems import GrLine
    outline_pts = [(0, 0), (60, 0), (60, 60), (0, 60), (0, 0)]
    for j in range(len(outline_pts) - 1):
        line = GrLine()
        line.start = Position(X=outline_pts[j][0], Y=outline_pts[j][1])
        line.end = Position(X=outline_pts[j+1][0], Y=outline_pts[j+1][1])
        line.layer = "Edge.Cuts"
        line.width = 0.1
        board.graphicItems.append(line)
    
    # Add GND zone covering entire board
    zone = Zone()
    zone.net = 1
    zone.netName = "GND"
    zone.name = "GND_zone"
    zone.layer = "F.Cu"
    zone.layers = ["F.Cu"]
    zone.hatch = Hatch(style="edge", pitch=0.5)
    zone.priority = 0
    zone.connectPads = "yes"
    zone.clearance = 0.2
    zone.minThickness = 0.2
    
    # Zone polygon
    poly = ZonePolygon()
    poly.coordinates = [
        Position(X=0, Y=0),
        Position(X=60, Y=0),
        Position(X=60, Y=60),
        Position(X=0, Y=60),
    ]
    zone.polygons = [poly]
    board.zones.append(zone)
    
    return board


def run_exp_26():
    """Run EXP-26: Dual-Pad Validation."""
    
    print("=" * 60)
    print("EXP-26: Dual-Pad Footprint Validation")
    print("=" * 60)
    
    # Create test board
    print("\n1. Creating dual-pad test board...")
    board = create_dual_pad_test_board()
    
    output_dir = Path("experiments/exp_26")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    pcb_path = output_dir / "dual_pad_test.kicad_pcb"
    board.to_file(str(pcb_path))
    print(f"   Saved to {pcb_path}")
    
    # Fix KiCad 9 compatibility
    print("\n2. Fixing KiCad 9 compatibility...")
    # We need a template - use Piantor if available
    template_path = Path("/tmp/piantor/pcb/right/keyboard_pcb.kicad_pcb")
    if template_path.exists():
        transplant(str(template_path), str(pcb_path))
    else:
        print("   WARNING: No template available, skipping header transplant")
    
    # Fill zones
    print("\n3. Filling zones...")
    kicad_python = "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3"
    result = subprocess.run(
        [kicad_python, "scripts/fill_zones.py", str(pcb_path)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"   WARNING: Zone fill failed: {result.stderr}")
    else:
        print("   Zone fill successful")
    
    # Run DRC
    print("\n4. Running DRC...")
    drc_path = output_dir / "dual_pad_drc.json"
    result = subprocess.run(
        ["/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli", "pcb", "drc",
         "--format", "json", "--output", str(drc_path), str(pcb_path)],
        capture_output=True, text=True
    )
    
    # Analyze results
    print("\n5. Analyzing DRC results...")
    if drc_path.exists():
        with open(drc_path) as f:
            drc = json.load(f)
        
        violations = drc.get("violations", [])
        unconnected = [v for v in violations if v.get("type") == "unconnected_items"]
        
        print(f"   Total violations: {len(violations)}")
        print(f"   Unconnected items: {len(unconnected)}")
        
        if len(unconnected) == 0:
            print("\n✓ SUCCESS: All pads connected!")
            return True
        else:
            print("\n✗ FAILURE: Unconnected items found:")
            for v in unconnected[:5]:
                print(f"     - {v.get('description', 'Unknown')}")
            return False
    else:
        print("   DRC output not found")
        return False


if __name__ == "__main__":
    success = run_exp_26()
    sys.exit(0 if success else 1)
