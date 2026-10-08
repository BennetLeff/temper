"""Thin KiCad adapter for Rust-emitted typed pins; contains no circuit decisions."""
from __future__ import annotations

import csv
import json
import math
import sys
import uuid
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAMESPACE = uuid.UUID("c1f93a27-737e-5e89-8d97-73e31d742ab6")

def uid(name: str) -> str:
    return str(uuid.uuid5(NAMESPACE, name))

def q(s: str) -> str:
    return json.dumps(s)

def source() -> dict[str, list[dict[str, str]]]:
    parts: dict[str, list[dict[str, str]]] = defaultdict(list)
    with (HERE / "generated/pins.tsv").open() as f:
        for row in csv.DictReader(f, delimiter="\t"):
            parts[row["reference"]].append(row)
    return dict(parts)

def render() -> None:
    parts = source()
    out = HERE / "native"
    out.mkdir(exist_ok=True)
    groups: dict[str, list[str]] = defaultdict(list)
    for ref, rows in parts.items():
        groups[rows[0]["sheet"]].append(ref)
    page_specs: list[tuple[str, list[str]]] = []
    for group, refs in groups.items():
        # Large devices receive a dedicated plate to preserve readable pin spacing.
        large = [r for r in refs if len(parts[r]) > 24]
        small = [r for r in refs if len(parts[r]) <= 24]
        for ref in large:
            page_specs.append((group + "_" + ref, [ref]))
        for offset in range(0, len(small), 12):
            page_specs.append((group + "_" + str(offset // 12 + 1), small[offset:offset + 12]))
    root_id = uid("root")
    sheets: list[str] = []
    library: list[str] = []
    for page_index, (page, refs) in enumerate(page_specs, 2):
        page_id = uid("page/" + page)
        definitions: list[str] = []
        objects: list[str] = []
        for index, ref in enumerate(refs):
            rows = parts[ref]
            count = len(rows)
            split = math.ceil(count / 2)
            h = max(5.08, split * 2.54)
            x = 80.01 + (index % 3) * 132.08
            y = 50.8 + (index // 3) * 58.42
            if count > 24:
                x, y = 203.2, 139.7
            name = "Part_" + ref
            definition = [f'(symbol {q(name)} (pin_names (offset 0.508)) (in_bom yes) (on_board yes)',
                          '(property "Reference" "U" (at 0 0 0) (effects (font (size 1.27 1.27))))',
                          f'(property "Value" {q(rows[0]["mpn"])} (at 0 0 0) (effects (font (size 1.27 1.27))))',
                          f'(symbol {q(name + "_0_1")} (rectangle (start -19.05 {-h}) (end 19.05 {h}) (stroke (width 0.254) (type default)) (fill (type background))))',
                          f'(symbol {q(name + "_1_1")}']
            pins = []
            for j, row in enumerate(rows):
                left = j < split
                n = split if left else count - split
                k = j if left else j - split
                px = -21.59 if left else 21.59
                py = (n - 1) * 2.54 - k * 5.08
                direction = 0 if left else 180
                definition.append(f'(pin {row["type"]} line (at {px} {py} {direction}) (length 2.54) (name {q(row["function"])} (effects (font (size 1.016 1.016)))) (number {q(row["pin"])} (effects (font (size 1.016 1.016)))))')
                nx, ny = x + px, y - py
                if row["net"] == "NC":
                    objects.append(f'(no_connect (at {nx} {ny}) (uuid "{uid(ref + "/nc/" + row["pin"])}"))')
                else:
                    angle = 0
                    lx = x - 59.69 if left else x + 24.13
                    objects.append(f'(wire (pts (xy {nx} {ny}) (xy {lx} {ny})) (stroke (width 0) (type default)) (uuid "{uid(ref + "/wire/" + row["pin"])}"))')
                    objects.append(f'(global_label {q(row["net"])} (shape bidirectional) (at {lx} {ny} {angle}) (effects (font (size 1.27 1.27)) (justify left)) (uuid "{uid(ref + "/label/" + row["pin"])}"))')
                pins.append(f'(pin {q(row["pin"])} (uuid "{uid(ref + "/pin/" + row["pin"])}"))')
            definition.append("))")
            raw = "\n".join(definition)
            library.append(raw)
            definitions.append(raw.replace(f'(symbol {q(name)}', f'(symbol {q("Supervisor:" + name)}', 1))
            objects.append(f'''(symbol (lib_id {q("Supervisor:" + name)}) (at {x} {y} 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) (uuid "{uid(ref)}")
(property "Reference" {q(ref)} (at {x} {y-h-3.81} 0) (effects (font (size 1.27 1.27))))
(property "Value" {q(rows[0]["mpn"])} (at {x} {y+h+3.81} 0) (effects (font (size 1.016 1.016))))
(property "Footprint" {q(rows[0]["footprint"])} (at {x} {y} 0) (effects (font (size 1.27 1.27)) hide))
{' '.join(pins)} (instances (project "supervisor" (path "/{root_id}/{page_id}" (reference {q(ref)}) (unit 1)))))''')
        sheet = f'''(kicad_sch (version 20231120) (generator "temper_supervisor") (uuid "{page_id}") (paper "A3")
(title_block (title {q("Temper supervisor: " + page)}) (date "2026-10-04") (rev "4-source-review") (comment 1 "Source connectivity review; NOT fabrication release"))
(lib_symbols {' '.join(definitions)}) {' '.join(objects)})\n'''
        (out / (page + ".kicad_sch")).write_text(sheet)
        sx, sy = 25 + ((page_index - 2) % 6) * 92, 35 + ((page_index - 2) // 6) * 42
        sheets.append(f'''(sheet (at {sx} {sy}) (size 75 25) (stroke (width 0.254) (type default)) (fill (color 0 0 0 0)) (uuid "{page_id}")
(property "Sheetname" {q(page)} (at {sx} {sy-1.27} 0) (effects (font (size 1.27 1.27)) (justify left bottom)))
(property "Sheetfile" {q(page + ".kicad_sch")} (at {sx} {sy+26.27} 0) (effects (font (size 1.016 1.016)) (justify left top)))
(instances (project "supervisor" (path "/{root_id}" (page "{page_index}")))))''')
    (out / "supervisor.kicad_sch").write_text(f'''(kicad_sch (version 20231120) (generator "temper_supervisor") (uuid "{root_id}") (paper "A1")
(title_block (title "Temper independent prototype supervisor") (date "2026-10-04") (rev "4-source-review") (comment 1 "Typed source capture; unresolved items in README; NOT a release"))
(lib_symbols) {' '.join(sheets)} (sheet_instances (path "/" (page "1"))))\n''')
    (out / "supervisor.kicad_sym").write_text('(kicad_symbol_lib (version 20231120) (generator "temper_supervisor")\n' + '\n'.join(library) + '\n)\n')
    (out / "sym-lib-table").write_text('(sym_lib_table (version 7) (lib (name "Supervisor") (type "KiCad") (uri "${KIPRJMOD}/supervisor.kicad_sym") (options "") (descr "Rust-source typed supervisor capture")))\n')
    (out / "supervisor.kicad_pro").write_text("{}\n")
    libraries = sorted({rows[0]["footprint"].split(":")[0] for rows in parts.values()} - {"EXTERNAL", "REVIEW_ONLY"})
    (out / "fp-lib-table").write_text('(fp_lib_table (version 7)\n' + '\n'.join(f'(lib (name "{lib}") (type "KiCad") (uri "${{KICAD10_FOOTPRINT_DIR}}/{lib}.pretty") (options "") (descr "Standard KiCad footprint candidate"))' for lib in libraries) + '\n)\n')
    print(f"Rendered {len(parts)} source components in {len(page_specs)} typed sheets")

def verify(xml_path: Path) -> None:
    parts = source()
    wanted = {(ref, row["pin"]): row["net"] for ref, rows in parts.items() for row in rows if row["net"] != "NC"}
    actual = {}
    root = ET.parse(xml_path).getroot()
    for net in root.findall("./nets/net"):
        for node in net.findall("node"):
            actual[(node.attrib["ref"], node.attrib["pin"])] = net.attrib["name"]
    failures = [{"pin": key, "expected": name, "actual": actual.get(key)} for key, name in wanted.items() if actual.get(key) != name]
    # Unconnected pins may be emitted under KiCad unconnected-* names; reject connected extras.
    extras = [key for key, name in actual.items() if key not in wanted and not name.startswith("unconnected-")]
    if failures or extras:
        raise ValueError(json.dumps({"mismatch": failures[:20], "extra": extras[:20]}))
    refs = {x.attrib["ref"] for x in root.findall("./components/comp")}
    if refs != set(parts):
        raise ValueError("component reference set differs")
    print(f"PASS KiCad external netlist oracle: {len(refs)} components, {len(wanted)} connected pins")

def verify_atopile() -> None:
    # Reuse the repo's existing parser; never trust libsource's aliased identity.
    sys.path.insert(0, str(HERE.parents[4] / "scripts"))
    from gen_schematics import parse_netlist
    parts = source()
    netlist = parse_netlist(HERE / "generated/build/default.net")
    wanted = {(ref + "1", row["pin"]): row["net"].lower() for ref, rows in parts.items() for row in rows if row["net"] != "NC"}
    actual = {node: net.name for net in netlist.nets.values() for node in net.nodes}
    mismatches = [{"pin": key, "expected": val, "actual": actual.get(key)} for key, val in wanted.items() if actual.get(key) != val]
    if mismatches:
        raise ValueError(json.dumps(mismatches[:20]))
    nc_pins = {(ref + "1", row["pin"]) for ref, rows in parts.items() for row in rows if row["net"] == "NC"}
    for net in netlist.nets.values():
        if any(node in nc_pins for node in net.nodes) and len(net.nodes) != 1:
            raise ValueError(f"Atopile incorrectly connected NC pin on {net.name}")
    if set(actual) != set(wanted) | nc_pins:
        raise ValueError("Atopile pin set differs")
    if set(netlist.components) != {r + "1" for r in parts}:
        raise ValueError("Atopile component set differs")
    resolved = json.loads((HERE / "generated/resolved-components.json").read_text())
    identities = {p["attributes"]["designator_prefix"]: p["attributes"] for p in resolved["components"]}
    if set(identities) != set(parts):
        raise ValueError("Resolved component set differs")
    for ref, rows in parts.items():
        for field in ("mpn", "footprint"):
            if identities[ref][field] != rows[0][field]:
                raise ValueError(f"resolved {ref} {field} differs")
    print(f"PASS Atopile external compilation: {len(parts)} component identities, {len(wanted)} connected pins")

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "verify":
        verify(Path(sys.argv[2]))
    elif sys.argv[1:] == ["verify-atopile"]:
        verify_atopile()
    else:
        render()
