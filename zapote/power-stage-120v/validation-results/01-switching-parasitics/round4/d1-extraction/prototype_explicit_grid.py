#!/usr/bin/env python3
"""Calibrate explicit planar edge segments against FastHenry uniform G."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from audit_geometry import HERE, digest
from run_fixtures import read_z


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--solver", type=Path, required=True)
    p.add_argument("--pitch", type=float, default=0.5)
    args = p.parse_args()
    pitch = args.pitch
    nx = ny = round(10 / pitch)
    out = HERE / "extraction" / f"explicit-grid-calibration-p{str(pitch).replace('.', 'p')}"
    out.mkdir(parents=True, exist_ok=True)
    z = 0
    base = ["* 10x10 mm planar copper calibration; 61 um", ".units mm", ".default sigma=5.8e4"]
    ground = base + ["g1 x1=0 y1=0 z1=0 x2=10 y2=0 z2=0 x3=10 y3=10 z3=0", f"+ thick=0.061 seg1={nx} seg2={ny} nhinc=1", "+ nleft (0,5,0) nright (10,5,0)"]
    edges = list(base)
    for j in range(ny + 1):
        for i in range(nx + 1):
            edges.append(f"n{i}_{j} x={i*pitch:.6f} y={j*pitch:.6f} z={z}")
    count = 0
    for j in range(ny + 1):
        for i in range(nx + 1):
            if i < nx:
                edges.append(f"e{count} n{i}_{j} n{i+1}_{j} w={pitch} h=0.061 wx=0 wy=1 wz=0 nhinc=1")
                count += 1
            if j < ny:
                edges.append(f"e{count} n{i}_{j} n{i}_{j+1} w={pitch} h=0.061 wx=1 wy=0 wz=0 nhinc=1")
                count += 1
    edges += [f".external n0_{ny//2} n{nx}_{ny//2}", ".freq fmin=1e7 fmax=1e7 ndec=1", ".end"]
    ground += [".external nleft nright", ".freq fmin=1e7 fmax=1e7 ndec=1", ".end"]
    result = {"pitch_mm":pitch,"edge_count":count,"solver_sha256":digest(args.solver.resolve(strict=True))}
    for name, lines in (("ground", ground),("explicit", edges)):
        d = out / name
        d.mkdir(exist_ok=True)
        deck = d / "model.inp"
        deck.write_text("\n".join(lines)+"\n")
        with (d/"solver.log").open("w") as log:
            run = subprocess.run([str(args.solver),str(deck),"-p","off"],cwd=d,stdout=log,stderr=subprocess.STDOUT,check=False)
        log = (d/"solver.log").read_text()
        result[name]={"exit_code":run.returncode,"deck_sha256":digest(deck),"duplicate_center_warnings":log.count("filaments had identical centers"),"hole_boundary_warnings":log.count("Multiple boundaries found around one hole region")}
        if run.returncode == 0:
            r,x = read_z(d/"Zc.mat")
            result[name].update({"R_ohm":r,"X_ohm":x})
    if all(result[name]["exit_code"] == 0 for name in ("ground","explicit")):
        result["R_delta_percent"] = 100*(result["explicit"]["R_ohm"]/result["ground"]["R_ohm"]-1)
        result["X_delta_percent"] = 100*(result["explicit"]["X_ohm"]/result["ground"]["X_ohm"]-1)
    (out/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__ == "__main__":
    main()
