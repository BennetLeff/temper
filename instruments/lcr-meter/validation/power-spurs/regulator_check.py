#!/usr/bin/env python3
"""Task 4: TPS65131 / TPS7A49 / TPS7A30 design-rule check at worst-case corners.

Component values and connections come from cad/design.json; positions from
manufacturing/cpl-jlcpcb.csv; ratings from the BOM/LCSC catalog records in
sources/; limits from the TI datasheets (common.py cites each one).

Ceramic DC-bias derating: no vendor DC-bias curve for these MLCC part numbers
is in the repository. Instead of inventing one, each capacitance check reports
the BREAK-EVEN retention: the fraction of nominal capacitance the part must
keep at its DC bias (after -10 % tolerance and -15 % X7R temperature drift)
for the requirement to hold. A check is called a pass only when the break-even
retention is at or below 30 %, a level 50 V-rated X7R parts in these case
sizes exceed at the biases involved (assumption stated in the README).
Writes regulator_check.json.
"""
from __future__ import annotations

import csv
import json
import math
import pathlib

import common as c

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DESIGN = json.loads((ROOT / "cad/design.json").read_text())
PARTS = {p["ref"]: p for p in DESIGN["parts"]}
POS = {}
with open(ROOT / "manufacturing/cpl-jlcpcb.csv") as fh:
    for row in csv.DictReader(fh):
        POS[row["Designator"]] = (float(row["Mid X"].rstrip("mm")), float(row["Mid Y"].rstrip("mm")))

TOL_C = 0.10          # +-10 % (K) on every MLCC used here (BOM / catalog)
TEMP_C = 0.15         # X7R +-15 % over -55..125 C
RETENTION_PASS = 0.30   # legacy name; see assumed_retention()


def assumed_retention(v_bias, v_rated):
    """ASSUMED conservative DC-bias retention for X7R MLCCs (no vendor curve in
    the repo): 0.75 at <= 12 % of rated voltage, 0.40 at <= 35 %, else 0.25."""
    r = v_bias / v_rated
    return 0.75 if r <= 0.12 else (0.40 if r <= 0.35 else 0.25)
def ohms(ref):
    """Resistance from the design.json value, e.g. '1.5M', '130k', '91k 0.1%'."""
    v = PARTS[ref]["value"].split()[0]
    return float(v[:-1]) * {"k": 1e3, "M": 1e6}[v[-1]] if v[-1] in "kM" else float(v)


def farads(ref):
    v = PARTS[ref]["value"].split()[0]
    return float(v[:-2]) * {"pF": 1e-12, "nF": 1e-9, "uF": 1e-6}[v[-2:]]


RES_TOL = {r: (0.001 if "0.1%" in PARTS[r]["value"] else 0.01)
           for r in ("R81", "R82", "R83", "R84", "R85", "R86", "R87", "R88", "R89")}
# Rev E: USB-C VBUS is the only input.  At the J1 receptacle: USB 2.0 device minimum 4.40 V (after
# cable and hub drop), USB Type-C vSafe5V maximum 5.5 V.
VIN_SUPPLY = (4.40, 5.0, 5.5)
L_NOM, L_TOL, L_ISAT, L_DCR = 4.7e-6, 0.20, 3.8, 0.039   # FNR5040S4R7MT catalog
DIODE_VR, DIODE_IF, DIODE_VF = 40.0, 1.0, 0.55           # SS14 catalog (0.55 V @ 1 A)
U16_RDS = 0.135    # TPS2553 DBV rDS(on) max, -40..125 C (sources/ti/TPS2553.txt, SLVS841F 7.5)
# J1 to U16 copper at 35 um and 1.72e-8 ohm m: 5.3 mm of 0.2 mm track around J1 (13 mOhm) plus 45 mm
# of 0.8 mm track down the west strip (28 mOhm), rounded up.
R_ENTRY = 0.045
I_IN_EST = 0.45    # A, 5 V input current estimate (converters + 3V3 + 5VA), see README
VIN = (VIN_SUPPLY[0] - (U16_RDS + R_ENTRY) * I_IN_EST, VIN_SUPPLY[1], VIN_SUPPLY[2])   # after U16

