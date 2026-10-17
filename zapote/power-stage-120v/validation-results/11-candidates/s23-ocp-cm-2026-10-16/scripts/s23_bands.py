#!/usr/bin/env python3
"""S23 / DECISIONS 64: U6 (shunt OCP) and U7 (bus OVP) comparator options on the s48 board.

    python3 -I s23_bands.py [PS_DIR]   -> ../results/s23_bands.json, ../results/s23_bands.md

Read-only on PS (sys.dont_write_bytecode; no PS main() is called; nothing is written under PS).

Engine: the committed c47 bands47.py (imported), i.e. task-02 round-3 thresholds.py exact_corners with the s47 REF25
mapping (LM4050AEM3-2.5: +-15 mV + 1.2 mV) and the solved B3 network temperatures, exactly as band_cmrr.py wraps it.
The wrapper replaces the TLV3201 comparator terms vertex by vertex:
  vos_vertex = s * VIO_max(candidate)                       (s = sign of the committed +-4 mV vertex)
             + bias  (committed method: IIB * (source Thevenin sum), scaled from the 5 nA the engine applies;
                      'lp' method: max over |I+|,|I-| <= IIB, |I+ - I-| <= IIO of I+ R+ - I- R-)
             + s * CM(VCM of this vertex)                    (0 if VIO is guaranteed over the full CM range)
             + s * PSRR(HOT5 corner)                         (only outside the supply span VIO is specified at)
The Kelvin shift is the committed s48 census (kelvin_budget.py CENSUS21 + CENSUS48 on plane-native21s48.json) with the
U6.2 / U7.2 rows set to the candidate's IQ max. Floor 64.17 A (kelvin_budget FLOOR), OVP top <= 288.02 V, OVP low
>= 269.37 V (bands47). Bank in the CT-failed double fault: Z0,max x OCP top <= 1600 V (stage15-28A fault_check.py).
Option B (divider re-centring) is the same engine with R32-R35 re-ratioed at a held nominal trip.
"""
import sys
sys.dont_write_bytecode = True
import importlib.util
import itertools
import json
import math
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "results"
PS = Path(sys.argv[1] if len(sys.argv) > 1 else
          "/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
VR = PS / "validation-results"
DL = Path("/Users/bennet/Desktop/temper/worktrees/runs-native21/s23cmp/dl")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


b = load("b47", VR / "11-candidates/c47-ref25-grade/scripts/bands47.py")   # top level reads only
kb = load("kb", VR / "02-protection-timing/kelvin/kelvin_budget.py")          # top level defines only
m = b.m
FLOOR, OVP_TOP, OVP_LOW = kb.FLOOR["native21s48"], b.OVP_TOP, b.OVP_LOW_MIN
HOT5 = {"Q1": (4.89, 5.11), "phys": (4.632, 5.5)}
# tank constants as stage15-28A/fault_check.py (L 66.5 uH +-10 %, C 0.50 uF +-10 %)
L_NOM, C_NOM = 66.5e-6, 0.50e-6
L_MIN, L_MAX, C_MIN = L_NOM * 0.9, L_NOM * 1.1, C_NOM * 0.9
Z0_MAX = math.sqrt(L_MAX / C_MIN)
F_RES_MIN = 1 / (2 * math.pi * math.sqrt(L_MAX * C_NOM * 1.1))
BANK_VR = 1600.0


# ---------------------------------------------------------------- datasheet citations (page = PDF page of the text)
def page_of(txt, pattern):
    t = Path(txt).read_text(errors="replace")
    mt = re.search(pattern, t)
    if not mt:
        raise AssertionError(f"citation not found: {txt}: {pattern}")
    return t.count("\f", 0, mt.start()) + 1


CITES = {
    "TLV3201AIDBVR": [("runs-native21/s47/u3-dl/tlv3201.txt", r"TA = –40°C to 125°C\s+4\b"),
                      ("runs-native21/s47/u3-dl/tlv3201.txt", r"–0\.2V < VCM < 5\.2V\s+60"),
                      ("runs-native21/s47/u3-dl/tlv3201.txt", r"High to low\s+Input overdrive = 100mV")],
    "TS3021AILT": [("ts3021/ts3021.txt", r"Table 5: Electrical characteristics at VCC = 5 V, Tamb = 25 ° C, and full Vicm range"),
                   ("ts3021/ts3021.txt", r"-40 °C < Tamb < 125°C\s+2 to 5"),
                   ("ts3021/ts3021.txt", r"TS3021AILT")],
    "NCS2250SN2T1G": [("ncs2250/ncs2250.txt", r"Boldface numbers apply from TA = −40°C to 125°C"),
                      ("ncs2250/ncs2250.txt", r"Common Mode Rejection Ratio\s+CMRR\s+81")],
    "TLV3601DBVR": [("tlv3601/tlv3601.txt", r"VCM = VEE \+ 300 mV"), ("tlv3601/tlv3601.txt", r"Common-mode rejection ratio\s+VCM = VEE – 0\.2V to VCC \+ 0\.2V\s+80")],
    "TLV1811DBVR": [("tlv1811/tlv1811.txt", r"VCM = VS / 2 at TA = 25°C"), ("tlv1811/tlv1811.txt", r"TA = –40°C to \+125°C\s+–4")],
    "LMV7219M5X/NOPB": [("lmv7219/lmv7219.txt", r"−40°C ≤ TJ ≤ \+85°C and TPCB ≤ 105°C")],
    "LMV7239M5X/NOPB": [("lmv7239/lmv7239.txt", r"At temp extremes\s+–8")],
    "MCP6561T-E/OT": [("mcp6561/mcp6561.txt", r"Input Offset Voltage\s+VOS\s+-10")],
    "TLV7011DBVR": [("tlv7011/tlv7011.txt", r"VS = 1\.8 V and 5 V, VCM = VS / 2\s+±0\.5\s+±8")],
    "TS3011ILT": [("ts3011/ts3011.txt", r"-40 °C < Tamb < 125 °C\s+-8\s+8")],
    "ADCMP600BRJZ": [("adcmp600/adcmp600.txt", r"Offset Voltage\s+VOS\s+−5\.0")],
}


def cite_pages():
    out = {}
    for mpn, lst in CITES.items():
        out[mpn] = []
        for f, pat in lst:
            path = (Path("/Users/bennet/Desktop/temper/worktrees") / f) if f.startswith("runs-native21") else DL / f
            out[mpn].append({"file": str(path), "pattern": pat, "pdf_page": page_of(path, pat)})
    return out


# ---------------------------------------------------------------- candidates with a guaranteed basis (or the reference)
# basis: 'vcc2'  VIO at VCM = VCC/2 only; CM term from a CMRR reading (TLV3201 readings R0/R1/R3/R4 of band_cmrr.py)
#        'full'  VIO max holds over the full input CM range and temperature -> no CM term
#        'fixed' VIO at a fixed VCM (vcm_spec) over temperature + a CMRR max over temperature (mV/V) -> slope x |VCM - vcm_spec|
# psrr: (V/V, (vlo, vhi) supply span VIO is specified over); term = psrr x distance of the HOT5 corner outside that span
CAND = {
    "TLV3201AIDBVR": dict(vio=4e-3, basis="vcc2", psrr=(10 ** (-65 / 20), (2.7, 5.0)), iib=5e-9, iio=2.5e-9, iq=65e-6,
                          tpd_ns="50 max (20 mV, 15 pF, 25 C) p.5", vcc=(2.7, 5.5), ta=(-40, 125), stock="JLC C105188: 3221",
                          price="$0.6135 @1000", src="TI SBOS561C 6.5 p.5"),
    "TS3021AILT": dict(vio=4e-3, basis="full", psrr=(10 ** (-58 / 20), (2.0, 5.0)), iib=300e-9, iio=100e-9, iq=135e-6,
                       tpd_ns="TPHL 95 / TPLH 105 max (20 mV, 50 pF) p.8", vcc=(2.0, 5.0), ta=(-40, 125),
                       stock="JLC C5199085: 23", price="$1.576 @1000",
                       src="ST DocID12485 Rev 8 Table 5 p.8 (header 'full Vicm range'); Table 2 p.3 VCC 2-5 V"),
    "MAX9140AAUK+T": dict(vio=6e-3, basis="fixed", vcm_spec=0.0, cm_slope=0.85e-3, psrr=(0.8e-3, (5.0, 5.0)),
                          iib=350e-9, iio=140e-9, iq=400e-6, tpd_ns="40 typ (VCC 3 V, 10 mV), no max p.3",
                          vcc=(2.7, 5.5), ta=(-40, 125), stock="JLC C3659233: 0", price="n/a",
                          src="ADI 19-2064 Rev 10 p.2 (VCM = 0 V header; CMRR Note 7 full CM range)"),
    "MAX999AAUK+T": dict(vio=6e-3, basis="fixed", vcm_spec=-0.1, cm_slope=1.0e-3, psrr=(0.3e-3, (5.0, 5.0)),
                         iib=30e-6, iio=30e-6, iq=7.0e-3, tpd_ns="10 max (5 mV, TMIN..TMAX) p.3", vcc=(2.7, 5.5),
                         ta=(-40, 125), stock="JLC C5328755: 3", price="$5.73 @100",
                         src="ADI 19-1129 Rev 8 pp.2-3 (VOS at VCM -0.1 / 5.1 V)"),
    "NCS2250SN2T1G": dict(vio=6e-3, basis="fixed", vcm_spec=None, cm_db=59.0, psrr=(10 ** (-62.5 / 20), (1.8, 5.0)),
                          iib=1e-9, iio=1e-9, iq=250e-6, tpd_ns="64 max (100 mV, 50 pF); 90 typ at 20 mV",
                          vcc=(1.8, 5.5), ta=(-40, 125), stock="JLC C603840: 0 (SC-88A C603841: 453)",
                          price="$0.367 @1000", src="onsemi NCS2250/D Rev 5 Table 6 (boldface -40..125 C)"),
}
TLV_READINGS = {"R0": ("slope", 0.0), "R1": ("slope", 1e-3), "R3": ("slope", 0.3e-3 / (2.75 - 1.2)), "R4": ("flat", 5.4e-3)}


def kelvin_shift(iq_u6, iq_u7):
    plane = json.loads((VR / "02-protection-timing/kelvin/plane-native21s48.json").read_text())
    T = plane["transfer_mohm_to_R35_2"]
    census = kb.CENSUS21 + [r for r in kb.CENSUS48 if r[0] in T]
    e = 0.0
    total = 0.0
    for pad, ma, *_ in census:
        if pad == "U6.2":
            ma = iq_u6 * 1e3
        elif pad == "U7.2":
            ma = iq_u7 * 1e3
        e += ma * 1e-3 * T[pad]
        total += ma
    return round(e * plane["trip_shift_A_per_mV_at_R35_2"], 3), round(total, 3)


def source_r(p, index):
    par = lambda a, c: a * c / (a + c)
    if index == 0:
        return par(p["R32"], p["R33"]), par(p["R34"], p["R35"])          # IN+ = ocp_node, IN- = ocp_thresh
    return par(p["R36"], p["R37"]), par(sum(p[f"R{i}"] for i in range(26, 30)), p["R30"])  # IN+ ovp_thresh, IN- vsense_in


def bias_lp(rp, rn, iib, iio):
    best = 0.0
    for ip, im in itertools.product((-iib, iib, -iib + iio, iib - iio), repeat=2):
        if abs(ip - im) <= iio + 1e-15:
            best = max(best, abs(ip * rp - im * rn))
    return best


def band(temps, c, reading=None, hot5=(4.89, 5.11), bias_mode="committed", parts=None):
    """c: candidate dict. reading: TLV3201 CM reading key (vcc2 basis only). parts: PARTS overrides (option B)."""
    tol, load, _ = b.REFS["LM4050AEM3-2.5/NOPB"]
    scale = (tol + load) / 0.020
    lo5, hi5 = hot5
    plo, (s_lo, s_hi) = c["psrr"]
    psrr = plo * max(0.0, hi5 - s_hi, s_lo - lo5)
    vcm_seen = {"ocp": [], "ovp": []}

    def cm(vcm):
        if c["basis"] == "full":
            return 0.0
        if c["basis"] == "vcc2":
            kind, val = TLV_READINGS[reading]
            return val if kind == "flat" else val * max(abs(vcm - lo5 / 2), abs(vcm - hi5 / 2))
        if c.get("vcm_spec") is None:                                       # CMRR (dB, over temp) from mid-supply
            return 10 ** (-c["cm_db"] / 20) * max(abs(vcm - lo5 / 2), abs(vcm - hi5 / 2))
        return c["cm_slope"] * abs(vcm - c["vcm_spec"])

    def thr(p, ref, vos, **kw):
        r = 2.5 + (ref - 2.5) * scale
        s = 1.0 if vos >= 0 else -1.0
        resid = vos - s * 0.004                                             # = bias_sign * 5 nA * source(index)
        v_ocp = r * p["R35"] / (p["R34"] + p["R35"])
        v_ovp = r * p["R37"] / (p["R36"] + p["R37"])
        vcm_seen["ocp"].append(v_ocp)
        vcm_seen["ovp"].append(v_ovp)
        if bias_mode == "committed":
            b_o = b_v = resid * c["iib"] / 5e-9
        else:
            b_o = s * bias_lp(*source_r(p, 0), c["iib"], c["iio"])
            b_v = s * bias_lp(*source_r(p, 3), c["iib"], c["iio"])
        base = b.ORIG_T(p, r, vos, **kw)
        o = b.ORIG_T(p, r, s * (c["vio"] + cm(v_ocp) + psrr) + b_o, **kw)[0]
        v = b.ORIG_T(p, r, s * (c["vio"] + cm(v_ovp) + psrr) + b_v, **kw)[3]
        return (o, base[1], base[2], v)

    saved = dict(m.PARTS)
    if parts:
        m.PARTS.update(parts)
    m.thresholds = thr
    try:
        corners = [m.exact_corners(-10.0, 50.0)]

        def cv(_t, _rise):
            vals = {}
            for name, (nominal, tl, tcr) in m.PARTS.items():
                drift = tcr * abs(temps.get(name, 85.0) - 25.0)
                vals[name] = (nominal * (1 - tl) * (1 - drift), nominal * (1 + tl) * (1 + drift))
            return vals
        m.corner_values = cv
        corners.append(m.exact_corners(0.0, 0.0))
    finally:
        m.thresholds, m.corner_values = b.ORIG_T, b.ORIG_CV
        m.PARTS.clear()
        m.PARTS.update(saved)
    res = {k: [round(min(x[k]["min"] for x in corners), 3), round(max(x[k]["max"] for x in corners), 3)]
           for k in ("shunt_a", "ovp_v")}
    res["vcm_V"] = {k: [round(min(v), 4), round(max(v), 4)] for k, v in vcm_seen.items()}
    return res


def row(label, temps, c, shift, **kw):
    r = band(temps, c, **kw)
    lo, hi = r["shunt_a"]
    lo_after = round(lo + shift, 2)
    return {"label": label, "ocp_before_A": r["shunt_a"], "ocp_low_after_A": lo_after,
            "floor_margin_A": round(lo_after - FLOOR, 2), "ocp_top_A": hi, "bank_V": round(Z0_MAX * hi),
            "bank_margin_V": round(BANK_VR - Z0_MAX * hi), "ovp_V": r["ovp_v"],
            "ovp_top_margin_V": round(OVP_TOP - r["ovp_v"][1], 3), "ovp_low_margin_V": round(r["ovp_v"][0] - OVP_LOW, 2),
            "vcm_V": r["vcm_V"]}


def delay_cost(extra_ns, hi=119.1, bus=280.0):
    """fault_check.py I_off form: extra front-end delay x the coil slope bound (CT-failed, shunt-only trip)."""
    dA = bus / (math.pi * L_MIN * F_RES_MIN)
    didt = (bus + Z0_MAX * (hi + dA)) / L_MIN
    return round(didt * extra_ns * 1e-9, 2), round(didt * 1e-6, 1)


def option_b_parts(vcm_target, ref=2.5, i_nom=None, r_ocp=20e3, r_th=24.3e3):
    """Re-ratio R32/R33 and R34/R35 for VCM ~ vcm_target at the trip, holding the nominal trip of the s48 values."""
    p0 = {k: v[0] for k, v in m.PARTS.items()}
    if i_nom is None:
        i_nom = b.ORIG_T(p0, ref, 0.0)[0]
    k = vcm_target / ref
    x = i_nom * p0["R5"] / ref
    kp = (k + x) / (1 + x)
    RT = m.PARTS["R34"][1:]
    return {"R32": (r_ocp * (1 - kp), *RT), "R33": (r_ocp * kp, *RT), "R34": (r_th * (1 - k), *RT),
            "R35": (r_th * k, *RT)}, {"k_thresh": k, "k_node": kp, "shunt_weight": 1 - kp, "i_nom_A": i_nom,
                                       "dI_dVOS_A_per_mV": round(1 / ((1 - kp) * p0["R5"]) * 1e-3, 3)}


def main():
    temps, board = b.solved_temps(b.B3R / "runs", b.B3R / "margins.json")
    nets = {"release c17.5@61": temps["c17.5_h10"], "c28@55": temps["c28_h10"]}
    tlv = CAND["TLV3201AIDBVR"]
    shift_tlv, ma_tlv = kelvin_shift(tlv["iq"], tlv["iq"])
    committed = json.loads((VR / "02-protection-timing/kelvin/budget-native21s48.json").read_text())
    assert abs(shift_tlv - committed["trip_shift_A"]) < 0.002 and abs(ma_tlv - committed["total_mA"]) < 0.002, (shift_tlv, committed)
    # control: the engine with the TLV3201 at R0 reproduces the committed s48 band (kelvin_budget BAND_BEFORE)
    # control: the wrapper with the TLV3201 at R0 and no PSRR term reproduces the committed bands47 engine on this
    # board's B3 solve. NOTE: kelvin_budget BAND_BEFORE["native21s48"] still carries the s47 solve (68.87, 117.45).
    nopsrr = dict(tlv, psrr=(0.0, (0.0, 99.0)))
    engine = {}
    for net, t in nets.items():
        ctrl = band(t, nopsrr, reading="R0")
        eng = b.band("LM4050AEM3-2.5/NOPB", ("parts", t))
        assert [round(x, 2) for x in ctrl["shunt_a"]] == eng["shunt_a"] and [round(x, 2) for x in ctrl["ovp_v"]] == eng["ovp_v"], (net, ctrl, eng)
        engine[net] = eng
    out = {"board_sha256": board, "floor_A": FLOOR, "ovp_top_rule_V": OVP_TOP, "ovp_low_rule_V": OVP_LOW,
           "z0_max_ohm": round(Z0_MAX, 3), "bank_rule_V": BANK_VR, "kelvin_s48_committed": {"shift_A": shift_tlv, "mA": ma_tlv},
           "engine_s48_bands47": engine, "kelvin_budget_BAND_BEFORE_native21s48": list(kb.BAND_BEFORE["native21s48"]),
           "temps_C": {n: {k: t[k] for k in ("U5", "U6", "U7", "R34", "R35", "R5")} for n, t in nets.items()},
           "citations": cite_pages(), "optionA": [], "optionB": []}
    # ---- Option A
    for mpn, c in CAND.items():
        shift, ma = kelvin_shift(c["iq"], c["iq"])
        readings = list(TLV_READINGS) if c["basis"] == "vcc2" else [None]
        for net, t in nets.items():
            for rd in readings:
                for h5 in ("Q1", "phys"):
                    for bm in (("committed",) if c["iib"] <= 5e-9 else ("committed", "lp")):
                        r = row(f"{mpn} {rd or c['basis']} {net} HOT5 {h5} bias {bm}", t, c, shift,
                                reading=rd, hot5=HOT5[h5], bias_mode=bm)
                        r.update({"mpn": mpn, "reading": rd or c["basis"], "network": net, "hot5": h5, "bias": bm,
                                  "kelvin_shift_A": shift, "kelvin_mA": ma})
                        out["optionA"].append(r)
    # ---- Option B: divider re-ratio sweep on the TLV3201 (same parts classes, nominal trip held)
    for vt in (0.8, 1.0, 1.2037, 1.6, 2.0, 2.3):
        parts, info = option_b_parts(vt)
        for net, t in nets.items():
            for rd in ("R0", "R1", "R3"):
                r = row(f"B vcm {vt} {net} {rd}", t, tlv, shift_tlv, reading=rd, parts=parts)
                r.update({"vcm_target": vt, "network": net, "reading": rd, **info,
                          "values_ohm": {k: round(v[0], 1) for k, v in parts.items()}})
                out["optionB"].append(r)
    out["delay_cost"] = {f"+{ns} ns": delay_cost(ns) for ns in (10, 45, 55, 100)}
    out["delay_cost_note"] = "(I_off increase A, coil slope bound A/us) at 280 V, OCP top 119.1 A; fault_check.py form"
    OUT.mkdir(exist_ok=True)
    (OUT / "s23_bands.json").write_text(json.dumps(out, indent=1) + "\n")
    L = [f"Board {board[:8]}; floor {FLOOR} A; Kelvin s48 {shift_tlv} A ({ma_tlv} mA); Z0max {Z0_MAX:.3f} ohm", "",
         "| case | Kelvin (A) | OCP before | low after (margin) | top / bank V | OVP band (V) | OVP top margin |",
         "|---|---:|---|---|---|---|---:|"]
    for r in out["optionA"]:
        L.append(f"| {r['label']} | {r['kelvin_shift_A']} | {r['ocp_before_A']} | {r['ocp_low_after_A']} ({r['floor_margin_A']:+.2f}) | "
                 f"{r['ocp_top_A']} / {r['bank_V']} | {r['ovp_V']} | {r['ovp_top_margin_V']:+.3f} |")
    L += ["", "| B case | values (ohm) | dI/dVOS | VCM | OCP before | low after (margin) | top / bank V |", "|---|---|---:|---|---|---|---|"]
    for r in out["optionB"]:
        L.append(f"| {r['label']} | {r['values_ohm']} | {r['dI_dVOS_A_per_mV']} | {r['vcm_V']['ocp']} | {r['ocp_before_A']} | "
                 f"{r['ocp_low_after_A']} ({r['floor_margin_A']:+.2f}) | {r['ocp_top_A']} / {r['bank_V']} |")
    L += ["", f"delay cost {out['delay_cost']} {out['delay_cost_note']}"]
    (OUT / "s23_bands.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    print(json.dumps(out["citations"], indent=0)[:3000])


if __name__ == "__main__":
    main()
