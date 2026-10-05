"""Thin KiCad adapter for the explicitly declared catch bleed card.

No shared placer implementation is added here. Circuit and dimensions live in
interface.json; pcbnew supplies board coordinates and KiCad verifies connectivity.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pcbnew as pcb

HERE = Path(__file__).resolve().parent
NATIVE = HERE / "native"


def uid(key: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "temper-round4-catch/" + key))


def vec(x: float, y: float) -> pcb.VECTOR2I:
    return pcb.VECTOR2I(pcb.FromMM(x), pcb.FromMM(y))


def main() -> None:
    c = json.loads((HERE / "interface.json").read_text())["bleed_card"]
    if (c["resistor_mpn"], c["pitch_mm"], c["pad_diameter_mm"], c["drill_mm"]) != (
        "VR37000001003JA100",
        15,
        2.4,
        1.0,
    ):
        raise ValueError("Footprint-critical part dimensions changed; review local drawing adapter")
    NATIVE.mkdir(exist_ok=True)
    lib = NATIVE / "Catch.pretty"
    lib.mkdir(exist_ok=True)
    footprint = """(footprint "VR37_P15" (version 20241229) (generator "temper_catch") (layer "F.Cu")
      (attr through_hole)
      (property "Reference" "R" (at 7.5 -3 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
      (property "Value" "100k" (at 7.5 3 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))
      (fp_rect (start 3 -2) (end 12 2) (stroke (width 0.15) (type default)) (fill none) (layer "F.SilkS"))
      (fp_rect (start 1.5 -2) (end 13.5 2) (stroke (width 0.1) (type default)) (fill none) (layer "F.Fab"))
      (fp_rect (start -1.5 -2.5) (end 16.5 2.5) (stroke (width 0.05) (type default)) (fill none) (layer "F.CrtYd"))
      (pad "1" thru_hole circle (at 0 0) (size 2.4 2.4) (drill 1) (layers "*.Cu" "*.Mask"))
      (pad "2" thru_hole circle (at 15 0) (size 2.4 2.4) (drill 1) (layers "*.Cu" "*.Mask")))"""
    # Courtyards may overlap at adjacent same-net pad ends; body rectangles do not.
    (lib / "VR37_P15.kicad_mod").write_text(footprint)
    (
        lib / "WirePad.kicad_mod"
    ).write_text("""(footprint "WirePad" (version 20241229) (generator "temper_catch") (layer "F.Cu") (attr through_hole)
      (property "Reference" "J" (at 0 2 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))
      (property "Value" "22AWG_SOLDER" (at 0 3 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))
      (pad "1" thru_hole circle (at 0 0) (size 2.8 2.8) (drill 1.3) (layers "*.Cu" "*.Mask")))""")
    (NATIVE / "fp-lib-table").write_text(
        '(fp_lib_table (version 7) (lib (name "Catch") (type "KiCad") (uri "${KIPRJMOD}/Catch.pretty") (options "") (descr "Drawing-derived local footprints")))\n'
    )
    board = pcb.BOARD()
    board.SetCopperLayerCount(2)
    nets = {}
    for name in ["CATCH_P_A", "HV_RET_A", "CATCH_P_B", "HV_RET_B"] + [
        f"B{b}_{n}" for b in (1, 2) for n in (1, 2, 3)
    ]:
        n = pcb.NETINFO_ITEM(board, name)
        board.Add(n)
        nets[name] = n
    parts = []
    for row, y in enumerate(c["row_y_mm"]):
        suffix = "A" if row == 0 else "B"
        names = (
            [f"CATCH_P_{suffix}"] + [f"B{row + 1}_{i}" for i in (1, 2, 3)] + [f"HV_RET_{suffix}"]
        )
        for col, x in enumerate(c["resistor_x_mm"]):
            ref = f"R{1 + 4 * row + col}"
            parts.append((ref, "VR37_P15", x, y, names[col : col + 2], "100k"))
    for ref, (x, y, net) in c["wire_terminals"].items():
        parts.append((ref, "WirePad", x, y, [net], "22AWG_SOLDER"))
    for ref, kind, x, y, pnets, value in parts:
        f = pcb.FootprintLoad(str(lib), kind)
        if f is None:
            raise ValueError(f"Missing local footprint {kind}")
        f.SetReference(ref)
        f.SetValue(value)
        f.SetFPID(pcb.LIB_ID("Catch", kind))
        f.SetPath(pcb.KIID_PATH(f"/{uid('root')}/{uid(ref)}"))
        board.Add(f)
        f.SetPosition(vec(x, y))
        if kind == "WirePad":
            f.Reference().SetLayer(pcb.F_SilkS)
            f.Reference().SetPosition(vec(x + 6 if ref in ("J1", "J3") else x - 6, y))
        for p in f.Pads():
            p.SetNet(nets[pnets[int(p.GetNumber()) - 1]])
    for x, y, diameter in c["npth_mm"]:
        f = pcb.FOOTPRINT(board)
        f.SetReference(f"H{int(x)}")
        f.SetAttributes(pcb.FP_BOARD_ONLY | pcb.FP_EXCLUDE_FROM_BOM | pcb.FP_EXCLUDE_FROM_POS_FILES)
        p = pcb.PAD(f)
        p.SetAttribute(pcb.PAD_ATTRIB_NPTH)
        p.SetShape(pcb.PAD_SHAPE_CIRCLE)
        p.SetSize(vec(diameter, diameter))
        p.SetDrillSize(vec(diameter, diameter))
        p.SetLayerSet(pcb.LSET.AllCuMask())
        f.Add(p)
        board.Add(f)
        f.SetPosition(vec(x, y))

    def track(a, b, net):
        t = pcb.PCB_TRACK(board)
        t.SetStart(vec(*a))
        t.SetEnd(vec(*b))
        t.SetWidth(pcb.FromMM(c["track_mm"]))
        t.SetLayer(pcb.F_Cu)
        t.SetNet(nets[net])
        board.Add(t)

    for row, y in enumerate(c["row_y_mm"]):
        for i in range(3):
            track(
                (c["resistor_x_mm"][i] + 15, y),
                (c["resistor_x_mm"][i + 1], y),
                f"B{row + 1}_{i + 1}",
            )
        wire_y = 3 if row == 0 else 31
        suffix = "A" if row == 0 else "B"
        track((4, wire_y), (4, y), f"CATCH_P_{suffix}")
        track(
            (c["resistor_x_mm"][-1] + 15, wire_y),
            (c["resistor_x_mm"][-1] + 15, y),
            f"HV_RET_{suffix}",
        )
    width, height, _ = c["size_mm"]
    for a, b in [
        ((0, 0), (width, 0)),
        ((width, 0), (width, height)),
        ((width, height), (0, height)),
        ((0, height), (0, 0)),
    ]:
        s = pcb.PCB_SHAPE(board)
        s.SetShape(pcb.SHAPE_T_SEGMENT)
        s.SetStart(vec(*a))
        s.SetEnd(vec(*b))
        s.SetLayer(pcb.Edge_Cuts)
        s.SetWidth(pcb.FromMM(0.05))
        board.Add(s)
    for text, x, y in (
        ("C+ A", 20, 3),
        ("RET A", 59, 3),
        ("C+ B", 20, 31),
        ("RET B", 59, 31),
        ("TCATCH BLEED R4 / DRAFT", 40, 17),
    ):
        label = pcb.PCB_TEXT(board)
        label.SetText(text)
        label.SetPosition(vec(x, y))
        label.SetLayer(pcb.F_SilkS)
        label.SetTextSize(vec(1, 1))
        label.SetTextThickness(pcb.FromMM(0.15))
        board.Add(label)
    pcb.SaveBoard(str(NATIVE / "catch-bleed.kicad_pcb"), board)
    (NATIVE / "catch-bleed.kicad_dru").write_text(
        '(version 1)\n(rule "Internal live-node engineering screen" (constraint clearance (min 8mm)))\n'
    )
    (NATIVE / "catch-bleed.kicad_pro").write_text(
        json.dumps(
            {
                "board": {
                    "design_settings": {
                        "rules": {
                            "min_clearance": 8,
                            "min_copper_edge_clearance": 1,
                            "min_hole_clearance": 0.25,
                        },
                        "rule_severities": {
                            "courtyards_overlap": "warning",
                            "lib_footprint_issues": "warning",
                            "footprint_type_mismatch": "warning",
                        },
                    }
                },
                "meta": {"filename": "catch-bleed.kicad_pro", "version": 1},
            },
            indent=2,
        )
        + "\n"
    )
    definitions, instances = [], []
    for idx, (ref, kind, _, _, pnets, value) in enumerate(parts):
        name = "Part_" + ref
        x, y = 38.1 + (idx % 4) * 63.5, 38.1 + (idx // 4) * 45.72
        definition = [
            f'(symbol "{name}" (pin_names (offset 0.508)) (in_bom yes) (on_board yes)',
            '(property "Reference" "R" (at 0 5 0) (effects (font (size 1.27 1.27))))',
            '(property "Value" "" (at 0 -5 0) (effects (font (size 1.27 1.27))))',
            f'(symbol "{name}_0_1" (rectangle (start -5 -2.54) (end 5 2.54) (stroke (width 0.254) (type default)) (fill (type background))))',
            f'(symbol "{name}_1_1"',
        ]
        pin_instances = []
        for p, net in enumerate(pnets, 1):
            dx, angle = (-7.62, 0) if p == 1 else (7.62, 180)
            definition.append(
                f'(pin passive line (at {dx} 0 {angle}) (length 2.62) (name "{p}" (effects (font (size 1 1)))) (number "{p}" (effects (font (size 1 1)))))'
            )
            instances.append(
                f'(global_label "{net}" (shape bidirectional) (at {x + dx} {y} {180 if p == 1 else 0}) (effects (font (size 1 1)) (justify left)) (uuid "{uid(ref + "/label/" + str(p))}"))'
            )
            pin_instances.append(f'(pin "{p}" (uuid "{uid(ref + "/pin/" + str(p))}"))')
        definition.append("))")
        definitions.append("\n".join(definition))
        instances.append(f'''(symbol (lib_id "Catch:{name}") (at {x} {y} 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) (uuid "{uid(ref)}")
          (property "Reference" "{ref}" (at {x} {y - 5} 0) (effects (font (size 1.27 1.27))))
          (property "Value" "{value}" (at {x} {y + 5} 0) (effects (font (size 1 1))))
          (property "Footprint" "Catch:{kind}" (at {x} {y} 0) (effects (font (size 1 1)) hide))
          {" ".join(pin_instances)} (instances (project "catch-bleed" (path "/{uid("root")}" (reference "{ref}") (unit 1)))))''')
    (NATIVE / "catch.kicad_sym").write_text(
        '(kicad_symbol_lib (version 20231120) (generator "temper_catch")\n'
        + "\n".join(definitions)
        + "\n)\n"
    )
    (NATIVE / "sym-lib-table").write_text(
        '(sym_lib_table (version 7) (lib (name "Catch") (type "KiCad") (uri "${KIPRJMOD}/catch.kicad_sym") (options "") (descr "Catch passive card")))\n'
    )
    embedded = [d.replace('(symbol "Part_', '(symbol "Catch:Part_', 1) for d in definitions]
    (NATIVE / "catch-bleed.kicad_sch").write_text(
        f'(kicad_sch (version 20250114) (generator "temper_catch") (uuid "{uid("root")}") (paper "A4")\n(lib_symbols '
        + "\n".join(embedded)
        + ")\n"
        + "\n".join(instances)
        + "\n)\n"
    )
    (HERE / "connectivity.json").write_text(
        json.dumps(
            {ref: {str(i + 1): n for i, n in enumerate(pnets)} for ref, _, _, _, pnets, _ in parts},
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
