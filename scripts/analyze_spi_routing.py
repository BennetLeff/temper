#!/usr/bin/env python3
"""Analyze why SPI nets are failing to route."""

import math
from temper_placer.io.kicad_parser import parse_kicad_pcb
from pathlib import Path

def main():
    # Parse PCB
    parse_result = parse_kicad_pcb(Path('pcb/temper_ready_for_route.kicad_pcb'))
    netlist = parse_result.netlist
    board = parse_result.board

    # Get component positions
    positions = {c.ref: c.initial_position for c in netlist.components}

    # Find SPI nets
    spi_nets = ['SPI_CLK', 'SPI_MOSI', 'SPI_MISO', 'SPI_CS_TEMP']
    print('=== SPI NET ANALYSIS ===')
    print()

    for net_name in spi_nets:
        net = next((n for n in netlist.nets if n.name == net_name), None)
        if not net:
            print(f'{net_name}: NOT FOUND')
            continue
        
        print(f'NET: {net_name}')
        print(f'  Pins: {len(net.pins)}')
        
        for comp_ref, pin_name in net.pins:
            comp = next((c for c in netlist.components if c.ref == comp_ref), None)
            if comp:
                pos = positions.get(comp_ref, (0, 0))
                # Find the specific pin
                for pin in comp.pins:
                    if pin.name == pin_name or pin.number == pin_name:
                        abs_pos = pin.absolute_position(pos, math.radians((comp.initial_rotation or 0)*90))
                        print(f'    {comp_ref}.{pin_name} @ ({abs_pos[0]:.1f}, {abs_pos[1]:.1f})')
                        break
                else:
                    print(f'    {comp_ref}.{pin_name} @ {pos} (pin not found)')
        print()

    # Analyze component density in SPI routing corridor
    print('=== COMPONENTS IN SPI CORRIDOR (x < 25, y > 50) ===')
    for comp in netlist.components:
        pos = positions.get(comp.ref, (0, 0))
        if pos[0] < 25 and pos[1] > 50:
            print(f'  {comp.ref}: ({pos[0]:.1f}, {pos[1]:.1f})')

if __name__ == "__main__":
    main()
