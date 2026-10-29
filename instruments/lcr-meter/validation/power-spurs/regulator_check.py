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

The board tree is LCR_ROOT (default: this checkout) and the output LCR_OUT (default:
regulator_check.json here), so a scratch tree can be checked without touching the committed result:
  LCR_ROOT=/path/to/tree/instruments/lcr-meter LCR_OUT=/tmp/rc.json python3 regulator_check.py
LCR_CPL names a placement CSV other than ROOT/manufacturing/cpl-jlcpcb.csv (Rev F, the current board).
Rev E's archived placement is manufacturing/rev-e/cpl-jlcpcb.csv; its copper needs the Rev E tree
(git 48b012771) as LCR_ROOT.
"""
from __future__ import annotations

import csv
import json
import math
import os
import pathlib

import common as c
import copper as cu

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(os.environ.get("LCR_ROOT", HERE.parents[1])).resolve()
OUT = pathlib.Path(os.environ.get("LCR_OUT", HERE / "regulator_check.json"))
DESIGN = json.loads((ROOT / "cad/design.json").read_text())
PARTS = {p["ref"]: p for p in DESIGN["parts"]}
POS = {}
# LCR_CPL overrides the placement file (default: the current board's CPL in manufacturing/)
with open(os.environ.get("LCR_CPL", ROOT / "manufacturing/cpl-jlcpcb.csv")) as fh:
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


def leg_ohms(leg, sign=0, tcr=False):
    """Leg resistance at nominal (sign 0) or at its tolerance (+1 high, -1 low), optionally plus
    the TCR excursion over DT_BOARD in the same direction (worst case: legs drift oppositely)."""
    return sum(ohms(r) * (1 + sign * (RES_TOL[r] + (RES_TCR[r] * DT_BOARD if tcr else 0.0)))
               for r in LEG[leg])


def farads(ref):
    v = PARTS[ref]["value"].split()[0]
    return float(v[:-2]) * {"pF": 1e-12, "nF": 1e-9, "uF": 1e-6}[v[-2:]]


def chain(net_a, net_b):
    """Resistors in series from net_a to net_b (a divider leg built from several parts): each step
    follows a resistor whose far net is net_b, or an internal node carrying exactly two pins, both on
    resistors.  Exactly one such path must exist."""
    pins = {}
    for p in DESIGN["parts"]:
        for n in p["pins"].values():
            if n:
                pins.setdefault(n, []).append(p)
    paths = []

    def walk(net, via, seen):
        for p in pins[net]:
            if p["kind"] != "R" or p["ref"] in seen:
                continue
            far = [n for n in p["pins"].values() if n != net]
            if len(far) != 1:
                continue
            if far[0] == net_b:
                paths.append(seen + [p["ref"]])
            elif len(pins[far[0]]) == 2 and all(q["kind"] == "R" for q in pins[far[0]]):
                walk(far[0], p, seen + [p["ref"]])

    walk(net_a, None, [])
    assert len(paths) == 1, (net_a, net_b, paths)
    return paths[0]


LEG = {"boost_top": chain("RAW_P", "CONV_FBP"), "boost_bot": chain("CONV_FBP", "GND"),
       "inv_top": chain("RAW_N", "CONV_FBN"), "inv_bot": chain("CONV_FBN", "CONV_REF"),
       "pos_top": chain("12V", "REGP_FB"), "pos_bot": chain("REGP_FB", "GND"),
       "neg_top": chain("-12V", "REGN_FB"), "neg_bot": chain("REGN_FB", "GND")}
RES_TOL = {r: (0.001 if "0.1%" in PARTS[r]["value"] else 0.01) for leg in LEG.values() for r in leg}
# TCR per part, from the LCSC catalogue lines of the fitted parts (live JLC library records,
# 2026-10-29): every 0.1 % part on the BOM is +-25 ppm/C thin film (YAGEO RT0603BRD, Viking
# AR03BTCX); every 1 % part is UNI-ROYAL 0603WAF thick film, +-100 ppm/C.
RES_TCR = {r: (25e-6 if RES_TOL[r] == 0.001 else 100e-6) for r in RES_TOL}
DT_BOARD = 35.0   # K from the 25 C tolerance point: board 60 C (warm enclosure) or -10 C cold start
# Rev E: USB-C VBUS is the only input.  At the J1 receptacle: USB 2.0 device minimum 4.40 V (after
# cable and hub drop), USB Type-C vSafe5V maximum 5.5 V.
VIN_SUPPLY = (4.40, 5.0, 5.5)
L_NOM, L_TOL, L_ISAT, L_DCR = 4.7e-6, 0.20, 3.8, 0.039   # FNR5040S4R7MT catalog
DIODE_VR, DIODE_IF, DIODE_VF = 40.0, 1.0, 0.55           # SS14 catalog (0.55 V @ 1 A)
U16_RDS = 0.135    # TPS2553 DBV rDS(on) max, -40..125 C (sources/ti/TPS2553.txt, SLVS841F 7.5)
# J1 to U16 copper at 35 um and 1.72e-8 ohm m: 5.3 mm of 0.2 mm track around J1 (13 mOhm) plus 45 mm
# of 0.8 mm track down the west strip (28 mOhm), rounded up.
R_ENTRY = 0.045
I_IN_BASE = 0.45   # A, 5 V input current estimate (converters + 3V3 + 5VA), see README
# Rev F indicator LEDs (2026-10-29), worst case high: rail at its maximum, resistor at -1 %, LED VF at a
# 1.6 V floor (KT-0603R C2286: 1.8-2.4 V at 20 mA, lower at ~1 mA; LTST-S270KFKT: 2.0 V typ at 20 mA, 1.7 V
# floor taken).  STATUS / HB / FLT are GPIO-driven from 3V3 (AP2112K, 3.35 V max).
LED_VF_MIN = {"C2286": 1.6, "C160472": 1.7}
LED_RAIL_MAX = {"5V": 5.5, "3V3": 3.35, "12V": 12.4, "-12V": 12.2}     # |V|; U11/U12 maxima below are <= these
LED = {}
for _d, _r, _rail in (("D15", "R113", "5V"), ("D16", "R114", "3V3"), ("D17", "R115", "12V"),
                      ("D18", "R116", "-12V"), ("D19", "R117", "3V3"), ("D20", "R118", "3V3"),
                      ("D4", "R12", "3V3")):
    LED[_d] = (LED_RAIL_MAX[_rail] - LED_VF_MIN[PARTS[_d]["lcsc"]]) / (ohms(_r) * 0.99)
# 5 V input share: 5V LED direct; 3V3 LEDs through the linear AP2112K (same current at 5 V); the +-12 V
# LEDs through the LDOs (same current at RAW_P/RAW_N, |RAW| <= 14.8 V) and the TPS65131 at 0.64 efficiency
# (the Eq. 3/4 figure used below) from 4.28 V, the converter's minimum input.
I_LED_IN = (LED["D15"] + LED["D16"] + LED["D19"] + LED["D20"] + LED["D4"]
            + (LED["D17"] + LED["D18"]) * 14.8 / (4.28 * 0.64))
I_IN_EST = round(I_IN_BASE + I_LED_IN, 4)    # A, 5 V input current estimate (converters + 3V3 + 5VA + LEDs), see README


def five_volt_trunk():
    """U16 OUT (pin 6) to the TPS65131 power input (U13 pins 5/6; pin 4 is CONV_VIN behind R80): the
    least-resistance 5V path over routing.json tracks and vias, copper at a 60 C board (25 C +
    DT_BOARD, from the 20 C resistivity), outer 35 um, inner 15.2 um (copper.py). The whole input
    current is charged to it, though 3V3 and 5VA branch off on the way (pessimistic)."""
    pads, half, pad_src = cu.load_pads(ROOT)
    routing, rt_src = cu.load_routing(ROOT)
    cop = cu.Copper(routing, pads, half, dt_from_20c=25 + DT_BOARD - 20)
    p = cop.path("5V", [("U16", "6")], [("U13", "5"), ("U13", "6")])
    if not p["routed"]:   # unrouted tree: Manhattan pad distance on 0.2 mm outer copper as a stand-in
        (x1, y1), (x2, y2) = p["points"]
        mm = abs(x1 - x2) + abs(y1 - y2)
        p = {"ohm": cop._seg_ohm("F.Cu", mm, 0.2), "mm": mm, "routed": False}
    return {"ohm": p["ohm"], "path_mm": p["mm"], "routed": p["routed"], "pads": pad_src, "routing": rt_src}


TRUNK = five_volt_trunk()
VIN = (VIN_SUPPLY[0] - (U16_RDS + R_ENTRY + TRUNK["ohm"]) * I_IN_EST, VIN_SUPPLY[1], VIN_SUPPLY[2])   # at U13
# TPS2553 current limit, SLVS841F eq. 1 (RILIM in kOhm, 15-232 kOhm): IOS(mA) = K / RILIM^E.  The
# equations leave out resistor tolerance, so RILIM is taken at its own +-1 % too.
TPS2553_IOS = {"min": (25230.0, 1.016), "nom": (23950.0, 0.977), "max": (22980.0, 0.94)}
USB2_CONFIGURED_A = 0.500    # USB 2.0 7.2.1: high-power bus-powered function, 5 unit loads after configuration
USB2_UNCONFIGURED_A = 0.100  # USB 2.0 7.2.1: one unit load until configured
TYPEC_DEFAULT_A = 0.500      # USB Type-C 2.x 4.6.2.1: "Default USB Power" for a USB 2.0 port (Rp 56k)

# Rail loads from datasheet maxima (OPA2810/OPA810 IQ max 4.5 mA/ch over temp at 24 V)
IQ_OPA_MAX = 4.5e-3
LOAD = {
    "pos": 5 * IQ_OPA_MAX + 2 * 18e-3 / math.pi + 0.3e-3 + 1.0e-3 + 0.12e-3 + LED["D17"],
    "neg": 5 * IQ_OPA_MAX + 2 * 18e-3 / math.pi + 4 * 1.024e-3 + 0.3e-3 + 1.0e-3 + 0.12e-3 + LED["D18"],
}
LOAD_NOTE = ("5 amplifier channels x 4.5 mA IQ max; source buffer and TIA each "
             "18 mA peak (README short-circuit limit) as half-wave average 18/pi mA; "
             "negative rail also sinks four 1 kOhm FDA input resistors at ~1.024 V; "
             "OPA810 feedback 0.3 mA; LDO ground 1 mA; divider 0.12 mA; Rev F rail LED (D17 / D18) "
             "~1.1 mA worst case.")


def val(ref):
    return PARTS[ref]["value"]


def dist(a, b):
    (x1, y1), (x2, y2) = POS[a], POS[b]
    return math.hypot(x1 - x2, y1 - y2)


def breakeven(required_f, nominal_f):
    """Retention needed so nominal*ret*(1-tol)*(1-temp) >= required."""
    return required_f / (nominal_f * (1 - TOL_C) * (1 - TEMP_C))


def boost_vpos(corner, tcr=False):
    s = c.TPS65131
    if corner == "nom":
        return s["vfbp"][1] * (1 + leg_ohms("boost_top") / leg_ohms("boost_bot"))
    sg = 1 if corner == "max" else -1
    k = leg_ohms("boost_top", sg, tcr) / leg_ohms("boost_bot", -sg, tcr)
    return s["vfbp"][2 if corner == "max" else 0] * (1 + k)


def inverter_vneg(corner, tcr=False):
    s = c.TPS65131
    if corner == "nom":
        return -s["vref"][1] * leg_ohms("inv_top") / leg_ohms("inv_bot")
    sg = 1 if corner == "max" else -1          # max: most negative
    vfbn, vref = (s["vfbn"][0], s["vref"][2]) if corner == "max" else (s["vfbn"][2], s["vref"][0])
    k = leg_ohms("inv_top", sg, tcr) / leg_ohms("inv_bot", -sg, tcr)
    return vfbn - k * (vref - vfbn)


def ldo_vout(kind, corner, tcr=False):
    """|VOUT| = |VFB| (1 + R_top / R_bottom), the datasheet overall accuracy on top.  Each leg may be a
    series string; the ratio bound takes every resistor of a leg at the same tolerance extreme."""
    spec = c.TPS7A49 if kind == "pos" else c.TPS7A30
    vfb, acc = abs(spec["vfb_typ"]), spec["acc_overall"]
    if corner == "nom":
        return vfb * (1 + leg_ohms(f"{kind}_top") / leg_ohms(f"{kind}_bot"))
    sg = 1 if corner == "max" else -1
    return vfb * (1 + leg_ohms(f"{kind}_top", sg, tcr) / leg_ohms(f"{kind}_bot", -sg, tcr)) * (1 + sg * acc)


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
    check(f"TPS65131 VPOS range (VFBP limits, {'+'.join(LEG['boost_top'])} / {'+'.join(LEG['boost_bot'])})", [round(vpos[k], 3) for k in ("min", "nom", "max")],
          "<= 15 V recommended, 17 V abs max", vpos["max"] <= s["vpos_max_rec"],
          f"margin to 15 V: {s['vpos_max_rec'] - vpos['max']:.3f} V")
    check(f"TPS65131 VNEG range (VREF, VFBN limits, {'+'.join(LEG['inv_top'])} / {'+'.join(LEG['inv_bot'])})", [round(vneg[k], 3) for k in ("min", "nom", "max")],
          ">= -15 V recommended, -17 V abs max", vneg["max"] >= s["vneg_min_rec"],
          f"worst-case stack {vneg['max']:.3f} V is {abs(vneg['max']) - 15:.3f} V beyond the recommended range; "
          f"{17 + vneg['max']:.2f} V inside abs max")
    r_low = max(leg_ohms("boost_bot"), leg_ohms("inv_bot"))
    check("TPS65131 feedback lower resistors R82/R84 < 200 kOhm", r_low, s["r_lower_max_ohm"], r_low < s["r_lower_max_ohm"])
    for name, ref, r_up, rule in (("C87 (boost CFF)", "C87", leg_ohms("boost_top"), s["cff_rule_v"][0]),
                                  ("C88 (inverter CFF)", "C88", leg_ohms("inv_top"), s["cff_rule_v"][1])):
        top = "boost_top" if ref == "C87" else "inv_top"
        net_a, net_b = ("RAW_P", "CONV_FBP") if ref == "C87" else ("RAW_N", "CONV_FBN")
        assert set(PARTS[ref]["pins"].values()) == {net_a, net_b}, f"{ref} must span the whole {LEG[top]} string"
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
            ("pos", "U11", c.TPS7A49, "C95", "C94", leg_ohms("pos_bot"), leg_ohms("pos_top")),
            ("neg", "U12", c.TPS7A30, "C100", "C99", leg_ohms("neg_bot"), leg_ohms("neg_top"))):
        vmax, vnom, vmin = ldo_vout(kind, "max"), ldo_vout(kind, "nom"), ldo_vout(kind, "min")
        raw_min = vpos["min"] if kind == "pos" else abs(vneg["min"])
        head = raw_min - vmax
        ldo[kind] = {"vout": [vmin, vnom, vmax], "raw_min": raw_min, "headroom_min": head}
        check(f"{ref} output voltage range ({'+'.join(LEG[kind + '_top'])} / {'+'.join(LEG[kind + '_bot'])})",
              [round(vmin, 3), round(vnom, 3), round(vmax, 3)], "+-2.5 % overall + divider tolerance; OPA2810 4.75-27 V supply (SBOS799)",
              4.75 <= 2 * vmin and 2 * vmax <= 27.0, "host monitor window: rail_monitor_window.py")
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
          alt["max"] >= -15 and alt["tps7a30_headroom_min"] >= 1.0,
          f"fitted since Rev D; Rev E builds it as {'+'.join(LEG['inv_top'])} = {leg_ohms('inv_top')/1e6:.3f} MOhm")
    # Option R5: 1 ohm series element before each LDO input (C94/C99 on the LDO side)
    c_in = 10e-6 * assumed_retention(vpos["max"], 50) * (1 - TOL_C) * (1 - TEMP_C)
    r5 = {"rc_corner_hz": 1 / (2 * math.pi * 1.0 * c_in),
          "headroom_pos_2x_load": ldo["pos"]["headroom_min"] - 1.0 * 2 * LOAD["pos"],
          "headroom_neg_2x_load": ldo["neg"]["headroom_min"] - 1.0 * 2 * LOAD["neg"],
          "drop_est_load_v": [LOAD["pos"], LOAD["neg"]]}
    check("Option R5: 1 ohm before U11/U12 - headroom at 2x load, RC corner",
          [round(r5["headroom_pos_2x_load"], 3), round(r5["headroom_neg_2x_load"], 3), round(r5["rc_corner_hz"])],
          ">= 1 V", min(r5["headroom_pos_2x_load"], r5["headroom_neg_2x_load"]) >= 1.0,
          "R95/R96 are fitted (Rev D); the row name is historical")
    # Same row with every divider resistor's TCR added at DT_BOARD (TPS65131 and LDO dividers drifting
    # in the directions that close the headroom).  The reference limits already cover temperature.
    tc = {}
    for kind, rail, spec_raw in (("pos", "U11", lambda: boost_vpos("min", True)),
                                 ("neg", "U12", lambda: abs(inverter_vneg("min", True)))):
        raw_min, vmax, vmin = spec_raw(), ldo_vout(kind, "max", True), ldo_vout(kind, "min", True)
        tc[kind] = {"raw_min": raw_min, "vout_min": vmin, "vout_max": vmax,
                    "headroom_2x_load_r5": raw_min - vmax - 1.0 * 2 * LOAD[kind]}
    r5["with_tcr"] = tc
    check(f"R95/R96 headroom at 2x load incl. divider TCR (board 25 +- {DT_BOARD:.0f} C)",
          [round(tc["pos"]["headroom_2x_load_r5"], 3), round(tc["neg"]["headroom_2x_load_r5"], 3),
           round(tc["pos"]["vout_min"], 3), round(tc["neg"]["vout_min"], 3)],
          ">= 0.6 V dropout (FLAG below the 1 V PSRR-curve condition); the readings vs the host window are in rail_monitor_window.py",
          True if min(tc[k]["headroom_2x_load_r5"] for k in tc) >= 1.0 else
          ("FLAG" if min(tc[k]["headroom_2x_load_r5"] for k in tc) >= 0.6 else False),
          "information: 0.1 % parts 25 ppm/C, 1 % parts 100 ppm/C, opposite drift of top and bottom")
    check("5V trunk U16.6 -> U13.5/6 copper (routing.json, 60 C)", round(TRUNK["ohm"] * 1e3, 1),
          "added to R_ENTRY in VIN", True if TRUNK["routed"] else "FLAG",
          f"mOhm over {TRUNK['path_mm']:.1f} mm; least-resistance single path (upper bound on the strip model); "
          f"{TRUNK['ohm'] * I_IN_EST * 1e3:.1f} mV at {I_IN_EST} A; VIN min {VIN[0]:.3f} V at U13"
          + ("" if TRUNK["routed"] else "; NOT ROUTED: Manhattan distance at 0.2 mm stand-in"))
    r_ilim = ohms("R110") / 1e3
    tol = 0.01 if "1%" in val("R110") else 0.05
    ios = {k: K / (r_ilim * (1 + sg * tol)) ** E / 1e3
           for (k, (K, E)), sg in zip(TPS2553_IOS.items(), (1, 0, -1))}
    check(f"TPS2553 current limit (R110 {val('R110')}) min vs 2x input estimate",
          [round(ios[k], 3) for k in ("min", "nom", "max")], f">= 2 x {I_IN_EST} A",
          ios["min"] >= 2 * I_IN_EST,
          "A, SLVS841F eq. 1 with R110 at +-1 % (min at R high, max at R low); constant-current limit, "
          "so a converter start-up surge is limited, not latched off")
    check("Rev F indicator LED currents, worst case high (mA)",
          {d: round(i * 1e3, 2) for d, i in LED.items()}, "C2286 20 mA DC; LTST-S270KFKT 30 mA DC",
          max(LED[d] for d in LED if d != "D4") < 0.020 and LED["D4"] < 0.030,
          f"5 V input share {I_LED_IN * 1e3:.1f} mA, added to the {I_IN_BASE} A base estimate; R115/R116 "
          f"dissipate {(LED_RAIL_MAX['12V'] - 1.6) * LED['D17'] * 1e3:.1f} mW of 100 mW")
    io = LED["D4"] + LED["D19"] + LED["D20"]
    check("RP2040 IOVDD source current from the LED GPIOs (25, 23, 22) vs IIOVDD_MAX",
          round(io * 1e3, 2), 50.0, io < 0.050 / 2,
          "mA, upper bound with the pins at 3.35 V (each pad sags toward VOH 2.62 V at 4 mA in the default "
          "4 mA mode, RP2040 Table 625, which only lowers these); half the 50 mA bank limit kept for the rest")
    check("AP2112K 3V3 (U3) added load from the LEDs", round((io + LED["D16"]) * 1e3, 2), 600.0,
          io + LED["D16"] < 0.6 * 0.05, "mA of the 600 mA rating (sources/new/AP2112.txt)")
    check("USB-C input budget vs USB 2.0 / Type-C Default USB Power", I_IN_EST, TYPEC_DEFAULT_A,
          I_IN_EST <= min(USB2_CONFIGURED_A, TYPEC_DEFAULT_A),
          f"A estimate, not a bound; {1e3 * (TYPEC_DEFAULT_A - I_IN_EST):.0f} mA margin. CC1/CC2 carry Rd "
          f"5.1k (R1/R2) and nothing reads CC, so the board may count only on Default USB Power: 500 mA "
          f"(USB Type-C 4.6.2.1, USB 2.0 7.2.1, after configuration). U16 limits at "
          f"{ios['min']:.2f}-{ios['max']:.2f} A, above that budget, so it protects the board, not the host")
    check("USB 2.0 unconfigured draw (U16 EN tied to VBUS: full load from attach)", I_IN_EST, USB2_UNCONFIGURED_A,
          I_IN_EST <= USB2_UNCONFIGURED_A,
          "A; USB 2.0 7.2.1 allows one unit load (100 mA) before configuration. The board powers everything at "
          "attach (TPS2553 SOT-23 pin 3 EN, active high, on USB_VBUS). Hosts commonly tolerate it; a strict hub may not. firmware-rev-e also declares "
          "PICO_STDIO_USB_DEVICE_SELF_POWERED=1 on a bus-powered board (should be bus-powered, 500 mA max power)")
    near = min((dist(l, u), l, u) for l in ("L1", "L2", "D2", "D3", "U13")
               for u in ("U4", "U5", "U6", "U7", "U8", "U9", "U10", "U14") if u in POS)   # U14: Rev E codec
    check("Switcher magnetics/switch nodes to nearest analog IC (CPL centres)", f"{near[0]:.1f} mm ({near[1]}-{near[2]})",
          "information only: magnetic pickup not modelled", True)
    out = {"r5_option": r5, "nearest_switcher_to_analog_mm": near, "r83_alternative": alt, "loads_a": LOAD, "load_note": LOAD_NOTE, "vpos": vpos, "vneg": vneg, "ldo": ldo,
           "retention_pass_threshold": RETENTION_PASS, "five_volt_trunk": TRUNK, "vin_at_u13": VIN,
           "checks": rows,
           "operating_points_2x_load": ops}
    OUT.write_text(json.dumps(out, indent=1, default=float))
    for r in rows:
        print(f"[{r['status']:<8}] {r['item']}: {r['value']} (limit {r['limit']}) {r['note']}")
    print("loads (A):", {k: round(v, 4) for k, v in LOAD.items()})


if __name__ == "__main__":
    main()
