#!/usr/bin/env python3
"""Generate pcb/controller.kicad_sch from the frozen netlist (schematic-parity reference for DRC).

    python3 layout/build_schematic.py

The design source is the atopile code in elec/src; this sheet is a mechanical rendering of
frozen/default.net so KiCad's DRC `--schematic-parity` can compare the board with the same
connectivity: one box symbol per component, one pin per connected pad, a global label carrying
the net name on every pin. Footprint and value fields equal what layout/build_board.py puts on
the board (resolved footprint, MPN). Pin electrical types are all "passive": this sheet is not
an ERC artefact. Same pattern as power-stage-120v/prototype-closure/pcb/build_schematic21.py.
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parent
PCB = UNIT / "pcb"


def uid(v: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "temper-controller-sch/" + v))


def q(v: str) -> str:
    return json.dumps(v)


def pin_key(p: str):
    return (0, int(p)) if p.isdigit() else (1, p)


def main() -> None:
    text = (UNIT / "frozen/default.net").read_text()
    comps = {}
    for m in re.finditer(r'\(comp \(ref "([^"]+)"\).*?\(sheetpath \(names "[^"]*::([^"]+)"\) \(tstamps "([^"]+)"\)',
                         text, re.S):
        comps[m.group(1)] = {"path": m.group(2), "tstamp": m.group(3)}
    attrs = {c["address"].split("::", 1)[1]: c["attributes"]
             for c in json.loads((UNIT / "frozen/resolved-components.json").read_text())["components"]}
    _, _, nets_text = text.partition("(nets")
    pin_net = {}
    for m in re.finditer(r'\(net \(code "?\d+"?\) \(name "([^"]*)"\)(.*?)(?=\n\s*\(net \(code|\Z)', nets_text, re.S):
        for r, p in re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', m.group(2)):
            pin_net[(r, p)] = m.group(1)
    # Datasheet text as the board carries it (footprint library field), so parity compares equal
    datasheet = {}
    board = PCB / "controller.kicad_pcb"
    if board.exists():
        for block in re.split(r"\n\t\(footprint ", board.read_text())[1:]:
            r_ = re.search(r'\(property "Reference" "([^"]+)"', block)
            ds = re.search(r'\(property "Datasheet" "([^"]*)"', block)
            if r_:
                datasheet[r_.group(1)] = ds.group(1) if ds else ""
    root = uid("root")
    defs, inst = [], []
    order = sorted(comps, key=lambda r: (r.rstrip("0123456789"), int(r[len(r.rstrip("0123456789")):])))
    for i, ref in enumerate(order):
        c = comps[ref]
        a = attrs[c["path"]]
        pins = sorted({p for (r, p) in pin_net if r == ref}, key=pin_key)
        name = f"Part_{ref}"
        x, y = 63.5 + (i % 16) * 101.6, 50.8 + (i // 16) * 63.5
        split = (len(pins) + 1) // 2
        h = max(5.08, (split - 1) * 2.54 + 2.54)
        d = [f'(symbol "Ctl:{name}" (pin_names (offset 0.508)) (in_bom yes) (on_board yes)',
             f'(property "Reference" "{ref.rstrip("0123456789")}" (at 0 {h + 2.54:.2f} 0) (effects (font (size 1.27 1.27))))',
             f'(property "Value" {q(a["mpn"])} (at 0 {-h - 2.54:.2f} 0) (effects (font (size 1.27 1.27))))',
             '(property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))',
             '(property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))',
             f'(symbol "{name}_0_1" (rectangle (start -10.16 {-h:.2f}) (end 10.16 {h:.2f}) (stroke (width 0.254) (type default)) (fill (type background))))',
             f'(symbol "{name}_1_1"']
        pin_inst = []
        for k, num in enumerate(pins):
            left = k < split
            cnt = split if left else len(pins) - split
            li = k if left else k - split
            px = -12.7 if left else 12.7
            py = (cnt - 1) * 2.54 - li * 5.08
            d.append(f'(pin passive line (at {px:.2f} {py:.2f} {0 if left else 180}) (length 2.54) '
                     f'(name {q(num)} (effects (font (size 1.016 1.016)))) (number {q(num)} (effects (font (size 1.016 1.016)))))')
            inst.append(f'(global_label {q(pin_net[(ref, num)])} (shape bidirectional) (at {x + px:.2f} {y - py:.2f} '
                        f'{180 if left else 0}) (effects (font (size 1.016 1.016)) (justify {"right" if left else "left"})) '
                        f'(uuid "{uid(ref + "/label/" + num)}"))')
            pin_inst.append(f'(pin {q(num)} (uuid "{uid(ref + "/pin/" + num)}"))')
        d.append("))")
        defs.append("\n".join(d))
        inst.append(f'''(symbol (lib_id "Ctl:{name}") (at {x:.2f} {y:.2f} 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) (uuid "{c["tstamp"]}")
 (property "Reference" {q(ref)} (at {x:.2f} {y - h - 3.81:.2f} 0) (effects (font (size 1.27 1.27))))
 (property "Value" {q(a["mpn"])} (at {x:.2f} {y + h + 3.81:.2f} 0) (effects (font (size 1.016 1.016))))
 (property "Footprint" {q(a["footprint"])} (at {x:.2f} {y:.2f} 0) (effects (font (size 1.27 1.27)) hide))
 (property "Datasheet" {q(datasheet.get(ref, ""))} (at {x:.2f} {y:.2f} 0) (effects (font (size 1.27 1.27)) hide))
 (property "MPN" {q(a["mpn"])} (at {x:.2f} {y:.2f} 0) (effects (font (size 1.27 1.27)) hide))
 (property "SourceInstance" {q(c["path"])} (at {x:.2f} {y:.2f} 0) (effects (font (size 1.27 1.27)) hide))
 {" ".join(pin_inst)}
 (instances (project "controller" (path "/{root}" (reference {q(ref)}) (unit 1)))))''')
    sheet = f'''(kicad_sch (version 20231120) (generator "temper_controller") (uuid "{root}") (paper "User" 1700 1000)
 (title_block (title "Temper SELV controller - netlist rendering for layout parity") (rev "L1") (company "Temper")
  (comment 1 "Generated by layout/build_schematic.py from frozen/default.net; the design source is elec/src (atopile)"))
 (lib_symbols {" ".join(defs)})
 {" ".join(inst)}
 (sheet_instances (path "/" (page "1"))))
'''
    ids = re.findall(r'uuid "([^"]+)"', sheet)
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate uuid")
    (PCB / "controller.kicad_sch").write_text(sheet)
    print(f"{len(comps)} symbols, {len(pin_net)} pins")


if __name__ == "__main__":
    main()
