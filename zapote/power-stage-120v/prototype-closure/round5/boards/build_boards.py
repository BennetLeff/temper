"""KiCad-only adapter. Circuit pins and hand-declared geometry are data inputs."""

from __future__ import annotations

import csv
import json
import shutil
import sys
import uuid
from collections import defaultdict
from pathlib import Path

import pcbnew as pcb

HERE = Path(__file__).resolve().parent
LIB = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")


def uid(s):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "temper-round5-boards/" + s))


def vec(x, y):
    return pcb.VECTOR2I(pcb.FromMM(x), pcb.FromMM(y))


def main(sensor="catch"):
    spec = json.loads((HERE / (sensor + "-layout.json")).read_text())
    dst = HERE / "native" / (sensor + "-sensor")
    dst.mkdir(parents=True, exist_ok=True)
    parts = defaultdict(list)
    for r in csv.DictReader((HERE / (sensor + "-pins.tsv")).open(), delimiter="\t"):
        parts[r["reference"]].append(r)
    local = dst / "Round5.pretty"
    local.mkdir(exist_ok=True)
    (
        local / "HV_WirePair_P25.kicad_mod"
    ).write_text("""(footprint "HV_WirePair_P25" (version 20241229) (generator "temper") (layer "F.Cu") (attr through_hole)
 (property "Reference" "J" (at 4 12.5 0) (layer "F.Fab") (effects (font (size 1 1)(thickness 0.15))))
 (property "Value" "SOLDER_22AWG" (at 6 12.5 0) (layer "F.Fab") (effects (font (size 1 1)(thickness 0.15))))
 (fp_rect (start -1.7 -1.7)(end 1.7 1.7)(stroke(width 0.05)(type default))(fill none)(layer "F.CrtYd")) (fp_rect (start -1.7 23.3)(end 1.7 26.7)(stroke(width 0.05)(type default))(fill none)(layer "F.CrtYd"))
 (pad "1" thru_hole circle (at 0 0)(size 2.8 2.8)(drill 1.3)(layers "*.Cu" "*.Mask"))
 (pad "2" thru_hole circle (at 0 25)(size 2.8 2.8)(drill 1.3)(layers "*.Cu" "*.Mask")))""")
    if spec.get("hv_pitch_mm", 25) != 25:
        path = local / "HV_WirePair_P25.kicad_mod"
        path.write_text(
            path.read_text()
            .replace("(at 0 25)", f"(at 0 {spec['hv_pitch_mm']})")
            .replace("23.3", str(spec["hv_pitch_mm"] - 1.7))
            .replace("26.7", str(spec["hv_pitch_mm"] + 1.7))
        )
    # TI DWE0016A HV/isolation option: 9.75 mm row spacing, 1.65 x 0.6 pads.
    f = pcb.FootprintLoad(str(LIB / "Package_SO.pretty"), "SOIC-16W_7.5x10.3mm_P1.27mm")
    for pd in f.Pads():
        pos = pd.GetPosition()
        pd.SetPosition(vec(-4.875 if pos.x < 0 else 4.875, pcb.ToMM(pos.y)))
        pd.SetSize(vec(1.65, 0.6))
    f.SetFPID(pcb.LIB_ID("Round5", "AMC3330_DWE_HV"))
    pcb.FootprintSave(str(local), f)
    names = {r[0]["footprint"].split(":")[0] for r in parts.values()}
    (dst / "fp-lib-table").write_text(
        "(fp_lib_table (version 7)\n"
        + "\n".join(
            f'(lib (name "{n}")(type "KiCad")(uri "${{KIPRJMOD}}/{n}.pretty")(options "")(descr "Vendored source footprint"))'
            for n in sorted(names)
        )
        + "\n)\n"
    )
    b = pcb.BOARD()
    b.SetCopperLayerCount(2)
    nets = {}
    for name in sorted(
        {r["net"] for rows in parts.values() for r in rows if r["net"] != "NC"}
        | {"unconnected-(U1-NC-Pad4)"}
    ):
        n = pcb.NETINFO_ITEM(b, name)
        b.Add(n)
        nets[name] = n
    fps = {}
    pads = {}
    for ref, rows in parts.items():
        lib, name = rows[0]["footprint"].split(":")
        (dst / (lib + ".pretty")).mkdir(exist_ok=True)
        if lib != "Round5":
            shutil.copyfile(
                LIB / (lib + ".pretty") / (name + ".kicad_mod"),
                dst / (lib + ".pretty") / (name + ".kicad_mod"),
            )
        f = pcb.FootprintLoad(str(dst / (lib + ".pretty")), name)
        if f is None:
            raise RuntimeError(rows[0]["footprint"])
        f.SetReference(ref)
        f.SetValue(rows[0]["value"])
        f.SetField("MPN", rows[0]["mpn"])
        f.GetField("MPN").SetVisible(False)
        f.SetFPID(pcb.LIB_ID(lib, name))
        f.SetPath(pcb.KIID_PATH("/" + uid(sensor + "-root") + "/" + uid(sensor + "/" + ref)))
        b.Add(f)
        x, y, a = spec["placement"][ref]
        f.SetPosition(vec(x, y))
        f.SetOrientationDegrees(a)
        f.Reference().SetVisible(False)
        f.Value().SetVisible(False)
        for pd in f.Pads():
            row = next((r for r in rows if r["pin"] == pd.GetNumber()), None)
            if row is None:
                raise ValueError(f"{ref}.{pd.GetNumber()} missing pin")
            pd.SetNet(nets[row["net"]] if row["net"] != "NC" else nets["unconnected-(U1-NC-Pad4)"])
            pads[ref + "." + pd.GetNumber()] = pd
        fps[ref] = f
    for i, (x, y, d) in enumerate(spec["mounts"], 1):
        f = pcb.FOOTPRINT(b)
        f.SetReference("H" + str(i))
        f.SetAttributes(pcb.FP_BOARD_ONLY | pcb.FP_EXCLUDE_FROM_BOM | pcb.FP_EXCLUDE_FROM_POS_FILES)
        pd = pcb.PAD(f)
        pd.SetAttribute(pcb.PAD_ATTRIB_NPTH)
        pd.SetShape(pcb.PAD_SHAPE_CIRCLE)
        pd.SetSize(vec(d, d))
        pd.SetDrillSize(vec(d, d))
        pd.SetLayerSet(pcb.LSET.AllCuMask())
        f.Add(pd)
        b.Add(f)
        f.SetPosition(vec(x, y))
    coords = {
        k: [pcb.ToMM(p.GetPosition().x), pcb.ToMM(p.GetPosition().y)] for k, p in pads.items()
    }
    (HERE / (sensor + "-pad-coordinates.json")).write_text(json.dumps(coords, indent=2) + "\n")
    for route in spec["routes"]:
        net, layer, points = route
        pts = [coords[p] if isinstance(p, str) else p for p in points]
        for aa, bb in zip(pts, pts[1:]):  # noqa: B905 -- KiCad embeds Python 3.9; adjacent pairs intentionally differ in length.
            t = pcb.PCB_TRACK(b)
            t.SetStart(vec(*aa))
            t.SetEnd(vec(*bb))
            t.SetWidth(pcb.FromMM(spec["track_mm"]))
            t.SetLayer(pcb.F_Cu if layer == "F" else pcb.B_Cu)
            t.SetNet(nets[net])
            b.Add(t)
    for net, x, y in spec.get("vias", []):
        v = pcb.PCB_VIA(b)
        v.SetPosition(vec(x, y))
        v.SetWidth(pcb.FromMM(0.6))
        v.SetDrill(pcb.FromMM(0.3))
        v.SetViaType(pcb.VIATYPE_THROUGH)
        v.SetLayerPair(pcb.F_Cu, pcb.B_Cu)
        v.SetNet(nets[net])
        b.Add(v)
    for net, polygon in spec.get("zones", []):
        z = pcb.ZONE(b)
        z.SetNet(nets[net])
        z.SetLayer(pcb.B_Cu)
        z.SetLocalClearance(pcb.FromMM(0.25))
        z.SetPadConnection(pcb.ZONE_CONNECTION_FULL)
        z.SetThermalReliefGap(pcb.FromMM(0.25))
        z.SetThermalReliefSpokeWidth(pcb.FromMM(0.3))
        z.SetMinThickness(pcb.FromMM(0.15))
        poly = z.Outline()
        poly.NewOutline()
        for x, y in polygon:
            poly.Append(pcb.FromMM(x), pcb.FromMM(y))
        b.Add(z)
    w, h, _ = spec["size_mm"]
    for a, c in [((0, 0), (w, 0)), ((w, 0), (w, h)), ((w, h), (0, h)), ((0, h), (0, 0))]:
        s = pcb.PCB_SHAPE(b)
        s.SetShape(pcb.SHAPE_T_SEGMENT)
        s.SetStart(vec(*a))
        s.SetEnd(vec(*c))
        s.SetLayer(pcb.Edge_Cuts)
        s.SetWidth(pcb.FromMM(0.05))
        b.Add(s)
    for label, x, y in [
        ("IN+", 6, 2),
        ("RET", 6, spec.get("hv_pitch_mm", 25) + 5),
        (f"{sensor.upper()} R5", spec["size_mm"][0] - 15, spec["size_mm"][1] - 3),
    ]:
        t = pcb.PCB_TEXT(b)
        t.SetText(label)
        t.SetPosition(vec(x, y))
        t.SetLayer(pcb.F_SilkS)
        t.SetTextSize(vec(0.8, 0.8))
        t.SetTextThickness(pcb.FromMM(0.12))
        b.Add(t)
    b.BuildConnectivity()
    pcb.ZONE_FILLER(b).Fill(b.Zones())
    pcb.SaveBoard(str(dst / (sensor + "-sensor.kicad_pcb")), b)
    (dst / (sensor + "-sensor.kicad_pro")).write_text(
        json.dumps(
            {
                "board": {
                    "design_settings": {
                        "rules": {
                            "min_clearance": 0.2,
                            "min_track_width": 0.2,
                            "min_via_diameter": 0.6,
                            "min_through_hole_diameter": 0.3,
                            "min_hole_clearance": 0.25,
                            "min_copper_edge_clearance": 0.5,
                        }
                    }
                }
            },
            indent=2,
        )
        + "\n"
    )
    hv = spec.get(
        "hv_nets",
        ["HV_RET", "CATCH_P", "VCATCH_TAP", "VCATCH_DCDC_H", "VCATCH_HLDO"]
        + [f"VCATCH_DIV{i}" for i in range(7)],
    ) + ["unconnected-(U1-NC-Pad4)"]
    aa = " || ".join(f"A.NetName == '{n}'" for n in hv)
    bb = " || ".join(f"B.NetName == '{n}'" for n in hv)
    rule = f"A.NetName != '' && B.NetName != '' && (({aa}) != ({bb}))"
    (dst / (sensor + "-sensor.kicad_dru")).write_text(
        '(version 1)\n(rule "Baseline" (constraint clearance (min 0.2mm)))\n'
        + f'(rule "HV to SELV provisional 8mm" (condition "{rule}") (constraint clearance (min 8mm)) (constraint creepage (min 8mm)))\n'
    )
    print(f"Built {sensor} sensor {len(parts)} parts; {len(spec['routes'])} explicit routes")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "catch")
