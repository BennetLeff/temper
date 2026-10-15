"""sensor-r3 PCB checks: the C1 pan-sensor channels on the zapote/controller board.

HANDOFF section B, items 1-9. Every number in pcb/*.md comes from this script.
Run:  python3 checks.py   -> checks.json  (exit 1 if any gate fails)

Circuit under test
- "captured": zapote/controller as captured on branch controller-layout
  (300b8a934, read-only): RTDSensing (MAX31865, 430 R Yageo RT 0.1 % 25 ppm,
  1 nF C0G across RTDIN, 1 M open-lead pull-ups at the pins, REF2025 window,
  TLV3201 runaway at BIAS/3 on the 100 k window branch), rim NTC on J12
  (104GT-2, 1.00 k pull-up, 10 k/100 nF, TLV9061, GPIO9 ADC1).
- "proposed": the same plus CHANGE-REQUEST.md: 2-stage RC on the sense lines
  (1.00 k / 100 nF C0G / 1.00 k / 100 nF C0G + 2 x 1 nF CM), pull-ups and
  window taps moved to the connector side, 10 nF on the window node,
  ESD5Z3.3 on the four RTD lines, Rref 430 R 0.05 % 5 ppm, rim trip.

Method: a small complex modified-nodal-analysis solver (numpy) for the AC
pickup cases and the DC fault/loading cases; datasheet worst-case corners.
Datasheet values are in SRC with their source; "assumption" marks every value
that is an engineering allowance rather than a datasheet limit.
"""
from __future__ import annotations

import itertools
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

# --------------------------------------------------------------------------- sources
SRC = {
    "MAX31865": "Maxim MAX31865 19-6478 Rev 3 (datasheets/max31865.pdf): VBIAS 1.95-2.06 V, "
                "bias load reg 30 mV/mA, IOUT max 5.75 mA, 15 bit, offset -3..+3 LSB (max), "
                "full-scale +/-1 LSB (typ), INL +/-1 LSB (typ), input leakage 14 nA (typ, -40..100 C), "
                "conversion 16.7 ms typ / 17.6 ms max continuous 60 Hz notch, analog pins 0..VBIAS, "
                "protection opens >VDD+0.1 V or <GND-0.4 V (D2), RREF 350 R..10 k, cable <=50 R/lead, "
                "auto fault cycle valid only if input RC tau <=100 us, sinc3 filter",
    "Pt100": "IEC 60751 Callendar-Van Dusen A 3.9083e-3, B -5.775e-7 (T>=0), C -4.183e-12 (T<0)",
    "Rref_captured": "Yageo RT0805BRD07430RL 0.1 % 25 ppm/K (controller C35 R39 swap)",
    "Rref_proposed": "Susumu RG2012V-431-W-T1 0.05 %, 5 ppm/K (RG2012V series, V = +/-5 ppm; RTD unit's "
                     "original part, swapped out in C35 for stock only)",
    "board_temp": "controller_calcs.py TEMP_SPAN_K 60 (25 -> 85 C board); 0 C lower bound (assumption)",
    "TLV3201": "TI SBOS561C: VIO +/-5 mV max (as used in controller_calcs.runaway)",
    "ESD5Z3.3": "onsemi ESD5Z3.3T1G: VRWM 3.3 V, IR 50 nA max at VRWM, 25 C (controller_parts.ato basis)",
    "104GT-2": "Semitec GT-2 series datasheet 2023-08-01 R-T table (copied in controller_calcs.py): "
               "100 k +/-3 %, B25/85 4267 K +/-2 %, -50..+300 C, 0.6 mW/K still air",
    "ESP32-S3 ADC": "12 bit; calibrated error bounds used: ATTEN0 +/-5 mV, ATTEN2 +/-10 mV, ATTEN3 "
                    "+/-50 mV (assumption to confirm against the ESP32-S3 datasheet ADC table at capture)",
    "v3v3": "TPS62933 3.3 V rail 3.242-3.367 V, measured by MCP3202 CH1 against LM4040A25 0.1 % "
            "(controller DECISIONS C20)",
    "tank_cm": "output/temper-coil-driver-r1/tank_cm.json: winding-mean CM voltage (one-sided bank) and "
               "winding-to-pan 70-81 pF (enclosure study 16)",
    "coil": "native-21 tank 242 V rms / 640 V peak recurring, 33-60 kHz (R40 DECISIONS item 2, power stage)",
    "B_eye": "R43 G7 spring screen B 5-20 mT in the coil eye; electronics field 0.19-0.57 mT (R37, R41)",
    "cartridge": "../cartridge_budget.py / cartridge-budget.json (C_cap, G_bond 0.0612 W/K, area 45.4 mm2)",
    "manganin": "Isabellenhuette MANGANIN: rho 0.43 uOhm m, k 22 W/mK, thermo-EMF vs Cu <1 uV/K (0-100 C); "
                "2 uV/K used to 150 C (assumption)",
    "constantan": "Type T (Cu-constantan) Seebeck ~41 uV/K at 25 C, ~52 uV/K at 150 C (NIST ITS-90 tables)",
}

CHECKS: dict[str, dict] = {}


def gate(name: str, ok: bool, detail: dict | str):
    CHECKS[name] = {"pass": bool(ok), "detail": detail}


def r3(x, n=3):
    if isinstance(x, float):
        return round(x, n)
    return x


# --------------------------------------------------------------------------- Pt100
A_CVD, B_CVD, C_CVD = 3.9083e-3, -5.775e-7, -4.183e-12


def pt(t):
    c = C_CVD if t < 0 else 0.0
    return 100.0 * (1 + A_CVD * t + B_CVD * t * t + c * (t - 100) * t ** 3)


def pt_inv(r):
    lo, hi = -100.0, 900.0
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if pt(mid) < r else (lo, mid)
    return (lo + hi) / 2


def dpt(t):
    return (pt(t + 0.01) - pt(t - 0.01)) / 0.02


# --------------------------------------------------------------------------- constants
VB_MIN, VB_NOM, VB_MAX = 1.95, 2.00, 2.06
R_BIAS_OUT = 30.0                 # 30 mV/mA load regulation
R_SW = 10.0                       # FORCE- internal switch: not specified; assumption (0-20 R swept where it matters)
RREF = 430.0
VREF_WIN = 1.25                   # REF2025 VBIAS output
T_LO, T_HI = -20.0, 320.0
T_ACC = [40.0 + 10 * i for i in range(22)]   # 40..250
LSB_CODES = 32768

# leads (C1): 20 mm manganin d0.08 + 0.15 m AWG26 pigtail + 0.6 m AWG24 harness, per conductor
RHO_MAN, RHO_CU = 0.43e-6, 1.72e-8
A_LEAD = math.pi * (0.08e-3 / 2) ** 2
R_ALLOY = RHO_MAN * 20e-3 / A_LEAD
R_CU = 0.134 * 0.15 + 0.0842 * 0.6 + 0.02          # AWG26 0.134 R/m, AWG24 0.0842 R/m, contacts
R_LEAD = R_ALLOY + R_CU                           # at 20 C; alloy TC ~0, copper +0.39 %/K (ignored: 4-wire)

