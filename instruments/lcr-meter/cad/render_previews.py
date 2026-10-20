#!/usr/bin/env python3
"""Render actual native exports; requires pygerber 2.4.3, cairosvg and pdftoppm."""
from pathlib import Path
import subprocess
import sys
import cairosvg

root = Path(__file__).resolve().parent.parent
preview = root / "previews"
for name in ["pcb-front", "assembly-top"]:
    cairosvg.svg2png(url=str(preview / (name+".svg")),
                    write_to=str(preview / (name+".png")), output_width=2400)
subprocess.run(["pdftoppm", "-scale-to", "3600", "-png", "-singlefile",
                str(preview / "schematic.pdf"), str(preview / "schematic")], check=True)
subprocess.run(["pdftoppm", "-scale-to", "2400", "-png",
                str(preview / "schematic.pdf"), str(preview / "schematic-page")], check=True)
for layer, name in [("F_Cu.gtl", "top-copper"), ("B_Cu.gbl", "bottom-copper"),
                    ("In1_Cu.g1", "ground"), ("In2_Cu.g2", "inner-routing"),
                    ("F_Mask.gts", "top-mask"), ("B_Mask.gbs", "bottom-mask"),
                    ("F_Paste.gtp", "top-paste"), ("F_Silkscreen.gto", "top-silk"),
                    ("Edge_Cuts.gm1", "outline")]:
    # API V2 is required: legacy raster-2d omits some KiCad roundrect macros.
    subprocess.run([str(Path(sys.executable).with_name("pygerber")), "render", "raster",
                    str(root / "manufacturing/gerbers" / ("temper-lcr-"+layer)),
                    "-o", str(preview / ("gerber-"+name+".png")), "-d", "30"], check=True)
