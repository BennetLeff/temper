
import sys
import os
from pathlib import Path

# Add packages to path
sys.path.insert(0, str(Path("packages/temper-placer/src").absolute()))
print(f"DEBUG: sys.path[0] = {sys.path[0]}")

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.routing.escape_analyzer import RingClassifier, PinInfo

def analyze_pcb_accessibility(pcb_path: str):
    try:
        result = parse_kicad_pcb(Path(pcb_path))
        board_obj = result.board
        netlist = result.netlist
    except Exception as e:
        print(f"Failed to parse PCB: {e}")
        import traceback
        traceback.print_exc()
        return

    print(f"--- Accessibility Analysis for {pcb_path} ---")
    
    components_with_escapes = []
    
    for comp in netlist.components:
        if len(comp.pins) < 1: # Debugging all
            # print(f"Component {comp.ref} has pins: {[p.number for p in comp.pins]}")
            pass

        if len(comp.pins) < 8: # Small components usually don't need escapes
            continue
            
        if comp.ref == "U_MCU":
            print(f"U_MCU pins found: {[p.number for p in comp.pins]}")
        print(f"Component {comp.ref} has {len(comp.pins)} pins.")
        pins_info = []
        for pin in comp.pins:
            pin_id = f"{comp.ref}-{pin.number}"
            pins_info.append(PinInfo(id=pin_id, x=pin.position[0], y=pin.position[1]))
            
        classifier = RingClassifier(pins_info)
        assignments = classifier.analyze()
        
        max_ring = max(a.ring_index for a in assignments.values())
        
        if max_ring > 0:
            trapped_pins_list = [a.pin_id for a in assignments.values() if a.ring_index > 0]
            trapped_count = len(trapped_pins_list)
            components_with_escapes.append({
                "ref": comp.ref,
                "total_pins": len(comp.pins),
                "max_ring": max_ring,
                "trapped_pins": trapped_count,
                "trapped_list": trapped_pins_list
            })
            
    # Sort by number of trapped pins
    components_with_escapes.sort(key=lambda x: x["trapped_pins"], reverse=True)
    
    print(f"{'Ref':<10} | {'Total Pins':<12} | {'Max Ring':<10} | {'Trapped Pins':<12}")
    print("-" * 55)
    for c in components_with_escapes:
        print(f"{c['ref']:<10} | {c['total_pins']:<12} | {c['max_ring']:<10} | {c['trapped_pins']:<12}")
        print(f"  Trapped: {', '.join(c['trapped_list'])}")

    if not components_with_escapes:
        print("No components require escape routing (all pins are on the periphery).")
    else:
        total_trapped = sum(c['trapped_pins'] for c in components_with_escapes)
        print(f"\nTotal trapped pins identified: {total_trapped}")
        print("These pins MUST have escape routes (fanouts) to be routable on a grid.")

if __name__ == "__main__":
    pcb = "pre_routed_v6.kicad_pcb"
    if len(sys.argv) > 1:
        pcb = sys.argv[1]
    analyze_pcb_accessibility(pcb)