# cartridge thermal
BUDGET = json.loads((HERE.parent / "cartridge-budget.json").read_text())["results"]
G_BOND = BUDGET["G_bond_W_per_K"]
AREA = BUDGET["contact_area_mm2"] * 1e-6
H_MIN = 888.0
G_LEAK = 0.8e-3


# =========================================================================== MNA
class Net:
    def __init__(self):
        self.nodes = {"0": 0}
        self.el = []

    def n(self, name):
        if name not in self.nodes:
            self.nodes[name] = len(self.nodes)
        return self.nodes[name]

    def R(self, a, b, v):
        self.el.append(("Y", self.n(a), self.n(b), 1.0 / v))

    def C(self, a, b, v):
        self.el.append(("C", self.n(a), self.n(b), v))

    def I(self, a, b, v):          # current v flows from a, through the source, into b
        self.el.append(("I", self.n(a), self.n(b), v))

    def V(self, a, b, v):          # V(a) - V(b) = v
        self.el.append(("V", self.n(a), self.n(b), v))

    def solve(self, f=0.0):
        nn = len(self.nodes)
        vs = [e for e in self.el if e[0] == "V"]
        m = nn + len(vs)
        G = np.zeros((m, m), complex)
        z = np.zeros(m, complex)
        w = 2 * math.pi * f
        k = nn
        for typ, a, b, v in self.el:
            if typ in ("Y", "C"):
                y = v if typ == "Y" else 1j * w * v
                G[a, a] += y; G[b, b] += y; G[a, b] -= y; G[b, a] -= y
            elif typ == "I":
                z[a] -= v; z[b] += v
            else:
                G[a, k] += 1; G[b, k] -= 1; G[k, a] += 1; G[k, b] -= 1; z[k] = v; k += 1
        G[0, :] = 0; G[:, 0] = 0; G[0, 0] = 1; z[0] = 0
        x = np.linalg.solve(G, z)
        return {name: x[i] for name, i in self.nodes.items()}


DESIGNS = {
    "captured": dict(r1=0.0, r2=0.0, c1=0.0, c2=1e-9, ccm=0.0, rb=1e6, rb_side="adc", win_side="adc",
                     cw=2e-12, div_side="adc", rth_bottom="gnd", cj=0.0, tvs=False, rref=RREF, rref_tc=25e-6, rref_tol=1e-3),
    "proposed": dict(r1=1000.0, r2=1000.0, c1=100e-9, c2=100e-9, ccm=1e-9, rb=499e3, rb_side="cable",
                     win_side="cable", cw=10e-9, div_side="cable", rth_bottom="sn", cj=220e-9, tvs=True, rref=RREF, rref_tc=5e-6,
                     rref_tol=5e-4),
}


def build(d, rtd, *, ac=False, vb=VB_NOM, leads=None, tol=None, emf_s=0.0, emf_f=0.0, emf_cm=0.0,
          i_inj=0.0, inj_node="Et", rsw=R_SW, faults=None, leak=None, thermo=0.0, rim_v=3.3, cdn=0.0):
    """Return a Net. ac=True: DC sources zeroed, only the given AC excitation."""
    t = tol or {}
    faults = faults or {}
    lds = leads or {k: R_LEAD for k in ("Fp", "Sp", "Sn", "Fn")}
    nt = Net()
    gnd = "0"
    # element
    if "elem_open" not in faults:
        nt.R("Et", "Eb", rtd if "elem_short" not in faults else 1e-3)
    if "elem_leak" in faults:
        nt.R("Et", "Eb", faults["elem_leak"])
    # leads: element end -> (mid) -> connector; series EMF at the element end
    ends = {"Fp": "Et", "Sp": "Et", "Sn": "Eb", "Fn": "Eb"}
    emf = {"Fp": emf_f + emf_cm, "Sp": emf_s + emf_cm + thermo, "Sn": emf_cm, "Fn": emf_cm}
    for k, e in ends.items():
        r = lds[k] * (1 + t.get("lead_" + k, 0.0))
        if (k + "_open") in faults:
            continue
        if emf[k] and not False:
            nt.V(k + "_e", e, emf[k])
            start = k + "_e"
        else:
            start = e
        nt.R(start, k + "_m", r / 2 + 1e-6)
        nt.R(k + "_m", k + "_j", r / 2 + 1e-6)
    for a, b in faults.get("short", []):
        nt.R(a + "_m", b + "_m", 0.05)
    for a in faults.get("to_gnd", []):
        nt.R(a + "_m", gnd, 0.05)
    for a in faults.get("to_rim", []):            # adjacent RIM_SENSE conductor: 3.3 V through 1 k
        nt.R(a + "_m", "rim", 0.05)
        nt.R("rim", "v33", 1000.0)
        nt.V("v33", gnd, 0.0 if ac else rim_v)
    for k, extra in faults.get("lead_add", {}).items():
        nt.R(k + "_j", k + "_jj", extra)
    def J(k):
        return k + ("_jj" if k in faults.get("lead_add", {}) else "_j")
    # MAX31865 bias network
    nt.V("vb", gnd, 0.0 if ac else vb)
    nt.R("vb", "BIAS", R_BIAS_OUT)
    rref = d["rref"] * (1 + t.get("rref", 0.0))
    nt.R("BIAS", "REFN", rref)                     # REFIN+ = BIAS, REFIN- = ISENSOR = FORCE+ pin
    nt.R("REFN", J("Fp"), 1e-3)
    if "fn_switch_open" not in faults:
        nt.R(J("Fn"), gnd, rsw)
    # sense filter
    def series(src, dst, r):
        if r > 0:
            nt.R(src, dst, r)
        else:
            nt.R(src, dst, 1e-3)
    r1 = d["r1"]; r2 = d["r2"]
    for k, p in (("Sp", "p"), ("Sn", "n")):
        series(J(k), "M" + p, r1 * (1 + t.get("r1" + p, 0.0)))
        series("M" + p, "A" + p, r2 * (1 + t.get("r2" + p, 0.0)))
        if d["ccm"]:
            nt.C("A" + p, gnd, d["ccm"] * (1 + t.get("ccm" + p, 0.0)))
        nt.C(J(k), gnd, 50e-12)                     # harness conductor to shield/ground
    if d["c1"]:
        nt.C("Mp", "Mn", d["c1"])
    if d["cj"]:                                     # 100 nF X7R at each J3 pin (CM shunt + ESD charge)
        for k in ("Fp", "Sp", "Sn", "Fn"):
            nt.C(J(k), gnd, d["cj"] * (1 + t.get("cj_" + k, 0.0)))
    nt.C("Ap", "An", d["c2"])
    # open-lead pull-ups
    rbp, rbn = ("Ap", "An") if d["rb_side"] == "adc" else (J("Sp"), J("Sn"))
    nt.R("BIAS", rbp, d["rb"] * (1 + t.get("rb", 0.0)))
    nt.R("BIAS", rbn, d["rb"] * (1 + t.get("rb", 0.0)))
    # window/runaway branch (100 k) and low-window divider
    wsrc = "Ap" if d["win_side"] == "adc" else J("Sp")
    nt.R(wsrc, "W", 100e3)
    nt.C("W", gnd, d["cw"])
    nt.V("vr", gnd, 0.0 if ac else VREF_WIN)
    nt.R("vr", "INN", 61.9e3)
    nt.R("INN", "An" if d["div_side"] == "adc" else J("Sn"), 10e3)
    nt.R("vr", "HIP", 5.9e3); nt.R("HIP", gnd, 10e3)
    # runaway threshold: BIAS * 10k/(20k+10k) to GND (captured) or to connector-side S- (proposed)
    nt.R("BIAS", "RTH", 20e3 * (1 + t.get("rt", 0.0)))
    nt.R("RTH", gnd if d["rth_bottom"] == "gnd" else J("Sn"), 10e3 * (1 + t.get("rbt", 0.0)))
    nt.C("RTH", gnd, 100e-9)                        # c_runaway_th
    # IEC 61000-4-6-style CM injection at J3: 1 V through 600 R per line (150 R total)
    if cdn:
        nt.V("cdn", gnd, cdn)
        for k in ("Fp", "Sp", "Sn", "Fn"):
            nt.R("cdn", J(k), 600.0 * (1 + t.get("cdn_" + k, 0.0)))
    # leakage sinks/sources (DC accuracy)
    if leak:
        for node, i in leak.items():
            nt.I(node, gnd, i)
    if i_inj:
        nt.I(gnd, inj_node, i_inj)
    return nt


