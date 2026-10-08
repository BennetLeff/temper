"""Author the functional drawing; source netlist remains the wiring authority."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "scripts"), str(REPO / "zapote/current-sense/tools")]
import gen_schematics as g  # noqa: E402 - shared native adapter path is set above.
from close_current_sense_schematic_erc import library_symbol  # noqa: E402

# Explicit agent-authored schematic poses; no layout/search policy here.
POSES = {
    "J1": (54.61, 54.61),
    "J2": (54.61, 149.86),
    "U1": (250.19, 54.61),
    "U2": (250.19, 149.86),
    "U3": (350.52, 54.61),
    "U4": (350.52, 149.86),
    "U5": (54.61, 219.71),
    "U6": (149.86, 219.71),
    "R1": (149.86, 25.4),
    "R2": (149.86, 35.56),
    "R3": (149.86, 44.45),
    "R4": (149.86, 54.61),
    "R5": (149.86, 64.77),
    "R6": (149.86, 74.93),
    "R7": (149.86, 85.09),
    "R8": (149.86, 124.46000000000001),
    "R9": (149.86, 139.7),
    "R10": (149.86, 154.94),
    "R11": (149.86, 170.18),
    "C1": (234.95000000000002, 214.63),
    "C2": (284.48, 214.63),
    "C3": (335.28000000000003, 214.63),
    "C4": (234.95000000000002, 240.03),
    "C5": (284.48, 240.03),
    "C6": (335.28000000000003, 240.03),
}


def passive(part, capacitor):
    sid = g._sanitize_name(part.part_name)
    body = (
        "(polyline (pts (xy -1 -2.54) (xy -1 2.54)) (stroke (width 0.254) (type default)) (fill (type none)))"
        "(polyline (pts (xy 1 -2.54) (xy 1 2.54)) (stroke (width 0.254) (type default)) (fill (type none)))"
        if capacitor
        else "(rectangle (start -2.54 -1.016) (end 2.54 1.016) (stroke (width 0.254) (type default)) (fill (type none)))"
    )
    length = 4.08 if capacitor else 2.54
    pins = "".join(
        f'(pin passive line (at {x} 0 {a}) (length {length}) (name "~" (effects (font (size 1 1)))) (number "{n}" (effects (font (size 1 1)))))'
        for n, x, a in [("1", -5.08, 0), ("2", 5.08, 180)]
    )
    return f'(symbol "{sid}" (pin_names (offset 0) hide) (pin_numbers hide) (in_bom yes) (on_board yes) (property "Reference" "R" (at 0 -2.54 0) (effects (font (size 1.27 1.27)))) (property "Value" "{part.part_name}" (at 0 2.54 0) (effects (font (size 1.27 1.27)))) (symbol "{sid}_0_1" {body}) (symbol "{sid}_1_1" {pins}))'


def main():
    unit = REPO / "zapote/interlock"
    src = unit / "source-build-02"
    out = unit / "candidate"
    net = g.parse_netlist(src / "build/default.net")
    g.apply_bom_values(net, g.load_bom_values(src / "build/default.csv"))
    components = sorted(net.components.values(), key=lambda c: c.ref)
    assert set(POSES) == {c.ref for c in components}
    source = json.loads((out / "source-manifest.json").read_text())
    values = {c["reference"]: c["value"] for c in source["components"]}
    symbols = {}
    for c in components:
        p = net.libparts[c.part_name]
        if c.ref[0] in "RC":
            symbol = passive(p, c.ref.startswith("C"))
        else:
            symbol = library_symbol(g, p)
            if c.ref in ("U1", "U2"):
                names = {
                    "1": "A1",
                    "2": "Y1",
                    "3": "A2",
                    "4": "Y2",
                    "5": "A3",
                    "6": "Y3",
                    "7": "GND",
                    "8": "Y4",
                    "9": "A4",
                    "10": "Y5",
                    "11": "A5",
                    "12": "Y6",
                    "13": "A6",
                    "14": "VCC",
                }
            elif c.ref == "U3":
                names = {
                    "1": "A",
                    "2": "B",
                    "3": "C",
                    "4": "D",
                    "5": "E",
                    "6": "F",
                    "7": "GND",
                    "8": "Y",
                    "9": "NC",
                    "10": "NC",
                    "11": "G",
                    "12": "H",
                    "13": "NC",
                    "14": "VCC",
                }
            elif c.ref == "U4":
                names = {
                    "1": "CLK",
                    "2": "D",
                    "3": "Q_BAR",
                    "4": "GND",
                    "5": "Q",
                    "6": "CLR_N",
                    "7": "PRE_N",
                    "8": "VCC",
                }
            elif c.ref == "U5":
                names = {"1": "RESET_N", "2": "GND", "3": "MR_N", "4": "WDI", "5": "VDD"}
            elif c.ref == "U6":
                names = {"1": "A", "2": "B", "3": "GND", "4": "Y", "5": "VCC"}
            else:
                names = {}
            for pin, name in names.items():
                symbol = symbol.replace(f'(name "{pin}"', f'(name "{name}"')
        original_id = g._sanitize_name(c.part_name)
        new_id = c.ref + "_" + original_id
        symbols[c.ref] = symbol.replace(original_id, new_id)
    d = [
        g._schematic_header("Standalone Safety Interlock / Rev A", g.ROOT_UUID)
        .replace("2026-07-15", "2026-09-12")
        .replace(
            "edit elec/src/*.ato and run make schematics",
            "Source: interlock_unit.ato; replay: tools/draw_schematic.py",
        ),
        "(lib_symbols",
    ]
    for ref, symbol in sorted(symbols.items()):
        c = next(c for c in components if c.ref == ref)
        sid = ref + "_" + g._sanitize_name(c.part_name)
        d.append(symbol.replace(f'(symbol "{sid}"', f'(symbol "InterlockUnit:{sid}"', 1))
    d.append(")")

    def note(text, x, y, size=1.27):
        return f'(text "{text}" (at {x} {y} 0) (effects (font (size {size} {size})) (justify left)) (uuid "{g._uuid_from_seed(text)}"))'

    d += [
        note("FAULT INPUTS / pulled high; any asserted fault removes PERMIT", 30.48, 15.24, 1.8),
        note("WATCHDOG + LATCH / qualified RESET_N edge required to restart", 30.48, 105, 1.8),
        note(
            "J1: GND + seven active-high fault inputs.  J2: +3V3, GND, WDI, RESET_N, SENSOR_LIVE, PERMIT, LATCHED_FAULT, WDT_RESET_N.",
            30.48,
            265,
        ),
        note(
            "U4 Q pin 5 = PERMIT; Q-bar pin 3 = LATCHED_FAULT. U5 RESET_N pin 1, GND pin 2. NC pads are explicitly marked.",
            30.48,
            274,
        ),
    ]
    pn = {(r, p): n.name for n in net.nets.values() for r, p in n.nodes}
    singles = {(r, p) for n in net.nets.values() if len(n.nodes) == 1 for r, p in n.nodes}
    opens = []
    for c in components:
        x, y = POSES[c.ref]
        p = net.libparts[c.part_name]
        sid = "InterlockUnit:" + c.ref + "_" + g._sanitize_name(c.part_name)
        instance = g._symbol_instance(
            c.ref,
            sid,
            x,
            y,
            c.footprint,
            c.part_name,
            g._uuid_from_seed(f"flatinst:{c.tstamp}"),
            libpart=p,
            display_value=c.display_value,
        )
        # Keep native Value equal to the exact BOM MPN for schematic/PCB parity.
        instance = instance.replace(
            f"(at {x:.2f} {y + 2.54:.2f} 0) (effects (font (size 1.27 1.27))))",
            f"(at {x:.2f} {y + 2.54:.2f} 0) (effects (font (size 1.27 1.27)) hide))",
        )
        if c.ref[0] not in "RC":
            instance = instance.replace(
                f"(at {x:.2f} {y - 2.54:.2f} 0)", f"(at {x:.2f} {y - 12.7:.2f} 0)"
            )
        if c.ref.startswith("C"):
            instance = instance.replace(
                f"(at {x:.2f} {y - 2.54:.2f} 0)", f"(at {x:.2f} {y - 4.445:.2f} 0)"
            )
        d.append(instance)
        label = values[c.ref].replace("+/-", "±") if c.ref[0] in "RC" else c.display_value
        d.append(note(label, x - 5.08, y + (5.08 if c.ref[0] in "RC" else 12.7), 1.016))
        for num, _ in p.pins:
            px, py = (
                (x + (-5.08 if num == "1" else 5.08), y)
                if c.ref[0] in "RC"
                else g._pin_absolute_position(p, num, x, y)
            )
            n = pn.get((c.ref, num))
            if n:
                label = g._global_label(n, px, py, g._uuid_from_seed(f"label:{c.ref}:{num}:{n}"))
                if px < x:
                    label = label.replace(
                        f"(at {px:.2f} {py:.2f} 0)", f"(at {px:.2f} {py:.2f} 180)"
                    ).replace("(justify left bottom)", "(justify right bottom)")
                d.append(label)
            if n is None or (c.ref, num) in singles:
                d.append(g._no_connect(px, py, g._uuid_from_seed(f"nc:{c.ref}:{num}")))
                opens.append([c.ref, num, n])
    d.append(")")
    artifacts = {
        "section.kicad_sch": "\n".join(d) + "\n",
        "InterlockUnit.kicad_sym": '(kicad_symbol_lib (version 20231120) (generator "zapote_interlock")\n'
        + "\n".join(symbols.values())
        + "\n)\n",
        "sym-lib-table": '(sym_lib_table (version 7) (lib (name "InterlockUnit")(type "KiCad")(uri "${KIPRJMOD}/InterlockUnit.kicad_sym")(options "")(descr "Source-derived symbols")))\n',
    }
    for name, text in artifacts.items():
        (out / name).write_text(text)

    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    rec = {
        "status": "emitted-native-verification-required",
        "source_netlist_sha256": sha(src / "build/default.net"),
        "helper_sha256": sha(Path(__file__)),
        "outputs": {name: sha(out / name) for name in artifacts},
        "intentional_open_pins": opens,
        "component_count": len(components),
        "native_erc": "NOT RUN",
        "native_netlist_equality": "NOT RUN",
        "pcb_touched": False,
    }
    (unit / "evidence/schematic-closure.json").write_text(json.dumps(rec, indent=2) + "\n")


if __name__ == "__main__":
    main()
