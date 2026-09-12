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
    "J1": (45.72, 50.8),
    "J2": (45.72, 142.24),
    "J3": (340.36, 228.6),
    "R1": (96.52, 50.8),
    "C1": (96.52, 76.2),
    "R2": (147.32, 35.56),
    "R3": (147.32, 81.28),
    "R4": (198.12, 35.56),
    "U1": (248.92, 60.96),
    "C2": (299.72, 60.96),
    "R5": (96.52, 142.24),
    "C3": (96.52, 167.64),
    "R6": (147.32, 127),
    "R7": (147.32, 172.72),
    "R8": (198.12, 127),
    "U2": (248.92, 152.4),
    "C4": (299.72, 152.4),
    "U3": (248.92, 91.44),
    "U4": (248.92, 182.88),
    "U5": (340.36, 60.96),
    "U6": (340.36, 152.4),
    "C5": (299.72, 91.44),
    "C6": (299.72, 182.88),
    "C7": (381.0, 60.96),
    "C8": (381.0, 152.4),
    "R9": (96.52, 213.36),
    "R10": (147.32, 213.36),
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
    unit = REPO / "zapote/thermal-sense"
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
            names = (
                {"1": "OUT", "2": "GND", "3": "IN+", "4": "IN-", "5": "VCC"}
                if c.ref in ("U1", "U2", "U3", "U4")
                else {"1": "A", "2": "B", "3": "GND", "4": "Y", "5": "VCC"}
                if c.ref in ("U5", "U6")
                else {}
            )
            for pin, name in names.items():
                symbol = symbol.replace(f'(name "{pin}"', f'(name "{name}"')
        original_id = g._sanitize_name(c.part_name)
        new_id = c.ref + "_" + original_id
        symbols[c.ref] = symbol.replace(original_id, new_id)
    d = [
        g._schematic_header("Heatsink and Coil Thermal Detectors / Rev B", g.ROOT_UUID)
        .replace("2026-07-15", "2026-09-11")
        .replace(
            "edit elec/src/*.ato and run make schematics",
            "Source: thermal_sense_unit.ato; replay: tools/draw_schematic.py",
        ),
        "(lib_symbols",
    ]
    for ref, symbol in sorted(symbols.items()):
        c = next(c for c in components if c.ref == ref)
        sid = ref + "_" + g._sanitize_name(c.part_name)
        d.append(symbol.replace(f'(symbol "{sid}"', f'(symbol "ThermalSenseUnit:{sid}"', 1))
    d.append(")")

    def note(text, x, y, size=1.27):
        return f'(text "{text}" (at {x} {y} 0) (effects (font (size {size} {size})) (justify left)) (uuid "{g._uuid_from_seed(text)}"))'

    d += [
        note("HEATSINK / nominal 85 C trip, 70 C release", 30.48, 15.24, 1.8),
        note("COIL / nominal 120 C trip, 100 C release", 30.48, 111.76, 1.8),
        note(
            "External NTCs connect at J1/J2; 100k R25, Vishay NTCALUG01A104GA.",
            30.48,
            243.84,
        ),
        note(
            "Hot OR open sensor asserts FAULT. Valid sensor >=0 C. Shutdown latch is external.",
            30.48,
            254,
        ),
    ]
    pn = {(r, p): n.name for n in net.nets.values() for r, p in n.nodes}
    singles = {(r, p) for n in net.nets.values() if len(n.nodes) == 1 for r, p in n.nodes}
    opens = []
    for c in components:
        x, y = POSES[c.ref]
        p = net.libparts[c.part_name]
        sid = "ThermalSenseUnit:" + c.ref + "_" + g._sanitize_name(c.part_name)
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
        "ThermalSenseUnit.kicad_sym": '(kicad_symbol_lib (version 20231120) (generator "zapote_thermal_sense")\n'
        + "\n".join(symbols.values())
        + "\n)\n",
        "sym-lib-table": '(sym_lib_table (version 7) (lib (name "ThermalSenseUnit")(type "KiCad")(uri "${KIPRJMOD}/ThermalSenseUnit.kicad_sym")(options "")(descr "Source-derived symbols")))\n',
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
