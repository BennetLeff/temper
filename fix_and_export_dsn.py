#!/usr/bin/env python3
"""
Re-export DSN with fixed pad layer definitions.

This script parses the KiCad PCB file with the updated parser that correctly
identifies through-hole pads and exports a DSN with proper multi-layer padstacks.
"""

import sys
from pathlib import Path

# Add temper-placer to path
sys.path.insert(0, str(Path(__file__).parent / "packages" / "temper-placer" / "src"))

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.dsn_exporter import DSNExporter


def main():
    # Parse the KiCad PCB
    kicad_pcb = Path("pcb/temper_boundary_fixed.kicad_pcb")
    if not kicad_pcb.exists():
        print(f"ERROR: {kicad_pcb} not found")
        sys.exit(1)

    print(f"Parsing {kicad_pcb}...")
    result = parse_kicad_pcb(kicad_pcb)

    if result.warnings:
        print("Warnings:")
        for w in result.warnings[:10]:
            print(f"  - {w}")

    netlist = result.netlist
    board = result.board

    print(f"\nParsed {len(netlist.components)} components, {len(netlist.nets)} nets")

    # Check pad layer info
    tht_count = 0
    smd_count = 0
    for comp in netlist.components:
        for pin in comp.pins:
            if pin.layer == "all":
                tht_count += 1
            else:
                smd_count += 1

    print(f"THT pads (layer='all'): {tht_count}")
    print(f"SMD pads (specific layer): {smd_count}")

    # Export DSN
    exporter = DSNExporter(board, netlist)
    dsn_expr = exporter.export_pcb(pcb_name="temper")
    dsn_content = str(dsn_expr)

    output_path = Path("pcb/temper_fixed_layers.dsn")
    output_path.write_text(dsn_content)
    print(f"\nExported to {output_path}")

    # Verify the DSN has correct padstack definitions
    print("\nVerifying DSN padstacks...")
    if "_ALL" in dsn_content:
        print("  OK: Found multi-layer padstacks (_ALL suffix)")
    else:
        print("  WARNING: No multi-layer padstacks found!")

    # Check layer types
    if '(layer F.Cu (type signal))' in dsn_content or '(layer "F.Cu" (type signal))' in dsn_content:
        print("  OK: F.Cu is signal type")
    if '(layer In1.Cu (type signal))' in dsn_content or '(layer "In1.Cu" (type signal))' in dsn_content:
        print("  OK: In1.Cu is signal type (was power)")
    if '(layer In2.Cu (type signal))' in dsn_content or '(layer "In2.Cu" (type signal))' in dsn_content:
        print("  OK: In2.Cu is signal type (was power)")

    print(f"\nDSN file ready for routing: {output_path}")


if __name__ == "__main__":
    main()
