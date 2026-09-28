#!/usr/bin/env python3
"""Unqualified one-net explicit-edge FastHenry feasibility and width audit."""
from __future__ import annotations

import argparse
import gzip
import json
import subprocess
from pathlib import Path

import numpy as np
import shapely
from audit_geometry import BOARD_SHA, COPPER, HERE, UNIT, board_drill_voids, digest, primitive_shape
from run_fixtures import read_z
from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--solver", type=Path, required=True)
    p.add_argument("--pitch", type=float, required=True, choices=(0.5, 0.25))
    p.add_argument("--fit-width", action="store_true")
    args = p.parse_args()
    solver = args.solver.resolve(strict=True)
    raw = json.load(gzip.open(COPPER,"rt"))
    if raw["board_sha256"] != BOARD_SHA or digest(UNIT/"native-15/section.kicad_pcb") != BOARD_SHA:
        raise ValueError("board/export hash mismatch")
    items = raw["primitives"]
    full_copper = unary_union([primitive_shape(item) for item in items if item["net"] == "bus_p" and item["layer"] == "In2.Cu"])
    full_copper = full_copper.difference(board_drill_voids(raw)["In2.Cu"])
    x0,y0,x1,y1 = 124.,0.,166.,43.
    pitch = args.pitch
    nx,ny = round((x1-x0)/pitch),round((y1-y0)/pitch)
    xs = x0 + np.arange(nx+1)*pitch
    ys = y0 + np.arange(ny+1)*pitch
    xx,yy = np.meshgrid(xs,ys)
    inside = shapely.intersects_xy(full_copper.intersection(box(x0,y0,x1,y1)),xx,yy)
    label = str(pitch).replace(".","p") + ("-fit" if args.fit_width else "-full")
    out=HERE/"extraction"/f"explicit-native-p{label}"
    out.mkdir(parents=True,exist_ok=True)
    z=1.062
    lines=["* UNQUALIFIED cropped BUS_P/In2 explicit-edge model", ".units mm", ".default sigma=5.8e4"]
    for j,i in np.argwhere(inside):
        lines.append(f"n{i}_{j} x={xs[i]:.6f} y={ys[j]:.6f} z={z:.6f}")
    port_nodes=[]
    for ref in ("C38.1","Q2.2"):
        pad=next(item for item in items if item["kind"] == "pad" and item.get("ref") == ref and item["layer"] == "In2.Cu")
        shape=primitive_shape(pad)
        candidates=sorted(np.argwhere(inside),key=lambda ji:(xs[ji[1]]-pad["centre"][0])**2+(ys[ji[0]]-pad["centre"][1])**2)
        j,i=next((int(ji[0]),int(ji[1])) for ji in candidates if shape.covers(Point(xs[ji[1]],ys[ji[0]])))
        port_nodes.append(f"n{i}_{j}")
    edge_count=0
    omitted=0
    narrowed=0
    violating_full_width=0
    min_width=pitch
    for j in range(ny+1):
        for i in range(nx+1):
            if not inside[j,i]:
                continue
            for di,dj,orient in ((1,0,"wx=0 wy=1 wz=0"),(0,1,"wx=1 wy=0 wz=0")):
                ii,jj=i+di,j+dj
                if ii>nx or jj>ny or not inside[jj,ii]:
                    continue
                segment=LineString(((xs[i],ys[j]),(xs[ii],ys[jj])))
                if not full_copper.covers(segment):
                    omitted+=1
                    continue
                width=pitch
                if not full_copper.covers(segment.buffer(pitch/2,cap_style=2)):
                    violating_full_width+=1
                    if args.fit_width:
                        low,high=0.,pitch
                        for _ in range(16):
                            mid=(low+high)/2
                            if full_copper.covers(segment.buffer(mid/2,cap_style=2)):
                                low=mid
                            else:
                                high=mid
                        width=low
                        if width<0.005:
                            omitted+=1
                            continue
                        narrowed+=1
                min_width=min(min_width,width)
                lines.append(f"e{edge_count} n{i}_{j} n{ii}_{jj} w={width:.7f} h=0.061 {orient} nhinc=1")
                edge_count+=1
    lines += [f".external {port_nodes[0]} {port_nodes[1]}",".freq fmin=1e7 fmax=1e7 ndec=1",".end"]
    deck=out/"model.inp"
    deck.write_text("\n".join(lines)+"\n")
    with (out/"solver.log").open("w") as log:
        try:
            run=subprocess.run(["/usr/bin/time","-l",str(solver),str(deck),"-p","off"],cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=300,check=False)
            status="EXITED"
            exit_code=run.returncode
        except subprocess.TimeoutExpired:
            status="TIMEOUT_300S"
            exit_code=None
    log=(out/"solver.log").read_text()
    result={"status":"UNQUALIFIED_SINGLE_NET_SLICE","solver_status":status,"solver_exit_code":exit_code,
            "board_sha256":BOARD_SHA,"export_sha256":digest(COPPER),"solver_sha256":digest(solver),"deck_sha256":digest(deck),
            "roi_xy_mm":[x0,y0,x1,y1],"pitch_mm":pitch,"fit_width":args.fit_width,"grid_nodes":int(inside.sum()),
            "edge_segments":edge_count,"omitted_edges":omitted,"violating_full_width_edges":violating_full_width,
            "narrowed_edges":narrowed,"minimum_segment_width_mm":min_width,"port_nodes":port_nodes,
            "duplicate_center_warnings":log.count("filaments had identical centers"),
            "hole_boundary_warnings":log.count("Multiple boundaries found around one hole region"),
            "scope_warning":"Single layer, one net, cropped; omits vias, other nets/layers, mutuals and actual pad current distribution. Cannot feed D2."}
    if exit_code==0:
        r,x=read_z(out/"Zc.mat")
        result.update({"R_ohm":r,"X_ohm":x,"L_nH_10MHz":x/(2*np.pi*1e7)*1e9})
    (out/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
