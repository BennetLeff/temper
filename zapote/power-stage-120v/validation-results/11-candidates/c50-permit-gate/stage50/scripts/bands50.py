#!/usr/bin/env python3
"""Stage 50: the stage-49 OCP / OVP band computation (c49-c34-bank/scripts/bands49.py, same engine, divider and readings)
on the s50 board's own hot-copper B3 solve, to confirm kelvin_budget.BAND_BEFORE["native21s50"] (carried from s49: stage 50
re-nets R135 on SELV copper only; no band part, pad or heat row moves).

    python3 -I validation-results/11-candidates/c50-permit-gate/stage50/scripts/bands50.py [--runs DIR] [--margins FILE]
        [--kelvin FILE] [--check]   -> stage50/results/bands-s50.json, bands-s50.md

--check: exit 1 unless kelvin_budget.BAND_BEFORE["native21s50"] equals the basis band (the S23 wrapper's R0 reading at
HOT5 Q1 on the release network, rounded to 0.01 A; bands49.py's docstring has the basis).
"""
import sys as _s; _s.dont_write_bytecode = True
import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS = HERE.parents[4]
VR = PS / "validation-results"
OUT = HERE.parent / "results"
KV = VR / "02-protection-timing/kelvin"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


b = load("b47", VR / "11-candidates/c47-ref25-grade/scripts/bands47.py")
m = b.m
RT = b.RT
BPRIME = {"R32": (10e3, *RT), "R33": (7.5e3, *RT), "R34": (16e3, *RT), "R35": (11e3, *RT)}
m.PARTS.update(BPRIME)
b.CURRENT.update({"R32": "RT0603BRD0710KL", "R33": "RT0603BRD077K5L", "R34": "RT0603BRD0716KL", "R35": "RT0603BRD0711KL"})
kb = load("kb", KV / "kelvin_budget.py")
FLOOR = kb.FLOOR["native21s50"]
LM = "LM4050AEM3-2.5/NOPB"
NOMINAL = (92.593, 1.0185)          # S23 B'-1.02 V: nominal trip A, U6 VCM V (s23_optb.json)


