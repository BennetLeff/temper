#!/usr/bin/env python3
"""Thermal-gate summary (s53 vs native-22 proxies, same B3 settings) and the inlet-module budget.

    python3 summarize.py   # -> results/thermal_gate.json, results/inlet_module_budget.json, renders/thermal_gate.png
"""
from __future__ import annotations

import json

import common as C

BOARDS = ("s53", "native22_218", "native22_210B", "native22_218_nofill")
HS = (10, 12, 16, 19, 25)
RELEASE_I_LINE = 13.5
HEAT_FILE_I_LINE = 11.1          # make_heat_sources builds the c28 file's L1 row at 11.1 A (run_basis.py)


def h_needed(pts, target=0.0):
    """Smallest h on the piecewise-linear margin(h) curve with margin >= target; '<= 10' / '> 25' outside the grid."""
    pts = sorted(pts)
    if pts[0][1] >= target:
        return f"<= {pts[0][0]}"
    for (h0, m0), (h1, m1) in zip(pts, pts[1:]):
        if m0 < target <= m1:
            return round(h0 + (target - m0) * (h1 - h0) / (m1 - m0), 1)
    return f"> {pts[-1][0]}"


def series(res, cur, key="worst_margin_k"):
    out = []
    for h in HS:
        c = f"c17.5_h{h}" if cur == 17.5 else f"c28_h{h}_jet100"
        if c in res["cases"]:
            out.append((h, res["cases"][c][key]))
    return out


def main():
    data = {}
    for b in BOARDS:
        p = C.RESULTS / f"b3_{b}.json"
        if p.exists():
            data[b] = json.loads(p.read_text())
    out = {"basis": "B3 body-level model (b3-ratings, unchanged code), bay 61 C, I_line 13.5 A, hot copper, FET drain-lead "
                    "path, both meshes, K_MESH extrapolation and every gated row of b3_ratings_gate; 17.5 A = c17.5 "
                    "(18.375 A trip) with h on both faces; 28 A = c28 (29.4 A) with the S24 jets (h_top 100 on "
                    "JET_REGION) plus base h on both faces. native-22 boards are transplant proxies (proxy.py).",
           "boards": {}}
    s53 = data.get("s53")
    for b, res in data.items():
        row = {}
        for cur in (17.5, 28.0):
            s = series(res, cur)
            s2 = series(res, cur, "worst_margin_k_ron2w")
            sb = series(res, cur, "worst_board_margin_k")
            sb2 = series(res, cur, "worst_board_margin_k_ron2w")
            if not s:
                continue
            cases = {h: res["cases"][f"c17.5_h{h}" if cur == 17.5 else f"c28_h{h}_jet100"] for h, _ in s}
            r = {"margin_k_by_h": dict(s), "binding_by_h": {h: cases[h]["binding"] for h, _ in s},
                 "margin_k_by_h_ron2w": dict(s2), "binding_by_h_ron2w": {h: cases[h]["binding_ron2w"] for h, _ in s},
                 "h_for_margin_ge_0": h_needed(s), "h_for_margin_ge_0_ron2w": h_needed(s2),
                 "board_rows_margin_k_by_h": dict(sb), "board_rows_binding_by_h": {h: cases[h]["binding_board"] for h, _ in s},
                 "board_rows_margin_k_by_h_ron2w": dict(sb2),
                 "board_rows_binding_by_h_ron2w": {h: cases[h]["binding_board_ron2w"] for h, _ in s},
                 "h_for_board_rows_ge_0": h_needed(sb), "h_for_board_rows_ge_0_ron2w": h_needed(sb2),
                 "mean_face_rise_k_by_h": {h: cases[h]["mean_face_rise_k"] for h, _ in s},
                 "advisory_by_h": {h: [(a["item"].split(":")[0], a["est_c"], a["limit_c"]) for a in cases[h]["advisory"]] for h, _ in s},
                 "source_w_by_h": {h: cases[h]["source_w"] for h, _ in s}}
            if s53 and b != "s53":
                ref = dict(series(s53, cur, "worst_board_margin_k"))
                r["delta_vs_s53_board_rows_k_by_h"] = {h: round(m - ref[h], 1) for h, m in sb if h in ref}
                if cur == 17.5 and 10 in ref:
                    r["s53_board_rows_margin_at_h10_k"] = ref[10]
                    r["h_to_match_s53_at_h10"] = h_needed(sb, ref[10])
            row[f"{cur:g}A"] = r
        out["boards"][b] = row
    C.dump(C.RESULTS / "thermal_gate.json", out)
    plot(out)
    budget()
    print(json.dumps({b: {k: {kk: v[kk] for kk in ("margin_k_by_h", "board_rows_margin_k_by_h", "board_rows_binding_by_h",
                                                  "board_rows_margin_k_by_h_ron2w", "h_for_board_rows_ge_0",
                                                  "h_for_board_rows_ge_0_ron2w", "source_w_by_h")}
                          for k, v in r.items()} for b, r in out["boards"].items()}, indent=1, default=str))


