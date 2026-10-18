"""Collect every number the README cites into results/summary.json and results/TABLES.md (generated; do not hand-edit).

Inputs: results/{validate,compare_3d,free_air,pans,system,ferrite}.json (run those scripts first; see ../README.md
"Reproduce"). Also solves the installed no-pan coil at 20-60 kHz (enclosure eddy R) for the two candidate layouts.
Run: .venv/bin/python model/report.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import coil_model as CM  # noqa: E402
import system_check as S  # noqa: E402

R = HERE / "results"


def load(n):
    return json.loads((R / f"{n}.json").read_text())


def main():
    val, c3, fa, pans, sysj, fer = (load(n) for n in ("validate", "compare_3d", "free_air", "pans", "system", "ferrite"))
    md = ["# Generated tables (model/report.py) - do not hand-edit", ""]
    summ = {}
    # validation
    v = val
    md += ["## Solver validation (validate.py)", "",
           f"- Air-core R43 winding: FEM {v['V1_air_core']['L_fem_uH']:.2f} uH vs filament sum {v['V1_air_core']['L_filament_uH']:.2f} uH "
           f"({v['V1_air_core']['err_pct']:+.2f} %)",
           "- Loop 10 mm over a half-space vs Dodd-Deeds (dR / dX error %): " + "; ".join(
               f"{r['case']} {r['err_dR_pct']:+.1f} / {r['err_dX_pct']:+.2f}" for r in v["V2_loop_over_halfspace"]),
           f"- Mesh refine 0.6: L {v['V3_V4_convergence']['delta_pct']['pan_ss430_mu200_installed']['L']:+.2f} %, "
           f"R {v['V3_V4_convergence']['delta_pct']['pan_ss430_mu200_installed']['R']:+.2f} % (pan case)", ""]
    f = c3["factors"]
    md += ["## 3D discrete-bar cross-check (compare_3d.py, fem3d/)", "",
           f"- Free-air R43 21.93 turns: 3D {c3['free_air']['L3D_bars_extrapolated_uH']:.2f} uH (h 1/0.7/0.5: "
           + "/".join(f"{x:.2f}" for x in c3["free_air"]["L3D_bars_uH"].values())
           + f"), 2D homogenised {c3['free_air']['L2D_bars_uH']:.2f} uH, k_free = {f['k_free']:.3f}; air-core control 3D/2D = {c3['free_air']['control_ratio']:.4f}",
           f"- With pan: k_L = {f['k_L_pan']:.3f} ({f['k_L_pan_range'][0]:.3f}-{f['k_L_pan_range'][1]:.3f}), k_R = {f['k_R_pan']:.3f} ({f['k_R_pan_range'][0]:.3f}-{f['k_R_pan_range'][1]:.3f})",
           ]
    t = c3.get("transfer_check_80uH")
    if t:
        md.append(f"- Transfer check, 80 uH layout solved in 3D: free {t['free_3D_uH']:.1f} vs 2D x k {t['free_2D_x_k_uH']:.1f} uH; "
                  f"430 pan L {t['pan430_L_3D_uH']:.1f} vs {t['pan430_L_2D_x_k_uH']:.1f} uH, R {t['pan430_R_3D_ohm']:.2f} vs {t['pan430_R_2D_x_k_ohm']:.2f} ohm")
    md.append("")
    # free air
    md += ["## Free-air / installed L and Litz R_ac (run_free_air.py; L is 3D-corrected)", "",
           "| Layout | Turns (inner + outer) | L free | L installed | R_dc 25 C | R_ac 40 kHz 25 C | R_ac 40 kHz 100 C | R_ac 20/30/40/50/60 kHz, 25 C (mOhm) |",
           "|---|---|---|---|---|---|---|---|"]
    for k, c in fa["candidates"].items():
        r25 = {x["f_kHz"]: x for x in c["rac"] if x["T_C"] == 25}
        r100 = {x["f_kHz"]: x for x in c["rac"] if x["T_C"] == 100}
        secs = " + ".join(f"{s['turns']:.2f}" for s in c["sections"])
        md.append(f"| {k} | {c['turns']:.2f} ({secs}) | {c['L_free_uH']:.1f} uH | {c['L_installed_uH']:.1f} uH | {r25[40]['R_dc_mohm']:.1f} mOhm | "
                  f"{r25[40]['R_ac_mohm']:.1f} mOhm | {r100[40]['R_ac_mohm']:.1f} mOhm | " + " / ".join(f"{r25[x]['R_ac_mohm']:.1f}" for x in sorted(r25)) + " |")
    md += ["", "Litz alternatives on the R1 layout (R_dc 25 C / R_ac 40 kHz 25 C / R_ac 40 kHz 100 C, mOhm): " + "; ".join(
        f"{k}: {[r for r in v if r['T_C'] == 25 and r['f_kHz'] == 40][0]['R_dc_mohm']:.1f} / {[r for r in v if r['T_C'] == 25 and r['f_kHz'] == 40][0]['R_ac_mohm']:.1f} / "
        f"{[r for r in v if r['T_C'] == 100 and r['f_kHz'] == 40][0]['R_ac_mohm']:.1f}" for k, v in fa["litz_alternatives_80uH"].items())]
    cs = fa["cases"]
    md += ["", "Sensitivities (R43, L free, uH): " + "; ".join(f"{k} {cs[k]['L_uH']:.1f}" for k in
            ("R43_free", "R43_aircore", "R43_mu1000", "R43_mu5000", "R43_bars_0.5mm_lower", "R43_bundle_z+0.3")),
           "", "Trim table (remove outer turns at constant pitch from R43; L free uH): " + "; ".join(
               f"-{k.split('-')[1]} t: {v['L_uH']:.1f}" for k, v in cs.items() if k.startswith("trim_outer")), ""]
    # installed no-pan vs f
    md += ["## Installed, no pan (enclosure eddy only), 3D-corrected L", "", "| Layout | f kHz | L uH | R_eddy mOhm |", "|---|---|---|---|"]
    summ["installed_nopan"] = {}
    for key in ("R1", "70uH_out6.46"):
        w = __import__("run_pans").layouts()[key]
        rows = []
        for fr in S.FREQS if hasattr(S, "FREQS") else (20e3, 30e3, 40e3, 50e3, 60e3):
            m = CM.build(w, enclosure=True)
            r = m.solve(fr)
            rows.append(dict(f_kHz=fr / 1e3, L_uH=r["L"] * 1e6 * f["k_free"], R_eddy_mohm=r["R"] * 1e3))
            md.append(f"| {key} | {fr / 1e3:.0f} | {rows[-1]['L_uH']:.1f} | {rows[-1]['R_eddy_mohm']:.1f} |")
        summ["installed_nopan"][key] = rows
    md.append("")
    # pans
    md += ["## Loaded L and reflected R, installed, pan base on the glass (run_pans.py; 3D-corrected)", "",
           "| Layout | Pan | mu | Pan D | L 40 kHz uH | R_refl 20/30/40/50/60 kHz (ohm) | heat r<55 / 55-92 / >=92 mm |", "|---|---|---|---|---|---|---|"]
    for lay in ("R1", "80uH_out6.46", "70uH_out6.46", "R43_21.93"):
        for pan in ("ss430", "triply", "cast_iron", "carbon_steel", "aluminium"):
            for tag in ("lo", "nom", "hi"):
                for d in (240.0, 180.0):
                    rows = sorted([r for r in pans["rows"] if r["layout"] == lay and r["pan"] == pan and r["mu_tag"] == tag and r["pan_d_mm"] == d],
                                  key=lambda r: r["f_kHz"])
                    if not rows:
                        continue
                    r40 = [r for r in rows if r["f_kHz"] == 40][0]
                    md.append(f"| {lay} | {pan} | {r40['mu']:.0f} | {d:.0f} | {r40['L_uH']:.1f} | " + " / ".join(f"{r['R_refl_ohm']:.2f}" for r in rows)
                              + f" | {r40['share_r_lt55'] * 100:.0f} / {r40['share_55_90'] * 100:.0f} / {r40['share_rim_ge92'] * 100:.0f} % |")
    md += ["", "Large-signal ESTIMATE (Frohlich effective mu, 40 kHz, 240 mm): " + "; ".join(
        f"{x['layout']} {x['pan']} {x['I_rms']:g} A: L {x['L_uH']:.1f} uH R {x['R_refl_ohm']:.2f} ohm" for x in pans["large_signal"]), ""]
    # system
    md += ["## System check (system_check.py): firmware loop end point, 108/120/132 V x C -5/0/+5 %", "",
           "| Layout | Basis / ceiling / lag rule | Full power | P min / median W | f_op kHz | f_res kHz | min f/f_res | I_pk max A | V_C rms / pk max V | over-ceiling at 60 kHz |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for lay in ("R1", "80uH_out6.46", "70uH_out6.46", "R43_21.93"):
        for k, s in sysj[lay].items():
            if k == "special_loads":
                continue
            md.append(f"| {lay} | {k} | {s['full_power_share'] * 100:.0f} % | {s['P_min_W']:.0f} / {s['P_median_W']:.0f} | {s['f_op_kHz'][0]:.1f}-{s['f_op_kHz'][1]:.1f} | "
                      f"{s['f_res_kHz'][0]:.1f}-{s['f_res_kHz'][1]:.1f} | {s['f_over_fres_min']:.2f} | {s['I_pk_max']:.1f} | {s['Vc_rms_max']:.0f} / {s['Vc_pk_max']:.0f} | {s['over_limit_at_fmax']} |")
    md += ["", "Loads at the loop's 60 kHz start (I_rms A, f_res kHz, Q) and at the 35 kHz floor:", ""]
    for lay in ("R1", "80uH_out6.46", "70uH_out6.46", "R43_21.93"):
        for name, v in sysj[lay]["special_loads"].items():
            md.append(f"- {lay} {name}: " + "; ".join(f"{kk} {vv['I_rms_at_60kHz']:.1f} A, f_res {vv['f_res_kHz']:.1f}, Q {vv['Q']:.0f} "
                                                      f"(at 35 kHz: {vv['I_rms_at_35kHz']:.1f} A, {vv['P_at_35kHz_W']:.0f} W)" for kk, vv in v.items()))
    md.append("")
    md += ["## Ferrite (ferrite.py; 3D discrete bars)", ""]
    for k, v in fer["cases"].items():
        md.append(f"- {k}: {v['B_max_mT_per_A']:.2f} mT/A peak; reaches Bs(100 C) 410 mT at {v['I_pk_at_Bs100_A']:.0f} A pk; " + "; ".join(
            f"{p} {r['B_max_mT']:.0f} mT ({r['frac_Bs_100C']:.2f} Bs)" for p, r in v["points"].items())
            + "; core loss " + ", ".join(f"{kk.replace('_W', '')} {vv:.1f} W" for kk, vv in v["core_loss"].items()))
    md.append("")
    th = load("trim_heating")
    md += ["## Tune move: R1 outer-section trim states (trim_heating.py; 40 kHz, 240 mm pans)", "",
           "| State | Outer turns | L free uH | Pan | L loaded uH | R_refl ohm | rim share (r >= 92) | centre share (r < 55) |", "|---|---|---|---|---|---|---|---|"]
    for r in th["rows"]:
        md.append(f"| {r['state']} | {r['outer_turns']:.2f} | {r['L_free_uH']:.1f} | {r['pan']} | {r['L_loaded_uH']:.1f} | {r['R_refl_ohm']:.2f} | "
                  f"{r['rim_share'] * 100:.1f} % | {r['centre_share'] * 100:.1f} % |")
    fid = load("fidelity")
    md += ["", "## Build fidelity (fidelity.py; R1, 40 kHz, 430 pan mu 200)", "", "| Case | dL free % | dL loaded % | dR loaded % |", "|---|---|---|---|"]
    for r in fid["rows"]:
        if not r["case"].startswith("jitter"):
            md.append(f"| {r['case']} | {r['dL_free_pct']:+.2f} | {r['dL_430_pct']:+.2f} | {r['dR_430_pct']:+.2f} |")
    for k, v in fid["jitter_summary"].items():
        md.append(f"| random radial error {k.replace('jitter_sigma', 'sigma ')} mm (6 seeds, range) | {v['dL_free_pct']['min']:+.2f} to {v['dL_free_pct']['max']:+.2f} | "
                  f"{v['dL_430_pct']['min']:+.2f} to {v['dL_430_pct']['max']:+.2f} | {v['dR_430_pct']['min']:+.2f} to {v['dR_430_pct']['max']:+.2f} |")
    md.append("")
    (R / "TABLES.md").write_text("\n".join(md) + "\n")
    (R / "summary.json").write_text(json.dumps(summ, indent=1) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