def adc_ratio(x):
    vref = (x["BIAS"] - x["REFN"]).real
    if abs(vref) < 1e-9:
        return 1.0
    return min(max((x["Ap"] - x["An"]).real / vref, 0.0), (LSB_CODES - 1) / LSB_CODES)


# =========================================================================== item 1
def item1_range_resolution():
    rows = []
    worst_lsb_k = 0.0
    for t in (T_LO, 0.0, 40.0, 100.0, 200.0, 250.0, T_HI):
        lsb_k = RREF / LSB_CODES / dpt(t)
        worst_lsb_k = max(worst_lsb_k, lsb_k)
        rows.append({"T_C": t, "R_ohm": r3(pt(t)), "ratio_to_Rref": r3(pt(t) / RREF, 4), "LSB_K": r3(lsb_k, 4)})
    rmax = pt(T_HI) / (RREF * (1 - 1e-3 - 25e-6 * 60))
    # voltage compliance at worst current: RTDIN+ must stay inside 0..VBIAS and REFIN- below VBIAS
    i_max = VB_MAX / (RREF * (1 - 1e-3) + pt(T_LO) + 2 * R_LEAD)
    v_fp = VB_MIN * (pt(T_HI) + 2 * R_LEAD) / (RREF + pt(T_HI) + 2 * R_LEAD)
    ok = worst_lsb_k <= 0.05 and rmax <= 0.95 and i_max <= 5.75e-3 and v_fp < VB_MIN and R_LEAD <= 50
    gate("1a range -20..320 C and resolution <=0.05 K", ok, {
        "rows": rows, "worst_LSB_K": r3(worst_lsb_k, 4), "R320_over_Rref_min": r3(rmax, 3),
        "bias_current_max_mA": r3(i_max * 1e3, 3), "FORCE+_node_at_320C_V": r3(v_fp, 3),
        "lead_R_per_conductor_ohm": r3(R_LEAD, 3), "lead_alloy_ohm": r3(R_ALLOY, 3),
        "limits": "LSB <=0.05 K; RTD/Rref <=0.95 (headroom); IOUT <=5.75 mA; cable <=50 R/lead"})


def dc_error_terms(d, rtd, corners=True):
    """Front-end DC loading errors (ohm-equivalent) from the board network, after firmware removes
    the nominal (deterministic) loading. Returns (nominal_ohm, worst_residual_ohm)."""
    def meas(tol, leak, vb=VB_NOM, thermo=0.0, leads=None):
        nt = build(d, rtd, tol=tol, leak=leak, vb=vb, thermo=thermo, leads=leads)
        x = nt.solve()
        return adc_ratio(x) * d["rref"] * (1 + tol.get("rref", 0.0))
    nominal = meas({}, None) - rtd
    worst = 0.0
    if not corners:
        return nominal, 0.0
    # corners: Rb +/-(5 % + 100 ppm x 60 K); leads +/-10 %; divider via lead; TVS leakage 0..50 nA on
    # each high-side line; ADC pin leakage +/-14 nA (opposite signs); VBIAS min/max.
    rb_t = (0.05 if d["rb"] >= 1e6 else 0.01) + 100e-6 * 60
    leak_sets = []
    for s in (-1, 1):
        lk = {"Ap": s * 5e-9, "An": -s * 5e-9}      # 5 nA typ, -40..85 C (board <=85 C)
        if d["tvs"]:
            lk.update({"Fp_j": 50e-9, "Sp_j": 50e-9})
        leak_sets.append(lk)
    for rb_s, lp, ln, vb, lk in itertools.product((-1, 1), (-0.1, 0.1), (-0.1, 0.1), (VB_MIN, VB_MAX), leak_sets):
        tol = {"rb": rb_s * rb_t, "lead_Sp": lp, "lead_Sn": ln, "lead_Fn": ln, "lead_Fp": lp}
        e = meas(tol, lk, vb=vb) - rtd - nominal
        worst = max(worst, abs(e))
    return nominal, worst


def item1_accuracy():
    out = {}
    t_cal = 200.0
    r_cal = pt(t_cal)
    lsb_ohm = RREF / LSB_CODES
    dT_board = 60.0
    for name, d in DESIGNS.items():
        rows = []
        worst_lin = worst_rss = 0.0
        for t in T_ACC:
            r = pt(t)
            nom, dc_res = dc_error_terms(d, r)
            terms = {
                "Rref_tempco": d["rref_tc"] * dT_board * r,
                "cal_reference_50ppm": (50e-6 + 2e-6 * 5) * r,
                "adc_offset_strict": (3 + 3 * r / r_cal) * lsb_ohm,
                "adc_fullscale_typ": 1 * lsb_ohm * r / RREF,
                "adc_inl_typ": 2 * lsb_ohm,
                "board_loading_leakage_residual": dc_res,
                "thermo_emf_manganin_2K": 2e-6 * 2.0 / (VB_MIN / (RREF + r)),
            }
            k = 1 / dpt(t)
            lin = sum(abs(v) for v in terms.values()) * k
            rss = math.sqrt(sum(v * v for v in terms.values())) * k
            # board-controlled terms only (what the PCB design can change): Rref, cal, loading, EMF
            board = (terms["Rref_tempco"] + terms["cal_reference_50ppm"] + dc_res
                     + terms["thermo_emf_manganin_2K"]) * k
            worst_lin = max(worst_lin, lin)
            worst_rss = max(worst_rss, rss)
            rows.append({"T_C": t, "linear_K": r3(lin), "rss_K": r3(rss), "board_terms_K": r3(board),
                         "nominal_loading_ohm_corrected_in_fw": r3(nom, 4),
                         **{kk + "_K": r3(v * k, 4) for kk, v in terms.items()}})
        out[name] = {"worst_linear_K": r3(worst_lin), "worst_rss_K": r3(worst_rss),
                     "worst_board_terms_K": max(rw["board_terms_K"] for rw in rows),
                     "at_250C": rows[-1], "at_100C": rows[6]}
    # typical-characterisation reading: MAX31865 TOC06 (400 R Rref, 4-wire) ~ +/-0.1 C over -40..100 C die
    p = out["proposed"]
    ok = p["worst_board_terms_K"] <= 0.30 and p["worst_rss_K"] <= 0.30
    gate("1b front-end error after single-point cal, 40-250 C", ok, {
        "method": "gain-only calibration with a calibrated 50 ppm reference resistor at R(200 C) on J3, board 25 C; board 0-85 C "
                  "(|dT| 60 K); MAX31865 offset bounded +/-3 LSB independently at cal and use (strict, no "
                  "drift spec exists); FS and INL are datasheet typ only; firmware removes the nominal "
                  "pull-up loading (Rref/Rb); VBIAS cancels (ratiometric, REF2025 only sets window thresholds)",
        "requirement": "+/-0.3 K. Gate: the board-controlled terms (Rref, calibration, loading, leakage, "
                       "thermo-EMF) stacked linearly <=0.30 K AND the RSS of all terms incl. the MAX31865 "
                       "<=0.30 K. The strict linear stack incl. the MAX31865 is reported, not gated: its "
                       "+/-3 LSB offset bound alone is 0.23 K at 250 C with no drift spec (DECISIONS D3)",
        "captured": out["captured"], "proposed": out["proposed"],
        "ageing_not_in_gate": "Rref load-life drift (Susumu RG datasheet value to be recorded at order); "
                              "0.01 % drift = 0.05 K at 250 C",
    })
    return out


