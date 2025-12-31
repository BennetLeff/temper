from temper_placer.io.kicad_parser import parse_kicad_pcb

r = parse_kicad_pcb('debug_zones.kicad_pcb')
print(f"Total Zones: {len(r.board.zones)}")
for z in r.board.zones:
    print(f"  Zone Net: {z.net_name} Layer: {z.layer}")