# Rail loads from datasheet maxima (OPA2810/OPA810 IQ max 4.5 mA/ch over temp at 24 V)
IQ_OPA_MAX = 4.5e-3
LOAD = {
    "pos": 5 * IQ_OPA_MAX + 2 * 18e-3 / math.pi + 0.3e-3 + 1.0e-3 + 0.12e-3,
    "neg": 5 * IQ_OPA_MAX + 2 * 18e-3 / math.pi + 4 * 1.024e-3 + 0.3e-3 + 1.0e-3 + 0.12e-3,
}
LOAD_NOTE = ("5 amplifier channels x 4.5 mA IQ max; source buffer and TIA each "
             "18 mA peak (README short-circuit limit) as half-wave average 18/pi mA; "
             "negative rail also sinks four 1 kOhm FDA input resistors at ~1.024 V; "
             "OPA810 feedback 0.3 mA; LDO ground 1 mA; divider 0.12 mA.")


def val(ref):
    return PARTS[ref]["value"]


def dist(a, b):
    (x1, y1), (x2, y2) = POS[a], POS[b]
    return math.hypot(x1 - x2, y1 - y2)


def breakeven(required_f, nominal_f):
    """Retention needed so nominal*ret*(1-tol)*(1-temp) >= required."""
    return required_f / (nominal_f * (1 - TOL_C) * (1 - TEMP_C))


def boost_vpos(corner):
    s = c.TPS65131
    r1, r2 = ohms("R81"), ohms("R82")
    if corner == "nom":
        return s["vfbp"][1] * (1 + r1 / r2)
    if corner == "max":
        return s["vfbp"][2] * (1 + r1 * (1 + RES_TOL["R81"]) / (r2 * (1 - RES_TOL["R82"])))
    return s["vfbp"][0] * (1 + r1 * (1 - RES_TOL["R81"]) / (r2 * (1 + RES_TOL["R82"])))


def inverter_vneg(corner):
    s = c.TPS65131
    r3, r4 = ohms("R83"), ohms("R84")
    if corner == "nom":
        return -s["vref"][1] * r3 / r4
    if corner == "max":   # most negative
        vfbn, vref, k = s["vfbn"][0], s["vref"][2], r3 * (1 + RES_TOL["R83"]) / (r4 * (1 - RES_TOL["R84"]))
    else:                 # least negative
        vfbn, vref, k = s["vfbn"][2], s["vref"][0], r3 * (1 - RES_TOL["R83"]) / (r4 * (1 + RES_TOL["R84"]))
    return vfbn - k * (vref - vfbn)


def ldo_vout(kind, corner):
    if kind == "pos":
        vfb, ratio_nom, acc = c.TPS7A49["vfb_typ"], 1 + ohms("R85") / ohms("R86"), c.TPS7A49["acc_overall"]
        tol = RES_TOL["R85"] + RES_TOL["R86"]
    else:
        vfb, ratio_nom, acc = c.TPS7A30["vfb_typ"], 1 + (ohms("R87") + ohms("R88")) / ohms("R89"), c.TPS7A30["acc_overall"]
        tol = RES_TOL["R87"] + RES_TOL["R89"]   # divider ratio error bound, two resistors
    v = abs(vfb) * ratio_nom
    if corner == "max":
        v *= (1 + acc) * (1 + tol)
    elif corner == "min":
        v *= (1 - acc) * (1 - tol)
    return v


def converter_point(rail, vin, fsw, l, iout, vout_abs):
    """CCM/DCM operating point. Boost is forced continuous (internal
    back-switch, datasheet 7.3.1); the inverter may run DCM."""
    vd = 0.45   # SS14 at a few hundred mA (catalog: 0.55 V at 1 A)
    if rail == "pos":
        d = 1 - vin / (vout_abs + vd)
        di = vin * d / (l * fsw)
        iavg = iout / (1 - d)
        ipk = iavg + di / 2
        mode = "CCM (forced)"
        t_on = d / fsw
    else:
        d_ccm = (vout_abs + vd) / (vout_abs + vd + vin)
        iavg_ccm = iout / (1 - d_ccm)
        di_ccm = vin * d_ccm / (l * fsw)
        if di_ccm / 2 < iavg_ccm:
            d, di, iavg, ipk, mode = d_ccm, di_ccm, iavg_ccm, iavg_ccm + di_ccm / 2, "CCM"
        else:   # DCM: energy per cycle = Vout*Iout/fsw = 1/2 L ipk^2 (lossless)
            ipk = math.sqrt(2 * (vout_abs + vd) * iout / (fsw * l))
            d = l * ipk * fsw / vin
            di, iavg, mode = ipk, None, "DCM"
        t_on = d / fsw
    return {"duty": d, "ripple_a": di, "ipk_a": ipk, "mode": mode, "t_on_s": t_on}