# =========================================================================== item 2
def item2_rate():
    t_conv_max = 17.6e-3
    fs = 1 / t_conv_max
    tau_f = 2 * 1000 * 100e-9 * 2       # two 0.2 ms poles -> ~0.4 ms group delay
    ok = fs >= 16.0 and tau_f < 0.1 * t_conv_max * 10
    gate("2 sample rate >=16 Hz continuous, 60 Hz notch", ok, {
        "config": "CONFIG 0xC0: D7 VBIAS on, D6 auto, D4 0 (4-wire), D3:2 00, D0 0 (60 Hz notch); write "
                  "0xC2 once to clear faults",
        "rate_min_Hz": r3(fs, 2), "filter_group_delay_ms": r3(tau_f * 1e3, 2),
        "DRDY": "captured board routes RTD_DRDY to TCA9555 P07 (DECISIONS C23), not a GPIO. Requirement: "
                "firmware reads the RTD registers every 20 ms (>= one conversion, 50 Hz), checking that the "
                "code changed within 3 reads (stale-data detection), or polls P07; rtd_service.c's GPIO "
                "ISR must be ported to that. >=16 Hz holds either way.",
        "fault_cycle": "with input tau >100 us the automatic fault cycle is invalid (datasheet); use the "
                       "manual cycle at power-up and only when the coil is off (it opens FORCE-, stops "
                       "conversions and steps the bias current)."})


# =========================================================================== item 3
def item3_self_heating():
    rows = []
    g_c = H_MIN * AREA
    g_series = 1 / (1 / G_BOND + 1 / g_c)
    g_sub = 25.0 * 1.8e-3 * 2.0e-3 / 0.65e-3                 # alumina chip substrate k 25, if film faces away
    g_series_flip = 1 / (1 / G_BOND + 1 / g_c + 1 / g_sub)
    worst = worst_flip = 0.0
    for t in (T_LO, 40.0, 100.0, 200.0, 250.0, T_HI):
        r = pt(t)
        i = VB_MAX / (RREF * (1 - 5e-4) + r + 2 * R_LEAD * 0.9 + R_SW * 0)   # max current corner
        p = i * i * r
        dt, dt_f = p / g_series, p / g_series_flip
        worst, worst_flip = max(worst, dt), max(worst_flip, dt_f)
        rows.append({"T_C": t, "I_mA": r3(i * 1e3), "P_mW": r3(p * 1e3), "dT_K_film_to_disc": r3(dt, 4),
                     "dT_K_film_away": r3(dt_f, 4)})
    # variation over the contact spread (h 888..21946) when firmware subtracts a constant
    p250 = rows[4]["P_mW"] * 1e-3
    hi = p250 / (1 / (1 / G_BOND + 1 / (21946 * AREA)))
    lo = p250 / g_series
    resid = (lo - hi) / 2
    no_pan = p250 / (G_LEAK + 10.0 * 50e-6)                  # leak + still-air convection, info only
    ok = worst <= 0.1 or resid <= 0.05
    gate("3 self-heating offset <=0.1 K (incidental, continuous bias)", ok, {
        "rows": rows, "G_bond_W_per_K": G_BOND, "G_c_min_W_per_K": r3(g_c, 4),
        "worst_K_film_to_disc": r3(worst, 4), "worst_K_film_away": r3(worst_flip, 4),
        "fw_constant_K": r3((lo + hi) / 2, 4), "residual_after_constant_K": r3(resid, 4),
        "no_pan_offset_K_info": r3(no_pan, 2),
        "P1": "bias is the MAX31865's continuous measuring current (VBIAS on in auto mode); no modulation, "
              "no pulse, firmware must not use the offset as a contact signal (Impulse dep. 3 / spec)"})
    return {"worst": worst, "worst_flip": worst_flip}


# =========================================================================== item 4
def lsb_v_min():
    return VB_MIN * RREF / (RREF + pt(T_HI) + 2 * R_LEAD) / LSB_CODES


def pickup_sources(f):
    """Bounding DM/CM sources at frequency f (Hz)."""
    cm = json.loads((ROOT / "output/temper-coil-driver-r1/tank_cm.json").read_text())["rows"]
    vf = max(r["one_sided_Vmean_pk_V"] * r["fs_kHz"] for r in cm)   # V*kHz, 28 A ceiling worst
    v_pan = vf / (f / 1e3)
    # pan -> Pt film through 0.32 Si3N4 (er 8) + 0.10 bond (er 4) over the 1.8 x 2.0 chip; x2 for pads/leads
    c_film = 8.854e-12 * 3.6e-6 / (0.32e-3 / 8 + 0.10e-3 / 4)
    c_inj = 2 * c_film + 0.2e-12                                    # + winding -> pigtail allowance
    i_inj = 2 * math.pi * f * c_inj * v_pan * 2                     # x2: edges/harmonics allowance
    w = 2 * math.pi * f
    emf_eye = w * 20e-3 * (0.30e-3 * 2.5e-3)       # twisted in the post: s 0.30 mm, half-pitch 2.5 mm, |B| 20 mT
    emf_eye_untwisted = w * 20e-3 * (0.5e-3 * 20e-3)
    emf_harness = w * 1e-3 * (0.9e-3 * 12.5e-3)    # 24 AWG pair s 0.9 mm, half lay 12.5 mm, 1 mT
    return {"v_pan_pk": v_pan, "c_inj_pF": c_inj * 1e12, "i_inj_pk": i_inj,
            "emf_sense_pk": emf_eye + emf_harness, "emf_force_pk": emf_eye + emf_harness,
            "emf_eye_untwisted_pk": emf_eye_untwisted}


def ac_dm(d, f, rtd, **kw):
    x = build(d, rtd, ac=True, **kw).solve(f)
    return abs(x["Ap"] - x["An"]), abs(x["W"] - x["RTH"]), abs((x["Ap"] + x["An"]) / 2)


