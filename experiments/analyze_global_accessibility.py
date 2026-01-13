
import sys
import os
from pathlib import Path
import numpy as np

# Add packages to path
sys.path.insert(0, str(Path("packages/temper-placer/src").absolute()))

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.routing.escape_analyzer import RingClassifier, PinInfo

def analyze_global_accessibility(pcb_path: str):
    try:
        result = parse_kicad_pcb(Path(pcb_path))
        board = result.board
        all_pads = result.pads
    except Exception as e:
        print(f"Failed to parse PCB: {e}")
        import traceback
        traceback.print_exc()
        return

    print(f"--- Global Accessibility Analysis for {pcb_path} ---")
    print(f"Total pads: {len(all_pads)}")
    
    if not all_pads:
        print("No pads found.")
        return

    # Treat all pads as one big component to find inner ones
    pins_info = []
    for i, pad in enumerate(all_pads):
        # We need a unique ID.
        pin_id = f"{pad.component_ref or 'UNK'}-{pad.number or i}-{pad.net or 'NoNet'}"
        pins_info.append(PinInfo(id=pin_id, x=pad.position[0], y=pad.position[1]))
        
    classifier = RingClassifier(pins_info)
    assignments = classifier.analyze()
    
    max_ring = max(a.ring_index for a in assignments.values())
    print(f"Max ring index: {max_ring}")
    
    trapped_pads = [a for a in assignments.values() if a.ring_index > 0]
    print(f"Trapped pads: {len(trapped_pads)}")
    
    # Group by ring
    for r in range(1, max_ring + 1):
        count = sum(1 for a in trapped_pads if a.ring_index == r)
        if count > 0:
            print(f"  Ring {r}: {count} pads")

    if trapped_pads:
        print("\nTop 10 Trapped Pads:")
        for a in trapped_pads[:10]:
            p = next(pi for pi in pins_info if pi.id == a.pin_id)
            print(f"  {a.pin_id} at ({p.x:.2f}, {p.y:.2f}) - Ring {a.ring_index}")

if __name__ == "__main__":
    pcb = "packages/temper-placer/router-experiments/results/EXP02E_BGA_Escape_input.kicad_pcb"
    if len(sys.argv) > 1:
        pcb = sys.argv[1]
    analyze_global_accessibility(pcb)
