"""Render the C49 board of record's placement with the C60 cut line, for comparison (renders/c49-placement.*).

    python3 -I scripts/render_c49.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import geom  # noqa: E402
import render  # noqa: E402

parts, d = geom.load_parts()
poses = {r: tuple(p["world"]) for r, p in parts.items()}
HOLES = [(164.0, 18.0), (164.0, 80.0), (65.0, 18.0), (75.0, 86.0), (-34.0, 18.0), (-26.0, 74.0)]   # C/layout/world.py:54
render.draw(parts, poses, (-38.0, 14.0, 168.0, 90.0), HOLES, HERE.parent / "renders" / "c49-placement",
            "C49 board of record (206 x 76 mm, 25.6 % courtyard): shaded strip X93..168 is what the A-cut removes",
            zones=[(93.0, 14.0, 168.0, 90.0, "removed by the 131 x 76 cut", "#c0392b")])