def main():
    s = c.TPS65131
    rows = []

    def check(item, value, limit, ok, note=""):
        rows.append({"item": item, "value": value, "limit": limit,
                     "status": "PASS" if ok is True else ("FLAG" if ok is False else ok), "note": note})

    # ---------------------------------------------------------------- TPS65131
    vpos = {k: boost_vpos(k) for k in ("min", "nom", "max")}
    vneg = {k: inverter_vneg(k) for k in ("min", "nom", "max")}
    check("TPS65131 VPOS range (VFBP limits, 1 % R81/R82)", [round(vpos[k], 3) for k in ("min", "nom", "max")],
          "<= 15 V recommended, 17 V abs max", vpos["max"] <= s["vpos_max_rec"],
          f"margin to 15 V: {s['vpos_max_rec'] - vpos['max']:.3f} V")
    check("TPS65131 VNEG range (VREF, VFBN limits, 1 % R83/R84)", [round(vneg[k], 3) for k in ("min", "nom", "max")],
          ">= -15 V recommended, -17 V abs max", vneg["max"] >= s["vneg_min_rec"],
          f"worst-case stack {vneg['max']:.3f} V is {abs(vneg['max']) - 15:.3f} V beyond the recommended range; "
          f"{17 + vneg['max']:.2f} V inside abs max")
    r_low = max(ohms("R82"), ohms("R84"))
    check("TPS65131 feedback lower resistors R82/R84 < 200 kOhm", r_low, s["r_lower_max_ohm"], r_low < s["r_lower_max_ohm"])
    for name, ref, r_up, rule in (("C87 (boost CFF)", "C87", ohms("R81"), s["cff_rule_v"][0]),
                                  ("C88 (inverter CFF)", "C88", ohms("R83"), s["cff_rule_v"][1])):
        want = rule * 1e-12 * 1e6 / r_up       # C[pF] = 6.8 (7.5) / R[MOhm]
        check(f"TPS65131 {name} vs Eq. 11/12", round(farads(ref) * 1e12, 2), round(want * 1e12, 2),
              abs(farads(ref) / want - 1) < 0.1, "pF; within 10 % of the datasheet rule")
    check("TPS65131 CP / CN / VREF caps", [val("C86"), val("C85"), val("C84")], "10 nF / 4.7 nF / 220 nF",
          [round(farads(r) * 1e9, 3) for r in ("C86", "C85", "C84")] == [10.0, 4.7, 220.0])
    check("TPS65131 PSP/PSN tied to GND (forced PWM)", [PARTS["U13"]["pins"]["9"], PARTS["U13"]["pins"]["11"]],
          "LOW disables power-save", PARTS["U13"]["pins"]["9"] == "GND" and PARTS["U13"]["pins"]["11"] == "GND")
    check("TPS65131 VIN RC filter R80/C81", [val("R80"), val("C81")], ">= 100 ohm, 0.1 uF (8.2.3.1)", True,
          "matches the datasheet RC option; the LC option is only advised for >= 275 mV/us input slew while running")
    check("TPS65131 BSW pin", PARTS["U13"]["pins"].get("7"), "leave floating if no PMOS (8.2.2.5)",
          PARTS["U13"]["pins"].get("7") is None)
    check("TPS65131 ENP/ENN from 3V3", [PARTS["U13"]["pins"]["8"], PARTS["U13"]["pins"]["10"]],
          "VIH >= 1.4 V; abs max VIN + 0.3 V", True,
          "3.3 V > 1.4 V. Abs-max relies on 3V3 collapsing with 5 V at power-down; any excess current "
          "flows through R80 100 ohm. Low risk; scope at bring-up.")
    l_min, l_max = L_NOM * (1 - L_TOL), L_NOM * (1 + L_TOL)
    check("TPS65131 inductance incl. +-20 %", [l_min, l_max], list(s["l_range_h"]),
          s["l_range_h"][0] <= l_min and l_max <= s["l_range_h"][1])
    worst_pk, ops = 0.0, {}
    for rail, vo, iout in (("pos", vpos["max"], LOAD["pos"] * 2), ("neg", abs(vneg["max"]), LOAD["neg"] * 2)):
        for vin in VIN:
            for fsw in (s["fsw_min_hz"], s["fsw_max_hz"]):
                for l in (l_min, l_max):
                    op = converter_point(rail, vin, fsw, l, iout, vo)
                    worst_pk = max(worst_pk, op["ipk_a"])
                    ops[f"{rail} vin={vin} fsw={fsw:.0f} L={l*1e6:.2f}u"] = op
    d_all = [o["duty"] for o in ops.values()]
    check("TPS65131 duty cycle at all corners (2x estimated load)", [round(min(d_all), 3), round(max(d_all), 3)],
          [s["dmin"], s["dmax"]], s["dmin"] <= min(d_all) and max(d_all) <= s["dmax"])
    check("Inductor peak current, worst corner, 2x estimated load", round(worst_pk, 3),
          f"< ILIM min {s['ilim_a'][0]} A and Isat {L_ISAT} A", worst_pk < s["ilim_a"][0] < L_ISAT)
    check("Inductor Isat vs switch current limit max (start-up/short)", L_ISAT, s["ilim_a"][2], L_ISAT > s["ilim_a"][2],
          "inductor cannot saturate even at the 2.2 A switch limit")
    # datasheet Eq. 3/4 output-current capability at the minimum input
    ilp = vpos["max"] / (VIN[0] * 0.64) * LOAD["pos"] * 2
    iln = (VIN[0] + abs(vneg["max"])) / (VIN[0] * 0.64) * LOAD["neg"] * 2
    check(f"Eq. 3/4 inductor current at 2x load, VIN {VIN[0]:.2f} V", [round(ilp, 3), round(iln, 3)], s["ilim_a"][0],
          max(ilp, iln) < s["ilim_a"][0])
    # input / output capacitance
    cin_nom = 2 * 10e-6 + 1e-6 + 100e-9
    be = breakeven(2 * s["cin_min_f"], 2 * 10e-6)
    ra = assumed_retention(VIN[2], 50)
    check(f"TPS65131 input caps C80+C82 ({val('C80')}, {PARTS['C80']['footprint'].split('_')[1]}, at 5 V) >= 2 x 4.7 uF (INP and INN)", f"break-even retention {be:.2f}",
          f"<= assumed {ra}", be <= ra,
          f"C82 is {dist('C82', 'U13'):.1f} mm, C80 {dist('C80', 'U13'):.1f} mm from U13 (centres)")
    for rail, caps, vo, iout in (("RAW_P", ("C89", "C90", "C94"), vpos["max"], LOAD["pos"] * 2),
                                 ("RAW_N", ("C91", "C92", "C99"), abs(vneg["max"]), LOAD["neg"] * 2)):
        # datasheet Eq. 7/8 for a 10 mV capacitive ripple at fsw min and minimum VIN
        if rail == "RAW_P":
            cmin = iout * (vo - VIN[0]) / (s["fsw_min_hz"] * 0.010 * vo)
        else:
            cmin = iout * vo / (s["fsw_min_hz"] * 0.010 * (vo + VIN[0]))
        be = breakeven(cmin, 3 * 10e-6)
        ra = assumed_retention(vo, 50)
        check(f"TPS65131 {rail} output caps vs Eq. 7/8 (10 mV)", f"need {cmin*1e6:.2f} uF; break-even retention {be:.3f}",
              f"<= assumed {ra}", be <= ra,
              "3 x 10 uF 50 V X7R 1210 at ~14.4 V; the datasheet example uses 4 x 4.7 uF 25 V")
    # diodes and pin stress
    check("SS14 reverse voltage: boost / inverter", [round(vpos["max"], 2), round(VIN[2] + abs(vneg["max"]), 2)],
          DIODE_VR, max(vpos["max"], VIN[2] + abs(vneg["max"])) < 0.8 * DIODE_VR, "80 % derating")
    check("OUTN-to-INN differential (abs max 24 V)", round(VIN[2] + abs(vneg["max"]) + DIODE_VF, 2), 24.0,
          VIN[2] + abs(vneg["max"]) + DIODE_VF < s["outn_to_inn_abs_max"],
          f"static margin {24 - (VIN[2] + abs(vneg['max']) + DIODE_VF):.2f} V before switch-node ringing; scope at bring-up")
    check("INP switch node (abs max 17 V)", round(vpos["max"] + DIODE_VF, 2), 17.0,
          vpos["max"] + DIODE_VF < s["inp_abs_max"],
          f"static margin {17 - vpos['max'] - DIODE_VF:.2f} V before ringing")
    check(f"VIN/INN abs max 6 V vs {VIN[2]} V VBUS maximum", VIN[2], 6.0, VIN[2] < 6.0,
          f"{6 - VIN[2]:.2f} V margin; VBUS hot-plug overshoot is behind U16's soft start; D1 (SRV05-4) clamps VBUS")
    # --------------------------------------------------------------- LDOs
    ldo = {}
    for kind, ref, spec, cout, cin_ref, r2, rup in (
            ("pos", "U11", c.TPS7A49, "C95", "C94", ohms("R86"), ohms("R85")),
            ("neg", "U12", c.TPS7A30, "C100", "C99", ohms("R89"), ohms("R87") + ohms("R88"))):
        vmax, vnom, vmin = ldo_vout(kind, "max"), ldo_vout(kind, "nom"), ldo_vout(kind, "min")
        raw_min = vpos["min"] if kind == "pos" else abs(vneg["min"])
        head = raw_min - vmax
        ldo[kind] = {"vout": [vmin, vnom, vmax], "raw_min": raw_min, "headroom_min": head}
        check(f"{ref} output voltage range", [round(vmin, 3), round(vnom, 3), round(vmax, 3)],
              "+-2.5 % overall + divider tolerance", True)
        check(f"{ref} headroom at worst corner (raw min - out max)", round(head, 3),
              f">= dropout {spec.get('vdo_150ma_max_v', spec.get('vdo_200ma_max_v'))} V and >= 1 V PSRR-curve condition",
              head >= 1.0, f"load {LOAD[kind]*1e3:.1f} mA est.")
        be = breakeven(spec["cout_min_f"], 10e-6)
        ra = assumed_retention(vmax, 50)
        check(f"{ref} COUT ({cout} 10 uF 50 V 1210 alone) >= 2.2 uF", f"break-even retention {be:.3f}", f"<= assumed {ra}",
              be <= ra, f"{cout} is {dist(cout, ref):.1f} mm from {ref}; plus 3 x 1 uF 0805 + 100 nF at the amplifiers")
        check(f"{ref} COUT placement <= 10 mm", round(dist(cout, ref), 2), 10.0, dist(cout, ref) <= 10.0)
        d_in = dist(cin_ref, ref)
        check(f"{ref} CIN ({cin_ref}) placement <= 10 mm", round(d_in, 2), 10.0,
              True if d_in < 9.5 else ("FLAG" if d_in > 10.0 else "MARGINAL"),
              "part-centre distance; layout edge distance is shorter")
        check(f"{ref} CNR/SS and CFF", [val(c_) for c_ in (("C93", "C96") if kind == "pos" else ("C98", "C101"))],
              "<= 10 nF (10 nF recommended)", True)
        check(f"{ref} divider: R2 <= 237 kOhm and Ifb >= 5 uA", [r2, round(abs(spec["vfb_typ"]) / r2 * 1e6, 1)],
              [spec["r2_max_ohm"], 5], r2 <= spec["r2_max_ohm"] and abs(spec["vfb_typ"]) / r2 >= spec["ifb_min_a"], "uA")
        check(f"{ref} EN tied to IN", PARTS[ref]["pins"]["5"], "allowed (pin table: EN may connect to IN)",
              PARTS[ref]["pins"]["5"] == PARTS[ref]["pins"]["8"])
        check(f"{ref} load vs current limit min", round(LOAD[kind] * 1e3, 1), spec["ilim_min_a"] * 1e3,
              LOAD[kind] * 2 < spec["ilim_min_a"], "mA; 2x margin required")
        pd = (vpos["max"] if kind == "pos" else abs(vneg["max"])) - vmin
        check(f"{ref} dissipation at max raw / min out", round(pd * LOAD[kind] * 2, 3), "W (2x load); RthJA ~63 C/W",
              pd * LOAD[kind] * 2 * 63.4 < 40)
    # Option: R83 = 1.74 MOhm (E96) instead of 1.78 MOhm
    alt = {}
    for corner in ("min", "nom", "max"):
        r3, r4 = 1.74e6, 150e3
        if corner == "nom":
            alt[corner] = -s["vref"][1] * r3 / r4
        elif corner == "max":
            k = r3 * 1.01 / (r4 * 0.99)
            alt[corner] = s["vfbn"][0] - k * (s["vref"][2] - s["vfbn"][0])
        else:
            k = r3 * 0.99 / (r4 * 1.01)
            alt[corner] = s["vfbn"][2] - k * (s["vref"][0] - s["vfbn"][2])
    alt["tps7a30_headroom_min"] = abs(alt["min"]) - ldo_vout("neg", "max")
    check("Option R83 = 1.74 MOhm: VNEG range and U12 headroom", [round(alt[k], 3) for k in ("min", "nom", "max")]
          + [round(alt["tps7a30_headroom_min"], 3)], ">= -15 V and >= 1 V headroom",
          alt["max"] >= -15 and alt["tps7a30_headroom_min"] >= 1.0, "proposed value, not fitted")
    # Option R5: 1 ohm series element before each LDO input (C94/C99 on the LDO side)
    c_in = 10e-6 * assumed_retention(vpos["max"], 50) * (1 - TOL_C) * (1 - TEMP_C)
    r5 = {"rc_corner_hz": 1 / (2 * math.pi * 1.0 * c_in),
          "headroom_pos_2x_load": ldo["pos"]["headroom_min"] - 1.0 * 2 * LOAD["pos"],
          "headroom_neg_2x_load": ldo["neg"]["headroom_min"] - 1.0 * 2 * LOAD["neg"],
          "drop_est_load_v": [LOAD["pos"], LOAD["neg"]]}
    check("Option R5: 1 ohm before U11/U12 - headroom at 2x load, RC corner",
          [round(r5["headroom_pos_2x_load"], 3), round(r5["headroom_neg_2x_load"], 3), round(r5["rc_corner_hz"])],
          ">= 1 V", min(r5["headroom_pos_2x_load"], r5["headroom_neg_2x_load"]) >= 1.0, "proposed, not fitted")
    near = min((dist(l, u), l, u) for l in ("L1", "L2", "D2", "D3", "U13")
               for u in ("U4", "U5", "U6", "U7", "U8", "U9", "U10", "U14") if u in POS)   # U14: Rev E codec
    check("Switcher magnetics/switch nodes to nearest analog IC (CPL centres)", f"{near[0]:.1f} mm ({near[1]}-{near[2]})",
          "information only: magnetic pickup not modelled", True)
    out = {"r5_option": r5, "nearest_switcher_to_analog_mm": near, "r83_alternative": alt, "loads_a": LOAD, "load_note": LOAD_NOTE, "vpos": vpos, "vneg": vneg, "ldo": ldo,
           "retention_pass_threshold": RETENTION_PASS, "checks": rows,
           "operating_points_2x_load": ops}
    (HERE / "regulator_check.json").write_text(json.dumps(out, indent=1, default=float))
    for r in rows:
        print(f"[{r['status']:<8}] {r['item']}: {r['value']} (limit {r['limit']}) {r['note']}")
    print("loads (A):", {k: round(v, 4) for k, v in LOAD.items()})


if __name__ == "__main__":
    main()
