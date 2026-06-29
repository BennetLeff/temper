
import argparse
from pathlib import Path

import jax.numpy as jnp

from temper_placer.io.dsn_exporter import DSNExporter
from temper_placer.io.kicad_parser import parse_kicad_pcb


def main():
    parser = argparse.ArgumentParser(description="Export KiCad PCB to SPECCTRA DSN format")
    parser.add_argument("input_pcb", type=Path, help="Input KiCad PCB file")
    parser.add_argument("output_dsn", type=Path, help="Output DSN file")
    parser.add_argument("--exclude-nets", type=str, default=None,
                        help="Comma-separated list of nets to exclude from routing (e.g., GND,PGND)")
    args = parser.parse_args()

    input_pcb = args.input_pcb
    output_dsn = args.output_dsn

    print(f"Parsing PCB: {input_pcb}")
    parse_result = parse_kicad_pcb(input_pcb)

    netlist = parse_result.netlist
    board = parse_result.board

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

    # Parse exclude_nets argument
    exclude_nets = None
    if args.exclude_nets:
        exclude_nets = {n.strip() for n in args.exclude_nets.split(",")}
        print(f"Excluding nets from routing: {exclude_nets}")

    print(f"Exporting to DSN: {output_dsn} (Traces: Disabled)")
    exporter = DSNExporter(board, netlist, positions_array, rotations_array)
    # We pass None for traces to ensure a clean board for autorouting
    dsn_content = str(exporter.export_pcb(traces=None, exclude_nets=exclude_nets))

    with open(output_dsn, "w") as f:
        f.write(dsn_content)

    print(f"Successfully exported {len(netlist.components)} components and {len(netlist.nets)} nets to {output_dsn}")

if __name__ == "__main__":
    main()

