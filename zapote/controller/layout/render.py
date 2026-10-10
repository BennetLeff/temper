#!/usr/bin/env python3
"""Render a board to PNG for review: kicad-cli PDF of chosen layers, converted with macOS sips.

    python3 layout/render.py pcb/controller.kicad_pcb out.png [layers]
"""
import subprocess
import sys
import tempfile
from pathlib import Path

CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
board, out = sys.argv[1], Path(sys.argv[2])
layers = sys.argv[3] if len(sys.argv) > 3 else "Edge.Cuts,F.Fab,F.Cu,F.Silkscreen"
with tempfile.TemporaryDirectory() as tmp:
    pdf = Path(tmp) / "b.pdf"
    subprocess.run([CLI, "pcb", "export", "pdf", "--layers", layers, "--mode-single", "--black-and-white",
                    "--exclude-value", "-o", str(pdf), board], check=True, capture_output=True)
    if not pdf.exists():
        pdf = next(Path(tmp).glob("*.pdf"))
    subprocess.run(["sips", "-s", "format", "png", "-Z", sys.argv[4] if len(sys.argv) > 4 else "4000", str(pdf),
                    "--out", str(out)], check=True, capture_output=True)
print(out)
