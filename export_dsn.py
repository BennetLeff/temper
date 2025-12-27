
import sys
from pathlib import Path
import jax.numpy as jnp
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.dsn_exporter import DSNExporter

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 export_dsn.py <input.kicad_pcb> <output.dsn>")
        sys.exit(1)

    input_pcb = Path(sys.argv[1])
    output_dsn = Path(sys.argv[2])

    print(f"Parsing PCB: {input_pcb}")
    parse_result = parse_kicad_pcb(input_pcb)
    
    netlist = parse_result.netlist
    board = parse_result.board
    traces = parse_result.traces
    
    # Extract positions and rotations from netlist components
    positions = []
    rotations = []
    for comp in netlist.components:
        # initial_position is board-relative in parse_kicad_pcb
        positions.append(comp.initial_position or (0.0, 0.0))
        # initial_rotation is 0-3 index
        rotations.append(comp.initial_rotation or 0)
    
    positions_array = jnp.array(positions)
    rotations_array = jnp.array(rotations)

    print(f"Exporting to DSN: {output_dsn} (Traces: Disabled)")
    exporter = DSNExporter(board, netlist, positions_array, rotations_array)
    # We pass None for traces to ensure a clean board for autorouting
    dsn_content = str(exporter.export_pcb(traces=None))
    
    with open(output_dsn, "w") as f:
        f.write(dsn_content)
    
    print(f"Successfully exported {len(netlist.components)} components and {len(netlist.nets)} nets to {output_dsn}")

if __name__ == "__main__":
    main()