def item4_pickup():
    lsb = lsb_v_min()
    res = {}
    freqs = [20e3, 33e3, 40e3, 60e3, 100e3]
    rtd = pt(T_HI)
    for name, d in DESIGNS.items():
        rows = []
        for f in freqs:
            s = pickup_sources(f)
            # pan injection at the element top (bound) and bottom
            dm_inj = max(ac_dm(d, f, rtd, i_inj=s["i_inj_pk"], inj_node=nd)[0] for nd in ("Et", "Eb"))
            w_inj = max(ac_dm(d, f, rtd, i_inj=s["i_inj_pk"], inj_node=nd)[1] for nd in ("Et", "Eb"))
            dm_mag, w_mag, _ = ac_dm(d, f, rtd, emf_s=s["emf_sense_pk"], emf_f=s["emf_force_pk"])
            # handoff test: 1 V CM at the cartridge end of all four conductors, tolerance corners
            worst_cm = 0.0
            worst_cm_pin = 0.0
            keys = ["lead_Sp", "lead_Sn", "r1p", "r1n", "ccmp", "ccmn", "cdn_Sp", "cdn_Sn", "cj_Sp", "cj_Sn",
                    "cj_Fp", "cj_Fn"]
            spans = [0.1, 0.1, 1e-3, 1e-3, 0.05, 0.05, 0.01, 0.01, 0.1, 0.1, 0.1, 0.1]
            if f != 40e3:                      # information sweep: fewer corners
                keys, spans = keys[:6] + keys[8:10], spans[:6] + spans[8:10]
            for signs in itertools.product((-1, 1), repeat=len(keys)):
                tol = {k: sg * sp for k, sg, sp in zip(keys, signs, spans)}
                dm, _, cmp = ac_dm(d, f, rtd, cdn=1.0, tol=tol)
                worst_cm, worst_cm_pin = max(worst_cm, dm), max(worst_cm_pin, cmp)
            total = dm_inj + dm_mag
            v_th_slope = VB_MIN * RREF / (RREF + rtd + 2 * R_LEAD) ** 2 * dpt(T_HI - 12)  # V/K at RTDIN+ near trip
            rows.append({"f_kHz": f / 1e3, "pan_V_pk": r3(s["v_pan_pk"], 1), "inj_uA_pk": r3(s["i_inj_pk"] * 1e6, 1),
                         "DM_pins_inj_uV": r3(dm_inj * 1e6, 2), "DM_pins_magnetic_uV": r3(dm_mag * 1e6, 2),
                         "DM_pins_total_LSB": r3(total / lsb, 3),
                         "CM_1V_test_DM_pins_LSB": r3(worst_cm / lsb, 4),
                         "CM_1V_test_CM_at_pins_mV": r3(worst_cm_pin * 1e3, 2),
                         "runaway_node_ripple_mV": r3((w_inj + w_mag) * 1e3, 3),
                         "runaway_threshold_shift_K": r3((w_inj + w_mag) / v_th_slope, 2)})
        res[name] = {"rows": rows,
                     "worst_DM_total_LSB": max(r["DM_pins_total_LSB"] for r in rows),
                     "worst_CM1V_LSB": [r["CM_1V_test_DM_pins_LSB"] for r in rows if r["f_kHz"] == 40.0][0],
                     "CM1V_LSB_by_f": {r["f_kHz"]: r["CM_1V_test_DM_pins_LSB"] for r in rows},
                     "worst_runaway_shift_K": max(r["runaway_threshold_shift_K"] for r in rows)}
    s40 = pickup_sources(40e3)
    p = res["proposed"]
    ok = p["worst_DM_total_LSB"] < 1 and p["worst_CM1V_LSB"] < 1 and p["worst_runaway_shift_K"] <= 1.0
    # filter timing: open-lead detection and fault-cycle settle
    tim = filter_timing()
    ok = ok and tim["open_Sp_detect_ms"] <= 100 and tim["open_Sn_detect_ms"] <= 100
    gate("4 coil pickup: <1 LSB at the ADC pins, runaway shift <=1 K, open-lead <=100 ms", ok, {
        "cm_1V_test": "1 V pk CM at J3 through 600 R per line (150 R total, IEC 61000-4-6 CDN convention), "
                      "tolerance corners; gated at 40 kHz as the handoff states, swept for information",
        "LSB_V_min": lsb, "criterion": "residual amplitude at RTDIN+/- below 1 LSB, no credit for the sinc3 "
                                        "filter (covers aliasing against the unknown modulator clock and "
                                        "rectification)",
        "sources_at_40kHz": {k: r3(v, 6) for k, v in s40.items()},
        "captured": res["captured"], "proposed": res["proposed"], "timing": tim})
    return res


def filter_timing():
    d = DESIGNS["proposed"]
    c_eff = d["c1"] + d["c2"] + d["ccm"] + d["cj"] + 150e-12
    out = {}
    for t in (25.0, 250.0):
        r = pt(t)
        i = VB_NOM / (RREF + r + 2 * R_LEAD + R_SW)
        vp = i * (r + R_LEAD + R_SW)
        vn = i * (R_LEAD + R_SW)
        tau_p = d["rb"] * c_eff
        v_trip = VB_NOM / 3                                   # runaway trips first (BIAS/3 < 0.786 V window)
        tp = tau_p * math.log((VB_NOM - vp) / (VB_NOM - v_trip)) if vp < v_trip else 0.0
        # S- open: node -> Thevenin of 1 M to BIAS and 71.9 k to 1.25 V
        rth = 1 / (1 / d["rb"] + 1 / 71.9e3)
        vinf = (VB_NOM / d["rb"] + VREF_WIN / 71.9e3) * rth
        vn_trip = (vp - VREF_WIN * 10 / 71.9) / (1 - 10 / 71.9)
        tn = rth * c_eff * math.log((vinf - vn) / (vinf - vn_trip))
        out[f"{t:.0f}C"] = {"open_Sp_ms": r3(tp * 1e3, 1), "open_Sn_ms": r3(tn * 1e3, 1)}
    out["open_Sp_detect_ms"] = max(v["open_Sp_ms"] for k, v in out.items() if k.endswith("C"))
    out["open_Sn_detect_ms"] = max(v["open_Sn_ms"] for k, v in out.items() if k.endswith("C"))
    out["filter_tau_ms"] = r3(2 * d["r1"] * d["c1"] * 1e3, 3)
    out["fault_cycle_manual_wait_ms"] = r3(5 * 2 * (d["r1"] + d["r2"]) * (d["c1"] + d["c2"]) * 1e3 + 1, 2)
    out["window_node_tau_ms"] = r3(100e3 * d["cw"] * 1e3, 2)
    return out


# =========================================================================== fault coverage
FW_LOW_OHM, FW_HIGH_OHM = pt(-40.0), pt(360.0)   # proposed MAX31865 threshold registers