def s23_module():
    saved = list(_s.argv)
    _s.argv[1:] = [str(PS)]
    try:
        return load("s23", VR / "11-candidates/s23-ocp-cm-2026-10-16/scripts/s23_bands.py")
    finally:
        _s.argv[:] = saved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default=str(b.B3R / "runs"))
    ap.add_argument("--margins", default=str(b.B3R / "margins.json"))
    ap.add_argument("--kelvin", default=str(KV / "budget-native21s50.json"))
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    kel = json.loads(Path(a.kelvin).read_text())
    b.SHIFT = kel["trip_shift_A"]
    b.FLOOR = FLOOR
    checks = m.validate_inputs(overrides=b.CURRENT)
    frozen = b.bom()
    assert frozen["U5"] == LM and frozen["U6"] == "TLV3201AIDBVR", (frozen["U5"], frozen["U6"])
    # nominal trip and VCM of the B' divider (thresholds() at nominal values, REF 2.5 V, VOS 0)
    p0 = {k: v[0] for k, v in m.PARTS.items()}
    p0["R5"] = 1e-3
    i_nom = b.ORIG_T(p0, 2.5, 0.0)[0]
    vcm = 2.5 * p0["R35"] / (p0["R34"] + p0["R35"])
    assert abs(i_nom - NOMINAL[0]) < 0.001 and abs(vcm - NOMINAL[1]) < 0.0001, (i_nom, vcm)
    temps, board = b.solved_temps(a.runs, a.margins)
    rows = []
    for c, t in temps.items():
        rows.append(b.row(LM, f"solved {c}@{b.CASES[c]:g}", ("parts", t)))
        hot = max(t[r] for r in b.NETWORK)
        rows.append(b.row(LM, f"hottest {c}@{b.CASES[c]:g} ({hot:.1f} C uniform, R5 +50 K)", ("uniform", hot)))
    rows.append(b.row(LM, "committed -10/85 C", ("uniform", 85.0)))
    basis = rows[0]
    assert basis["network"].startswith("solved c17.5"), basis
    # S23 comparator readings on this board (record; B' parts passed explicitly)
    s23 = s23_module()
    tlv = s23.CAND["TLV3201AIDBVR"]
    readings = []
    for c, t in temps.items():
        for rd in ("R0", "R1", "R3", "R4"):
            for h5 in ("Q1", "phys"):
                r = s23.band(t, tlv, reading=rd, hot5=s23.HOT5[h5], parts=BPRIME)
                lo, hi = r["shunt_a"]
                readings.append({"network": f"{c}@{b.CASES[c]:g}", "reading": rd, "hot5": h5, "ocp_before_A": r["shunt_a"],
                                 "ocp_low_after_A": round(lo + b.SHIFT, 2), "floor_margin_A": round(lo + b.SHIFT - FLOOR, 2),
                                 "ocp_top_A": hi, "ovp_V": r["ovp_v"], "vcm_ocp_V": r["vcm_V"]["ocp"]})
    base = next(r for r in readings if r["network"].startswith("c17.5") and r["reading"] == "R0" and r["hot5"] == "Q1")
    basis_band = [round(x, 2) for x in base["ocp_before_A"]]
    assert basis_band[0] <= basis["ocp_band_before_kelvin_A"][0] and basis_band[1] >= basis["ocp_band_before_kelvin_A"][1]
    in_budget = list(kb.BAND_BEFORE.get("native21s50", ()))
    out = {"board_sha256": board, "divider": {k: v[0] for k, v in BPRIME.items()}, "mpn_overrides": b.CURRENT,
           "nominal_trip_A": round(i_nom, 3), "u6_vcm_V": round(vcm, 4),
           "kelvin": {"file": str(Path(a.kelvin).relative_to(PS)) if Path(a.kelvin).is_relative_to(PS) else a.kelvin,
                      "trip_shift_A": b.SHIFT, "kelvin_plane_board": kel.get("board_sha256")},
           "floor_A": FLOOR, "ovp_top_rule_V": b.OVP_TOP, "ovp_low_rule_V": b.OVP_LOW_MIN, "validate_inputs": checks,
           "band_basis_s50": {"row": "s23 wrapper, release c17.5_h10@61, TLV3201 R0, HOT5 Q1 (PSRR outside 2.7-5.0 V)",
                              "ref25": LM, "ocp_band_before_kelvin_A": basis_band,
                              "committed_engine_band_A": basis["ocp_band_before_kelvin_A"],
                              "kelvin_budget_BAND_BEFORE": in_budget, "matches": in_budget == basis_band,
                              "low_after_kelvin_A": round(basis_band[0] + b.SHIFT, 2),
                              "floor_margin_A": round(basis_band[0] + b.SHIFT - FLOOR, 2)},
           "solved_temperatures_C": temps,
           "ocp_network_max_C": {c: max(t[r] for r in ("R32", "R33", "R34", "R35")) for c, t in temps.items()},
           "rows": rows, "tlv3201_readings": readings,
           "note": "acceptance = rows (R0, the committed engine); tlv3201_readings = the S23 record (R1 the review's reading, "
                   "R3 typical, R4 spec-literal; HOT5 Q1 4.89-5.11 V / phys 4.632-5.5 V)"}
    OUT.mkdir(exist_ok=True)
    (OUT / "bands-s50.json").write_text(json.dumps(out, indent=1) + "\n")
    L = ["# OCP / OVP bands, stage 50 (generated by stage50/scripts/bands50.py; do not edit)\n",
         f"Board {board[:8]}. Divider R32 10 k / R33 7.5 k / R34 16 k / R35 11 k: nominal {i_nom:.3f} A, U6 VCM {vcm:.4f} V. "
         f"Kelvin shift {b.SHIFT} A ({out['kelvin']['file']}), floor {FLOOR} A; OVP top <= {b.OVP_TOP} V, low >= {b.OVP_LOW_MIN} V.\n",
         "| Network | OCP band before Kelvin (A) | OCP low after Kelvin (margin) | OVP band (V) | OVP top vs 288.02 | Pass |",
         "|---|---|---|---|---:|---|"]
    for r in rows:
        L.append(f"| {r['network']} | {r['ocp_band_before_kelvin_A']} | {r['ocp_low_after_kelvin_A']} ({r['ocp_floor_margin_A']:+.2f}) | "
                 f"{r['ovp_band_V']} | {r['ovp_top_vs_288_02_V']:+.2f} | {'yes' if r['pass'] else '**no**'} |")
    L += ["", "TLV3201 common-mode readings (S23 record):", "",
          "| Network | Reading | HOT5 | OCP before (A) | Low after (margin) | Top (A) |", "|---|---|---|---|---|---:|"]
    for r in readings:
        L.append(f"| {r['network']} | {r['reading']} | {r['hot5']} | {r['ocp_before_A']} | {r['ocp_low_after_A']} "
                 f"({r['floor_margin_A']:+.2f}) | {r['ocp_top_A']} |")
    L += ["", f"kelvin_budget.BAND_BEFORE['native21s50'] = {in_budget}; basis band here {basis_band} "
          f"({'match' if out['band_basis_s50']['matches'] else 'MISMATCH'})"]
    (OUT / "bands-s50.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    if a.check and not out["band_basis_s50"]["matches"]:
        print("bands50: kelvin_budget BAND_BEFORE['native21s50'] is not this board's solve", file=_s.stderr)
        _s.exit(1)


if __name__ == "__main__":
    main()
