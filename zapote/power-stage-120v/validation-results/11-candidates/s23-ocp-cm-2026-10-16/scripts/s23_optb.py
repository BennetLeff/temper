#!/usr/bin/env python3
"""S23 option B / B': re-ratio the OCP dividers (R32/R33 at ocp_node, R34/R35 at ocp_thresh) to move U6's trip common
mode, holding the nominal trip current. Same engine and comparator terms as s23_bands.py (imported).

    python3 -I s23_optb.py [PS_DIR]   -> ../results/s23_optb.json, ../results/s23_optb.md

Search: E192 values (0.1 % / 25 ppm thin film, the RT0603BRD class the model already uses), R32 + R33 and R34 + R35 near
the committed 20 k / 24.3 k (REF25 current budget, audit.rs ocp_threshold_load), R32 || R33 within 4-6 k (C30 filter
tau, the 500 ns front-end RC of the timing model), nominal trip within 0.25 A of the s48 nominal. Each design is run
through every exact_corners vertex at the solved release and c28 networks, with the TLV3201 readings R0 / R1 / R3 / R4.
"""
import sys
sys.dont_write_bytecode = True
import importlib.util
import bisect
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("s23", HERE / "s23_bands.py")
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
m, b = s.m, s.b
E192 = [100, 101, 102, 104, 105, 106, 107, 109, 110, 111, 113, 114, 115, 117, 118, 120, 121, 123, 124, 126, 127, 129,
        130, 132, 133, 135, 137, 138, 140, 142, 143, 145, 147, 149, 150, 152, 154, 156, 158, 160, 162, 164, 165, 167, 169,
        172, 174, 176, 178, 180, 182, 184, 187, 189, 191, 193, 196, 198, 200, 203, 205, 208, 210, 213, 215, 218, 221, 223,
        226, 229, 232, 234, 237, 240, 243, 246, 249, 252, 255, 258, 261, 264, 267, 271, 274, 277, 280, 284, 287, 291, 294,
        298, 301, 305, 309, 312, 316, 320, 324, 328, 332, 336, 340, 344, 348, 352, 357, 361, 365, 370, 374, 379, 383, 388,
        392, 397, 402, 407, 412, 417, 422, 427, 432, 437, 442, 448, 453, 459, 464, 470, 475, 481, 487, 493, 499, 505, 511,
        517, 523, 530, 536, 542, 549, 556, 562, 569, 576, 583, 590, 597, 604, 612, 619, 626, 634, 642, 649, 657, 665, 673,
        681, 690, 698, 706, 715, 723, 732, 741, 750, 759, 768, 777, 787, 796, 806, 816, 825, 835, 845, 856, 866, 876, 887,
        898, 909, 920, 931, 942, 953, 965, 976, 988]
VALS = sorted({v * 10 for v in E192} | {v * 100 for v in E192})          # 1.00 k .. 98.8 k
EXISTING = {1e3, 2.21e3, 2.94e3, 4.42e3, 6.2e3, 10e3, 11e3, 12.6e3, 15.8e3, 49.9e3, 63.4e3, 90.9e3, 104e3, 105e3, 140e3, 11.7e3}
REF, R5 = 2.5, 1e-3


def nominal(r32, r33, r34, r35):
    k, kp = r35 / (r34 + r35), r33 / (r32 + r33)
    return REF * (kp - k) / (1 - kp) / R5, REF * k, 1 - kp


def search(i_target, vcm_lo, vcm_hi):
    out = []
    for r34 in VALS:
        for r35 in VALS:
            if not 21e3 <= r34 + r35 <= 27.5e3:
                continue
            vcm = REF * r35 / (r34 + r35)
            if not vcm_lo <= vcm <= vcm_hi:
                continue
            for r33 in VALS:
                # solve R32 for the target, then snap to E192
                k = r35 / (r34 + r35)
                x = i_target * R5 / REF
                kp = (k + x) / (1 + x)
                r32_ideal = r33 * (1 - kp) / kp
                j = bisect.bisect_left(VALS, r32_ideal)
                for r32 in VALS[max(0, j - 1): j + 1]:
                    if abs(r32 / r32_ideal - 1) > 0.006:
                        continue
                    if not 17e3 <= r32 + r33 <= 23e3:
                        continue
                    th = r32 * r33 / (r32 + r33)
                    if not 4.0e3 <= th <= 6.0e3:
                        continue
                    i, v, w = nominal(r32, r33, r34, r35)
                    if abs(i - i_target) <= 0.25:
                        new = sum(1 for r in (r32, r33, r34, r35) if r not in EXISTING)
                        out.append((new, abs(i - i_target), r32, r33, r34, r35, i, v, w))
    return sorted(out)


def mpn(r):
    if abs(r - 11.7e3) < 1:
        return "TNPW060311K7BEEA"
    kv = r / 1e3
    txt = (f"{kv:g}".replace(".", "K") if "." in f"{kv:g}" else f"{kv:g}K")
    return f"RT0603BRD07{txt}L"


