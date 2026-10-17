#!/usr/bin/env python3
"""Build an explicitly unqualified coupled leg-A FastHenry feasibility deck.

Uses actual KiCad-exported polygons and drill annuli, but the grid, cropped
domain, plated-barrel wall and contact spokes must pass independent validation
before any resulting matrix is allowed into a switching model.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import re
import subprocess
from collections import defaultdict
from pathlib import Path

import numpy as np
import shapely
from audit_geometry import BOARD_SHA, COPPER, HERE, UNIT, board_drill_voids, digest, primitive_shape
from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union

LAYERS = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
Z = (0.0, 0.501, 1.062, 1.563)
THICK = (0.070, 0.061, 0.061, 0.070)
ROI = (124.0, 0.0, 166.0, 43.0)
PLATING_MM = 0.018  # assumed A4/JLCPCB nominal, not measured
SECTORS = 8


def key_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "_", value)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--solver", type=Path, required=True)
    p.add_argument("--pitch", type=float, required=True, choices=(0.25, 0.125))
    p.add_argument("--fit-width", action="store_true")
    p.add_argument("--nhinc", type=int, choices=(1,3,5), default=1)
    p.add_argument("--solve", action="store_true")
    args = p.parse_args()
    solver = args.solver.resolve(strict=True)
    raw = json.load(gzip.open(COPPER, "rt"))
    if raw["board_sha256"] != BOARD_SHA or digest(UNIT / "native-15/section.kicad_pcb") != BOARD_SHA:
        raise ValueError("board/export hash mismatch")
    all_items = raw["primitives"]
    ports = json.loads((HERE / "port-map.json").read_text())["legs"]["A"]
    nets = {port["net"] for port in ports}
    pitch = args.pitch
    x0,y0,x1,y1 = ROI
    nx,ny = round((x1-x0)/pitch),round((y1-y0)/pitch)
    xs = x0 + np.arange(nx+1)*pitch
    ys = y0 + np.arange(ny+1)*pitch
    xx,yy = np.meshgrid(xs,ys)
    roi_poly = box(*ROI)
    items = [item for item in all_items if item["net"] in nets and item["layer"] in LAYERS
             and primitive_shape(item).intersects(roi_poly)]
    by_nl: dict[tuple[str,str],list[dict]] = defaultdict(list)
    for item in items:
        by_nl[item["net"],item["layer"]].append(item)
    bores=board_drill_voids(raw)
    geometry = {(net,layer): unary_union([primitive_shape(item) for item in group]).difference(bores[layer])
                for (net,layer),group in by_nl.items()}
    occupied = {key: shapely.intersects_xy(geom.intersection(roi_poly),xx,yy) for key,geom in geometry.items()}
    suffix=("-fit" if args.fit_width else "")+f"-nh{args.nhinc}"
    out = HERE/"extraction"/f"coupled-a-p{str(pitch).replace('.', 'p')}{suffix}"
    out.mkdir(parents=True,exist_ok=True)
    lines = ["* UNQUALIFIED native leg-A coupled prototype; no D2 use", ".units mm", ".default sigma=5.8e4"]
    nodes: dict[tuple[str,str,int,int],str] = {}
    edge_count = 0
    bad_centerline = 0
    bad_width = 0
    narrowed_edges=0
    omitted_narrow_edges=0
    minimum_edge_width=pitch
    for (net,layer), mask in occupied.items():
        li=LAYERS.index(layer)
        tag=key_name(net)+f"l{li}"
        for j,i in np.argwhere(mask):
            name=f"n{tag}x{i}y{j}"
            nodes[net,layer,int(i),int(j)] = name
            lines.append(f"{name} x={xs[i]:.6f} y={ys[j]:.6f} z={Z[li]:.6f}")
        geom=geometry[net,layer]
        for j in range(ny+1):
            for i in range(nx+1):
                if not mask[j,i]:
                    continue
                for di,dj,direction in ((1,0,"wx=0 wy=1 wz=0"),(0,1,"wx=1 wy=0 wz=0")):
                    ii,jj=i+di,j+dj
                    if ii>nx or jj>ny or not mask[jj,ii]:
                        continue
                    seg=LineString(((xs[i],ys[j]),(xs[ii],ys[jj])))
                    if not geom.covers(seg):
                        bad_centerline+=1
                        continue
                    width=pitch
                    if not geom.covers(seg.buffer(pitch/2,cap_style=2)):
                        bad_width+=1
                        if args.fit_width:
                            low,high=0.,pitch
                            for _ in range(16):
                                mid=(low+high)/2
                                if geom.covers(seg.buffer(mid/2,cap_style=2)):
                                    low=mid
                                else:
                                    high=mid
                            width=low
                            if width<0.005:
                                omitted_narrow_edges+=1
                                continue
                            narrowed_edges+=1
                    minimum_edge_width=min(minimum_edge_width,width)
                    a,b=nodes[net,layer,i,j],nodes[net,layer,ii,jj]
                    lines.append(f"e{edge_count} {a} {b} w={width:.7f} h={THICK[li]:.6f} {direction} nhinc={args.nhinc}")
                    edge_count+=1

    # Physical plated wall is represented by eight finite axial strips; each
    # strip lands on a native annulus at each exposed layer through a short
    # copper spoke. These contacts are a mesh approximation, audited below.
    # Barrel metadata is exported from native PTH/via objects independently of
    # planar pad flashes. A PTH barrel remains physical even where KiCad has
    # removed its unconnected annulus (e.g. C38.1 is only flashed on In2.Cu).
    barrels=[]
    for barrel in raw["barrels"]:
        cx,cy=barrel["centre"]
        if barrel["net"] in nets and x0+pitch<cx<x1-pitch and y0+pitch<cy<y1-pitch:
            barrels.append(barrel)
    barrel_seg_count=0
    spoke_seg_count=0
    max_spoke_mm=0.0
    far_spokes=[]
    spoke_centerline_violations=0
    spoke_width_violations=0
    narrowed_spokes=0
    omitted_narrow_spokes=0
    sectors_unlanded=[]
    barrel_groups=0
    barrel_port_nodes={}
    terminal_equiv=[]
    for barrel in barrels:
        barrel_groups+=1
        kind,ref,net,cx,cy=barrel["kind"],barrel.get("ref","via"),barrel["net"],*barrel["centre"]
        drill=barrel["drill_mm"]
        if isinstance(drill,list):
            if abs(drill[0]-drill[1])>1e-8:
                raise ValueError(f"noncircular plated hole {ref}: {drill}")
            diameter=float(drill[0])
        else:
            diameter=float(drill)
        span_start,span_end=barrel["physical_span_layers"]
        ilo,ihi=LAYERS.index(span_start),LAYERS.index(span_end)
        if ilo>ihi:
            ilo,ihi=ihi,ilo
        present_layers=LAYERS[ilo:ihi+1]
        by_layer={item["layer"]:item for item in items if item["kind"]==kind and item.get("ref","via")==ref
                  and item["net"]==net and item.get("centre")==[cx,cy]}
        radius=diameter/2+PLATING_MM/2
        arc_width=2*math.pi*radius/SECTORS
        btag=f"b{barrel_groups}"
        if kind=="pad":
            side=barrel["component_side"]
            if side not in present_layers:
                raise ValueError(f"component side outside barrel span: {ref}")
            terminal_li=LAYERS.index(side)
            terminal=f"n{btag}s0l{terminal_li}"
            barrel_port_nodes[f"{net}:{ref}"]=terminal
            for sector in range(1,SECTORS):
                # An ideal solder/lead contact ties the plated wall at its
                # component-side end. Pin/lead inductance remains external.
                terminal_equiv.append(f".equiv {terminal} n{btag}s{sector}l{terminal_li}")
        for sector in range(SECTORS):
            angle=2*math.pi*sector/SECTORS
            bx,by=cx+radius*math.cos(angle),cy+radius*math.sin(angle)
            strand=[]
            for layer in present_layers:
                li=LAYERS.index(layer)
                bnode=f"n{btag}s{sector}l{li}"
                lines.append(f"{bnode} x={bx:.7f} y={by:.7f} z={Z[li]:.6f}")
                strand.append((li,bnode))
                if layer not in barrel["flashed_layers"]:
                    continue
                item=by_layer.get(layer)
                if item is None:
                    sectors_unlanded.append([ref,layer,sector,"flashed annulus missing from export"])
                    continue
                pad_shape=primitive_shape(item)
                mask=occupied[net,layer]
                ci,cj=round((bx-x0)/pitch),round((by-y0)/pitch)
                candidates=[]
                for jj in range(max(0,cj-4),min(ny,cj+4)+1):
                    for ii in range(max(0,ci-4),min(nx,ci+4)+1):
                        if not mask[jj,ii] or not pad_shape.covers(Point(xs[ii],ys[jj])):
                            continue
                        distance=math.hypot(xs[ii]-bx,ys[jj]-by)
                        candidates.append((distance,ii,jj))
                if not candidates:
                    sectors_unlanded.append([ref,layer,sector,"no grid node on annulus"])
                    continue
                distance,ii,jj=min(candidates)
                max_spoke_mm=max(max_spoke_mm,distance)
                if distance>pitch:
                    far_spokes.append({"group":ref,"layer":layer,"sector":sector,"distance_mm":distance})
                endpoint=nodes[net,layer,ii,jj]
                if distance<1e-7:
                    lines.append(f".equiv {bnode} {endpoint}")
                else:
                    dx,dy=xs[ii]-bx,ys[jj]-by
                    wx,wy=-dy/distance,dx/distance
                    spoke=LineString(((bx,by),(xs[ii],ys[jj])))
                    if not pad_shape.covers(spoke):
                        spoke_centerline_violations+=1
                    width=min(pitch,arc_width)
                    if not pad_shape.covers(spoke.buffer(width/2,cap_style=2)):
                        spoke_width_violations+=1
                        if args.fit_width:
                            low,high=0.,width
                            for _ in range(16):
                                mid=(low+high)/2
                                if pad_shape.covers(spoke.buffer(mid/2,cap_style=2)):
                                    low=mid
                                else:
                                    high=mid
                            width=low
                            if width<0.005:
                                omitted_narrow_spokes+=1
                                sectors_unlanded.append([ref,layer,sector,"fitted spoke below 5 um"])
                                continue
                            narrowed_spokes+=1
                    lines.append(f"e{edge_count} {bnode} {endpoint} w={width:.7f} h={THICK[li]:.6f} wx={wx:.8f} wy={wy:.8f} wz=0 nhinc={args.nhinc}")
                    edge_count+=1
                    spoke_seg_count+=1
            for (_li,a),(_lj,b) in zip(strand,strand[1:], strict=False):
                wx,wy=-math.sin(angle),math.cos(angle)
                lines.append(f"e{edge_count} {a} {b} w={arc_width:.7f} h={PLATING_MM:.6f} wx={wx:.8f} wy={wy:.8f} wz=0 nhinc={args.nhinc}")
                edge_count+=1
                barrel_seg_count+=1
    lines.extend(terminal_equiv)

    port_nodes: dict[str,str] = {}
    for port in ports:
        for ref in (port["from_ref"],port["to_ref"]):
            key=f"{port['net']}:{ref}"
            if key in port_nodes:
                continue
            if key in barrel_port_nodes:
                port_nodes[key]=barrel_port_nodes[key]
                continue
            available=port["from_layers"] if ref==port["from_ref"] else port["to_layers"]
            layer=available[0]
            pad=next((item for item in items if item["kind"]=="pad" and item.get("ref")==ref
                      and item["net"]==port["net"] and item["layer"]==layer),None)
            if pad is None:
                raise ValueError(f"missing flashed port pad {key} on {layer}")
            shape=primitive_shape(pad)
            mask=occupied[port["net"],layer]
            cx,cy=pad["centre"]
            candidates=[]
            ci,cj=round((cx-x0)/pitch),round((cy-y0)/pitch)
            for jj in range(max(0,cj-12),min(ny,cj+12)+1):
                for ii in range(max(0,ci-12),min(nx,ci+12)+1):
                    if mask[jj,ii] and shape.covers(Point(xs[ii],ys[jj])):
                        candidates.append(((xs[ii]-cx)**2+(ys[jj]-cy)**2,ii,jj))
            if not candidates:
                raise ValueError(f"no flashed pad node for {key} on {layer}")
            _,ii,jj=min(candidates)
            port_nodes[key]=nodes[port["net"],layer,ii,jj]
    for port in ports:
        a=port_nodes[f"{port['net']}:{port['from_ref']}"]
        b=port_nodes[f"{port['net']}:{port['to_ref']}"]
        lines.append(f".external {a} {b}")
    lines += [".freq fmin=1e7 fmax=1e7 ndec=1", ".end"]
    deck=out/"coupled.inp"
    deck.write_text("\n".join(lines)+"\n")
    result={"status":"UNQUALIFIED_PROTOTYPE_DECK","board_sha256":BOARD_SHA,"export_sha256":digest(COPPER),
            "port_map_sha256":digest(HERE/"port-map.json"),"solver_sha256":digest(solver),"deck_sha256":digest(deck),
            "leg":"A","roi_xy_mm":ROI,"pitch_mm":pitch,"net_layer_masks":len(occupied),"directed_ports":[port["name"] for port in ports],
            "fit_width":args.fit_width,"nhinc":args.nhinc,
            "node_count":len(nodes),"edge_segments_total":edge_count,"barrel_groups":barrel_groups,
            "barrel_axial_segments":barrel_seg_count,"barrel_spokes":spoke_seg_count,"max_barrel_spoke_mm":max_spoke_mm,
            "spokes_longer_than_pitch":far_spokes,"spoke_centerlines_outside_native_annulus":spoke_centerline_violations,
            "spoke_widths_outside_native_annulus":spoke_width_violations,
            "narrowed_spokes":narrowed_spokes,"omitted_narrow_spokes":omitted_narrow_spokes,
            "unlanded_barrel_sectors":sectors_unlanded,"centerlines_outside_native_copper":bad_centerline,
            "full_width_rectangles_outside_native_copper":bad_width,
            "narrowed_planar_edges":narrowed_edges,"omitted_narrow_planar_edges":omitted_narrow_edges,
            "minimum_planar_edge_width_mm":minimum_edge_width,"deck_bytes":deck.stat().st_size,
            "critical_limitations":["Cropped ROI excludes finite-plane spreading outside crop",
                                    "18 um barrel plating assumed; sector walls and pad spokes require independent calibration",
                                    f"{omitted_narrow_edges} planar edges and {omitted_narrow_spokes} spokes omitted by width fit" if args.fit_width else "Full-width edge rectangles protrude beyond exact native copper",
                                    "No 2x self/mutual convergence, thickness refinement, or 1/30 MHz frequency sweep"]}
    if args.solve:
        with (out/"solver.log").open("w") as log:
            try:
                run=subprocess.run(["/usr/bin/time","-l",str(solver),str(deck),"-p","off"],cwd=out,
                                   stdout=log,stderr=subprocess.STDOUT,timeout=600,check=False)
                result["solver_exit_code"]=run.returncode
            except subprocess.TimeoutExpired:
                result["solver_status"]="TIMEOUT_600S"
        log=(out/"solver.log").read_text()
        result["duplicate_center_warnings"]=log.count("filaments had identical centers")
        result["hole_boundary_warnings"]=log.count("Multiple boundaries found around one hole region")
    (out/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
