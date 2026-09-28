#!/usr/bin/env python3
"""Test one holed uniform-G plane against native BUS_P/In2 copper (unqualified)."""
from __future__ import annotations

import argparse
import gzip
import json
import subprocess
from pathlib import Path

import numpy as np
import shapely
from audit_geometry import BOARD_SHA, COPPER, HERE, UNIT, board_drill_voids, digest, primitive_shape
from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver", type=Path, required=True)
    parser.add_argument("--pitch", type=float, required=True, choices=(0.5, 0.25, 0.125))
    parser.add_argument("--solve", action="store_true")
    args = parser.parse_args()
    data = json.load(gzip.open(COPPER, "rt"))
    if data["board_sha256"] != BOARD_SHA or digest(UNIT / "native-15/section.kicad_pcb") != BOARD_SHA:
        raise ValueError("native board hash mismatch")
    primitives = data["primitives"]
    roi = (124.0, 0.0, 166.0, 43.0)
    x0, y0, x1, y1 = roi
    pitch = args.pitch
    nx, ny = round((x1-x0)/pitch), round((y1-y0)/pitch)
    full_copper = unary_union([primitive_shape(p) for p in primitives if p["net"] == "bus_p" and p["layer"] == "In2.Cu"])
    full_copper = full_copper.difference(board_drill_voids(data)["In2.Cu"])
    copper = full_copper.intersection(box(*roi))
    xs = x0 + np.arange(nx+1)*pitch
    ys = y0 + np.arange(ny+1)*pitch
    xx, yy = np.meshgrid(xs, ys)
    present = shapely.intersects_xy(copper, xx, yy)
    violations = []
    footprint_violations = []
    edge_count = 0
    for j in range(ny+1):
        for i in range(nx+1):
            if not present[j,i]:
                continue
            for di,dj in ((1,0),(0,1)):
                ii,jj = i+di,j+dj
                if ii <= nx and jj <= ny and present[jj,ii]:
                    edge_count += 1
                    segment = LineString(((xs[i],ys[j]),(xs[ii],ys[jj])))
                    if not copper.covers(segment):
                        violations.append([i,j,ii,jj])
                    if not full_copper.covers(segment.buffer(pitch/2, cap_style=2)):
                        footprint_violations.append([i,j,ii,jj])
    label = str(pitch).replace(".", "p")
    out = HERE / "extraction" / f"single-g-p{label}"
    out.mkdir(parents=True, exist_ok=True)
    result = {"status":"GEOMETRY_DIAGNOSTIC_ONLY", "board_sha256":BOARD_SHA, "export_sha256":digest(COPPER), "roi_mm":roi, "pitch_mm":pitch,
              "grid_nodes":int((nx+1)*(ny+1)), "present_nodes":int(present.sum()), "removed_nodes":int((~present).sum()),
              "grid_edges_between_present_nodes":edge_count, "edges_not_contained_in_native_copper":len(violations),
              "first_20_bad_edges_grid_indices":violations[:20], "scope":"One cropped copper layer/net; no other conductor, barrel, ports, mutual, or matrix."}
    result["full_width_filament_rectangles_not_contained_in_native_copper"] = len(footprint_violations)
    result["first_20_bad_width_edge_indices"] = footprint_violations[:20]
    z=1.062
    lines=["* UNQUALIFIED one-G native-copper mask experiment", ".units mm", ".default sigma=5.8e4",
           f"g1 x1={x0} y1={y0} z1={z} x2={x1} y2={y0} z2={z} x3={x1} y3={y1} z3={z}",
           f"+ thick=0.061 seg1={nx} seg2={ny} nhinc=1 rh=1"]
    holes = [f"+ hole point ({xs[i]:.6f},{ys[j]:.6f},{z:.6f})" for j,i in np.argwhere(~present)]
    port_names=[]
    for ref in ("C38.1","Q2.2"):
        pad=next(p for p in primitives if p["kind"] == "pad" and p.get("ref") == ref and p["layer"] == "In2.Cu")
        pad_shape=primitive_shape(pad)
        coords=np.argwhere(present)
        coords=sorted(coords, key=lambda ji:(xs[ji[1]]-pad["centre"][0])**2+(ys[ji[0]]-pad["centre"][1])**2)
        j,i=next((int(ji[0]),int(ji[1])) for ji in coords if pad_shape.covers(Point(xs[ji[1]],ys[ji[0]])))
        name="n"+ref.replace(".","_")
        port_names.append(name)
        lines.append(f"+ {name} ({xs[i]:.6f},{ys[j]:.6f},{z:.6f})")
    lines += holes
    lines += [f".external {port_names[0]} {port_names[1]}",".freq fmin=1e7 fmax=1e7 ndec=1",".end"]
    deck=out/"single-g.inp"
    deck.write_text("\n".join(lines)+"\n")
    result["deck_sha256"]=digest(deck)
    result["deck_bytes"]=deck.stat().st_size
    if args.solve:
        with (out/"solver.log").open("w") as log:
            try:
                run=subprocess.run(["/usr/bin/time","-l",str(args.solver.resolve(strict=True)),str(deck)], cwd=out,
                                   text=True,stdout=log,stderr=subprocess.STDOUT,timeout=300,check=False)
                result["solver_exit_code"]=run.returncode
            except subprocess.TimeoutExpired:
                result["solver_status"]="TIMEOUT_300S"
        log=(out/"solver.log").read_text()
        result["duplicate_center_warning_count"]=log.count("filaments had identical centers")
        result["solver_status"]=result.get("solver_status", "EXITED")
    (out/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__ == "__main__":
    main()