def main():
    temps, board = b.solved_temps(b.B3R / "runs", b.B3R / "margins.json")
    nets = {"release c17.5@61": temps["c17.5_h10"], "c28@55": temps["c28_h10"]}
    tlv = s.CAND["TLV3201AIDBVR"]
    shift, _ = s.kelvin_shift(tlv["iq"], tlv["iq"])
    p0 = {k: v[0] for k, v in m.PARTS.items()}
    i0 = b.ORIG_T(p0, REF, 0.0)[0]
    RT = (0.001, 25e-6)
    designs = {"as built (12.6 k / 11.7 k, 10 k / 10 k)": (10e3, 10e3, 12.6e3, 11.7e3)}
    picks = {}
    for lo, hi, tag in ((0.78, 0.84, "0.8"), (0.88, 0.93, "0.9"), (0.97, 1.03, "1.0")):
        found = search(i0, lo, hi)
        if found:
            picks[tag] = found[:5]
    # explicit picks: E192 values that JLC stocks (LCSC codes in results.md); the search tops stay in the JSON.
    # The automatic 0.8 V top needs RT0603BRD076K42L (JLC stock 0) and the 1.0 V top RT0603BRD077K59L (not listed).
    designs.update({"B' 0.90 V (11k / 6.81k, 15.8k / 8.87k)": (11e3, 6.81e3, 15.8e3, 8.87e3),
                    "B' 0.94 V (11k / 7.32k, 16.5k / 10k)": (11e3, 7.32e3, 16.5e3, 10e3),
                    "B' 1.02 V (10k / 7.5k, 16k / 11k)": (10e3, 7.5e3, 16e3, 11e3)})
    rows = []
    for name, (r32, r33, r34, r35) in designs.items():
        parts = {"R32": (r32, *RT), "R33": (r33, *RT), "R34": (r34, *RT), "R35": (r35, *RT)}
        i, v, w = nominal(r32, r33, r34, r35)
        for net, t in nets.items():
            for rd in ("R0", "R1", "R3", "R4"):
                for h5 in ("Q1", "phys"):
                    r = s.row(f"{name} {net} {rd} {h5}", t, tlv, shift, reading=rd, hot5=s.HOT5[h5], parts=parts)
                    r.update({"design": name, "network": net, "reading": rd, "hot5": h5, "nominal_trip_A": round(i, 3),
                              "vcm_nom_V": round(v, 4), "shunt_weight": round(w, 4), "dI_dVOS_A_per_mV": round(1 / w, 3),
                              "R32||R33_ohm": round(r32 * r33 / (r32 + r33)), "R34||R35_ohm": round(r34 * r35 / (r34 + r35)),
                              "ref_load_kohm": [round((r32 + r33) / 1e3, 2), round((r34 + r35) / 1e3, 2)],
                              "values": {"R32": r32, "R33": r33, "R34": r34, "R35": r35},
                              "mpn": {"R32": mpn(r32), "R33": mpn(r33), "R34": mpn(r34), "R35": mpn(r35)}})
                    # bench allowance: the extra adverse offset (beyond the TLV3201 4 mV at VCC/2 and the PSRR term)
                    # that still meets the floor, = R0 margin / (A per mV)
                    rows.append(r)
    allow = {}
    for name in designs:
        for net in nets:
            r0 = next(r for r in rows if r["design"] == name and r["network"] == net and r["reading"] == "R0" and r["hot5"] == "Q1")
            allow[f"{name} | {net}"] = round(r0["floor_margin_A"] / r0["dI_dVOS_A_per_mV"], 3)
    out = {"board_sha256": board, "nominal_trip_A_s48": round(i0, 3), "kelvin_shift_A": shift, "search_top5": picks,
           "rows": rows, "bench_allowance_mV_at_Q1_HOT5": allow}
    s.OUT.mkdir(exist_ok=True)
    (s.OUT / "s23_optb.json").write_text(json.dumps(out, indent=1) + "\n")
    L = [f"Board {board[:8]}; nominal trip {i0:.3f} A; Kelvin {shift} A; floor {s.FLOOR} A", "",
         "| design | net | reading | HOT5 | nominal A | VCM | A/mV | OCP before | low after (margin) | top / bank V |",
         "|---|---|---|---|---:|---:|---:|---|---|---|"]
    for r in rows:
        L.append(f"| {r['design']} | {r['network']} | {r['reading']} | {r['hot5']} | {r['nominal_trip_A']} | {r['vcm_nom_V']} | "
                 f"{r['dI_dVOS_A_per_mV']} | {r['ocp_before_A']} | {r['ocp_low_after_A']} ({r['floor_margin_A']:+.2f}) | "
                 f"{r['ocp_top_A']} / {r['bank_V']} |")
    L += ["", "Bench allowance (mV of adverse CM + other unmodelled offset at the trip VCM, Q1 HOT5, on top of 4 mV VIO and PSRR):"]
    L += [f"- {k}: {v}" for k, v in allow.items()]
    L += ["", "Designs: " + json.dumps({k: [round(x) for x in v] for k, v in designs.items()}),
          "MPNs: " + json.dumps({r['design']: r['mpn'] for r in rows if r['network'].startswith('release') and r['reading'] == 'R0' and r['hot5'] == 'Q1'})]
    (s.OUT / "s23_optb.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    print(json.dumps(picks, indent=0)[:2500])


if __name__ == "__main__":
    main()
