import os
import subprocess
import json
import uuid
import sys
from pathlib import Path
from kiutils.board import Board
from kiutils.items.brditems import Segment, Via
from kiutils.items.common import Position, Net
from kiutils.footprint import Footprint, Pad
from kiutils.items.zones import Zone, ZonePolygon, Hatch

def create_stub_pcb(output_path, template_path):
    """Create a minimal PCB with 4 different ground connectivity styles."""
    board = Board.from_file(template_path)
    
    # Clear existing trace items and footprints, but KEEP ZONES
    board.traceItems = []
    board.footprints = []
    # board.zones = [] # KEEP EXISTING ZONES
    
    # Find GND net
    gnd_net = next((n for n in board.nets if n.name == "GND"), None)
    if not gnd_net:
        print("Error: GND net not found in template!")
        sys.exit(1)
    net_id = gnd_net.number
    
    styles = [
        {"name": "ViaAtPad", "pos": (100, 80), "via_offset": (0, 0), "width": 0.2},
        {"name": "Stub0.1mm", "pos": (100, 90), "via_offset": (0.1, 0), "width": 0.2},
        {"name": "Stub0.5mm", "pos": (100, 100), "via_offset": (0.5, 0), "width": 0.2},
        {"name": "ThickStub", "pos": (110, 80), "via_offset": (0.5, 0), "width": 0.5},
    ]
    
    import uuid
    for s in styles:
        pad_x, pad_y = s["pos"]
        via_x, via_y = pad_x + s["via_offset"][0], pad_y + s["via_offset"][1]
        
        # Add Via
        v = Via(
            position=Position(X=via_x, Y=via_y),
            size=0.6,
            drill=0.3,
            layers=["F.Cu", "B.Cu"],
            net=net_id,
            tstamp=str(uuid.uuid4())
        )
        board.traceItems.append(v)
        
        # Add Stub
        seg = Segment(
            start=Position(X=pad_x, Y=pad_y),
            end=Position(X=via_x, Y=via_y),
            width=s["width"],
            layer="F.Cu",
            net=net_id,
            tstamp=str(uuid.uuid4())
        )
        board.traceItems.append(seg)
        # If offset is 0, add a tiny bit of track to avoid zero-length
        if s["via_offset"] == (0, 0):
             seg.end.X += 0.01

    # Add a footprint with a pad to anchor the zone
    fp = Footprint(
        description="GND Anchor",
        tstamp=str(uuid.uuid4()),
        position=Position(X=10, Y=10),
        layer="F.Cu"
    )
    pad = Pad(
        number="1",
        type="smd",
        shape="rect",
        position=Position(X=0, Y=0),
        size=Position(X=2, Y=2),
        layers=["F.Cu", "F.Mask"],
        net=Net(number=net_id, name="GND")
    )
    fp.pads.append(pad)
    board.footprints.append(fp)
    
    board.to_file(output_path)
    # ... (hack remains)
    
    # KiCad 9 Hack: Replace tstamp with uuid and fix connect_pads
    with open(output_path, 'r') as f:
        content = f.read()
    
    content = content.replace("tstamp", "uuid")
    content = content.replace("(connect_pads yes", "(connect_pads")
    
    with open(output_path, 'w') as f:
        f.write(content)
        
    print(f"Created and patched {output_path}")

def run_experiment():
    pcb_path = "experiments/exp_25_stubs.kicad_pcb"
    template_path = "piantor_production.kicad_pcb"
    os.makedirs("experiments", exist_ok=True)
    create_stub_pcb(pcb_path, template_path)
    
    # Fix and Fill
    subprocess.run(["python3", "fix_pcb.py", pcb_path], check=True)
    kicad_python = "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3"
    subprocess.run([kicad_python, "scripts/fill_zones.py", pcb_path], check=True)
    
    # Run DRC
    drc_path = "experiments/exp_25_drc.json"
    kicad_cli = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
    subprocess.run([
        kicad_cli, "pcb", "drc",
        "--output", drc_path,
        "--format", "json",
        pcb_path
    ], check=True)
    
    # Analyze
    with open(drc_path, 'r') as f:
        data = json.load(f)
    
    print("\nDRC Results:")
    violations = data.get('violations', [])
    unconnected = data.get('unconnected_items', [])
    
    print(f"Found {len(violations)} violations and {len(unconnected)} unconnected items.")
    
    for v in violations[:10]:
        print(f"  Violation: {v.get('description')} at {v.get('items')[0].get('pos')}")
        for item in v.get('items', []):
             print(f"    - {item.get('description')}")
    
    for u in unconnected[:10]:
        print(f"  Unconnected: {u.get('description')}")
        for item in u.get('items', []):
            print(f"    - {item.get('description')} at {item.get('pos')}")

if __name__ == "__main__":
    run_experiment()