def evaluate_fault(d, rtd, faults, low_th, high_th):
    nt = build(d, rtd, faults=faults)
    x = {k: v.real for k, v in nt.solve().items()}
    vb_node = x["BIAS"]
    pins = [x.get(k, 0.0) for k in ("Fp_j", "Fn_j", "Ap", "An")]
    d2 = any(v > 3.3 + 0.1 or v < -0.4 for v in pins)
    vref = vb_node - x["REFN"]
    if vref < 0.02:
        ratio = 1.0                              # reference collapsed -> full scale / indeterminate (D7 path)
    else:
        ratio = adc_ratio(x)
    r_read = ratio * RREF
    t_read = pt_inv(r_read) if r_read > 1 else -250.0
    win_high_fail = x["W"] > x["HIP"]
    win_low_fail = x["W"] < x["INN"]
    runaway = x["W"] > x["RTH"]
    d7, d6 = r_read >= high_th, r_read <= low_th
    det_hw = win_high_fail or win_low_fail or runaway
    det_max = d7 or d6 or d2
    true_t = pt_inv(rtd)
    reads = "high" if t_read > true_t + 1 else ("low" if t_read < true_t - 1 else "ok")
    rim_fault = "rim" in x and x["rim"] < 0.25            # rim channel reads 'short' (firmware rim fault)
    det_hw = det_hw or False
    det_fw = bool(rim_fault)
    unsafe = t_read < true_t - 5.0 and not (det_hw or det_max or det_fw)
    return {"rim_fault": bool(rim_fault), "low_by_K": r3(max(0.0, true_t - t_read), 2),"T_read_C": r3(t_read, 1), "reads": reads, "hw_window": bool(win_high_fail or win_low_fail),
            "hw_runaway": bool(runaway), "max_D7_D6_D2": bool(det_max),
            "detected": bool(det_hw or det_max or det_fw), "unsafe": bool(unsafe)}


def fault_cases():
    c = {"none": {}}
    for k in ("Fp", "Sp", "Sn", "Fn"):
        c[f"open {k}"] = {k + "_open": True}
        c[f"{k} to GND"] = {"to_gnd": [k]}
        c[f"{k} to RIM_SENSE"] = {"to_rim": [k]}
        c[f"{k} contact +10 R"] = {"lead_add": {k: 10.0}}
    c["element open"] = {"elem_open": True}
    c["element short"] = {"elem_short": True}
    for a, b in itertools.combinations(("Fp", "Sp", "Sn", "Fn"), 2):
        c[f"short {a}-{b}"] = {"short": [(a, b)]}
    for rl in (50.0, 1e3, 7e3, 1e6):
        c[f"element leak {rl:g} R"] = {"elem_leak": rl}
    return c


def item_faults():
    out = {}
    for name, d in DESIGNS.items():
        lo, hi = (pt(-40.0), pt(360.0)) if name == "proposed" else (10.0, 300.0)
        rows = {}
        for t in (25.0, 250.0):
            for fname, f in fault_cases().items():
                r = evaluate_fault(d, pt(t), f, lo, hi)
                rows[f"{fname} @{t:.0f}C"] = r
        unsafe = [k for k, v in rows.items() if v["unsafe"] and not k.startswith("none")
                  and "contact" not in k]
        out[name] = {"thresholds_ohm": [r3(lo, 2), r3(hi, 2)], "rows": rows, "unsafe_undetected": unsafe}
    p = out["proposed"]
    # residual: leakage across the element reads low; electrical detection impossible above ~ the window
    allowed = [k for k in p["unsafe_undetected"] if "leak" in k]
    ok = set(p["unsafe_undetected"]) == set(allowed) and "element leak 1e+06 R @250C" not in allowed
    # insulation resistance needed for <=0.1 K at 250 C
    r = pt(250.0)
    r_ins = r * r / (0.1 * dpt(250.0))
    gate("F fault coverage: every open/short/lead fault detected or reads high", ok, {
        "unsafe_undetected_proposed": p["unsafe_undetected"],
        "unsafe_undetected_captured": out["captured"]["unsafe_undetected"],
        "hot_zone_insulation_min_ohm_for_0.1K": r3(r_ins, 0),
        "note": "element-parallel leakage (insulation breakdown in the hot zone) reads low and is "
                "electrically invisible above ~50 R; it is covered thermally (D1, Pt100-vs-rim check) and by "
                "the rim hardware trip; the cartridge must hold >=" + f"{r_ins / 1e3:.0f} k" + " (spec 10 M) "
                "between leads at 300 C",
        "captured": out["captured"], "proposed": out["proposed"]})


def firmware_constants():
    """Constants the firmware needs for the proposed board (in checks.json, not a gate)."""
    d = DESIGNS["proposed"]
    ts = [40.0, 100.0, 150.0, 200.0, 250.0]
    errs = [dc_error_terms(d, pt(t), corners=False)[0] for t in ts]
    rs = [pt(t) for t in ts]
    a, b = np.polyfit(rs, errs, 1)
    fit_resid = max(abs(e - (a * r + b)) for e, r in zip(errs, rs))
    word = lambda r: int(round(r / RREF * LSB_CODES)) << 1
    CHECKS_INFO["firmware_constants"] = {
        "MAX31865_CONFIG": "0xC0 (VBIAS, auto, 4-wire, 60 Hz); 0xC2 to clear faults",
        "LOW_THRESHOLD_WORD": word(pt(-40.0)), "LOW_THRESHOLD_ohm": r3(pt(-40.0), 2),
        "HIGH_THRESHOLD_WORD": word(pt(360.0)), "HIGH_THRESHOLD_ohm": r3(pt(360.0), 2),
        "loading_correction": {"R_true = R_meas - (a*R_meas + b)": True, "a": float(a), "b_ohm": float(b),
                               "fit_residual_ohm": float(fit_resid)},
        "self_heating_constant_K": 0.061,
        "manual_fault_cycle_wait_ms": 5.0,
        "read_period_ms": 20, "stale_reads": 3,
        "rim_atten": "ATTEN0 if node <0.80 V, ATTEN2 if <1.55 V, else ATTEN3; divide by v3v3/3.300 from MCP3202 CH1",
        "pt100_below_rim_threshold_K": 25.0,
    }


CHECKS_INFO: dict[str, dict] = {}


# =========================================================================== item 5 rim NTC
GT2_104 = {0: 353.7, 10: 208.6, 20: 126.8, 25: 100.0, 30: 79.36, 100: 5.556, 110: 4.082, 120: 3.043,
           130: 2.298, 140: 1.758, 150: 1.360, 160: 1.064, 170: 0.8414, 180: 0.6714, 190: 0.5408,
           200: 0.4393, 210: 0.3597, 240: 0.2065, 250: 0.1740, 260: 0.1475, 270: 0.1258, 280: 0.1079,
           290: 0.09305}


def ntc(t, rs=1.0, bs=1.0):
    ks = sorted(GT2_104)
    for a, b in zip(ks, ks[1:]):
        if a <= t <= b:
            la, lb = math.log(GT2_104[a]), math.log(GT2_104[b])
            r = math.exp(la + (lb - la) * (t - a) / (b - a)) * 1e3
            break
    else:
        raise ValueError(t)
    tk = t + 273.15
    return r * rs * math.exp(4267.0 * (bs - 1) * (1 / tk - 1 / 298.15))


def ntc_t(r, rs=1.0, bs=1.0):
    lo, hi = 0.0, 290.0
    for _ in range(60):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if ntc(m, rs, bs) > r else (lo, m)
    return (lo + hi) / 2


