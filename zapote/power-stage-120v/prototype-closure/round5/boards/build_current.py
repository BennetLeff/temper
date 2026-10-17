"""KiCad artifact adapter for Talema current transformers and permanent burdens.

Electrical values are copied from the immutable Rust-emitted round4 pin table.
The local footprint directly records Talema AC1005 mechanical drawing dimensions.
"""

from __future__ import annotations

import csv
import json
import shutil
import uuid
from collections import defaultdict
from pathlib import Path

import pcbnew as p
from render_sensor import definition, pins

HERE = Path(__file__).resolve().parent
LIB = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")


def uid(text):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "temper-current-r5/" + text))


def vec(x, y):
    return p.VECTOR2I(p.FromMM(x), p.FromMM(y))


def main(channel):
    name = channel.lower()
    dst = HERE / "native" / (name + "-sensor")
    dst.mkdir(parents=True, exist_ok=True)
    refmap = {
        f"CT_{channel}": "T1",
        f"R_{channel}B1": "R1",
        f"R_{channel}B2": "R2",
        f"TVS_{channel}": "D1",
    }
    with (HERE / "../../round4/supervisor/generated/pins.tsv").open() as f:
        selected = [dict(r) for r in csv.DictReader(f, delimiter="\t") if r["reference"] in refmap]
    for row in selected:
        row["source_ref"] = row["reference"]
        row["reference"] = refmap[row["reference"]]
        if row["reference"] == "T1":
            row["footprint"] = "Round5:Talema_AC1005_AC1020"
        row["value"] = row["mpn"].split()[0]
    for i, net in enumerate([channel + "_RAW", "REF_1V25"], 1):
        selected.append(
            {
                "reference": "J1",
                "mpn": "B2B-XH-A(LF)(SN)",
                "footprint": "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical",
                "sheet": "CURRENT",
                "pin": str(i),
                "function": str(i),
                "type": "passive",
                "net": net,
                "source_ref": "J_" + channel + "_SIGNAL",
                "value": "B2B-XH-A",
            }
        )
    with (HERE / (name + "-pins.tsv")).open("w") as f:
        writer = csv.DictWriter(f, fieldnames=selected[0], delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(selected)
    (HERE / (name + "-ref-map.json")).write_text(json.dumps(refmap, indent=2) + "\n")
    local = dst / "Round5.pretty"
    local.mkdir(exist_ok=True)
    # Talema drawing: end terminals 15.24 pitch; mechanical pin 7.62 behind;
    # body 23.80 x 11.12, first terminal row 1.75 from the body edge.
    (
        local / "Talema_AC1005_AC1020.kicad_mod"
    ).write_text("""(footprint "Talema_AC1005_AC1020" (version 20241229) (generator "temper-drawing-adapter") (layer "F.Cu") (attr through_hole)
 (descr "Talema AC1005-AC1020; official AC-1005.pdf drawing; pin 3 mechanical only. Primary insulated conductor through 9.50 mm aperture, not PCB.")
 (property "Reference" "T" (at 0 -3.5) (layer "F.SilkS") (effects(font(size 1 1)(thickness 0.15))))
 (property "Value" "AC1005" (at 0 11.5) (layer "F.Fab") (effects(font(size 1 1)(thickness 0.15))))
 (fp_rect(start -12.15 -2)(end 12.15 9.62)(stroke(width 0.05)(type default))(fill none)(layer "F.CrtYd"))
 (fp_rect(start -11.9 -1.75)(end 11.9 9.37)(stroke(width 0.1)(type default))(fill none)(layer "F.Fab"))
 (fp_rect(start -12.01 -1.86)(end 12.01 9.48)(stroke(width 0.12)(type default))(fill none)(layer "F.SilkS"))
 (pad "1" thru_hole rect(at 7.62 0)(size 2.2 2.2)(drill 1.2)(layers "*.Cu" "*.Mask"))
 (pad "2" thru_hole circle(at -7.62 0)(size 2.2 2.2)(drill 1.2)(layers "*.Cu" "*.Mask"))
 (pad "3" thru_hole circle(at 0 7.62)(size 2.2 2.2)(drill 1.2)(layers "*.Cu" "*.Mask")))\n""")
    grouped = defaultdict(list)
    for row in selected:
        grouped[row["reference"]].append(row)
    b = p.BOARD()
    b.SetCopperLayerCount(2)
    nets = {}
    for net in [channel + "_RAW", "REF_1V25", "unconnected-(T1-SUPPORT-Pad3)"]:
        n = p.NETINFO_ITEM(b, net)
        b.Add(n)
        nets[net] = n
    placement = {
        "T1": (20, 5, 0),
        "R1": (18, 22, 90),
        "R2": (23, 22, 90),
        "D1": (31, 22, 90),
        "J1": (9, 28, 0),
    }
    padcoords = {}
    libs = {"Round5"}
    for ref, rows in grouped.items():
        lib, fpname = rows[0]["footprint"].split(":")
        libs.add(lib)
        fplocal = dst / (lib + ".pretty")
        fplocal.mkdir(exist_ok=True)
        if lib != "Round5":
            shutil.copyfile(
                LIB / (lib + ".pretty") / (fpname + ".kicad_mod"), fplocal / (fpname + ".kicad_mod")
            )
        fp = p.FootprintLoad(str(fplocal), fpname)
        fp.SetFPID(p.LIB_ID(lib, fpname))
        fp.SetReference(ref)
        fp.SetValue(rows[0]["value"])
        fp.SetField("MPN", rows[0]["mpn"])
        fp.GetField("MPN").SetVisible(False)
        fp.SetPath(p.KIID_PATH("/" + uid(name + "/root") + "/" + uid(name + "/" + ref)))
        b.Add(fp)
        x, y, a = placement[ref]
        fp.SetPosition(vec(x, y))
        fp.SetOrientationDegrees(a)
        fp.Reference().SetVisible(False)
        fp.Value().SetVisible(False)
        bypin = {r["pin"]: r for r in rows}
        assert {pd.GetNumber() for pd in fp.Pads()} == set(bypin)
        for pd in fp.Pads():
            row = bypin[pd.GetNumber()]
            net = row["net"] if row["net"] != "NC" else "unconnected-(T1-SUPPORT-Pad3)"
            pd.SetNet(nets[net])
            padcoords[ref + "." + pd.GetNumber()] = [
                p.ToMM(pd.GetPosition().x),
                p.ToMM(pd.GetPosition().y),
            ]
    routes = [
        (
            channel + "_RAW",
            "F",
            ["T1.1", [35, 5], [35, 27.5], [14, 27.5], [14, 25], [9, 25], "J1.1"],
        )
    ]
    for ref in ["R1", "R2", "D1"]:
        x, y = padcoords[ref + ".1"]
        routes.append((channel + "_RAW", "F", [ref + ".1", [x, 27.5]]))
    for ref in ["R1", "R2", "D1"]:
        x, y = padcoords[ref + ".2"]
        routes.append(("REF_1V25", "F", [ref + ".2", [x, y - 1.5]]))
        via = p.PCB_VIA(b)
        via.SetNet(nets["REF_1V25"])
        via.SetPosition(vec(x, y - 1.5))
        via.SetWidth(p.FromMM(0.6))
        via.SetDrill(p.FromMM(0.3))
        via.SetViaType(p.VIATYPE_THROUGH)
        via.SetLayerPair(p.F_Cu, p.B_Cu)
        b.Add(via)
    for net, _layer, points in routes:
        points = [padcoords[x] if isinstance(x, str) else x for x in points]
        for a, c in zip(points, points[1:]):  # noqa: B905 -- KiCad embeds Python 3.9; adjacent pairs intentionally differ in length.
            t = p.PCB_TRACK(b)
            t.SetNet(nets[net])
            t.SetStart(vec(*a))
            t.SetEnd(vec(*c))
            t.SetWidth(p.FromMM(0.4))
            t.SetLayer(p.F_Cu)
            b.Add(t)
    zone = p.ZONE(b)
    zone.SetNet(nets["REF_1V25"])
    zone.SetLayer(p.B_Cu)
    zone.SetLocalClearance(p.FromMM(0.25))
    zone.SetPadConnection(p.ZONE_CONNECTION_FULL)
    zone.SetThermalReliefGap(p.FromMM(0.25))
    zone.SetThermalReliefSpokeWidth(p.FromMM(0.4))
    zone.SetMinThickness(p.FromMM(0.15))
    outline = zone.Outline()
    outline.NewOutline()
    for x, y in [(1, 1), (44, 1), (44, 34), (1, 34)]:
        outline.Append(p.FromMM(x), p.FromMM(y))
    b.Add(zone)
    for a, c in [((0, 0), (45, 0)), ((45, 0), (45, 35)), ((45, 35), (0, 35)), ((0, 35), (0, 0))]:
        line = p.PCB_SHAPE(b)
        line.SetShape(p.SHAPE_T_SEGMENT)
        line.SetStart(vec(*a))
        line.SetEnd(vec(*c))
        line.SetLayer(p.Edge_Cuts)
        line.SetWidth(p.FromMM(0.05))
        b.Add(line)
    for i, (x, y) in enumerate([(3, 3), (42, 3), (42, 32)], 1):
        f = p.FOOTPRINT(b)
        f.SetReference("H" + str(i))
        f.SetAttributes(p.FP_BOARD_ONLY | p.FP_EXCLUDE_FROM_BOM | p.FP_EXCLUDE_FROM_POS_FILES)
        pd = p.PAD(f)
        pd.SetAttribute(p.PAD_ATTRIB_NPTH)
        pd.SetShape(p.PAD_SHAPE_CIRCLE)
        pd.SetSize(vec(2.7, 2.7))
        pd.SetDrillSize(vec(2.7, 2.7))
        pd.SetLayerSet(p.LSET.AllCuMask())
        f.Add(pd)
        b.Add(f)
        f.SetPosition(vec(x, y))
    b.BuildConnectivity()
    p.ZONE_FILLER(b).Fill(b.Zones())
    p.SaveBoard(str(dst / (name + "-sensor.kicad_pcb")), b)
    (dst / "fp-lib-table").write_text(
        "(fp_lib_table (version 7)\n"
        + "".join(
            f'(lib (name "{lib}") (type "KiCad") (uri "${{KIPRJMOD}}/{lib}.pretty") (options "") (descr "Drawing verified or official footprint"))'
            for lib in sorted(libs)
        )
        + ")\n"
    )
    (dst / (name + "-sensor.kicad_pro")).write_text(
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
    (dst / (name + "-sensor.kicad_dru")).write_text(
        '(version 1)\n(rule "SELV burden" (constraint clearance (min 0.2mm)))\n'
    )
    (HERE / (name + "-pad-coordinates.json")).write_text(json.dumps(padcoords, indent=2) + "\n")
    render(name, grouped, dst)


def render(name, parts, dst):
    defs = {
        n: definition(lib, n)
        for lib, n in [
            ("Device", "L"),
            ("Device", "R_Small_US"),
            ("Device", "D_TVS"),
            ("Connector_Generic", "Conn_01x02"),
        ]
    }
    defs["CT"] = defs.pop("L").replace('"L', '"CT')
    defs["CT"] = (
        defs["CT"][:-1]
        + '(symbol "CT_1_1" (pin no_connect line(at 7.62 0 180)(length 2.54)(name "SUPPORT"(effects(font(size 1 1))))(number "3"(effects(font(size 1 1)))))))'
    )
    objects = []
    coords = {}
    serial = 0
    positions = {
        "T1": (60.96, 71.12),
        "R1": (101.6, 71.12),
        "R2": (127, 71.12),
        "D1": (152.4, 71.12),
        "J1": (195.58, 71.12),
    }
    for ref, rows in parts.items():
        symbol = (
            "CT"
            if ref == "T1"
            else "R_Small_US"
            if ref.startswith("R")
            else "D_TVS"
            if ref == "D1"
            else "Conn_01x02"
        )
        x, y = positions[ref]
        pp = pins(defs[symbol])
        assert set(pp) == {r["pin"] for r in rows}
        pininst = []
        for number, (dx, dy, _angle) in pp.items():
            coords[(ref, number)] = (x + dx, y - dy)
            pininst.append(f'(pin "{number}"(uuid "{uid(name + ref + number)}"))')
        objects.append(
            f'(symbol(lib_id "Current:{symbol}")(at {x} {y} 0)(unit 1)(in_bom yes)(on_board yes)(dnp no)(uuid "{uid(name + "/" + ref)}")(property "Reference" "{ref}"(at {x + 5.08} {y - 5.08} 0)(effects(font(size 1.27 1.27))))(property "Value" "{rows[0]["value"]}"(at {x + 5.08} {y + 7.62} 0)(effects(font(size 1.27 1.27))))(property "Footprint" "{rows[0]["footprint"]}"(at {x} {y} 0)(effects(font(size 1 1)) hide))(property "MPN" "{rows[0]["mpn"]}"(at {x} {y} 0)(effects(font(size 1 1)) hide)){"".join(pininst)}(instances(project "{name}-sensor"(path "/{uid(name + "/root")}"(reference "{ref}")(unit 1)))))'
        )
        for row in rows:
            xy = coords[(ref, row["pin"])]
            serial += 1
            if row["net"] == "NC":
                objects.append(
                    f'(no_connect(at {xy[0]} {xy[1]})(uuid "{uid(name + str(serial))}"))'
                )
                continue
            end = (xy[0], xy[1] - 10.16 if row["pin"] == "1" else xy[1] + 10.16)
            objects.append(
                f'(wire(pts(xy {xy[0]} {xy[1]})(xy {end[0]} {end[1]}))(stroke(width 0)(type default))(uuid "{uid(name + "w" + str(serial))}"))'
            )
            objects.append(
                f'(global_label "{row["net"]}"(shape bidirectional)(at {end[0]} {end[1]} 0)(effects(font(size 1.27 1.27))(justify left))(uuid "{uid(name + "l" + str(serial))}"))'
            )
    for i, text in enumerate(
        [
            "Permanent parallel burdens and bidirectional TVS stay with CT when J1 disconnects.",
            "CT is 50/60 Hz only. Insulated one-turn primary passes through aperture; never a PCB terminal.",
            "Pin 3 is mechanical support only. 4 kVrms datasheet test does not qualify the product insulation.",
            "Candidate 45 x 35 mm. Primary wire insulation, retention and enclosure mounting remain held.",
        ]
    ):
        objects.append(
            f'(text "{text}"(at 140 {110 + i * 10.16} 0)(effects(font(size 1.27 1.27)))(uuid "{uid(name + text)}"))'
        )
    embedded = "".join(
        raw.replace('(symbol "' + key + '"', '(symbol "Current:' + key + '"', 1)
        for key, raw in defs.items()
    )
    (dst / "current.kicad_sym").write_text(
        '(kicad_symbol_lib(version 20250114)(generator "temper")' + "".join(defs.values()) + ")\n"
    )
    (dst / "sym-lib-table").write_text(
        '(sym_lib_table (version 7) (lib (name "Current") (type "KiCad") (uri "${KIPRJMOD}/current.kicad_sym") (options "") (descr "Standard KiCad symbols; CT secondary plus mechanical pin")))\n'
    )
    (dst / (name + "-sensor.kicad_sch")).write_text(
        f'(kicad_sch(version 20250114)(generator "temper")(uuid "{uid(name + "/root")}")(paper "A4")(title_block(title "Temper {name} permanent burden card")(date "2026-10-05")(rev "R5 candidate"))(lib_symbols {embedded})'
        + "".join(objects)
        + '(sheet_instances(path "/"(page "1"))))\n'
    )


if __name__ == "__main__":
    for channel in ["IPROOF", "ILINE"]:
        main(channel)
