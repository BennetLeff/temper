#!/usr/bin/env python3
"""Extract native pcbnew geometry, then invoke the Rust P2 truth function.

This is transport only: it does not calculate acceptance decisions.
"""
import hashlib, json, math, pathlib, subprocess, sys, tempfile
import pcbnew

ROOT = pathlib.Path(__file__).resolve().parents[3]
ZAPOTE = ROOT / "zapote"
BOARDS = [
    "rtd/unit/candidate/section.kicad_pcb", "current-sense/candidate/section.kicad_pcb",
    "voltage-sense/candidate/section.kicad_pcb", "thermal-sense/candidate/section.kicad_pcb",
    "interlock/candidate/section.kicad_pcb", "gate-drive/candidate/section.kicad_pcb",
    "power-entry/candidate/section.kicad_pcb",
]
def mm(p): return [pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)]
def poly(points): return {"vertices_mm": [mm(p) for p in points]}
def native_polygon(item, layer=pcbnew.F_Cu):
    """Return one exact pcbnew effective polygon, or None if unsupported."""
    if not hasattr(item, "GetEffectivePolygon"): return None
    try: ps = item.GetEffectivePolygon(layer)
    except TypeError: ps = item.GetEffectivePolygon()
    if ps.OutlineCount() != 1: return None
    ring = ps.Outline(0)
    if ring.PointCount() < 3: return None
    return poly([ring.GetPoint(i) for i in range(ring.PointCount())])
def rect(cx, cy, sx, sy, deg):
    a = -deg * math.pi / 180; s, c = math.sin(a), math.cos(a)
    return poly([pcbnew.VECTOR2I(pcbnew.FromMM(cx + c*x - s*y), pcbnew.FromMM(cy + s*x + c*y)) for x,y in [(-sx/2,-sy/2),(sx/2,-sy/2),(sx/2,sy/2),(-sx/2,sy/2)]])
def extract(path):
    b = pcbnew.LoadBoard(str(path)); bodies=[]; pads=[]; holes=[]; copper=[]; outline=[]; unsupported=[]
    for fp in b.GetFootprints():
        ref = fp.GetReference(); pos=mm(fp.GetPosition()); angle=fp.GetOrientationDegrees()
        fab=[]
        for g in fp.GraphicalItems():
            if g.GetLayer() != pcbnew.F_Fab: continue
            polygon = native_polygon(g)
            if polygon: fab.append(polygon)
        if fab:
            # pcbnew returns these in world coordinates; keep them world-space
            # and use an identity pose to avoid a second rotation.
            bodies.append({"component":ref,"local_polygon":fab[0],"position_mm":[0.,0.],"rotation_deg":0.,"required":True})
        else: unsupported.append(ref+": missing F.Fab polygon")
        for pad in fp.Pads():
            p=mm(pad.GetPosition()); polygon=native_polygon(pad)
            if polygon is None:
                unsupported.append(ref+"."+pad.GetNumber()+": unsupported native pad shape")
                continue
            pads.append({"id":ref+"."+pad.GetNumber(),"copper":polygon,"drill_mm":pcbnew.ToMM(pad.GetDrillSize().x) if pad.GetDrillSize().x else None,"drill_center_mm":p if pad.GetDrillSize().x else None,"plated":pad.GetAttribute()==pcbnew.PAD_ATTRIB_PTH})
            for layer in pad.GetLayerSet().Seq():
                copper.append({"id":ref+"."+pad.GetNumber()+"@"+pcbnew.LayerName(layer),"layer":pcbnew.LayerName(layer),"polygon":polygon})
            if pad.GetDrillSize().x: holes.append({"id":ref+"."+pad.GetNumber(),"center_mm":p,"diameter_mm":pcbnew.ToMM(pad.GetDrillSize().x)})
    edge_set=pcbnew.SHAPE_POLY_SET()
    if b.GetBoardPolygonOutlines(edge_set, True) and edge_set.OutlineCount():
        outline=list(edge_set.Outline(0).CPoints())
        for hi in range(edge_set.HoleCount(0)):
            unsupported.append("Edge.Cuts hole extracted but cutout transport is pending")
    # Edge.Cuts often consists of segments; retain a conservative polygon only
    # when the native drawing forms a usable ordered loop.
    if len(outline)>=3: outline=poly(outline)
    else: outline={"vertices_mm":[]}
    for track_index, t in enumerate(b.GetTracks()):
        if not (hasattr(t, "GetStart") and hasattr(t, "GetEnd") and hasattr(t, "GetWidth")):
            unsupported.append("native via encountered: via geometry transport pending")
            continue
        polygon=native_polygon(t)
        if polygon is None:
            unsupported.append("track-"+str(track_index)+": unsupported native track polygon")
            continue
        copper.append({"id":"track-"+str(track_index),"layer":t.GetLayerName(),"polygon":polygon})
    if len(b.Zones()): unsupported.append(f"{len(b.Zones())} filled zones: native zone transport pending")
    return {"board_id":path.name,"bodies":bodies,"pads":pads,"holes":holes,"copper":copper,"outline":outline,"cutouts":[],"limits":{"name":"","source":"","qualified":False,"minimum_annular_ring_mm":0.0,"minimum_hole_clearance_mm":0.0,"assembly_process":""},"angle_policy":"Arbitrary","unsupported":unsupported}
def main():
    paths=[ZAPOTE/p for p in BOARDS] if len(sys.argv)==1 else [pathlib.Path(sys.argv[1]).resolve()]
    import os
    artifact_root = os.environ.get("P2_ARTIFACT_DIR")
    artifact_dir = pathlib.Path(artifact_root).resolve() if artifact_root else None
    temp = tempfile.TemporaryDirectory(prefix="zapote-p2-") if artifact_dir is None else None
    td = str(artifact_dir) if artifact_dir else temp.name
    if artifact_dir: artifact_dir.mkdir(parents=True, exist_ok=True)
    try:
        for path in paths:
            name = "-".join(path.relative_to(ZAPOTE).parts[:-1]).replace("/", "-")
            inp=pathlib.Path(td)/(name+".json"); inp.write_text(json.dumps(extract(path)))
            cmd=["cargo","run","--quiet","--locked","--bin","p2-manufacturing","--",str(inp)]
            result=subprocess.run(cmd,cwd=ZAPOTE,env={**__import__('os').environ,"CARGO_TARGET_DIR":"/private/tmp/zapote-rtd-target"},text=True,capture_output=True)
            print(json.dumps({"board":str(path.relative_to(ROOT)),"board_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"extractor_sha256":hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),"returncode":result.returncode,"report":json.loads(result.stdout) if result.stdout else None,"stderr":result.stderr}))
        return 0
    finally:
        if temp: temp.cleanup()
if __name__ == "__main__": raise SystemExit(main())
