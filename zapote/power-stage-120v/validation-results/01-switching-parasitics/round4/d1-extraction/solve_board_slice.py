#!/usr/bin/env python3
"""Exploratory native BUS_P/In2 uniform-G tiling feasibility run.

This deliberately omits the rest of the 3-D copper, vias, mutual coupling,
and package. Its result must not be used as the D1 board inductance.
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import subprocess
from pathlib import Path

import numpy as np
import shapely
from audit_geometry import BOARD_SHA, COPPER, HERE, UNIT, board_drill_voids, digest, primitive_shape
from run_fixtures import read_z
from shapely.geometry import Point, box
from shapely.ops import unary_union

ROI = (124.0, 0.0, 166.0, 43.0)
PORT_REFS = ("C38.1", "Q2.2")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver", required=True, type=Path)
    parser.add_argument("--pitch", required=True, type=float, choices=(0.5, 0.25))
    parser.add_argument("--nhinc", type=int, default=1, choices=(1, 3))
    args = parser.parse_args()
    solver = args.solver.resolve(strict=True)
    pitch = args.pitch
    native = json.load(gzip.open(COPPER, "rt"))
    if {digest(UNIT / "native-15/section.kicad_pcb"), native["board_sha256"]} != {BOARD_SHA}:
        raise ValueError("board/copper hash mismatch")
    items = native["primitives"]
    copper = unary_union([primitive_shape(item) for item in items
                          if item["net"] == "bus_p" and item["layer"] == "In2.Cu"])
    copper = copper.difference(board_drill_voids(native)["In2.Cu"]).intersection(box(*ROI))
    x0, y0, x1, y1 = ROI
    xcentres = np.arange(x0 + pitch/2, x1, pitch)
    ycentres = np.arange(y0 + pitch/2, y1, pitch)
    xx, yy = np.meshgrid(xcentres, ycentres)
    occupied = shapely.intersects_xy(copper, xx, yy)
    patches = []
    for j, row in enumerate(occupied):
        delta = np.diff(np.pad(row.astype(np.int8), (1,1)))
        for start, stop in zip(np.flatnonzero(delta == 1), np.flatnonzero(delta == -1), strict=False):
            patches.append({"id": len(patches), "j": j, "start": int(start), "stop": int(stop), "nodes": {}})
    if not patches:
        raise ValueError("no bus copper")
    by_row: dict[int, list[dict]] = {}
    for patch in patches:
        by_row.setdefault(patch["j"], []).append(patch)
    def node(patch: dict, xi: int, yi: int) -> str:
        key = (xi, yi)
        if key not in patch["nodes"]:
            patch["nodes"][key] = f"n{patch['id']}x{xi}y{yi}"
        return patch["nodes"][key]
    equivalents = []
    for j in sorted(by_row):
        if j == 0:
            continue
        for lower in by_row.get(j-1, []):
            for upper in by_row[j]:
                lo, hi = max(lower["start"], upper["start"]), min(lower["stop"], upper["stop"])
                if lo < hi:
                    for xi in range(lo, hi + 1):
                        equivalents.append((node(lower, xi, j), node(upper, xi, j)))
    port_nodes = {}
    port_offsets = {}
    for ref in PORT_REFS:
        pad = next(item for item in items if item["kind"] == "pad" and item.get("ref") == ref
                   and item["layer"] == "In2.Cu")
        pad_shape = primitive_shape(pad)
        px, py = pad["centre"]
        candidates = []
        for patch in patches:
            ylo, yhi = y0 + patch["j"]*pitch, y0 + (patch["j"]+1)*pitch
            if py < ylo - 2 or py > yhi + 2:
                continue
            for yi in (patch["j"], patch["j"]+1):
                for xi in range(patch["start"], patch["stop"]+1):
                    x, y = x0 + xi*pitch, y0 + yi*pitch
                    if abs(x-px) <= 2 and pad_shape.covers(Point(x,y)):
                        candidates.append(((x-px)**2+(y-py)**2, patch, xi, yi))
        if not candidates:
            raise ValueError(f"no G node on exact {ref} annulus")
        distance2, patch, xi, yi = min(candidates, key=lambda value: value[0])
        port_nodes[ref] = node(patch, xi, yi)
        port_offsets[ref] = distance2**0.5
    label = str(pitch).replace(".", "p")
    directory = HERE / "extraction" / f"board-slice-p{label}-nh{args.nhinc}"
    directory.mkdir(parents=True, exist_ok=True)
    lines = ["* UNQUALIFIED board slice: A leg BUS_P/In2 only, local rectangular crop; no other conductors",
             ".units mm", ".default sigma=5.8e4"]
    z = 1.062 # copper centre from committed stackup/round3 A2; audited below
    stack_z = json.loads((UNIT / "validation-results/01-switching-parasitics/round3/a2-inductance/outputs/connected_routes_0p25.json").read_text())["z_centres_mm"]["In2.Cu"]
    if abs(stack_z-z) > 1e-9:
        raise ValueError("stackup z mismatch")
    for patch in patches:
        j, i0, i1 = patch["j"], patch["start"], patch["stop"]
        xa, xb = x0+i0*pitch, x0+i1*pitch
        ya, yb = y0+j*pitch, y0+(j+1)*pitch
        lines.append(f"g{patch['id']} x1={xa:.6f} y1={ya:.6f} z1={z:.6f} x2={xb:.6f} y2={ya:.6f} z2={z:.6f} x3={xb:.6f} y3={yb:.6f} z3={z:.6f}")
        lines.append(f"+ thick=0.061 seg1={i1-i0} seg2=1 nhinc={args.nhinc} rh=1")
        for (xi, yi), name in sorted(patch["nodes"].items()):
            lines.append(f"+ {name} ({x0+xi*pitch:.6f},{y0+yi*pitch:.6f},{z:.6f})")
    for a,b in equivalents:
        lines.append(f".equiv {a} {b}")
    lines.extend([f".external {port_nodes[PORT_REFS[0]]} {port_nodes[PORT_REFS[1]]}",
                  ".freq fmin=1e7 fmax=1e7 ndec=1", ".end"])
    deck = directory / "board-slice.inp"
    deck.write_text("\n".join(lines) + "\n")
    timed = subprocess.run(["/usr/bin/time", "-l", str(solver), str(deck)], cwd=directory,
                           text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=120, check=False)
    (directory / "solver.log").write_text(timed.stdout)
    rss = re.search(r"(\d+)\s+maximum resident set size", timed.stdout)
    result = {"status": "SOLVED_UNQUALIFIED_SLICE" if timed.returncode == 0 else "SOLVER_FAILED",
              "board_sha256": BOARD_SHA, "source_export_sha256": digest(COPPER),
              "roi_xy_mm": ROI, "net": "bus_p", "layer": "In2.Cu", "pitch_mm": pitch,
              "nhinc": args.nhinc, "scope_warning": "Single layer, one net, one branch, cropped polygon-cell approximation; omits other copper, other nets, vias, mutuals and true pad contact distribution. Cannot feed D2.",
              "exact_cropped_area_mm2": copper.area, "raster_cell_area_mm2": int(occupied.sum())*pitch*pitch,
              "G_patch_count": len(patches), "seam_equiv_count": len(equivalents),
              "port_nodes": port_nodes, "port_to_pad_centre_offset_mm": port_offsets,
              "input_bytes": deck.stat().st_size,
              "maximum_resident_set_size_bytes": int(rss[1]) if rss else None,
              "exit_code": timed.returncode}
    if timed.returncode == 0:
        r, x = read_z(directory / "Zc.mat")
        result.update({"R_ohm": r, "X_ohm": x, "L_nH_at_10MHz": x/(2*np.pi*10_000_000)*1e9})
    (directory / "result.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