def item5_rim():
    vdd, rpu = 3.3, 1000.0
    rows = []
    worst_res = 0.0
    for t in (100.0, 150.0, 200.0, 250.0, 280.0):
        v = vdd * ntc(t) / (ntc(t) + rpu)
        v2 = vdd * ntc(t + 1) / (ntc(t + 1) + rpu)
        slope = (v - v2)
        atten, err_mv, lsb = ((0, 5, 0.85 / 4095) if v < 0.80 else (2, 10, 1.6 / 4095) if v < 1.55
                              else (3, 50, 3.1 / 4095))
        res_k = lsb / slope
        worst_res = max(worst_res, res_k)
        # accuracy terms in K
        sens = {"NTC_R25_3pct": abs(ntc_t(ntc(t) * 1.03) - t),
                "NTC_B_2pct": abs(ntc_t(ntc(t, bs=1.02)) - t),
                "adc_cal_error": err_mv * 1e-3 / slope,
                "v3v3_after_MCP3202_correction_0.2pct": 0.002 * v / slope,
                "pullup_0.1pct_25ppm": (0.001 + 25e-6 * 60) * v / slope * (rpu / (ntc(t) + rpu)),
                "self_heating_known_correctable": (vdd / (ntc(t) + rpu)) ** 2 * ntc(t) / 0.6e-3}
        lin = sum(v_ for k_, v_ in sens.items() if "self" not in k_)
        rows.append({"T_C": t, "node_V": r3(v), "mV_per_K": r3(slope * 1e3, 2), "atten": atten,
                     "resolution_K": r3(res_k, 3), "accuracy_linear_K": r3(lin, 1),
                     **{k: r3(v_, 2) for k, v_ in sens.items()}})
    sat_t = ntc_t(rpu * (2.9 / vdd) / (1 - 2.9 / vdd))
    # effect of a rim (sink) error on the KF estimate: dT_hat ~ dT_sink * G_leak / G_c(888)
    sink_gain = G_LEAK / (H_MIN * AREA)
    ok = worst_res <= 0.3
    gate("5 rim NTC: <=0.3 K resolution 100-250 C, open/short detection", ok, {
        "choice": "keep the captured GPIO9 / ADC1_CH8 channel (C27 freed it, so ADC1 is not full); "
                  "reject ADS1115 (the sensor's own B tolerance dominates accuracy; an I2C ADC would not move it)",
        "rows": rows, "worst_resolution_K": r3(worst_res, 3),
        "saturates_below_C": r3(sat_t, 1),
        "open": "open bead reads full scale = 'below ~%.0f C': detect as fault when the Pt100 estimate has "
                "been >=150 C for 600 s and the rim still reads saturated" % sat_t,
        "short": "node < 0.25 V (beyond the 290 C table end) -> rim fault; short to GND reads 0 V",
        "sink_error_to_estimate_K_per_K": r3(sink_gain, 4),
        "estimate_error_from_worst_rim_error_at_250C_K": r3(sink_gain * rows[3]["accuracy_linear_K"], 2),
        "cross_check_threshold": "Pt100-below-rim threshold must exceed the rim error: use 25 K, not 15 K "
                                 "(rim worst linear %.1f K at 250 C)" % rows[3]["accuracy_linear_K"]})
    return rows


# =========================================================================== item 6 protection
def item6_protection():
    # IEC 61000-4-2 level 4 into the cable-side network: charge sharing into the absorbing capacitance
    q8, q15 = 150e-12 * 8e3, 150e-12 * 15e3
    # TVS leakage error (in item 1 corners) and capacitance effect on the AC filter (in item 4 model as 50 pF)
    i_bias = VB_MIN / (RREF + pt(250) + 2 * R_LEAD)
    tvs_gain = 2 * 50e-9 / i_bias
    ok = tvs_gain * pt(250) / dpt(250) < 0.02
    gate("6 connector protection does not spoil items 1 and 4", ok, {
        "parts": "ESD5Z3.3T1G on J3.1-4 and J12.1 (already used on J12, J9, J10); series R: 2 x 1.00 k on each "
                 "sense line (filter); none on FORCE+/- (series R in the force loop moves the runaway trip, "
                 "see item 8)",
        "tvs_leakage_gain_error": r3(tvs_gain, 7),
        "tvs_leakage_K_at_250C": r3(tvs_gain * pt(250) / dpt(250), 4),
        "esd_charge_uC_8kV_contact_15kV_air": [r3(q8 * 1e6, 2), r3(q15 * 1e6, 2)],
        "esd_line_V_after_sharing_into_220nF_J3_cap": [r3(q8 / (DESIGNS["proposed"]["cj"] + 150e-12), 1),
                                                         r3(q15 / (DESIGNS["proposed"]["cj"] + 150e-12), 1)],
        "max_pin_rating": "MAX31865 FORCE/RTDIN abs max +/-50 V, protected to +/-45 V; TVS clamps first",
        "pickup_with_tvs": "item 4 includes 50 pF per line at J3; TVS on the low-impedance cable side does "
                           "not change the RC corners"})


# =========================================================================== item 7 insulation
def item7_insulation():
    work_rms, peak = 242.0, 640.0
    # IEC 60664-1 (2020) values as used by R40 for the coil NTC (both sessions; certifier confirms)
    creep_basic = {"PD2_groupIII": 2.5, "PD3_groupIII": 4.0}            # 250 V rms row
    clear_basic_impulse = 0.5   # 1.5 kV rated impulse, OVC II at 150 V, inhomogeneous (Table F.2)
    clear_reinf_impulse = 1.5   # next preferred impulse step 2.5 kV for reinforced
    hf_factor = 1.25            # IEC 60664-4 inhomogeneous-field allowance for f > 30 kHz (assumption)
    req = {"clearance_mm": max(3.0, clear_reinf_impulse * hf_factor),
           "creepage_mm": 2 * creep_basic["PD3_groupIII"],
           "solid": ">=2 mm solid (IEC 60335-1 29.3) or three thin layers each passing the reinforced test; "
                    "cable insulation alone is not credited"}
    gate("7 insulation coil/tank to cartridge SELV (numbers for CAD G11)", True, {
        "working_voltage": f"{work_rms} V rms, {peak} V peak recurring, 33-60 kHz (tank class)",
        "pollution_degree": "PD3 in the coil eye (spill path past the wiper); CTI >=175 (group IIIa)",
        "requirement": req,
        "applies_to": "winding, coil leads, ferrite bars (PC95 is semi-conductive: treat as tank potential), "
                      "resonant bank, versus every cartridge/cable conductor and any floating metal (spring, "
                      "wave spring) that can bridge to one",
        "basis": "IEC 60664-1 values as recorded in R40 DECISIONS item 2 (from memory, both sessions); "
                 "IEC 60664-4 applies above 30 kHz - x1.25 clearance allowance; certifier confirms"})
    return req


