#!/usr/bin/env python3
"""Stage 47: the OCP and OVP bands REF25 sets, with U5 on the LM4050AEM3-2.5 and with the divider network at the
temperature the hot-copper B3 model solves for it.

    python3 -I scripts/bands47.py [--runs DIR] [--margins FILE]   -> results/bands-s47.json, results/bands-s47.md

DIR (default ../../../04-board-current-thermal/round5-native21/b3-ratings/runs) holds the B3 body runs that
run_basis.py writes, <case>_p0p25.json / <case>_p0p5.json with "probes" (pad-copper maxima per ref). FILE (default
b3-ratings/margins.json) supplies the R5 element row. Both must be solved on one board.

Method = the committed one (round5-native21/stage17-r5/ocp_band17.py, c46-monitor-grades/scripts/ref25_46.py):
task-02 round-3 thresholds.py exact_corners (imported read-only, every vertex of every part tolerance, TCR sign, the
two REF25 corners, TLV3201 VOS and input bias) with stage 17's R5 CSS2H tuple and the stage-15 OCP divider
(R34 12.6 k / R35 11.7 k). Two inputs change:

1. REF25 error. exact_corners takes 2.5 V +- 20 mV (A25I +-19 mV full range plus the 1 mV load allowance). Every output
   is monotonic in REF25, so the two vertices still bound it when they are mapped to 2.5 V +- (T + L):
     A25I    T 19 mV  (TI SLOS456Q 6.8 p.9, -40..85 C)     L 1.0 mV (IZ,min < IZ < 1 mA, full range, same table)
     LM4050  T 15 mV  (TI SNOS455H 5.6 p.7, LM4050AEM3, TA = TJ -40..125 C; note 5 p.11: 0.1 % + 50 ppm/C x 100 K)
             L 1.2 mV (IRMIN <= IR <= 1 mA over temperature, p.7). U5 runs at 0.14-0.23 mA (audit.rs window).
2. Network temperature. exact_corners puts every resistor at one board temperature, -10 and 85 C (R5 50 K above it).
   The hot-copper B3 field puts U5's neighbourhood near 90-105 C. corner_values is replaced by a per-part map:
     committed   -10 and 85 C uniform, R5 +50 K (the control: ocp_band17.json 69.89-116.44 A, OVP 272.09-288.02 V)
     uniform105  -10 and 105 C uniform, R5 +50 K (the c46 / u5-ref flag)
     solved:<case> the -10 C corner as committed, and a hot corner with each of R26-R37 at its own B3 pad estimate
                 (gate estimator Q(0.25) + 3 |Q(0.25) - Q(0.5)| + (bay - 50), the run's bay) and R5 at the gate's R5
                 element row (margins.json): the board as solved
     hottest:<case> the hot corner with every network resistor at the hottest network estimate and R5 at that + 50 K
                 (the committed R5 rule; a bound on solved)
Acceptance (committed): OCP low corner after the Kelvin shift (-2.123 A, kelvin/budget-native21s46.json) >= the 64.17 A
floor (kelvin_budget.FLOOR); OVP upper corner <= 288.02 V, the "must not rise" rule (simplify-2026-10-15 ovp_band.py:
the bus maximum the D3 / C5 C6 / ALT-BIAS ledger rows use against 286 V); OVP lower corner >= 0.99 x 272.09 = 269.37 V
(the same file's nuisance-trip rule).
"""
import sys as _s; _s.dont_write_bytecode = True
import argparse
import csv
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = HERE.parents[3]
VR = PS / "validation-results"
OUT = HERE.parent / "results"
B3R = VR / "04-board-current-thermal/round5-native21/b3-ratings"
spec = importlib.util.spec_from_file_location("thr", VR / "02-protection-timing/round3/thresholds.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
RT = (0.001, 25e-6)
m.PARTS.update({"R34": (12.6e3, *RT), "R35": (11.7e3, *RT)})
m.PARTS["R5"] = m.SHUNT_CSS2H
ORIG_T, ORIG_CV = m.thresholds, m.corner_values
# current freeze identities of the parts the band model uses (round-3 defaults changed since stages 15-19)
CURRENT = {"R5": "CSS2H-2512R-1L00F", "R34": "RT0603BRD0712K6L", "R35": "TNPW060311K7BEEA",
           "R39": "RC1206FR-073RL", "R43": "RT0603BRD072K21L", "R46": "RT0603BRD072K21L"}
KELVIN = json.loads((VR / "02-protection-timing/kelvin/budget-native21s46.json").read_text())
SHIFT = KELVIN["trip_shift_A"]
FLOOR = 64.17
OVP_TOP, OVP_LOW_MIN = 288.02, round(0.99 * 272.09, 2)
REFS = {"LM4040A25IDBZR": (0.019, 0.0010, "SLOS456Q 6.8 p.9: +-19 mV -40..85 C, 1.0 mV IZ,min..1 mA"),
        "LM4050AEM3-2.5/NOPB": (0.015, 0.0012, "SNOS455H 5.6 p.7: +-15 mV -40..125 C (note 5 p.11), 1.2 mV IRMIN..1 mA")}
NETWORK = [f"R{i}" for i in range(26, 38) if i != 31]   # the band resistors; R31 (bias) is not in either band
CASES = {"c17.5_h10": 61.0, "c28_h10": 55.0}            # b3_ratings_gate.BASIS release case and the c28 ratchet case
K_MESH = 3.0


def est(q25, q05, bay):
    return q25 + K_MESH * abs(q25 - q05) + (bay - 50.0)


def solved_temps(runs, margins):
    """case -> {ref: est C} for R26-R37 (and R31, U5 for the record) and R5 (element row); the board hash."""
    mg = json.loads(Path(margins).read_text())
    out, boards = {}, set()
    for c, bay in CASES.items():
        a = json.loads((Path(runs) / f"{c}_p0p25.json").read_text())
        b = json.loads((Path(runs) / f"{c}_p0p5.json").read_text())
        assert a.get("bay_c") == bay == b.get("bay_c"), (c, a.get("bay_c"), b.get("bay_c"))
        assert a["copper_temp_model"]["model"] == "hot-iterated", c
        boards |= {a["board_sha256"], b["board_sha256"], mg["board_sha256"][c]}
        t = {}
        for r in NETWORK + ["R31", "U5", "U6", "U7"]:
            t[r] = round(est(a["probes"][r]["pad_max_cell_c"], b["probes"][r]["pad_max_cell_c"], bay), 2)
        r5 = [row for row in mg["cases"][c] if row["item"].startswith("R5: element max")]
        assert len(r5) == 1, c
        t["R5"] = r5[0]["est_c"]
        out[c] = t
    assert len(boards) == 1, f"run files and margins.json are not one board: {boards}"
    return out, boards.pop()


def band(ref_mpn, net):
    """net: ('uniform', T) or ('parts', {ref: T}) for the hot corner; the cold corner is always -10 C (R5 +50 K)."""
    tol, load, _ = REFS[ref_mpn]
    scale = (tol + load) / 0.020
    m.thresholds = lambda p, ref, vos, **kw: ORIG_T(p, 2.5 + (ref - 2.5) * scale, vos, **kw)
    try:
        corners = [m.exact_corners(-10.0, 50.0)]
        if net[0] == "uniform":
            corners.append(m.exact_corners(net[1], 50.0))
        else:
            temps = net[1]

            def cv(_t, _rise):
                vals = {}
                for name, (nominal, tl, tcr) in m.PARTS.items():
                    drift = tcr * abs(temps.get(name, 85.0) - 25.0)   # parts outside both bands: committed 85 C
                    vals[name] = (nominal * (1 - tl) * (1 - drift), nominal * (1 + tl) * (1 + drift))
                return vals
            m.corner_values = cv
            corners.append(m.exact_corners(0.0, 0.0))
    finally:
        m.thresholds, m.corner_values = ORIG_T, ORIG_CV
    return {k: [round(min(x[k]["min"] for x in corners), 2), round(max(x[k]["max"] for x in corners), 2)]
            for k in ("shunt_a", "ovp_v")}


def row(ref_mpn, label, net):
    b = band(ref_mpn, net)
    lo_after = round(b["shunt_a"][0] + SHIFT, 2)
    return {"ref25": ref_mpn, "network": label, "ocp_band_before_kelvin_A": b["shunt_a"], "ocp_low_after_kelvin_A": lo_after,
            "ocp_floor_margin_A": round(lo_after - FLOOR, 2), "ovp_band_V": b["ovp_v"],
            "ovp_top_vs_288_02_V": round(b["ovp_v"][1] - OVP_TOP, 2), "ovp_low_vs_269_37_V": round(b["ovp_v"][0] - OVP_LOW_MIN, 2),
            "pass": lo_after >= FLOOR and b["ovp_v"][1] <= OVP_TOP and b["ovp_v"][0] >= OVP_LOW_MIN}


def bom():
    out = {}
    for r in csv.DictReader(open(PS / "native-21/frozen/default.csv")):
        for d in r["Designator"].split(","):
            out[d.strip()] = r["Comment"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default=str(B3R / "runs"))
    ap.add_argument("--margins", default=str(B3R / "margins.json"))
    a = ap.parse_args()
    checks = m.validate_inputs(overrides=CURRENT)              # current freeze identities + the band topology
    frozen = bom()
    assert frozen["U5"] == "LM4050AEM3-2.5/NOPB", frozen["U5"]
    # controls: the A25I on the committed network reproduces ocp_band17.json and the 288.02 V OVP corner; the
    # u5-ref search's LM4050 row and its 105 C flag row reproduce too
    ctrl = band("LM4040A25IDBZR", ("uniform", 85.0))
    assert ctrl == {"shunt_a": [69.89, 116.44], "ovp_v": [272.09, 288.02]}, ctrl
    assert band("LM4040A25IDBZR", ("uniform", 105.0))["ovp_v"][1] == 288.75
    assert band("LM4050AEM3-2.5/NOPB", ("uniform", 85.0))["ovp_v"] == [272.5, 287.58]
    temps, board = solved_temps(a.runs, a.margins)
    rows = []
    for mpn in REFS:
        rows.append(row(mpn, "committed -10/85 C", ("uniform", 85.0)))
        rows.append(row(mpn, "uniform -10/105 C", ("uniform", 105.0)))
        for c, t in temps.items():
            rows.append(row(mpn, f"solved {c}@{CASES[c]:g}", ("parts", t)))
            hot = max(t[r] for r in NETWORK)
            rows.append(row(mpn, f"hottest {c}@{CASES[c]:g} ({hot:.1f} C uniform, R5 +50 K)", ("uniform", hot)))
    # the s47 Kelvin budget takes the band on this basis (kelvin_budget.BAND_BEFORE): LM4050, network solved at release
    ks = importlib.util.spec_from_file_location("kb", VR / "02-protection-timing/kelvin/kelvin_budget.py")
    kb = importlib.util.module_from_spec(ks)
    ks.loader.exec_module(kb)
    basis = next(r for r in rows if r["ref25"] == "LM4050AEM3-2.5/NOPB" and r["network"].startswith("solved c17.5"))
    assert list(kb.BAND_BEFORE["native21s47"]) == basis["ocp_band_before_kelvin_A"], (kb.BAND_BEFORE["native21s47"], basis)
    out = {"board_sha256": board, "band_basis_s47": {"row": basis["network"], "ref25": basis["ref25"],
           "kelvin_budget_BAND_BEFORE": list(kb.BAND_BEFORE["native21s47"])}, "controls": "A25I committed network = ocp_band17.json 69.89-116.44 A and OVP "
           "272.09-288.02 V; A25I uniform 105 C OVP top 288.75 V; LM4050 committed 272.50-287.58 V (u5-ref search)",
           "validate_inputs": checks, "kelvin_shift_A": SHIFT, "floor_A": FLOOR, "ovp_top_rule_V": OVP_TOP,
           "ovp_low_rule_V": OVP_LOW_MIN, "ref25_error": {k: {"T_V": v[0], "L_V": v[1], "source": v[2]} for k, v in REFS.items()},
           "solved_temperatures_C": temps,
           "network_max_C": {c: max(t[r] for r in NETWORK) for c, t in temps.items()},
           "ovp_network_max_C": {c: max(t[r] for r in ("R26", "R27", "R28", "R29", "R30", "R36", "R37")) for c, t in temps.items()},
           "ocp_network_max_C": {c: max(t[r] for r in ("R32", "R33", "R34", "R35")) for c, t in temps.items()},
           "rows": rows}
    OUT.mkdir(exist_ok=True)
    (OUT / "bands-s47.json").write_text(json.dumps(out, indent=1) + "\n")
    L = ["# REF25 bands, stage 47 (generated by scripts/bands47.py; do not edit)\n",
         f"Board {board[:8]}. Controls: {out['controls']}. Kelvin shift {SHIFT} A (s46 budget), floor {FLOOR} A; OVP top "
         f"rule <= {OVP_TOP} V, low rule >= {OVP_LOW_MIN} V.\n",
         "Solved temperatures (C, B3 gate estimator; R5 = the gate's element row):\n",
         "| Case | " + " | ".join(NETWORK + ["R31", "R5", "U5", "U6", "U7"]) + " |",
         "|---|" + "---:|" * (len(NETWORK) + 5)]
    for c, t in temps.items():
        L.append(f"| {c}@{CASES[c]:g} | " + " | ".join(f"{t[r]:.1f}" for r in NETWORK + ["R31", "R5", "U5", "U6", "U7"]) + " |")
    L += ["", "| REF25 | Network | OCP band before Kelvin (A) | OCP low after Kelvin (margin) | OVP band (V) | OVP top vs 288.02 | Pass |",
          "|---|---|---|---|---|---:|---|"]
    for r in rows:
        L.append(f"| {r['ref25']} | {r['network']} | {r['ocp_band_before_kelvin_A']} | {r['ocp_low_after_kelvin_A']} "
                 f"({r['ocp_floor_margin_A']:+.2f}) | {r['ovp_band_V']} | {r['ovp_top_vs_288_02_V']:+.2f} | "
                 f"{'yes' if r['pass'] else '**no**'} |")
    (OUT / "bands-s47.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
