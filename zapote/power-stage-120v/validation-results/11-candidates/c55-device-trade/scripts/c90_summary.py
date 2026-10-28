#!/usr/bin/env python3
"""One row per candidate for the README's ranked table, read only from this study's result files:
results/switching.json (c20), results/loss_thermal.json (c50), results/gate_heat.json (c40), results/cost.json (c70).

    python3 -I c90_summary.py   -> ../results/summary.json, ../results/summary.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import C55  # noqa: E402

R = C55 / "results"
SW = json.loads((R / "switching.json").read_text())
LT = json.loads((R / "loss_thermal.json").read_text())["devices"]
GH = {r["case"]: r for r in json.loads((R / "gate_heat.json").read_text())["rows"]}
CO = json.loads((R / "cost.json").read_text())["parts"]

# (label, part key in loss_thermal, cost MPN, S4-at-max-Qrr grid, S4-at-typical-Qrr grid, decision grid, gate-heat case)
CANDS = [
    ("1 CFD7, s42 network (68 ohm / 4.7 nF), as built", "IPW65R018CFD7", "IPW65R018CFD7XKSA1",
     ("cfd7_c39_tt260", "s4L"), ("cfd7_c39_tt125", "s4L"), ("cfd7_c39_tt260", "full"), "CFD7 s42 network (control)"),
    ("2 CM8, 100 ohm / 1 nF", "IPW65R018CM8", "IPW65R018CM8XKSA1",
     ("cm8_r100_tt180", "fullL"), ("cm8_r100_tt100", "s4bL"), ("cm8_r100_tt180", "fullL"),
     "CM8 + 100 ohm / 1 nF (representative)"),
    ("2' CM8, 39 ohm / 1 nF (DECISIONS 54 route)", None, "IPW65R018CM8XKSA1",
     ("cm8_r39_tt180", "full"), ("cm8_r39_tt100", "full"), ("cm8_r39_tt180", "full"), "CM8 + 39 ohm / 1 nF"),
    ("3 SiC IMW65R026M2H, +15 V, 8.2 ohm / 1 nF", "IMW65R026M2H_15", "IMW65R026M2HXKSA1",
     ("sic26_15_r8p2", "full"), ("sic26_15_r8p2", "full"), ("sic26_15_r8p2", "full"),
     "IMW65R026M2H 15 V, 8.2 ohm / 1 nF"),
    ("3 SiC IMW65R026M2H, +15 V, DT 200 ns", "IMW65R026M2H_15_dt200", "IMW65R026M2HXKSA1",
     ("sic26_15_r8p2", "full"), ("sic26_15_r8p2", "full"), ("sic26_15_r8p2", "full"),
     "IMW65R026M2H 15 V, 8.2 ohm / 1 nF"),
    ("3 SiC IMW65R026M2H, +15 V, s42 network 68 ohm / 4.7 nF, DT 200 ns", "IMW65R026M2H_15_s42_dt200",
     "IMW65R026M2HXKSA1", ("sic26_15_r68c4p7", "full"), ("sic26_15_r68c4p7", "full"), ("sic26_15_r68c4p7", "full"),
     "IMW65R026M2H 15 V, s42 network 68 ohm / 4.7 nF"),
    ("3 SiC IMW65R026M2H, +15 V, s42 network, DT unchanged (FET-only swap)", "IMW65R026M2H_15_s42",
     "IMW65R026M2HXKSA1", ("sic26_15_r68c4p7", "full"), ("sic26_15_r68c4p7", "full"), ("sic26_15_r68c4p7", "full"),
     "IMW65R026M2H 15 V, s42 network 68 ohm / 4.7 nF"),
    ("3 SiC IMW65R026M2H, +18 V, 8.2 ohm / 1 nF", "IMW65R026M2H_18", "IMW65R026M2HXKSA1",
     ("sic26_18_r8p2", "s4b"), ("sic26_18_r8p2", "s4b"), ("sic26_18_r8p2", "s4b"), "IMW65R026M2H 18 V, 8.2 ohm / 1 nF"),
    ("3 SiC IMW65R026M2H, +18 V, DT 200 ns", "IMW65R026M2H_18_dt200", "IMW65R026M2HXKSA1",
     ("sic26_18_r8p2", "s4b"), ("sic26_18_r8p2", "s4b"), ("sic26_18_r8p2", "s4b"), "IMW65R026M2H 18 V, 8.2 ohm / 1 nF"),
    ("3 SiC C3M0025065D [EST, no model]", "C3M0025065D", "C3M0025065D", None, None, None, None),
    ("3 SiC NTHL032N065M3S [EST, no model]", "NTHL032N065M3S", "NTHL032N065M3S", None, None, None, None),
    ("4a RC-IGBT IHW40N65R6, 35-60 kHz", "IHW40N65R6", "IHW40N65R6XKSA1",
     ("rch6_r8p2", "s4b"), ("rch6_r8p2", "s4b"), ("rch6_r8p2", "s4b"), "IHW40N65R6 8.2 ohm / 1 nF"),
    ("4a RC-IGBT IHW40N65R5, 35-60 kHz (loss grid incomplete)", "IHW40N65R5", "IHW40N65R5XKSA1", None, None, None,
     None),
]


def s4(dev_grid):
    if not dev_grid or dev_grid[0] not in SW or dev_grid[1] not in SW[dev_grid[0]]:
        return None
    s = SW[dev_grid[0]][dev_grid[1]]
    x = s.get("S4", {})
    return {"slew": max(x.get("max_slew2080_esl10_Vns", 0), x.get("max_slew2080_esl1.06_Vns", 0)),
            "difdt": x.get("max_difdt_75_25_Apus"), "vds": x.get("max_vds_V"), "no_edge": x.get("no_edge_rows"),
            "ratio": s["ratings_check"].get("diode_dvdt_ratio"), "rating": s["ratings_check"].get("diode_dvdt_rating_Vns")}


def main():
    rows = []
    for label, part, mpn, smax, styp, dgrid, gcase in CANDS:
        row = {"candidate": label, "part": part, "mpn": mpn, "S4_max_Qrr": s4(smax), "S4_typ_Qrr": s4(styp)}
        if dgrid and dgrid[0] in SW and dgrid[1] in SW[dgrid[0]]:
            s = SW[dgrid[0]][dgrid[1]]
            row["decision_grid"] = {"grid": "/".join(dgrid), "complete": f"{s['complete']}/{s['runs']}",
                                    "pass": s["screens_c25_pass"], "pass_hot": s["screens_c25_pass_hot"],
                                    "S1_t_trans_ns": s.get("S1", {}).get("worst_t_trans_ns"),
                                    "S2_vds_V": s.get("S2", {}).get("max_vds_V"),
                                    "max_off_gate_V": s["ratings_check"].get("max_off_gate_V")}
        lt = LT.get(part) if part else None
        if lt and "missing_energy_grid" not in lt:
            for key, v in lt.items():
                row.setdefault("thermal", {})[key] = {
                    "S8_tj": v["S8"].get("tj_max"), "S8_ts": v["S8"].get("ts"), "S8_P_dev_W": v["S8"].get("p_worst_W"),
                    "S8_P_4dev_W": v["S8"].get("p_total_4_W"), "bench_tj": v["bench"].get("tj_max"),
                    "bench_ts": v["bench"].get("ts"), "tj_limit": v["tj_limit_C"],
                    "S8_runaway_f": v["S8"].get("runaway_at_f"), "bench_runaway_f": v["bench"].get("runaway_at_f")}
        if gcase and gcase in GH and "P_Ron_W" in GH[gcase]:
            g = GH[gcase]
            row["gate"] = {k: g[k] for k in ("Q_nC", "P_Ron_W", "I_bias_channel_mA", "R10_margin_at_17.5A_K_est")}
        c = CO[mpn]
        row["cost"] = {k: c[k] for k in ("per_board_20", "per_board_500", "delta_vs_cfd7_500", "stock", "lead_time")}
        rows.append(row)
    (R / "summary.json").write_text(json.dumps(rows, indent=1) + "\n")
    md = ["| candidate | S4 diode dv/dt, max Qrr (typ) V/ns, ratio | S4 diF/dt A/us | grid pass | S8 Tj 17.5 / 28 A C "
          "| S8 4-device W 17.5 / 28 A | bench Tj 17.5 A C | R_on W | $/board 20 / 500 | stock |", "|" + "---|" * 10]
    for r in rows:
        a, b = r["S4_max_Qrr"], r["S4_typ_Qrr"]
        th = r.get("thermal", {})
        sets = sorted({k.split("|")[0] for k in th}) or [None]
        dg = r.get("decision_grid", {})
        for fs in sets:
            t17 = th.get(f"{fs}|17.5", {})
            t28 = th.get(f"{fs}|28", {})
            name = r["candidate"] + (f" [{fs} kHz]" if fs and len(sets) > 1 else "")
            md.append(f"| {name} | " + (f"{a['slew']:.1f} ({b['slew']:.1f}), {a['ratio']}" if a and b else "-")
                      + f" | {a['difdt'] if a else '-'} | {dg.get('pass', '-')} of {dg.get('complete', '-').split('/')[-1]} | "
                      f"{t17.get('S8_tj', '-')} / {t28.get('S8_tj', '-')} | {t17.get('S8_P_4dev_W', '-')} / "
                      f"{t28.get('S8_P_4dev_W', '-')} | {t17.get('bench_tj', '-')} | {r.get('gate', {}).get('P_Ron_W', '-')} | "
                      f"{r['cost']['per_board_20']} / {r['cost']['per_board_500']} | {r['cost']['stock']} |")
    (R / "summary.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
