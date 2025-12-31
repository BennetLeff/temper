from temper_placer.io.kicad_parser import parse_kicad_pcb

r = parse_kicad_pcb('placement_optimized_02.kicad_pcb')
print("All Net Pin Counts:")
for net in r.netlist.nets:
    print(f"  {net.name}: {len(net.pins)} pins")
