#!/usr/bin/env python3
"""Bench heatsink r1: insulation sanity check per insulator, and creepage / clearance of the mount geometry.

    python3 -I scripts/bench_insulation.py       (from bench-sink-r1/)  -> results/insulation.json, results/insulation.md

The bench sink is bonded to PE (README section 3). Every HOT part near it must therefore be insulated from it, and the
bench floor is BASIC insulation (isolation transformer + verified PE bond as the second measure): creepage 4.0 mm,
clearance 1.3 mm (M11 RECOMMENDATION section 2, 'Basic, for reference'; bench_params.py).

Stress bound (peak, tab or HOT conductor to the PE sink):
  * tab to the HOT return: the worst die VDS on record, 435.7 V (OPEN-ITEMS S3, s51 matrices, S2 fault case at 280 V);
    it bounds every switching overshoot at the bench's lower 186.7 V bus;
  * HOT return to PE on an isolation transformer: up to the line peak (132 V x sqrt 2 = 186.7 V) when one line
    terminal is pulled to earth (a probe, a fault);
  -> 622.4 V peak bounds the 132 V AC steps. Step 3 (300 V isolated DC, gates disconnected) adds no switching and its
     floating supply's offset to PE is bounded by the same 300 V: 600 V DC < 622.4 V.
Geometry corners: sink lower edge 4.5 +/- 0.3 mm, strip overhang 2.5 +/- 0.3 mm, strip ends/top +/- 0.5 mm (hand),
device x +/- 0.15 mm, TO-247 outline min/max ([IPW] p.12). JLC-soldered devices (owner 2026-10-18): the sink face sits
anywhere in bench_mech.sink_face_range() (it settles on the most-proud tab), per-device shims sit under the strip from
SHIM_FET_Z0 up, an unseated body may float up to FET_FLOAT_MAX, and a device may carry the 1.6 / 0.8 mm FR-4 pad or none.
"""
from __future__ import annotations

import itertools
import json
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
sys.path.insert(0, str(HERE))
import bench_params as P  # noqa: E402
import bench_mech as M  # noqa: E402

EPS0 = 8.854e-12
V_LINE_PK = P.V_LINE_MAX_RMS * math.sqrt(2)
V_STRESS_PK = P.V_DIE_WORST + V_LINE_PK
V_STEP3 = 2 * P.V_STEP3_DC


def stresses():
    pad = P.PADS[P.PAD_CHOICE]
    rows = []

    def row(name, rating_vac, thick_mm, stress_pk, note, hipot_basic=True, freq_hf=False):
        r = dict(insulator=name, rating_Vac=rating_vac, rating_pk=rating_vac * math.sqrt(2), stress_pk=stress_pk,
                 ratio_pk=rating_vac * math.sqrt(2) / stress_pk if stress_pk else None,
                 field_kV_per_mm=(stress_pk / thick_mm / 1000) if thick_mm and stress_pk else None,
                 rating_over_basic_hipot=rating_vac / P.HIPOT_BASIC_VAC if hipot_basic else None, note=note)
        rows.append(r)
    row(f"{P.PAD_CHOICE} strip, FET tab -> PE sink", pad["bd_vac"], pad["t"], V_STRESS_PK,
        "low-side tabs (Q3 sw_a, Q6 sw_b) carry the 33-60 kHz swing: field shown for the HF note")
    row(f"{P.PAD_CHOICE} strip behind BR1 (in series with the GBJ case)", pad["bd_vac"] + P.BR1_CASE_VRMS, pad["t"],
        V_LINE_PK + 0.0, "BR1 nodes sit within the line peak of the HOT return; case rated 2500 Vrms on its own (basic)")
    row("GBJ2510 case alone (screw hole through the strip)", P.BR1_CASE_VRMS, None, V_LINE_PK,
        "at the M3 screw the strip is pierced; the case is basic by its datasheet rating, as M11 credits it")
    row("3M 5413 polyimide tape x 2 layers on the DF110S TCO (live case, TCO_L)", 2 * 7000, 2 * 0.069, V_LINE_PK,
        "TCO_L is line-side mains feeding PS2; no switching node. 7000 V per layer (3M TDS, ASTM D149)")
    row("NTCALUG01A lug -> leads (SELV; sink at PE = SELV return through the PE link)", P.NTC["dw_vac"], None, 0.0,
        "no HOT stress by design; with the PE link open the SELV return floats and the stress stays at leakage level",
        hipot_basic=False)
    row("FR-4 pressure pad 1.6 mm (spring -> package front, supplementary)", 0, 1.6, 0.0,
        "not a HOT barrier: the package front carries no HOT metal; credited for nothing", hipot_basic=False)
    # tab -> PE capacitance (CM current into the bench PE)
    c = [EPS0 * pad["er"] * a * 1e-6 / (pad["t"] * 1e-3) * 1e12 for a in P.TAB_AREA]
    return rows, c


