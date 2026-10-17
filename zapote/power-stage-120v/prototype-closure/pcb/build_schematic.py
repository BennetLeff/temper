"""Render the frozen native19 source with explicit function/type pin metadata.

Uses the repository netlist reader; never derives connectivity from placement.
The checked pin-functions.json is the schematic electrical-role annotation.
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from pathlib import Path

from source_snapshot import verify_source_snapshot

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[1]
REPO = UNIT.parents[1]
sys.path.insert(0, str(REPO / "zapote" / "tools" / "generators"))
import gen_schematics as source  # noqa: E402 — existing repository adapter, loaded after explicit path.


def uid(value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "temper-native19-sch/" + value))


def q(value: str) -> str:
    return json.dumps(value)


def main() -> None:
    verify_source_snapshot(UNIT)
    out = UNIT / "native-19"
    netlist = source.parse_netlist(out / "frozen/default.net")
    metadata = json.loads((HERE / "pin-functions.json").read_text())
    roles = metadata["components"]
    if set(roles) != set(netlist.components):
        raise ValueError("pin annotations must cover exactly the source components")
    pin_net = {(r, p): n.name for n in netlist.nets.values() for r, p in n.nodes}
    definitions, instances = [], []
    type_counts = {}
    for index, (ref, c) in enumerate(netlist.components.items()):
        a = roles[ref]
        pins = a["pins"]
        if set(pins) != {p for r, p in pin_net if r == ref}:
            raise ValueError(f"annotation/source pins differ for {ref}")
        name = f"Part_{ref}"
        x, y = 63.5 + (index % 10) * 114.3, 50.8 + (index // 10) * 50.8
        split = (len(pins) + 1) // 2
        height = max(5.08, (split - 1) * 2.54 + 2.54)
        definition = [
            f'(symbol "{name}" (pin_names (offset 0.508)) (in_bom yes) (on_board yes)',
            f'(property "Reference" "{ref.rstrip("0123456789")}" (at 0 {height + 2.54:.4f} 0) (effects (font (size 1.27 1.27))))',
            f'(property "Value" {q(a["mpn"])} (at 0 {-height - 2.54:.4f} 0) (effects (font (size 1.27 1.27))))',
            '(property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))',
            '(property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))',
            f'(symbol "{name}_0_1" (rectangle (start -12.7 {-height:.4f}) (end 12.7 {height:.4f}) (stroke (width 0.254) (type default)) (fill (type background))))',
            f'(symbol "{name}_1_1"',
        ]
        pin_instances = []
        for i, (number, annotation) in enumerate(pins.items()):
            left = i < split
            count = split if left else len(pins) - split
            local_index = i if left else i - split
            px = -15.24 if left else 15.24
            py = (count - 1) * 2.54 - local_index * 5.08
            angle = 0 if left else 180
            kind, function = annotation["type"], annotation["function"]
            type_counts[kind] = type_counts.get(kind, 0) + 1
            definition.append(
                f"(pin {kind} line (at {px:.4f} {py:.4f} {angle}) (length 2.54) (name {q(function)} (effects (font (size 1.016 1.016)))) (number {q(number)} (effects (font (size 1.016 1.016)))))"
            )
            # Schematic Y increases downward; library symbol Y increases upward.
            nx, ny = x + px, y - py
            label_angle = 180 if left else 0
            instances.append(
                f'(global_label {q(pin_net[(ref, number)])} (shape bidirectional) (at {nx:.4f} {ny:.4f} {label_angle}) (effects (font (size 1.016 1.016)) (justify left)) (uuid "{uid(ref + "/label/" + number)}"))'
            )
            pin_instances.append(f'(pin {q(number)} (uuid "{uid(ref + "/pin/" + number)}"))')
        definition.append("))")
        definitions.append("\n".join(definition))
        instances.append(f'''(symbol (lib_id "Native19:{name}") (at {x:.4f} {y:.4f} 0) (unit 1)
 (in_bom yes) (on_board yes) (dnp no) (uuid "{c.tstamp}")
 (property "Reference" {q(ref)} (at {x:.4f} {y - height - 3.81:.4f} 0) (effects (font (size 1.27 1.27))))
 (property "Value" {q(a["mpn"])} (at {x:.4f} {y + height + 3.81:.4f} 0) (effects (font (size 1.016 1.016))))
 (property "Footprint" {q(c.footprint)} (at {x:.4f} {y:.4f} 0) (effects (font (size 1.27 1.27)) hide))
 {" ".join(pin_instances)}
 (instances (project "section" (path "/{uid("root")}" (reference {q(ref)}) (unit 1)))))''')
    flag_definition = '(symbol "SupplyAssertion" (pin_names (offset 0)) (in_bom no) (on_board no) (property "Reference" "#FLG" (at 0 2.54 0) (effects (font (size 1.27 1.27)) hide)) (property "Value" "PHYSICAL_SUPPLY_ASSERTION" (at 0 -2.54 0) (effects (font (size 1.016 1.016)))) (symbol "SupplyAssertion_0_1" (polyline (pts (xy -1.27 1.27) (xy 0 2.54) (xy 1.27 1.27) (xy 0 0) (xy -1.27 1.27)) (stroke (width 0.254) (type default)) (fill (type none)))) (symbol "SupplyAssertion_1_1" (pin power_out line (at 0 0 90) (length 0) (name "SUPPLY_ASSERTED" (effects (font (size 1.016 1.016)))) (number "1" (effects (font (size 1.016 1.016)))))))'
    for index, assertion in enumerate(metadata["supply_assertions"]):
        for ref, pin, net in assertion["requires"]:
            if pin_net[(ref, pin)] != net:
                raise ValueError(f"invalid bootstrap supply assertion: {ref}.{pin} expected {net}")
        net = assertion["net"]
        x, y = 63.5 + index * 254, 787.4
        ref = f"#FLG0{index + 1}"
        instances.append(
            f'(symbol (lib_id "Native19:SupplyAssertion") (at {x} {y} 0) (unit 1) (in_bom no) (on_board no) (dnp no) (uuid "{uid(ref)}") (property "Reference" "{ref}" (at {x} {y} 0) (effects (font (size 1.27 1.27)) hide)) (property "Value" "PHYSICAL_SUPPLY_ASSERTION" (at {x} {y + 3.81} 0) (effects (font (size 1.016 1.016)))) (pin "1" (uuid "{uid(ref + "pin")}")) (instances (project "section" (path "/{uid("root")}" (reference "{ref}") (unit 1)))))'
        )
        instances.append(
            f'(global_label "{net}" (shape input) (at {x} {y} 0) (effects (font (size 1.016 1.016)) (justify left)) (uuid "{uid(ref + "label")}"))'
        )
    definitions.append(flag_definition)
    library = (
        '(kicad_symbol_lib (version 20231120) (generator "temper_native19")\n'
        + "\n".join(definitions)
        + "\n)\n"
    )
    (out / "native19.kicad_sym").write_text(library)
    (out / "sym-lib-table").write_text(
        '(sym_lib_table (version 7) (lib (name "Native19") (type "KiCad") (uri "${KIPRJMOD}/native19.kicad_sym") (options "") (descr "Native19 source-specific typed symbols")))\n'
    )
    embedded = []
    for ref, definition in zip(netlist.components, definitions[:-1], strict=True):
        embedded.append(
            definition.replace(f'(symbol "Part_{ref}"', f'(symbol "Native19:Part_{ref}"', 1)
        )
    embedded.append(
        flag_definition.replace(
            '(symbol "SupplyAssertion"', '(symbol "Native19:SupplyAssertion"', 1
        )
    )
    sheet = f'''(kicad_sch (version 20231120) (generator "temper_native19") (uuid "{uid("root")}") (paper "A0")
 (title_block (title "Temper 120V power board — native19 HOT5 candidate") (date "2026-10-04") (rev "19-candidate") (company "Temper") (comment 1 "Typed source-derived schematic; prototype candidate, not release"))
 (lib_symbols {" ".join(embedded)})
 {" ".join(instances)}
 (sheet_instances (path "/" (page "1"))))\n'''
    all_uuids = re.findall(r'(?:uuid) "([^" ]+)"', sheet)
    if len(all_uuids) != len(set(all_uuids)):
        raise ValueError("duplicate schematic object UUID")
    (out / "section.kicad_sch").write_text(sheet)
    (out / "verification/schematic-build.json").write_text(
        json.dumps(
            {
                "components": len(roles),
                "pins": len(pin_net),
                "pin_type_counts": type_counts,
                "connectivity_authority": "frozen/default.net",
                "annotation_authority": "../prototype-closure/pcb/pin-functions.json",
                "physical": "NOT_RUN",
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
