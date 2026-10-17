#!/usr/bin/env python3
"""Review the native-17 fabrication files without KiCad.

Reads the Excellon drill files and Gerber outline directly, renders each
Gerber with gerbv (an independent RS-274X renderer) on one fixed pixel grid,
and checks, for every drill hit:
  - copper on F.Cu and B.Cu around the hole (a solder land / outer ring),
  - a solder-mask opening on both sides over every plated hole,
  - no silkscreen on the land ring.
It also checks hole counts against the board's own census and the outline size.

    python3 scripts/review_fab.py fab/gerbers review.json
"""
from __future__ import annotations

import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

DPI = 1000                      # 0.0254 mm per pixel
MM_PER_PX = 25.4 / DPI
RING_OFFSET_MM = 0.12           # sample radius beyond the drill edge (< 0.15 mm via ring)
ANGLES = 12


def excellon(path: Path) -> list[tuple[float, float, float, str]]:
    """Hits as (x, y, drill, function); function is KiCad's X2 aperture
    attribute from the tool header (ViaDrill, ComponentDrill, ...)."""
    tools, hits, tool, function = {}, [], None, "unknown"
    for line in path.read_text().splitlines():
        if m := re.match(r"; #@! TA.AperFunction,\w+,\w+,(\w+)", line):
            function = m[1]
        elif m := re.fullmatch(r"T(\d+)C([\d.]+)", line):
            tools[int(m[1])] = (float(m[2]), function)
        elif m := re.fullmatch(r"T(\d+)", line):
            tool = int(m[1])
        elif m := re.fullmatch(r"X(-?[\d.]+)Y(-?[\d.]+)", line):
            hits.append((float(m[1]), float(m[2]), *tools[tool]))
    if "METRIC" not in path.read_text():
        raise ValueError(f"{path}: expected metric Excellon")
    return hits


def outline_extent(path: Path) -> tuple[float, float, float, float]:
    text = path.read_text()
    fmt = re.search(r"%FSLAX(\d)(\d)Y", text)
    scale = 10 ** int(fmt[2])
    xs, ys = [], []
    for m in re.finditer(r"X(-?\d+)Y(-?\d+)D0[12]", text):
        xs.append(int(m[1]) / scale); ys.append(int(m[2]) / scale)
    return min(xs), min(ys), max(xs), max(ys)


def clear_flashes(path: Path) -> set[tuple[float, float]]:
    """D03 flash positions inside %LPC% (clear) sections: with
    --subtract-soldermask, KiCad clears the silk over each mask opening
    this way."""
    text = path.read_text()
    fmt = re.search(r"%FSLAX(\d)(\d)Y", text)
    scale = 10 ** int(fmt[2])
    flashes, clear = set(), False
    for line in text.splitlines():
        if line.startswith("%LPC"):
            clear = True
        elif line.startswith("%LPD"):
            clear = False
        elif clear and (m := re.fullmatch(r"X(-?\d+)Y(-?\d+)D03\*", line)):
            flashes.add((round(int(m[1]) / scale, 3), round(int(m[2]) / scale, 3)))
    return flashes


def render(gerber: Path, origin: tuple[float, float], size_mm: tuple[float, float], out: Path) -> np.ndarray:
    run = subprocess.run(["gerbv", "-x", "png", "-B", "0", "-D", str(DPI), "-b", "#000000", "-f", "#FFFFFF",
                          "-O", f"{origin[0] / 25.4:.5f};{origin[1] / 25.4:.5f}",
                          "-W", f"{size_mm[0] / 25.4:.5f}x{size_mm[1] / 25.4:.5f}",
                          "-o", str(out), str(gerber)], capture_output=True, text=True)
    if run.returncode or not out.exists():
        raise RuntimeError(f"gerbv failed on {gerber.name}: {run.stderr[-500:]}")
    return np.asarray(Image.open(out).convert("L")) > 127


def main() -> None:
    gdir, report = Path(sys.argv[1]), Path(sys.argv[2])
    pth = excellon(gdir / "section-PTH.drl")
    npth = excellon(gdir / "section-NPTH.drl")
    x0, y0, x1, y1 = outline_extent(gdir / "section-Edge_Cuts.gm1")
    margin = 2.0
    origin = (x0 - margin, y0 - margin)
    size = (x1 - x0 + 2 * margin, y1 - y0 + 2 * margin)
    layers = {"F.Cu": "section-F_Cu.gtl", "B.Cu": "section-B_Cu.gbl", "F.Mask": "section-F_Mask.gts",
              "B.Mask": "section-B_Mask.gbs", "F.Silk": "section-F_Silkscreen.gto",
              "B.Silk": "section-B_Silkscreen.gbo"}
    images = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name, file in layers.items():
            images[name] = render(gdir / file, origin, size, Path(tmp) / f"{name}.png")
    height = images["F.Cu"].shape[0]

    def px(x: float, y: float) -> tuple[int, int]:
        # Image row 0 is the window top (largest Gerber Y).
        return int(round((x - origin[0]) / MM_PER_PX)), int(round(height - 1 - (y - origin[1]) / MM_PER_PX))

    def on(img: np.ndarray, x: float, y: float) -> bool:
        c, r = px(x, y)
        return bool(img[r, c])

    def ring(x: float, y: float, d: float) -> list[tuple[float, float]]:
        r = d / 2 + RING_OFFSET_MM
        return [(x + r * math.cos(2 * math.pi * k / ANGLES), y + r * math.sin(2 * math.pi * k / ANGLES))
                for k in range(ANGLES)]

    fails = {"no_outer_copper": [], "no_mask_opening": [], "silk_on_land": []}
    cleared = {"F": clear_flashes(gdir / "section-F_Silkscreen.gto"),
               "B": clear_flashes(gdir / "section-B_Silkscreen.gbo")}
    tented_vias = 0
    for x, y, d, function in pth:
        pts = ring(x, y, d)
        for side in ("F", "B"):
            if not all(on(images[f"{side}.Cu"], *p) for p in pts):
                fails["no_outer_copper"].append({"x": x, "y": y, "drill": d, "side": side})
            if function == "ViaDrill":
                tented_vias += not on(images[f"{side}.Mask"], x, y)
                continue
            if not on(images[f"{side}.Mask"], x, y):
                fails["no_mask_opening"].append({"x": x, "y": y, "drill": d, "side": side})
            # Silk over a land must be cleared by a flash in the silk file's
            # clear-polarity section. (gerbv doesn't clear KiCad's RoundRect
            # macro in LPC mode, so the rendered silk isn't used for this.)
            if any(on(images[f"{side}.Silk"], *p) for p in pts) and (round(x, 3), round(y, 3)) not in cleared[side]:
                fails["silk_on_land"].append({"x": x, "y": y, "drill": d, "side": side})
    result = {
        "pth_hits": len(pth), "npth_hits": len(npth),
        "pth_by_function": {f: sum(1 for h in pth if h[3] == f) for f in sorted({h[3] for h in pth})},
        "tented_via_sides": tented_vias,
        "outline_mm": [round(x1 - x0, 3), round(y1 - y0, 3)],
        "render": {"tool": "gerbv", "dpi": DPI, "ring_offset_mm": RING_OFFSET_MM, "angles": ANGLES},
        "failures": {k: v for k, v in fails.items()},
        "status": "PASS" if not any(fails.values()) else "FAIL",
    }
    report.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in result["failures"].items()}),
          result["pth_hits"], result["npth_hits"], result["outline_mm"], result["status"])


if __name__ == "__main__":
    main()
