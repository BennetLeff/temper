#!/usr/bin/env python3
"""Generate the native-21 board from the frozen netlist and an authored placement.

    KICAD_PY prototype-closure/pcb/build_native21.py [--placement native-21/placement.json]

Native-20's board supplies only the stackup, design settings and layer setup:
every footprint, track, via, zone and outline item is removed. Each native-21
component is added from its footprint library (vendored into
native-21/candidate-libs for reproducibility), with reference, MPN, value,
SourceInstance and pad nets from native-21/frozen/default.net, at the authored
pose in placement.json ({instance path: [x_mm, y_mm, angle_deg]}, footprint
origin, KiCad frame). The outline is the L-shaped native-21 outline below.
Copper is authored separately. Output: native-21/section.kicad_pcb.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import uuid
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[1]
N20, OUT = UNIT / "native-20", UNIT / "native-21"
STOCK = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
LOCAL = {"temper": UNIT / "libraries/temper.pretty", "lib": UNIT / "libraries/lib.pretty"}
# KiCad frame, mm. Main 290 x 140 plus the 91 x 50 tongue under the power core (D-36, FLOORPLAN.md).
OUTLINE = [(0, 0), (290, 0), (290, 140), (91, 140), (91, 190), (0, 190)]
N20_BOARD_SHA = "27657a0ebce66140b6ea6a0b84940dba420b3a187199798bce3c3d122abf9dae"


def mm(v):
    return pcbnew.FromMM(float(v))


def parse_netlist(text):
    comps = {}
    for m in re.finditer(r'\(comp \(ref "([^"]+)"\).*?\(sheetpath \(names "[^"]*::([^"]+)"\) \(tstamps "([^"]+)"\)', text, re.S):
        comps[m.group(1)] = {"path": m.group(2), "tstamp": m.group(3)}
    nets = {}
    for m in re.finditer(r'\(net \(code "\d+"\) \(name "([^"]+)"\)(.*?)\)\s*(?=\(net |\)\s*\)\s*$)', text, re.S):
        nets[m.group(1)] = re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', m.group(2))
    return comps, nets


def footprint_dir(lib, name):
    for d in ([LOCAL[lib]] if lib in LOCAL else []) + [N20 / "candidate-libs" / f"{lib}.pretty", STOCK / f"{lib}.pretty"]:
        if (d / f"{name}.kicad_mod").is_file():
            return d
    raise FileNotFoundError(f"{lib}:{name}")


def vendor(lib, name):
    src = footprint_dir(lib, name)
    dst = OUT / "candidate-libs" / f"{lib}.pretty"
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / f"{name}.kicad_mod", dst / f"{name}.kicad_mod")
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--placement", default=str(OUT / "placement.json"))
    a = ap.parse_args()
    base = N20 / "section.kicad_pcb"
    if hashlib.sha256(base.read_bytes()).hexdigest() != N20_BOARD_SHA:
        print("note: native-20 board differs from the pre-refill hash; only settings are taken from it")
    placement = json.loads(Path(a.placement).read_text())
    comps, nets = parse_netlist((OUT / "frozen/default.net").read_text())
    attrs = {c["address"].split("::", 1)[1]: c["attributes"]
             for c in json.loads((OUT / "frozen/resolved-components.json").read_text())["components"]}
    fp_of = {}
    for row in csv.DictReader((OUT / "frozen/default.csv").open()):
        for r in row["Designator"].split(","):
            fp_of[r] = row["Footprint"]
    missing = sorted({c["path"] for c in comps.values()} - set(placement))
    if missing:
        raise SystemExit(f"{len(missing)} instances have no pose, e.g. {missing[:8]}")

    # Per-instance 3D model assignments come from native-20 (its models3d maps), not the libraries.
    n20_models = {}
    for f in pcbnew.LoadBoard(str(base)).GetFootprints():
        n20_models[f.GetField("SourceInstance").GetText()] = (
            f.GetFPID().GetLibItemName().wx_str(),
            [(m.m_Filename, (m.m_Offset.x, m.m_Offset.y, m.m_Offset.z), (m.m_Rotation.x, m.m_Rotation.y, m.m_Rotation.z),
              (m.m_Scale.x, m.m_Scale.y, m.m_Scale.z)) for m in f.Models()])
    board = pcbnew.LoadBoard(str(base))
    tracks = [t for t in board.GetTracks()]
    zones = [z for z in board.Zones()]
    drawings = [d for d in board.GetDrawings()]
    footprints = [f for f in board.GetFootprints()]
    for item in tracks + zones + drawings + footprints:
        board.Remove(item)
    for name in sorted(nets):
        if not board.FindNet(name):
            board.Add(pcbnew.NETINFO_ITEM(board, name))
    for (x0, y0), (x1, y1) in zip(OUTLINE, OUTLINE[1:] + OUTLINE[:1]):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(pcbnew.VECTOR2I(mm(x0), mm(y0)))
        seg.SetEnd(pcbnew.VECTOR2I(mm(x1), mm(y1)))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(mm(0.1))
        board.Add(seg)
    pin_net = {(r, p): n for n, nodes in nets.items() for r, p in nodes}
    root = str(uuid.uuid5(uuid.NAMESPACE_URL, "temper-native21-sch/root"))
    for ref, c in sorted(comps.items()):
        lib, name = fp_of[ref].split(":", 1)
        fp = pcbnew.FootprintLoad(str(vendor(lib, name)), name)
        a_ = attrs[c["path"]]
        fp.SetReference(ref)
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        fp.SetValue(a_["mpn"])
        fp.SetField("MPN", a_["mpn"])
        fp.SetField("SourceInstance", c["path"])
        fp.GetField("MPN").SetVisible(False)
        fp.GetField("SourceInstance").SetVisible(False)
        fp.Value().SetVisible(False)
        x, y, ang = placement[c["path"]]
        fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        fp.SetOrientationDegrees(float(ang))
        fp.SetPath(pcbnew.KIID_PATH(f"/{root}/{c['tstamp']}"))
        prior = n20_models.get(c["path"])
        if prior and prior[0] == name and prior[1]:
            fp.Models().clear()
            for fn, off, rot, sc in prior[1]:
                m = pcbnew.FP_3DMODEL()
                m.m_Filename = fn
                m.m_Offset = pcbnew.VECTOR3D(*off)
                m.m_Rotation = pcbnew.VECTOR3D(*rot)
                m.m_Scale = pcbnew.VECTOR3D(*sc)
                fp.Models().append(m)
        for model in fp.Models():          # vendored libraries point one level up
            model.m_Filename = model.m_Filename.replace("${KIPRJMOD}/../models3d/", "${KIPRJMOD}/models3d/")
        board.Add(fp)
        for pad in fp.Pads():
            n = pin_net.get((ref, pad.GetNumber()))
            if n:
                pad.SetNet(board.FindNet(n))
    for f in ("section.kicad_pro", "fp-lib-table", "stackup.json"):
        if (N20 / f).exists():
            shutil.copy2(N20 / f, OUT / f)
    if not (OUT / "models3d").exists() and (N20 / "models3d").exists():
        shutil.copytree(N20 / "models3d", OUT / "models3d")
    pcbnew.SaveBoard(str(OUT / "section.kicad_pcb"), board)
    print(json.dumps({"footprints": len(comps), "nets": len(nets), "outline": OUTLINE}))


if __name__ == "__main__":
    main()
