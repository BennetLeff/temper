#!/usr/bin/env python3
"""Item 1: TLV3201 common-mode (CMRR) term on the s47 shunt-OCP and bus-OVP bands, per corner vertex.

    python3 -I band_cmrr.py [PS_DIR]   -> ../results/band_cmrr.json, ../results/band_cmrr.md
    (run kelvin_census.py first: the corrected Kelvin shift is read from ../results/kelvin_census.json)

Read-only on PS. The band engine is the committed c47 bands47.py (imported; its main() is not called), which is
thresholds.py exact_corners with the s47 REF25 mapping and the solved B3 network temperatures. This script only
wraps thresholds() so that each vertex gets an extra comparator offset, in the adverse direction (same sign as the
+-4 mV VIO vertex), computed from THAT vertex's own common-mode voltage:

  U6 (OCP): IN+ = ocp_node, IN- = ocp_thresh, GND = ocp_kelvin_p, VCC = hot5 (netlist). At the trip the inputs are equal,
            so VCM = ocp_thresh = REF25 x R35/(R34+R35) (about 1.20 V above the comparator ground).
  U7 (OVP): IN+ = ovp_thresh, IN- = vsense_in, same GND/VCC. VCM = ovp_thresh = REF25 x R37/(R36+R37) (about 2.33 V).
  VIO (4 mV max, TA -40..125 C) is specified at VCM = VCC/2 (SBOS561C 6.5 p.5). The CM term is
  |VCM - VCC/2| x 10^(-CMRR/20), with VCC/2 taken at the HOT5 corner farther from VCM.

CMRR readings (no reading below is a datasheet guarantee at temperature; see results.md):
  R1  60 dB min (SBOS561C 6.5 p.5; header 'TA = 25 C, VCC = 5 V'; condition -0.2 V < VCM < 5.2 V), linear in VCM,
      applied at temperature (the review's term)
  R2  R1 derated by the TYPICAL temperature fall of Figure 6-7 p.8 (VCC 5 V curve, read by eye: 74.5 dB at 25 C,
      73.5 at 75 C, 70 at 95 C, 67 at 110 C, 64.5 at 125 C), at the comparator's own B3 temperature
  R3  typical mid-range slope from Figure 6-5 p.7 (VCC 5.5 V, 25 C, 5 units): |dVOS| <= 0.3 mV between VCM 1.2 V and
      VCC/2 = 2.75 V (read by eye), i.e. 0.2 mV/V
  R4  spec-literal: CMRR is a ratio over the whole -0.2..5.2 V range, so it bounds |dVOS| only by 5.4 V x 10^-3
      = 5.4 mV anywhere inside it
PSRR term as in the S19/S20 review: VIO is tabulated at VCC 5 V and 2.7 V; above 5 V add 10^(-65/20) x (HOT5 - 5)
(SBOS561C 6.5 p.5: PSRR >= 65 dB, VCC 2.5..5.5 V).
"""
import sys
sys.dont_write_bytecode = True
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = Path(sys.argv[1] if len(sys.argv) > 1 else
          "/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
OUT = HERE.parent / "results"
spec = importlib.util.spec_from_file_location("b47", PS / "validation-results/11-candidates/c47-ref25-grade/scripts/bands47.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)        # top level: loads thresholds.py and the s46 Kelvin JSON; writes nothing
m = b.m
FLOOR = b.FLOOR
SHIFT_COMMITTED = b.SHIFT
census = json.loads((OUT / "kelvin_census.json").read_text())
SHIFT_CENSUS = census["trip_shift_A"]
SHIFT_BOUND = census["bound_all_at_max_transfer"]["trip_shift_A"]
PSRR = 10 ** (-65 / 20)
HOT5 = {"Q1 grade guaranteed 4.89-5.11 V (SLVSCE6D 5.5 p.5)": (4.89, 5.11),
        "physical window 4.632-5.5 V (UV no-trip floor .. 5.5 V IC ceiling)": (4.632, 5.5)}
FIG67 = [(25, 74.5), (75, 73.5), (95, 70.0), (110, 67.0), (125, 64.5)]   # VCC 5 V CMRR typ, read by eye


def typ_cmrr(t):
    for (t0, c0), (t1, c1) in zip(FIG67, FIG67[1:]):
        if t <= t1:
            return c0 + (c1 - c0) * (max(t, t0) - t0) / (t1 - t0)
    return FIG67[-1][1]


def reading(name, t_cmp):
    """-> (kind, value): ('slope', V per V of |VCM - VCC/2|) or ('flat', V)."""
    if name == "R0":
        return ("slope", 0.0)
    if name == "R1":
        return ("slope", 10 ** (-60 / 20))
    if name == "R2":
        return ("slope", 10 ** (-(60 - (FIG67[0][1] - typ_cmrr(t_cmp))) / 20))
    if name == "R3":
        return ("slope", 0.3e-3 / (2.75 - 1.2))
    if name == "R4":
        return ("flat", 5.4e-3)
    raise KeyError(name)


def band(temps, rd, hot5, psrr_on):
    tol, load, _ = b.REFS["LM4050AEM3-2.5/NOPB"]
    scale = (tol + load) / 0.020
    lo5, hi5 = hot5
    psrr = PSRR * max(0.0, hi5 - 5.0) if psrr_on else 0.0
    k6 = reading(rd, temps.get("U6", 85.0))
    k7 = reading(rd, temps.get("U7", 85.0))
    vcm_seen = {"ocp": [], "ovp": []}

    def cm(kind_val, vcm):
        kind, val = kind_val
        if kind == "flat":
            return val
        return val * max(abs(vcm - lo5 / 2), abs(vcm - hi5 / 2))

    def thr(p, ref, vos, **kw):
        r = 2.5 + (ref - 2.5) * scale
        s = 1.0 if vos >= 0 else -1.0
        v_ocp = r * p["R35"] / (p["R34"] + p["R35"])
        v_ovp = r * p["R37"] / (p["R36"] + p["R37"])
        vcm_seen["ocp"].append(v_ocp)
        vcm_seen["ovp"].append(v_ovp)
        base = b.ORIG_T(p, r, vos, **kw)
        o = b.ORIG_T(p, r, vos + s * (cm(k6, v_ocp) + psrr), **kw)[0]
        v = b.ORIG_T(p, r, vos + s * (cm(k7, v_ovp) + psrr), **kw)[3]
        return (o, base[1], base[2], v)

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
    res = {k: [round(min(x[k]["min"] for x in corners), 3), round(max(x[k]["max"] for x in corners), 3)]
           for k in ("shunt_a", "ovp_v")}
    res["vcm_range_V"] = {k: [round(min(v), 4), round(max(v), 4)] for k, v in vcm_seen.items()}
    res["cm_term_mV_worst"] = {
        "ocp": round((cm(k6, min(vcm_seen["ocp"])) + psrr) * 1e3, 4),
        "ovp": round((max(cm(k7, min(vcm_seen["ovp"])), cm(k7, max(vcm_seen["ovp"]))) + psrr) * 1e3, 4)}
    res["cmrr_dB_used"] = {"U6": None if k6[0] == "flat" or k6[1] == 0 else round(-20 * __import__("math").log10(k6[1]), 2),
                           "U7": None if k7[0] == "flat" or k7[1] == 0 else round(-20 * __import__("math").log10(k7[1]), 2)}
    return res


def main():
    temps, board = b.solved_temps(b.B3R / "runs", b.B3R / "margins.json")
    # control: bands47's own s47 basis reproduces (no extra term)
    for c, want in (("c17.5_h10", ([68.87, 117.45], [272.64, 287.45])), ("c28_h10", ([67.57, 119.09], [272.47, 287.62]))):
        r = band(temps[c], "R0", (4.89, 5.11), False)
        got = r["shunt_a"] + r["ovp_v"]
        assert all(abs(g - w) <= 0.006 for g, w in zip(got, want[0] + want[1])), (c, r)
    rows = []
    labels = {"R0": "control (bands47, no CM term)", "R1": "CMRR 60 dB min, linear, at temperature (review term)",
              "R2": "60 dB min less Fig. 6-7 typical temperature fall", "R3": "typical mid-range slope (Fig. 6-5)",
              "R4": "spec-literal range bound 5.4 mV"}
    for c, t in temps.items():
        for h5, rng in HOT5.items():
            for rd in ("R0", "R1", "R2", "R3", "R4"):
                for psrr_on in ((False, True) if rd in ("R0", "R1") else (True,)):
                    r = band(t, rd, rng, psrr_on)
                    lo = r["shunt_a"][0]
                    row = {"case": c, "hot5": h5, "reading": rd, "reading_label": labels[rd], "psrr": psrr_on, **r,
                           "ocp_low_after": {}, "ocp_floor_margin_A": {}}
                    for nm, sh in (("committed -2.123", SHIFT_COMMITTED), ("census -2.391", SHIFT_CENSUS),
                                   ("bound -2.437", SHIFT_BOUND)):
                        row["ocp_low_after"][nm] = round(lo + sh, 2)
                        row["ocp_floor_margin_A"][nm] = round(lo + sh - FLOOR, 2)
                    row["ovp_top_vs_288_02_V"] = round(r["ovp_v"][1] - b.OVP_TOP, 3)
                    rows.append(row)
    out = {"board_sha256_runs": board, "solved_temperatures_C": {c: {k: t[k] for k in ("U6", "U7", "R34", "R35")}
                                                                 for c, t in temps.items()},
           "floor_A": FLOOR, "kelvin_shift_A": {"committed": SHIFT_COMMITTED, "census": SHIFT_CENSUS, "bound": SHIFT_BOUND},
           "fig_6_7_typ_cmrr_dB": {c: {u: round(typ_cmrr(t[u]), 2) for u in ("U6", "U7")} for c, t in temps.items()},
           "dI_dVOS_A_per_mV": None, "rows": rows}
    # sensitivity of the OCP trip to comparator offset: (1 + R33/R32) / R5 = 2 A/mV nominal
    out["dI_dVOS_A_per_mV"] = round((1 + 10e3 / 10e3) / 1e-3 * 1e-3, 3)
    OUT.mkdir(exist_ok=True)
    (OUT / "band_cmrr.json").write_text(json.dumps(out, indent=1) + "\n")
    L = ["| case | HOT5 | reading | PSRR | VCM U6 (V) | CM+PSRR U6 / U7 (mV) | OCP band before Kelvin (A) | low after census "
         "-2.391 (margin) | after committed -2.123 (margin) | OVP band (V) | OVP top vs 288.02 |",
         "|---|---|---|---|---|---|---|---|---|---|---:|"]
    for r in rows:
        L.append(f"| {r['case']} | {r['hot5'].split(' (')[0]} | {r['reading']} {r['reading_label']} | {'y' if r['psrr'] else 'n'} | "
                 f"{r['vcm_range_V']['ocp']} | {r['cm_term_mV_worst']['ocp']} / {r['cm_term_mV_worst']['ovp']} | "
                 f"{r['shunt_a']} | {r['ocp_low_after']['census -2.391']} ({r['ocp_floor_margin_A']['census -2.391']:+.2f}) | "
                 f"{r['ocp_low_after']['committed -2.123']} ({r['ocp_floor_margin_A']['committed -2.123']:+.2f}) | "
                 f"{r['ovp_v']} | {r['ovp_top_vs_288_02_V']:+.3f} |")
    (OUT / "band_cmrr.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    print(json.dumps({k: out[k] for k in ("solved_temperatures_C", "fig_6_7_typ_cmrr_dB", "kelvin_shift_A")}, indent=1))


if __name__ == "__main__":
    main()
