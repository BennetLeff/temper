#!/usr/bin/env python3
"""
Render PCB Result to SVG.

Exports the routed PCB layers for visual verification.
"""

import sys
from pathlib import Path
from temper_placer.io.render import export_layers_svg


def main():
    root_dir = Path(__file__).parent.parent
    pcb_dir = root_dir / "pcb"
    pcb_file = pcb_dir / "temper_router_v6_output.kicad_pcb"
    output_dir = pcb_dir / "renders"

    if not pcb_file.exists():
        print(f"Error: {pcb_file} not found. Run router first.")
        sys.exit(1)

    print(f"Rendering {pcb_file.name}...")

    # Render Top Layer (Cu + Silk + Edge)
    try:
        svg_path = export_layers_svg(
            pcb_file, output_dir, ["F.Cu", "F.SilkS", "Edge.Cuts"], filename_suffix="top"
        )
        print(f"  Exported Top Layer: {svg_path}")

    except Exception as e:
        print(f"Error rendering Top Layer: {e}")

    # Render Bottom Layer
    try:
        svg_path = export_layers_svg(
            pcb_file, output_dir, ["B.Cu", "Edge.Cuts"], filename_suffix="bottom"
        )
        print(f"  Exported Bottom Layer: {svg_path}")
    except Exception as e:
        print(f"Error rendering Bottom Layer: {e}")


if __name__ == "__main__":
    main()