def plot(out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    col = {"s53": "#444444", "native22_218": "#d62728", "native22_210B": "#1f77b4", "native22_218_nofill": "#ff9896"}
    lab = {"s53": "s53 (board of record)", "native22_218": "native-22 218 x 140 (proxy)",
           "native22_210B": "native-22 210 x 140 (proxy)",
           "native22_218_nofill": "native-22 218, vacated cells bare (sensitivity)"}
    fig, axs = plt.subplots(1, 2, figsize=(13, 4.8))
    for ax, cur, title in zip(axs, ("17.5A", "28A"), ("17.5 A release basis (18.375 A trip), bay 61 C, h both faces",
                                                      "28 A (29.4 A), S24 jets h_top 100 + base h, bay 61 C")):
        for b, r in out["boards"].items():
            if cur not in r:
                continue
            m = r[cur]["board_rows_margin_k_by_h"]
            m2 = r[cur]["board_rows_margin_k_by_h_ron2w"]
            hs = sorted(int(h) for h in m)
            ax.plot(hs, [m[h] for h in hs], "-o", c=col[b], label=lab[b], ms=4)
            ax.plot(hs, [m2[h] for h in hs], "--", c=col[b], lw=1, label=lab[b] + ", R_on 2 W class [EST]")
        ax.axhline(0, c="k", lw=0.8)
        ax.set_xlabel("board-face h, W/m2K")
        ax.set_ylabel("worst gated B3 board-row margin, K\n(PS2 local-air row excluded on both)")
        ax.set_title(title, fontsize=10)
        ax.grid(True, lw=0.3)
    axs[0].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(C.RENDERS / "thermal_gate.png", dpi=110)
    plt.close(fig)


def budget():
    """What the inlet module now carries: board courtyard, and the heat B3 had on the board for those parts."""
    fp = json.loads((C.RESULTS / "floorplan_native22_218.json").read_text())
    heat = json.loads((C.B3 / "b3/inputs/native21-board-heat-sources-c28.json").read_text())
    rows = {p["ref"]: p for p in heat["parts"]}
    inlet = [r for r in fp["removed"] if r["why"].startswith("inlet")]
    cy = sum(r["courtyard_mm2"] for r in inlet)
    l1 = rows["L1"]["watts_nominal"] * (RELEASE_I_LINE / HEAT_FILE_I_LINE) ** 2
    ps2 = rows["PS2"]["watts_nominal"]
    prx = json.loads((C.RESULTS / "proxy_native22_218.json").read_text())
    line_cu = sum(prx["a4"][c]["dropped_with_removed_parts_w"] for c in ("ac_n_main-p0125-pl18", "ac_l_main-p0125-pl18"))
    line_cu *= (RELEASE_I_LINE / 15.0) ** 2           # run_study.cases(): line rows scale (I_line / 15 A)^2, 20 C copper
    out = {
        "parts": [{"ref": r["ref"], "what": r["why"].split(": ", 1)[1], "board_courtyard_mm2": r["courtyard_mm2"]} for r in inlet],
        "board_courtyard_leaving_mm2": round(cy, 1),
        "module_area_added_mm2_est": [round(cy / 0.65), round(cy / 0.50)],
        "module_area_note": "[EST] courtyard / 0.50-0.65 packing (a carrier with mains spacing); D-22 reserved "
                            "110 x 80 x 50 mm (8,800 mm2 plan) before these parts",
        "heat_leaving_board_w": {"L1 at 13.5 A (B3 heat row, c28 file x (13.5/11.1)^2)": round(l1, 3),
                                 "PS2 MPM-20-24 whole loss (B3 module row)": round(ps2, 3),
                                 "board line copper J1-F1-L1 at 13.5 A, 20 C (A4 cells owned by removed parts)": round(line_cu, 3)},
        "heat_not_quantified": ["F1 fuse element I2R (no B3 row)", "R130 blower resistor (no B3 row)",
                                "RV1, C1-C4, R1/R2: small (no B3 rows)"],
        "d22_allowance_w": 8.0,
        "module_heat_total_w_est_min": round(8.0 + l1 + ps2, 2),
    }
    C.dump(C.RESULTS / "inlet_module_budget.json", out)


if __name__ == "__main__":
    main()