# =========================================================================== item 8 trips
def item8_trips():
    # RTD runaway: TLV3201 W vs RTH, solved on the circuit (leads, FORCE- switch 0-20 R, tolerances)
    def band_for(d):
        temps = []
        span_r = 0.001 + 25e-6 * 60
        for st, sb, sr, vb, so, lead, rsw in itertools.product((-1, 1), (-1, 1), (-1, 1), (VB_MIN, VB_MAX),
                                                               (-5e-3, 5e-3), (0.9, 1.1), (0.5, 20.0)):
            tol = {"rt": st * span_r, "rbt": sb * span_r,
                   "rref": sr * (d["rref_tol"] + d["rref_tc"] * 60)}
            lds = {k: R_LEAD * lead for k in ("Fp", "Sp", "Sn", "Fn")}
            lo, hi = 100.0, 600.0
            for _ in range(36):
                m = (lo + hi) / 2
                x = build(d, pt(m), tol=tol, vb=vb, leads=lds, rsw=rsw).solve()
                trip = (x["W"] - x["RTH"]).real > so
                lo, hi = (lo, m) if trip else (m, hi)
            temps.append((lo + hi) / 2)
        return min(temps), max(temps)
    band_cap = band_for(DESIGNS["captured"])
    band = band_for(DESIGNS["proposed"])
    # rim hardware trip: comparator on rim_filt vs v3v3 * 10k/(86.6k+10k); trips when NTC < R_th
    k_rim = 10e3 / (86.6e3 + 10e3)
    r_th = 1000.0 * k_rim / (1 - k_rim)
    t_nom = ntc_t(r_th)
    rim = []
    for rs, bs, s1, s2, s3, so in itertools.product((0.97, 1.03), (0.98, 1.02), (-1, 1), (-1, 1), (-1, 1),
                                                    (-1, 1)):
        rpu = 1000 * (1 + s1 * (0.001 + 25e-6 * 60))
        rt = 86.6e3 * (1 + s2 * (0.001 + 25e-6 * 60))
        rb = 10e3 * (1 + s3 * (0.001 + 25e-6 * 60))
        k = rb / (rt + rb) + so * 5e-3 / 3.242
        rim.append(ntc_t(rpu * k / (1 - k), rs, bs))
    sh = (3.3 / (r_th + 1000)) ** 2 * r_th / 0.6e-3      # self-heating at trip: reads hot -> trips early
    rim_band = (min(rim) - sh, max(rim))
    ok = band[0] > 250 + 5 + 15 and band[1] < 325 and rim_band[0] > 250 and rim_band[1] < 300
    gate("8 hardware trips vs 250 C max setpoint", ok, {
        "rtd_runaway_band_C": [r3(band[0], 1), r3(band[1], 1)],
        "rtd_runaway_band_captured_C": [r3(band_cap[0], 1), r3(band_cap[1], 1)],
        "rtd_runaway_note": "C1 leads 0.9-1.1 x %.2f R/conductor and the unspecified FORCE- switch 0-20 R (the "
                            "captured C6 band assumed 0-1 R leads, no switch). Captured: divider bottom at GND, "
                            "so every ohm in the FORCE- return moves the trip. Proposed: divider bottom at the "
                            "connector-side S- (ratiometric to V(BIAS)-V(S-)), which removes the FORCE- path. "
                            "Latched by the interlock; TLV3201 internal hysteresis only. Gate: above 250 C max "
                            "setpoint + 5 K B2 overshoot + 15 K; below the bond's 325 C intermittent limit" % R_LEAD,
        "rim_trip_nominal_C": r3(t_nom, 1), "rim_trip_band_C": [r3(rim_band[0], 1), r3(rim_band[1], 1)],
        "rim_trip_note": "ORed into RUNAWAY_FAULT (interlock has no free input). Rim NTC is outside the cap, "
                         "so the Pt100 stays the only under-cap sensor feeding hardware (US10278238B2 rule). "
                         "Enable only after bench T3 logs the max rim temperature under a 250 C hold <= band "
                         "low - 10 K (study 08: glass underside 12-46 K below the pan at 200 C)"})


# =========================================================================== item 9 cable + ratings
def item9_cable_and_ratings():
    parts = [
        # name, rating, applied, unit, basis
        ("Rref RG2012V-431-W-T1 power", 125e-3, (VB_MAX / (RREF + pt(T_LO))) ** 2 * RREF, "W", "Susumu RG 0805 0.125 W"),
        ("1.00 k RT0603 sense series power", 0.1, (VB_MAX ** 2) / 1e6 * 1e3 + 1e-6, "W", "Yageo RT 0603 0.1 W"),
        ("100 nF C0G 1206 50 V voltage", 50.0, VB_MAX, "V", "Murata GRM31C5C1H104JA01L 50 V"),
        ("ESD5Z3.3 VRWM vs line max", 3.3, VB_MAX, "V", "onsemi ESD5Z3.3T1G"),
        ("ESD5Z5.0 on RIM_SENSE (replaces ESD5Z3.3)", 5.0, 3.367, "V", "captured ESD5Z3.3 has VRWM 3.3 V < v3v3 max 3.367 V; CR swaps to ESD5Z5.0T1G"),
        ("MAX31865 IOUT", 5.75e-3, VB_MAX / (RREF + pt(T_LO)) + 67e-6 + 2 * VB_MAX / 1e6, "A", "MAX31865 + C6 divider"),
        ("Harness cable temperature", 200.0, 105.0, "C", "Alpha Wire 55493 -80..+200 C, 300 V, UL AWM 20229; route <=105 C"),
        ("Pigtail wire temperature", 260.0, 200.0, "C", "M22759/12 PTFE Ni-Cu 260 C 600 V; local max <=200 C (CAD G8)"),
        ("Inline connector temperature", 105.0, 85.0, "C", "Molex Micro-Fit 3.0 -40..+105 C; place where <=85 C"),
        ("Hot-zone lead insulation", 300.0, 260.0, "C", "glass-fibre sleeve or PI bore; >=10 M between leads at 300 C"),
    ]
    rows = []
    ok = True
    for nm, rating, applied, unit, basis in parts:
        good = applied <= rating
        ok &= good
        rows.append({"item": nm, "rating": rating, "applied": r3(applied, 5), "unit": unit, "basis": basis,
                     "ok": good})
    # thermo-EMF: constantan vs manganin with 2 K between the S+ and S- splices
    i = VB_MIN / (RREF + pt(250))
    emf = {"constantan_52uV_per_K": 52e-6 * 2, "manganin_2uV_per_K": 2e-6 * 2}
    emf_k = {k: r3(v / i / dpt(250), 4) for k, v in emf.items()}
    g_leads = {"manganin_k22": 4 * 22.0 * A_LEAD / 20e-3 * 1e3, "constantan_k21": 4 * 21.0 * A_LEAD / 20e-3 * 1e3}
    gate("9 cable, leads and part ratings (UL basis)", ok, {
        "rows": rows, "thermo_emf_error_K_at_250C_2K_splice_dT": emf_k,
        "lead_cold_leak_mW_per_K": {k: r3(v, 4) for k, v in g_leads.items()},
        "decision": "low-k Pt leads in MANGANIN (same k as constantan, CAD G4 unchanged; thermo-EMF vs Cu "
                    "about 25x lower), sense leads twisted S+/S-, force leads F+/F-"})


# =========================================================================== main
def main():
    item1_range_resolution()
    item1_accuracy()
    item2_rate()
    item3_self_heating()
    item4_pickup()
    item_faults()
    item5_rim()
    item6_protection()
    item7_insulation()
    item8_trips()
    item9_cable_and_ratings()
    firmware_constants()
    summary = {k: v["pass"] for k, v in CHECKS.items()}
    out = {"scope": __doc__.strip(), "sources": SRC, "summary": summary, "checks": CHECKS, "info": CHECKS_INFO}
    (HERE / "checks.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    for k, v in summary.items():
        print(f"{'PASS' if v else 'FAIL'}  {k}")
    return 0 if all(summary.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