def creepage_clearance():
    t = P.PADS[P.PAD_CHOICE]["t"]
    y_face = P.Y_TAB - t
    T = P.TO247
    z_metal_bot_min = T["L1"][0] + T["D"][0] - T["D2"][1] - T["D1"][1]      # 5.55
    z_metal_top_max = T["L1"][1] + T["D"][1] - T["D2"][0]                    # 25.49
    lead_back_off = T["A1"][0] - T["c"][1] / 2                               # tab plane -> nearest lead surface
    out = []
    zs_set = (P.Z_SINK_BOTTOM - P.Z_SINK_TOL, P.Z_SINK_BOTTOM, P.Z_SINK_BOTTOM + P.Z_SINK_TOL)
    ov_set = (P.STRIP_OVERHANG - P.STRIP_OVERHANG_TOL, P.STRIP_OVERHANG, P.STRIP_OVERHANG + P.STRIP_OVERHANG_TOL)

    def add(path, kind, value, floor, corner, how):
        out.append(dict(path=path, kind=kind, mm=round(value, 3), floor=floor, ok=value >= floor - 1e-9, corner=corner, how=how))

    worst = {}
    for zs, ov in itertools.product(zs_set, ov_set):
        zb = zs - ov
        corner = f"z_sink {zs}, strip bottom {zb:.1f}"
        # C1 tab-metal bottom edge -> round the strip bottom -> sink lower edge
        v = (z_metal_bot_min - zb) + t + (zs - zb)
        worst.setdefault("C1", []).append((v, corner))
        # C2 sink lower edge -> strip -> package bottom -> nearest lead
        v = (zs - zb) + t + abs(T["L1"][0] - zb) + lead_back_off
        worst.setdefault("C2", []).append((v, corner))
        # C3 sink lower edge -> strip outer face -> board surface over the edge pours. A gap under the strip narrower than
        # X is bridged (the path then reaches the board); a wider gap leaves no surface path from strip to board.
        gap = zb
        v = (zs - zb) + gap if gap < P.X_GROOVE_PD3 else float("inf")
        worst.setdefault("C3", []).append((v, corner + f", gap {gap:.1f}"))
        # K1 clearance sink lower edge -> F.Cu pour directly below (2 oz = 0.07 mm)
        worst.setdefault("K1", []).append((zs - 0.07, corner))
        # K2 clearance sink lower edge -> nearest lead, round the strip bottom (the strip blocks the straight line)
        worst.setdefault("K2", []).append(((zs - zb) + t + lead_back_off, corner))
        # K3 clearance sink lower edge -> FET pad copper on the board top (pad edge y 1.965)
        for yf in M.sink_face_range():
            worst.setdefault("K3", []).append((math.hypot(max(P.Y_PAD_EDGE_FET - yf, 0.0), zs - 0.07), corner + f", face y {yf:.2f}"))
        # S1 tab-metal bottom edge -> strip bottom -> up the strip back -> shim lower edge (shimmed device)
        worst.setdefault("S1", []).append(((z_metal_bot_min - zb) + t + (P.SHIM_FET_Z0 - zb), corner))
    labels = {"C1": ("tab-metal bottom edge -> strip bottom -> sink lower edge", "creepage"),
              "C2": ("sink lower edge -> strip -> package bottom face -> lead", "creepage"),
              "C3": ("sink lower edge -> strip outer face -> (gap < X bridged) -> board over edge pours", "creepage"),
              "K1": ("sink lower edge -> edge pour below (F.Cu y >= 0.6)", "clearance"),
              "K2": ("sink lower edge -> round strip bottom -> lead", "clearance"),
              "K3": ("sink lower edge -> FET lead pad copper (sink face anywhere in its range)", "clearance"),
              "S1": ("tab-metal bottom edge -> strip bottom -> shim lower edge (shimmed device)", "creepage")}
    for k, vals in worst.items():
        v, c = min(vals)
        floor = P.CREEPAGE_BASIC if labels[k][1] == "creepage" else P.CLEARANCE_BASIC
        add(labels[k][0], labels[k][1], v if v != float("inf") else 99.0, floor, c,
            "worst of z_sink x overhang corners" + (" (no surface path at any corner)" if v == float("inf") else ""))
    # strip ends and top (hand placement tolerance)
    q5_metal_left = P.FET_X["Q5"] - T["E1"][1] / 2 - P.FET_POS_TOL
    add("Q5 tab-metal left edge -> strip left end -> sink face", "creepage",
        q5_metal_left - (P.STRIP_X[0] + P.STRIP_PLACE_TOL) + t, P.CREEPAGE_BASIC, "strip 0.5 mm short", "E1 max, device -0.15")
    add("tab-metal top edge -> strip top -> sink face", "creepage",
        (P.STRIP_TOP_Z - P.STRIP_PLACE_TOL) - (z_metal_top_max + P.FET_FLOAT_MAX) + t, P.CREEPAGE_BASIC,
        f"strip 0.5 mm low, body floated {P.FET_FLOAT_MAX} mm", "L1, D max, D2 min")
    shim_top = P.SHIM_FET_Z0 + P.SHIM_FET_SIZE[1]
    add("tab-metal top edge -> strip top -> down the strip back -> shim top edge", "creepage",
        (P.STRIP_TOP_Z - P.STRIP_PLACE_TOL) - (z_metal_top_max + P.FET_FLOAT_MAX) + t + (P.STRIP_TOP_Z - P.STRIP_PLACE_TOL - shim_top),
        P.CREEPAGE_BASIC, f"shim top z {shim_top:.1f}", "shim inside the strip outline")
    # strip right end: nothing metal on BR1's back; Q2 metal -> shim edge is under the strip (no path round it)
    q2_metal_right = P.FET_X["Q2"] + T["E1"][1] / 2 + P.FET_POS_TOL
    add("Q2 tab-metal right edge -> strip right end (beyond BR1)", "creepage",
        (P.STRIP_X[1] - P.STRIP_PLACE_TOL) - q2_metal_right + t, P.CREEPAGE_BASIC, "strip 0.5 mm short", "E1 max")
    # clamp bar and springs (PE)
    y_bar = y_face + P.SPACER_L
    add("clamp bar underside -> tallest HOT SMD part under it (SOD-128)", "clearance",
        P.BAR["z"][0] - P.H_SMD_MAX, P.CLEARANCE_BASIC, "bar z 6.0", "EST part height 1.1 mm")
    y_pf_min = P.Y_TAB + T["A"][0]
    dx = (T["E1"][1] / 2) - P.SPRING["OD"] / 2            # spring edge -> tab-metal side edge; the widest metal is nearest
    for name, t4 in (("FR-4 1.6", P.FR4_T[0]), ("FR-4 0.8", P.FR4_THIN_T[0]), ("no pad", 0.0)):
        dy = (y_pf_min + t4) - (P.Y_TAB + T["A2"][1])
        add(f"spring end -> tab-metal side edge (through air, round the package side), {name}", "clearance", math.hypot(dx, dy),
            P.CLEARANCE_BASIC, "A min, A2 max, E1 max", "")
        if t4:
            creep_spring = (P.FR4_PAD[0] - P.SPRING["OD"]) / 2 + t4 + (T["E"][0] - P.FR4_PAD[0]) / 2 + \
                (T["A"][0] - T["A2"][1]) + (T["E"][0] - T["E1"][1]) / 2
        else:
            creep_spring = (T["E"][0] - P.SPRING["OD"]) / 2 + (T["A"][0] - T["A2"][1]) + (T["E"][0] - T["E1"][1]) / 2
        add(f"spring -> pad / package front and side -> tab-metal edge, {name}", "creepage", creep_spring,
            P.CREEPAGE_BASIC, "A min, A2 max, E min, E1 max", "")
    add("bar end spacer (x 115.5) -> board edge pours below", "clearance", P.BAR_SCREW_Z - 6.0 / 2 - 0.07,
        P.CLEARANCE_BASIC, "spacer OD 6.0 at z 18.7", "")
    add("sink brackets / fins -> board-edge copper (plan view)", "clearance", 5.0 + P.Y_EDGE_COPPER, P.CLEARANCE_BASIC,
        "brackets kept >= 5 mm off-board", "")
    # BR1: its leads to the sink lower edge, round the strip. BR1 is seated on the strip, so its leads stand the package's
    # back-to-lead offset (footprint 4.6 - 2.30) in front of the strip face, less the lead play it may use (bench_tolerance)
    play_br1 = (P.BR1_DRILL_FIN[1] - P.GBJ["lead_t"][0]) / 2
    br1_lead_back = (P.Y_BR1_LEAD - P.Y_BR1_BACK) - play_br1 - P.GBJ["lead_t"][1] / 2
    ov_min = P.STRIP_OVERHANG - P.STRIP_OVERHANG_TOL      # shortest strip overhang = shortest path round its bottom
    add("sink lower edge -> round strip bottom -> BR1 lead", "clearance", ov_min + t + br1_lead_back,
        P.CLEARANCE_BASIC, f"overhang {ov_min:.1f}, BR1 using its full lead play", "BR1 back plastic; its case is the basic barrier")
    # bar access slot at BR1's screw: the bar stays PE; its slot edge -> BR1 front (plastic) only, no HOT metal
    return out, dict(y_face=y_face, z_metal_bot_min=z_metal_bot_min, z_metal_top_max=z_metal_top_max,
                     lead_back_offset=lead_back_off)


