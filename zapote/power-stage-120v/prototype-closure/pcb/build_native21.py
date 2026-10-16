#!/usr/bin/env python3
"""Generate the native-21 board from the frozen netlist and an authored placement.

    KICAD_PY prototype-closure/pcb/build_native21.py [--placement native-21/placement.json]

Native-20's board supplies only the design settings and the non-copper layer setup:
every footprint, track, via, zone and outline item is removed. The copper layers and
the (stackup ...) come from native-21/stackup.json, the single layer-stack source
(stage 33; native-21/layout/layers21.py reads the same file for the layout, gates and
models): write_stack() rewrites the saved board's copper (layers) entries, the
(setup (stackup ...)) block and (general (thickness ...)) from it. Each native-21
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
import sys
import uuid
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[1]
N20, OUT = UNIT / "native-20", UNIT / "native-21"
STOCK = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
LOCAL = {"temper": UNIT / "libraries/temper.pretty", "lib": UNIT / "libraries/lib.pretty",
         # stage 19 (review K6): the IRM-20 pin-1 tick moved from y -3.65 (past the board edge on PS1 / PS2) to -2.65
         "Converter_ACDC": OUT / "footprint-overrides/Converter_ACDC.pretty"}
# KiCad frame, mm. Main 290 x 140 plus the 91 x 50 tongue under the power core (D-36, FLOORPLAN.md).
OUTLINE = [(0, 0), (290, 0), (290, 140), (91, 140), (91, 190), (0, 190)]
N20_BOARD_SHA = "27657a0ebce66140b6ea6a0b84940dba420b3a187199798bce3c3d122abf9dae"
sys.path.insert(0, str(OUT / "layout"))
import layers21  # noqa: E402  (native-21/stackup.json)


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


def _num(v):
    """A stackup number as KiCad writes it (shortest round-trip decimal: 0.4355, 0.5, 4.29)."""
    return repr(float(v))


def stackup_sexpr(st):
    """The (stackup ...) block, KiCad 10's text layout, from a stackup.json."""
    out = ["\t\t(stackup"]
    for e in st["layers"]:
        extra = set(e) - {"name", "type", "thickness_mm", "material", "epsilon_r", "loss_tangent", "kicad_id", "z_mm"}
        if extra:
            raise ValueError(f"stackup.json {e['name']}: fields the builder does not write: {sorted(extra)}")
        out.append(f'\t\t\t(layer "{e["name"]}"')
        out.append(f'\t\t\t\t(type "{e["type"]}")')
        out.append(f'\t\t\t\t(thickness {_num(e["thickness_mm"])})')
        if "material" in e:
            out.append(f'\t\t\t\t(material "{e["material"]}")')
        for k in ("epsilon_r", "loss_tangent"):
            if k in e:
                out.append(f"\t\t\t\t({k} {_num(e[k])})")
        out.append("\t\t\t)")
    ks = st.get("kicad_stackup", {"copper_finish": "None", "dielectric_constraints": "no"})   # KiCad's defaults
    out.append(f'\t\t\t(copper_finish "{ks["copper_finish"]}")')
    out.append(f'\t\t\t(dielectric_constraints {ks["dielectric_constraints"]})')
    out.append("\t\t)")
    return "\n".join(out) + "\n"


def write_stack(path):
    """Rewrite the saved board's copper (layers) entries, (stackup ...) and (general (thickness ...)) from
    native-21/stackup.json (layers21), then reload it and check KiCad reads that stack back."""
    text = path.read_text()
    m = re.search(r"\n\t\(layers\n((?:\t\t\(\d+ \"[^\"]+\" \w+(?: \"[^\"]*\")?\)\n)+)\t\)\n", text)
    if not m:
        raise SystemExit("build_native21: no (layers ...) block in the saved board")
    rows = m.group(1).splitlines()
    others = [r for r in rows if not re.match(r'\t\t\(\d+ "[^"]+\.Cu" ', r)]
    copper = [f'\t\t({layers21.KICAD_ID[n]} "{n}" signal)' for n in layers21.CU]
    text = text[:m.start(1)] + "\n".join(copper + others) + "\n" + text[m.end(1):]
    text, n_st = re.subn(r"\t\t\(stackup\n.*?\n\t\t\)\n", lambda _: stackup_sexpr(layers21.STACKUP), text, count=1,
                         flags=re.S)
    text, n_th = re.subn(r"(\n\t\(general\n\t\t\(thickness )[0-9.]+\)",
                         lambda g: g.group(1) + _num(layers21.STACKUP["board_thickness_mm"]) + ")", text, count=1)
    if n_st != 1 or n_th != 1:
        raise SystemExit("build_native21: no (stackup ...) or (general (thickness ...)) in the saved board")
    path.write_text(text)
    back = pcbnew.LoadBoard(str(path))
    got = tuple(back.GetLayerName(lid) for lid in back.GetEnabledLayers().CuStack())
    if got != layers21.CU or back.GetCopperLayerCount() != len(layers21.CU):
        raise SystemExit(f"build_native21: KiCad reads copper {got}, stackup.json has {layers21.CU}")


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
        # stage 53 (s52 footprint/3D review item 22): every unit model resolves to the TRACKED PS/models3d/
        # (${KIPRJMOD}/../models3d/ with KIPRJMOD = native-21), as the vendored libraries already point. The native-20
        # assignments named ${KIPRJMOD}/models3d/, an untracked copy, so a clean checkout exported the STEP without L1,
        # C1-C6, C38-C41, BR1, RV1, J4, J6 and T1 (gates/model_gate.py now fails the chain on that).
        for model in fp.Models():
            model.m_Filename = model.m_Filename.replace("${KIPRJMOD}/models3d/", "${KIPRJMOD}/../models3d/")
        board.Add(fp)
        for pad in fp.Pads():
            n = pin_net.get((ref, pad.GetNumber()))
            if n:
                pad.SetNet(board.FindNet(n))
    # stage 33: native-21/stackup.json is native-21's own (tracked) source, no longer copied from native-20
    for f in ("section.kicad_pro", "fp-lib-table"):
        if (N20 / f).exists():
            shutil.copy2(N20 / f, OUT / f)
    # JLC multilayer limits (tools/jlc_dfm_check.py): via drill >= 0.15 mm and our 0.15 mm via ring
    # floor, so KiCad's own DRC enforces the via rules too (PTH rings are checked by the gate)
    pro = json.loads((OUT / "section.kicad_pro").read_text())
    rules = pro["board"]["design_settings"]["rules"]
    rules.update(min_through_hole_diameter=0.15, min_via_annular_width=0.15)
    (OUT / "section.kicad_pro").write_text(json.dumps(pro, indent=2) + "\n")
    # (stage 53: no native-21/models3d copy any more; the models are PS/models3d/, tracked)
    if board.GetCopperLayerCount() != len(layers21.CU):
        board.SetCopperLayerCount(len(layers21.CU))
    pcbnew.SaveBoard(str(OUT / "section.kicad_pcb"), board)
    write_stack(OUT / "section.kicad_pcb")
    print(json.dumps({"footprints": len(comps), "nets": len(nets), "outline": OUTLINE}))


if __name__ == "__main__":
    main()
