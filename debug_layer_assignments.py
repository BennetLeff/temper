#!/usr/bin/env python3
"""
Diagnostic script to check layer assignments and via generation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "packages" / "temper-placer" / "src"))

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.routing.layer_assignment import assign_layers

def main():
    input_pcb = Path("pcb/temper_placed.kicad_pcb")
    
    print("Parsing PCB...")
    parse_result = parse_kicad_pcb(input_pcb)
    netlist = parse_result.netlist
    
    print("\\nAssigning layers...")
    assignments = assign_layers(netlist)
    
    print("\\n=== Layer Assignments ===\\n")
    
    # Focus on nets that failed in Run #33
    failed_nets = [
        "SPI_CS_TEMP", "USB_D-", "SPI_CLK", "SPI_MOSI", "SPI_MISO",
        "PWM_L", "SW_NODE", "VCC_BOOT", "PWM_H", "DC_BUS+"
    ]
    
    for net_name in failed_nets:
        if net_name in assignments:
            a = assignments[net_name]
            allowed_str = ", ".join([l.name for l in a.allowed_layers])
            print(f"{net_name:20} → Primary: {a.primary_layer.name:10} | Allowed: [{allowed_str}]")
            print(f"{'':20}   Vias: {'YES' if a.vias_required else 'NO':3} | Reason: {a.reason}")
            print()
        else:
            print(f"{net_name:20} → NOT FOUND")
            print()

if __name__ == "__main__":
    main()
