
import os
from pathlib import Path
import math

def create_dense_pcb(output_path: str):
    """Creates a KiCad PCB with a dense grid component and peripheral pins."""
    content = [
        '(kicad_pcb (version 20211014) (generator "manual")',
        '  (paper "A4")',
        '  (layers',
        '    (0 "F.Cu" signal)',
        '    (31 "B.Cu" signal)',
        '    (44 "Edge.Cuts" user)',
        '  )',
        '  (gr_line (start 0 0) (end 100 0) (layer "Edge.Cuts") (width 0.1))',
        '  (gr_line (start 100 0) (end 100 100) (layer "Edge.Cuts") (width 0.1))',
        '  (gr_line (start 100 100) (end 0 100) (layer "Edge.Cuts") (width 0.1))',
        '  (gr_line (start 0 100) (end 0 0) (layer "Edge.Cuts") (width 0.1))'
    ]
    
    # 1. Nets
    for i in range(1, 17):
        content.append(f'  (net {i} "NET_{i:03d}")')
        
    # 2. Dense Component (4x4 BGA-style grid)
    # Center at (50, 50), Pitch 1mm
    content.append('  (footprint "Test:DenseGrid" (layer "F.Cu") (at 50 50)')
    content.append('    (property "Reference" "U1")')
    for r in range(4):
        for c in range(4):
            idx = r * 4 + c + 1
            px = (c - 1.5) * 1.0
            py = (r - 1.5) * 1.0
            content.append(f'    (pad "{idx}" smd circle (at {px:.2f} {py:.2f}) (size 0.5 0.5) (layers "F.Cu" "F.Mask") (net {idx} "NET_{idx:03d}"))')
    content.append('  )')
    
    # 3. Peripheral Component (16-pin Header)
    # At (10, 50), Pitch 2.54mm
    content.append('  (footprint "Connector_PinHeader_2.54mm:PinHeader_1x16_P2.54mm_Vertical" (layer "F.Cu") (at 10 50)')
    content.append('    (property "Reference" "J1")')
    for i in range(1, 17):
        py = (i - 8.5) * 2.54
        content.append(f'    (pad "{i}" thru_hole circle (at 0 {py:.2f}) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net {i} "NET_{i:03d}"))')
    content.append('  )')
    
    content.append(')')
    
    with open(output_path, "w") as f:
        f.write("\n".join(content))
    print(f"Created dense PCB at {output_path}")

if __name__ == "__main__":
    create_dense_pcb("experiments/dense_test.kicad_pcb")
