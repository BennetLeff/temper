#!/usr/bin/env python3
"""
Run Placement Audit on a PCB file.
"""

import sys
from pathlib import Path
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
from temper_placer.placement.audit import PlacementAuditor


def main():
    pcb_path = Path("pcb/temper.kicad_pcb")
    if not pcb_path.exists():
        print(f"Error: {pcb_path} not found")
        sys.exit(1)

    print(f"Loading {pcb_path}...")
    pcb = parse_kicad_pcb_v6(pcb_path)

    print(f"Auditing placement of {len(pcb.components)} components...")
    auditor = PlacementAuditor(pcb)
    collisions = auditor.check_collisions()

    print(f"\nFound {len(collisions)} collisions:")
    for c in collisions:
        print(
            f"  {c.ref1} <-> {c.ref2} : Overlap {c.area:.2f} mm^2 at ({c.center[0]:.1f}, {c.center[1]:.1f})"
        )

    if collisions:
        sys.exit(1)
    else:
        print("\nPlacement is valid.")
        sys.exit(0)


if __name__ == "__main__":
    main()
