#!/usr/bin/env python3
"""Check native CAD exports against JSON and emit BOM/CPL; no circuit inference."""
from __future__ import annotations
import csv
import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
parts = json.loads((ROOT / "cad/design.json").read_text())["parts"]
source = {p["ref"]: p for p in parts}
netlist = ET.parse(ROOT / "build/netlist.xml").getroot()
components = {c.attrib["ref"]: c for c in netlist.findall("components/comp")}
assert set(components) == set(source), "Schematic/source component mismatch"
schematic_pins = {}
for net in netlist.findall("nets/net"):
    for node in net.findall("node"):
        schematic_pins[(node.attrib["ref"], node.attrib["pin"])] = net.attrib["name"]
board_pins = json.loads((ROOT / "build/pad-coordinates.json").read_text())
for p in parts:
    fields = {f.attrib["name"]: f.text for f in components[p["ref"]].findall("fields/field")}
    for name, key in [("MPN", "mpn"), ("Manufacturer", "manufacturer"), ("LCSC", "lcsc")]:
        assert fields[name] == p[key], (p["ref"], name)
    for pin, net in p["pins"].items():
        expected = net if net else None
        sch = schematic_pins[(p["ref"], pin)]
        pcb = board_pins[p["ref"]][pin][2]
        if expected:
            assert sch == pcb == expected, (p["ref"], pin, expected, sch, pcb)
        else:
            assert sch == pcb and sch.startswith("unconnected-"), (p["ref"], pin, sch, pcb)
positions = {r["Ref"]: r for r in csv.DictReader((ROOT / "build/positions.csv").open())}
# drill/place origin: lower-left outline corner (Rev E default x 50, y 150; Rev F from design.json)
X0, _, _, Y1 = json.loads((ROOT / "cad/design.json").read_text()).get("board", {}).get("outline", [50, 45, 190, 150])
assert set(positions) == set(source), "Native placement membership mismatch"
for ref, row in positions.items():
    x, y, angle = source[ref]["pcb"]
    assert abs(float(row["PosX"]) - (x - X0)) < 1e-5
    assert abs(float(row["PosY"]) - (Y1 - y)) < 1e-5
    assert (float(row["Rot"]) - angle) % 360 == 0
    assert row["Side"] == "top"
out = ROOT / "manufacturing"
out.mkdir(exist_ok=True)
def csv_file(name: str, header: list[str], rows: list[list]) -> None:
    with (out / name).open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
groups = defaultdict(list)
for p in parts:
    groups[(p["mpn"], p["lcsc"], p["assembly"])].append(p)
rows = []
bom = []
for _, group in sorted(groups.items()):
    p = group[0]
    refs = ",".join(x["ref"] for x in group)
    rows.append([refs, len(group), p["value"], p["manufacturer"], p["mpn"], p["lcsc"],
                 p["footprint"], p["assembly"], p["unit_usd"],
                 round(len(group) * p["unit_usd"], 4)])
    if p["assembly"] == "SMT":
        bom.append([p["value"] + " " + p["mpn"], refs,
                    p["footprint"].split(":")[1], p["lcsc"]])
csv_file("bom-complete.csv", ["Designators", "Quantity", "Value", "Manufacturer", "MPN",
         "LCSC", "Footprint", "Assembly", "Catalog unit USD", "Catalog subtotal USD"], rows)
csv_file("bom-jlcpcb.csv", ["Comment", "Designator", "Footprint", "LCSC Part #"], bom)
smt = [p for p in parts if p["assembly"] == "SMT"]
offsets = json.loads((ROOT / "sources/placement-rev-c.json").read_text())["rotation_offsets_by_ref"]
def keyed(p: dict) -> bool:
    """Everything but plain R/C lands; a polarized capacitor (KiCad CP_*) is keyed."""
    return p["kind"] not in ["R", "C"] or p["footprint"].split(":")[1].startswith("CP_")
def assembly_angle(p: dict) -> float:
    if keyed(p):
        assert p["ref"] in offsets, "Keyed part has no placement-library audit"
    return (float(positions[p["ref"]]["Rot"]) + offsets.get(p["ref"], 0)) % 360
csv_file("cpl-jlcpcb.csv", ["Designator", "Mid X", "Mid Y", "Layer", "Rotation"],
         [[p["ref"], positions[p["ref"]]["PosX"]+"mm", positions[p["ref"]]["PosY"]+"mm",
           "top", assembly_angle(p)] for p in smt])
csv_file("orientation-audit.csv",
         ["Designator", "MPN", "LCSC", "Native angle deg", "Library offset deg", "CPL angle deg",
          "Pin1 board X mm", "Pin1 board Y mm", "Verification basis"],
         [[p["ref"], p["mpn"], p["lcsc"], p["pcb"][2],
           offsets.get(p["ref"], 0), assembly_angle(p),
           *board_pins[p["ref"]].get("1", [None, None])[:2],
           "LCSC EasyEDA pad-number audit; final JLC preview required" if p["ref"] in offsets
           else "Nonpolar R/C; native angle retained"] for p in smt])
result = {"source_components": len(parts), "smt_placements": len(smt),
          "smt_unique_lines": len(bom), "source_schematic_board_pin_parity": "PASS",
          "source_native_placement_coordinates_angles": "PASS",
          "catalog_components_usd": round(sum(p["unit_usd"] for p in parts), 4),
          "catalog_smt_usd": round(sum(p["unit_usd"] for p in smt), 4),
          "keyed_placement_library_rotation_audit": "PASS; offsets applied",
          "vendor_rotation_preview": "NOT PERFORMED"}
(ROOT / "validation/cad-bom-parity.json").write_text(json.dumps(result, indent=2)+"\n")
print(json.dumps(result, indent=2))