def main():
    rows, cap = stresses()
    paths, geo = creepage_clearance()
    md = ["# Bench sink r1: insulation check (generated by scripts/bench_insulation.py; do not edit)", "",
          f"Stress bound tab -> PE sink: {P.V_DIE_WORST} V (worst die VDS, OPEN-ITEMS S3) + {V_LINE_PK:.1f} V (132 V line peak) "
          f"= **{V_STRESS_PK:.1f} V peak**; step 3: <= {V_STEP3:.0f} V DC. Bench floor: basic (creepage {P.CREEPAGE_BASIC} mm, "
          f"clearance {P.CLEARANCE_BASIC} mm, type-test level {P.HIPOT_BASIC_VAC} Vac).", "",
          "## Per insulator", "", "| insulator | rating Vac | rating pk V | stress pk V | rating / stress (pk) | field kV/mm | rating / 1250 Vac | note |",
          "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['insulator']} | {r['rating_Vac'] or '-'} | {r['rating_pk']:.0f} | {r['stress_pk']:.1f} | "
                  f"{(f'{r['ratio_pk']:.1f}') if r['ratio_pk'] else '-'} | {(f'{r['field_kV_per_mm']:.2f}') if r['field_kV_per_mm'] else '-'} | "
                  f"{(f'{r['rating_over_basic_hipot']:.2f}') if r['rating_over_basic_hipot'] else '-'} | {r['note']} |")
    md += ["", f"Tab -> PE capacitance through the {P.PAD_CHOICE} strip: {cap[0]:.1f}-{cap[1]:.1f} pF per tab "
           f"(production 2 mm AlN: 5.8-9.1 pF, stack-calc.txt). Two switching tabs (Q3, Q6) inject C dv/dt into the bench PE.", "",
           "## Creepage and clearance of the mount (worst corner)", "", "| path | kind | mm | floor | ok | corner | basis |", "|---|---|---|---|---|---|---|"]
    for p in paths:
        md.append(f"| {p['path']} | {p['kind']} | {p['mm']} | {p['floor']} | {p['ok']} | {p['corner']} | {p['how']} |")
    allok = all(p["ok"] for p in paths) and all((r["ratio_pk"] or 99) >= 4 for r in rows)
    md += ["", f"All paths >= floor and every rated insulator >= 4x its peak stress: **{allok}**", "",
           f"Geometry: sink face y {geo['y_face']:.3f} nominal, {M.sink_face_range()[0]:.3f}..{M.sink_face_range()[2]:.3f} with JLC-soldered devices; tab metal z {geo['z_metal_bot_min']:.2f}..{geo['z_metal_top_max']:.2f}; "
           f"tab plane -> nearest lead surface {geo['lead_back_offset']:.3f} mm."]
    (STUDY / "results").mkdir(exist_ok=True)
    (STUDY / "results" / "insulation.json").write_text(json.dumps(dict(stress=rows, cap_pF=cap, paths=paths, geometry=geo,
                                                                      all_ok=allok), indent=1, default=float) + "\n")
    (STUDY / "results" / "insulation.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
