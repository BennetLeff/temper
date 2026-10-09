"""Native KiCad adapter for source-derived central-supervisor pins and placement."""

from __future__ import annotations

import csv
import json
import shutil
import uuid
from collections import defaultdict
from pathlib import Path

import pcbnew as pcb

HERE = Path(__file__).resolve().parent / "central"
LIB = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
DST = HERE / "native"
NAMESPACE = uuid.UUID("c1f93a27-737e-5e89-8d97-73e31d742ab6")


def uid(s):
    return str(uuid.uuid5(NAMESPACE, s))


def vec(x, y):
    return pcb.VECTOR2I(pcb.FromMM(x), pcb.FromMM(y))


def main():
    spec = json.loads((HERE / "layout.json").read_text())
    DST.mkdir(parents=True, exist_ok=True)
    parts = defaultdict(list)
    for r in csv.DictReader((HERE / "generated/pins.tsv").open(), delimiter="\t"):
        parts[r["reference"]].append(r)
    b = pcb.BOARD()
    b.SetCopperLayerCount(4)
    nets = {}
    nc = {}
    for ref, rows in parts.items():
        for r in rows:
            name = (
                r["net"]
                if r["net"] != "NC"
                else f"unconnected-({ref}-{r['function']}-Pad{r['pin']})"
            )
            nc[ref + "." + r["pin"]] = name
            if name not in nets:
                n = pcb.NETINFO_ITEM(b, name)
                b.Add(n)
                nets[name] = n
    # Match round4 renderer hierarchy IDs deterministically, including 12-per-sheet split.
    groups = defaultdict(list)
    for ref, rows in parts.items():
        groups[rows[0]["sheet"]].append(ref)
    pages = {}
    for g, refs in groups.items():
        large = [r for r in refs if len(parts[r]) > 24]
        small = [r for r in refs if len(parts[r]) <= 24]
        for ref in large:
            pages[ref] = g + "_" + ref
        for i, ref in enumerate(small):
            pages[ref] = g + "_" + str(i // 12 + 1)
    missing = []
    pads = {}
    footprint_sources = {}
    for ref, rows in parts.items():
        lib, name = rows[0]["footprint"].split(":")
        path = LIB / (lib + ".pretty") / (name + ".kicad_mod")
        if not path.is_file():
            missing.append(str(path))
            continue
        local = DST / (lib + ".pretty")
        local.mkdir(exist_ok=True)
        shutil.copyfile(path, local / path.name)
        f = pcb.FootprintLoad(str(local), name)
        f.SetFPID(pcb.LIB_ID(lib, name))
        f.SetReference(ref)
        f.SetValue(rows[0]["mpn"])
        if lib == "NetTie":
            # Keep the explicitly captured PCB feature in the engineering inventory.
            f.SetAttributes(f.GetAttributes() & ~pcb.FP_EXCLUDE_FROM_BOM)
        f.SetPath(
            pcb.KIID_PATH("/" + uid("root") + "/" + uid("page/" + pages[ref]) + "/" + uid(ref))
        )
        b.Add(f)
        x, y, a = spec["placement"][ref]
        f.SetPosition(vec(x, y))
        f.SetOrientationDegrees(a)
        if ref in spec.get("backside_parts", []):
            f.Flip(f.GetPosition(), False)
        f.Reference().SetVisible(False)
        f.Value().SetVisible(False)
        wanted = {r["pin"]: r for r in rows}
        actual = {p.GetNumber() for p in f.Pads() if p.GetNumber()}
        if actual != set(wanted):
            raise ValueError(
                f"{ref} {rows[0]['source_ref']}: footprint pins {actual} vs source {set(wanted)}"
            )
        for pd in f.Pads():
            if pd.GetNumber():
                pd.SetNet(nets[nc[ref + "." + pd.GetNumber()]])
                pads[ref + "." + pd.GetNumber()] = [
                    pcb.ToMM(pd.GetPosition().x),
                    pcb.ToMM(pd.GetPosition().y),
                ]
        footprint_sources[rows[0]["footprint"]] = str(path)
    if missing:
        raise ValueError("Unresolved exact footprints: " + str(missing))
    local = DST / "MountingHole.pretty"
    local.mkdir(exist_ok=True)
    name = "MountingHole_3.2mm_M3"
    shutil.copyfile(
        LIB / "MountingHole.pretty" / (name + ".kicad_mod"), local / (name + ".kicad_mod")
    )
    footprint_sources["MountingHole:" + name] = str(
        LIB / "MountingHole.pretty" / (name + ".kicad_mod")
    )
    for i, (x, y, d) in enumerate(spec["mounts"], 1):
        assert d == 3.2
        f = pcb.FootprintLoad(str(local), name)
        f.SetReference("H" + str(i))
        f.SetFPID(pcb.LIB_ID("MountingHole", name))
        f.SetAttributes(pcb.FP_BOARD_ONLY | pcb.FP_EXCLUDE_FROM_BOM | pcb.FP_EXCLUDE_FROM_POS_FILES)
        f.SetPosition(vec(x, y))
        b.Add(f)
    if (HERE / "copper.json").exists():
        copper = json.loads((HERE / "copper.json").read_text())
        layers = {b.GetLayerName(i): i for i in [pcb.F_Cu, pcb.In1_Cu, pcb.In2_Cu, pcb.B_Cu]}
        for n, layer, width, a, c in copper["tracks"]:
            t = pcb.PCB_TRACK(b)
            t.SetNet(nets[n])
            t.SetLayer(layers[layer])
            t.SetWidth(pcb.FromMM(width))
            if (
                n in {"AUX_24V", "POD_5V", "REG3_5V", "COIL_RET"} and width >= 0.4
            ) or [n, layer, width, a, c] in copper.get("locked_tracks", []):
                t.SetLocked(True)
            t.SetStart(vec(*a))
            t.SetEnd(vec(*c))
            b.Add(t)
        for n, x, y, width, drill in copper["vias"]:
            v = pcb.PCB_VIA(b)
            v.SetNet(nets[n])
            v.SetPosition(vec(x, y))
            v.SetWidth(pcb.FromMM(width))
            v.SetDrill(pcb.FromMM(drill))
            if [n, x, y, width, drill] in copper.get("locked_vias", []):
                v.SetLocked(True)
            v.SetViaType(pcb.VIATYPE_THROUGH)
            v.SetLayerPair(pcb.F_Cu, pcb.B_Cu)
            b.Add(v)
    w, h, _ = spec["size_mm"]
    for a, c in [((0, 0), (w, 0)), ((w, 0), (w, h)), ((w, h), (0, h)), ((0, h), (0, 0))]:
        s = pcb.PCB_SHAPE(b)
        s.SetShape(pcb.SHAPE_T_SEGMENT)
        s.SetStart(vec(*a))
        s.SetEnd(vec(*c))
        s.SetLayer(pcb.Edge_Cuts)
        s.SetWidth(pcb.FromMM(0.05))
        b.Add(s)
    ds = b.GetDesignSettings()
    ds.m_MinClearance = pcb.FromMM(0.15)
    ds.m_TrackMinWidth = pcb.FromMM(0.15)
    ds.m_ViasMinSize = pcb.FromMM(0.6)
    ds.m_MinThroughDrill = pcb.FromMM(0.3)
    for region in spec.get("zones", []):
        zone = pcb.ZONE(b)
        zone.SetNet(nets[region["net"]])
        zone.SetLayer(b.GetLayerID(region["layer"]))
        zone.SetLocalClearance(pcb.FromMM(region["clearance_mm"]))
        zone.SetPadConnection(pcb.ZONE_CONNECTION_FULL)
        zone.SetMinThickness(pcb.FromMM(0.2))
        x0, y0, x1, y1 = region["rect_mm"]
        polygon = zone.Outline()
        polygon.NewOutline()
        for x, y in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]:
            polygon.Append(pcb.FromMM(x), pcb.FromMM(y))
        b.Add(zone)
    b.BuildConnectivity()
    # Load the saved board so native DRC/zone-fill has a project-backed context.
    pcb.SaveBoard(str(DST / "supervisor.kicad_pcb"), b)
    (HERE / "pad-coordinates.json").write_text(json.dumps(pads, indent=2) + "\n")
    names = {n.split(":")[0] for n in footprint_sources}
    (DST / "fp-lib-table").write_text(
        "(fp_lib_table (version 7)\n"
        + "\n".join(
            f'(lib (name "{n}") (type "KiCad") (uri "${{KIPRJMOD}}/{n}.pretty") (options "") (descr "Vendored installed official footprint"))'
            for n in sorted(names)
        )
        + "\n)\n"
    )
    (DST / "supervisor.kicad_pro").write_text(
        json.dumps(
            {
                "board": {
                    "design_settings": {
                        "rules": {
                            "min_clearance": 0.15,
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
    (DST / "supervisor.kicad_dru").write_text(
        '(version 1)\n(rule "SELV prototype baseline" (constraint clearance (min 0.15mm)))\n'
    )
    b = pcb.LoadBoard(str(DST / "supervisor.kicad_pcb"))
    b.BuildConnectivity()
    pcb.ZONE_FILLER(b).Fill(b.Zones())
    pcb.SaveBoard(str(DST / "supervisor.kicad_pcb"), b)
    if not pcb.ExportSpecctraDSN(b, str(HERE / "supervisor.dsn")):
        raise RuntimeError("DSN export failed")
    print(f"Created central supervisor {len(parts)} electrical components / {len(nets)} nets")


if __name__ == "__main__":
    main()
