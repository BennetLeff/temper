#!/usr/bin/env python3
"""Loss per device and junction temperature on the bench sink and on the production sink S8, at the 17.5 A release
ceiling and the 28 A route (tank RMS at the 1.05 x trip: 18.375 / 29.4 A, as the bench tool and DECISIONS 15).

Loss model (per device, line-cycle averaged, the device study's basis D extended to each candidate):
  * conduction  MOSFET: I_t^2 / 2 x RDS(on),max(Tj)  (RDS,max(25 C) x the datasheet typical RDS(Tj)/RDS(25 C) at the
                drive VGS; device_data.json). IGBT (RC): the HF half-wave splits into diode (lag angle phi) and IGBT
                (pi - phi) parts, V0 + r*I fits of the datasheet output curves at the Tj grid, line-averaged.
  * switching   the candidate's own deck energy grid (trade.py 'energy': V 20..198 V, I 2..60 A, Tj 100/150 C,
                DT 569 ns = the longest window edge, both directions, long 3.75 us window), integrated with the device
                study's p_switch_leg() (bus = Vpk|sin|, turn-off current = 2 I_t |sin| sin(phi), phi = 60 deg).
                It holds the turn-off (and the IGBT tail), the dead-time diode / third-quadrant conduction in excess of
                the channel (or, for the IGBT, of the steady diode) and any slow turn-on penalty.
Sinks (tools imported read-only, nothing re-derived):
  * S8 production: device-study thermal.solve() (S8 R_SA 0.29 + pedestal, 13 CFM, 50 C inlet, M11 AlN Rcs 0.634,
    upstream air heating in device order, BR1). 120 V line (its basis).
  * bench: bench-sink-r1 bench_thermal.solve() (Wakefield 511-3M natural convection, SIL PAD 2000 + design shim at the
    worst pressure corner, 30 C ambient, BR1 at 13.5 A line, 132 V line). Its p_fet() and RTH_JC_FET are replaced by the
    candidate's.
Controls (asserted before any candidate row): CFD7 with the device study's committed energy grid reproduces
  C1 the DS thermal.json basis-D S8 rows and C2 the bench-sink-r1 thermal.json rows (SIL PAD 2000, basis D);
  C3 this study's generic die-energy measure in the long window, on the device study's own 8.2 ohm deck, gives the
  same S8 Tj as the device study's vendor heat-channel grid (within 0.2 K).

    python3 -I c50_loss_thermal.py   -> ../results/loss_thermal.json, ../results/loss_thermal.md
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import C55, DS_DIR, SIMS, VR, _load  # noqa: E402

T = _load("ds_thermal_c50", DS_DIR / "scripts/thermal.py")
BENCH_DIR = VR / "11-candidates/bench-sink-r1/scripts"
sys.path.insert(0, str(BENCH_DIR))
BT = _load("bench_thermal_c50", BENCH_DIR / "bench_thermal.py")
P = BT.P
DATA = json.loads((Path(__file__).resolve().parent / "device_data.json").read_text())

CEILINGS = {"17.5": 17.5, "28": 28.0}
FREQS = (35e3, 50e3, 60e3)
PHI = math.radians(60.0)
MOS = ("Q5", "Q6", "Q3", "Q2")


def grid_from(path: Path, key="eg_extra_J"):
    rows = [r for r in json.loads(path.read_text())["rows"] if r["status"] == "complete" and r.get(key) is not None]
    g = {}
    for r in rows:
        g.setdefault((r["leg"], r["temp_C"]), {}).setdefault((r["vbus"], r["il"]), {})[r["dir"]] = r[key]
    return g


def ratio(tab, tj):
    """piecewise-linear in Tj over the datasheet points [[T, value], ...] (clamped)."""
    pts = sorted(tab)
    if tj <= pts[0][0]:
        return pts[0][1]
    for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
        if tj <= t1:
            return v0 + (v1 - v0) * (tj - t0) / (t1 - t0)
    (t0, v0), (t1, v1) = pts[-2], pts[-1]
    return v1 + (v1 - v0) * (tj - t1) / (t1 - t0)


def p_cond(d, tj, it):
    if d["class"] != "IGBT":
        r = d["rds_max25"] * ratio(d["rds_typ_ratio_vs_T"], tj)
        return it * it / 2 * r
    # RC-IGBT: per HF period the device carries a half sine of peak Ip, the first phi as diode, then pi - phi as IGBT
    v0, rc = ratio(d["vce_V0_vs_T"], tj), ratio(d["vce_r_vs_T"], tj)
    vf0, rf = ratio(d["vf_V0_vs_T"], tj), ratio(d["vf_r_vs_T"], tj)
    e1, e2 = 2 * it * 2 / math.pi, (2 * it) ** 2 / 2          # line averages of Ip and Ip^2 (Ip = 2 I_t |sin|)
    avg_i = e1 / (2 * math.pi) * (1 + math.cos(PHI))
    rms2_i = e2 / (2 * math.pi) * ((math.pi - PHI) / 2 + math.sin(2 * PHI) / 4)
    avg_d = e1 / (2 * math.pi) * (1 - math.cos(PHI))
    rms2_d = e2 / (2 * math.pi) * (PHI / 2 - math.sin(2 * PHI) / 4)
    return v0 * avg_i + rc * rms2_i + vf0 * avg_d + rf * rms2_d


def grid_path(d) -> Path:
    src = d["energy_grid"]["path"]
    return Path(src) if src.startswith("/") else C55 / src


def diode_extra(dev, tj, it):
    """RC-IGBT: the diode share of conduction loss sees the diode RthJC instead of the IGBT one [EST: separate
    regions on one die, both RthJC values from the datasheet]; extra rise = P_diode x (RthJC,diode - RthJC,IGBT)."""
    d = dev.d
    vf0, rf = ratio(d["vf_V0_vs_T"], tj), ratio(d["vf_r_vs_T"], tj)
    e1, e2 = 2 * it * 2 / math.pi, (2 * it) ** 2 / 2
    pd = vf0 * e1 / (2 * math.pi) * (1 - math.cos(PHI)) + rf * e2 / (2 * math.pi) * (PHI / 2 - math.sin(2 * PHI) / 4)
    return round(pd * (d["rjc_diode"] - d["rjc"]), 2)


class Dev:
    def __init__(self, name):
        self.name = name
        self.d = DATA["devices"][name]
        self.grid = grid_from(grid_path(self.d), self.d["energy_grid"]["key"])
        self._sw = {}

    def p_sw(self, leg, temp, vpk, it, f):
        if (leg, temp) not in self.grid:          # leg-A-only grids ('eA', 'eAs') serve both legs
            leg = "A"
        k = (leg, temp, round(vpk, 3), it, f)
        if k not in self._sw:
            self._sw[k] = T.p_switch_leg(self.grid, leg, temp, vpk, it, f) / 2
        return self._sw[k]

    def p_dev(self, ref, tj, it, f, vpk):
        leg = P.FET_LEG[ref]
        a, b = self.p_sw(leg, 100, vpk, it, f), self.p_sw(leg, 150, vpk, it, f)
        x = min(max((tj - 100) / 50, 0), 1)
        return p_cond(self.d, tj, it) + a + (b - a) * x


def s8(dev: Dev, it, f, line_v=120.0):
    case = {"frequency_hz": f, "i_rms_a": it, "target_w": 1239.0, "vrms_v": line_v}
    r = T.solve(case, T.SINKS["S8"] + T.R_PED, lambda ref, tj: dev.p_dev(ref, tj, it, f, line_v * math.sqrt(2)),
                dev.d["rjc"])
    return r


def bench(dev: Dev, ceil, f, t_amb=30.0):
    it = BT.i_tank(ceil)
    BT.p_fet = lambda ref, tj, c, ff, basis: dev.p_dev(ref, tj, it, ff, BT.V_PK)
    P.RTH_JC_FET = dev.d["rjc"]
    worst = None
    for ac, fc in BT.CORNERS:
        r = BT.solve(P.PAD_CHOICE, ceil, f, "D", t_amb, ac, force_case=fc)
        if r is None:
            return None
        if worst is None or max(r["tj"].values()) > max(worst["tj"].values()):
            worst = r
    return worst


def breakdown(dev: Dev, tj, it, f, vpk):
    cond = p_cond(dev.d, tj, it)
    sw = {leg: dev.p_dev("Q2" if leg == "A" else "Q5", tj, it, f, vpk) - cond for leg in "AB"}
    return {"cond_W": round(cond, 2), "sw_dead_W_legA": round(sw["A"], 2), "sw_dead_W_legB": round(sw["B"], 2)}


def controls():
    """C1: CFD7 + DS committed grid through this script's path = DS thermal.json basis D (S8);
    C2: same through the bench path = bench-sink-r1 results/thermal.json (SIL PAD 2000, basis D, 30/40 C)."""
    d = Dev("_ctrl_cfd7_ds")
    ref = json.loads((DS_DIR / "results/thermal.json").read_text())["devices"]["IPW65R018CFD7"]["cases"]
    worst1 = 0.0
    for cname, (i, f, V, Pw) in T.CASES.items():
        case = {"frequency_hz": f, "i_rms_a": i, "target_w": Pw, "vrms_v": V}
        r = T.solve(case, T.SINKS["S8"] + T.R_PED, lambda ref_, tj: d.p_dev(ref_, tj, i, f, V * math.sqrt(2)),
                    d.d["rjc"])
        worst1 = max(worst1, abs(round(r["max_tj"], 1) - ref[cname]["D_deck"]["S8"]["tj_max"]))
    bref = json.loads((VR / "11-candidates/bench-sink-r1/results/thermal.json").read_text())["pads"][P.PAD_CHOICE]["rows"]
    worst2 = 0.0
    n2 = 0
    for row in bref:
        if row["basis"] != "D" or row.get("runaway"):
            continue
        r = bench(d, row["ceil"], row["f"], row["t_amb"])
        worst2 = max(worst2, abs(max(r["tj"].values()) - row["tj"]))
        n2 += 1
    # C3: the measure used for every candidate (generic die energy, long window; trade.py 'energy' on cfd7_8p2, the
    # device study's own network) against the device study's vendor heat-channel grid: S8 Tj at 17.5 / 28 A, 35-60 kHz
    g = Dev("_ctrl_cfd7_8p2_generic")
    worst3 = 0.0
    for it in (18.375, 29.4):
        for f in FREQS:
            ra, rb = s8(d, it, f), s8(g, it, f)
            worst3 = max(worst3, abs(ra["max_tj"] - rb["max_tj"]))
    ok = worst1 <= 0.05 and worst2 <= 1e-6 and worst3 <= 0.2
    return {"C1_S8_DS_thermal_json_basisD_max_abs_dC": worst1, "C2_bench_thermal_json_basisD_max_abs_dC": worst2,
            "C2_rows": n2, "C3_generic_long_vs_DS_vendor_S8_max_abs_dC": round(worst3, 3), "pass": ok}


def main():
    c = controls()
    print("controls", c)
    assert c["pass"], c
    out = {"controls": c, "assumptions": {"phi_deg": 60, "S8": "DS thermal.solve, 13 CFM, 50 C inlet, Rcs 0.634, 120 V",
                                          "bench": f"bench_thermal.solve, {P.SINK_PN}, {P.PAD_CHOICE}, 30 C, 132 V",
                                          "I_t": "1.05 x ceiling (18.375 / 29.4 A)", "freqs_Hz": FREQS},
           "devices": {}}
    md = ["| device | freq set | ceiling | worst f kHz (S8 / bench) | S8: P worst device W (cond / sw+dead) | S8 Tj max C | "
          "Tj limit C | S8 sink W | bench: P worst W | bench Tj max C | bench sink C |", "|" + "---|" * 11]
    for name, d in DATA["devices"].items():
        if name.startswith("_"):
            continue
        if not grid_path(d).is_file():
            out["devices"][name] = {"missing_energy_grid": d["energy_grid"]["path"]}
            continue
        dev = Dev(name)
        res = {}
        for fs_name, freqs in d.get("freq_sets", {"35-60": list(FREQS)}).items():
            for cl, ceil in CEILINGS.items():
                it = 29.4 if ceil == 28.0 else 1.05 * ceil
                ws, wb = None, None
                for f in freqs:
                    r = s8(dev, it, f)
                    if r is None:
                        ws = {"runaway": True, "f": f}
                        break
                    if ws is None or r["max_tj"] > ws["max_tj"]:
                        ws = dict(r, f=f)
                for f in freqs:
                    r = bench(dev, ceil, f)
                    if r is None:
                        wb = {"runaway": True, "f": f}
                        break
                    if wb is None or max(r["tj"].values()) > max(wb["tj"].values()):
                        wb = dict(r, f=f)
                row = {"I_t": it, "tj_limit_C": d["ratings"]["tj_max_C"]}
                if ws.get("runaway"):
                    row["S8"] = {"runaway_at_f": ws["f"]}
                else:
                    pw = max(v for k, v in ws["powers"].items() if k != "BR1")
                    row["S8"] = {"f": ws["f"], "tj_max": round(ws["max_tj"], 1), "worst": ws["worst"],
                                 "psink": round(ws["psink"], 1), "ts": round(ws["ts"], 1), "p_worst_W": round(pw, 2),
                                 "p_total_4_W": round(sum(v for k, v in ws["powers"].items() if k != "BR1"), 1),
                                 "breakdown_at_worst_tj": breakdown(dev, ws["max_tj"], it, ws["f"], 120 * math.sqrt(2))}
                    if d["class"] == "IGBT":
                        row["S8"]["diode_region_extra_K_est"] = diode_extra(dev, ws["max_tj"], it)
                if wb.get("runaway"):
                    row["bench"] = {"runaway_at_f": wb["f"]}
                else:
                    row["bench"] = {"f": wb["f"], "tj_max": round(max(wb["tj"].values()), 1), "ts": round(wb["ts"], 1),
                                    "p_worst_W": round(max(wb["p"].values()), 2), "psink": round(wb["ptot"], 1),
                                    "breakdown_at_worst_tj": breakdown(dev, max(wb["tj"].values()), it, wb["f"], BT.V_PK)}
                res[f"{fs_name}|{cl}"] = row
                s, b = row["S8"], row["bench"]
                md.append(f"| {name} | {fs_name} | {cl} A | {s.get('f', 0) / 1e3:.0f} / {b.get('f', 0) / 1e3:.0f} | "
                          + (f"{s['p_worst_W']} ({s['breakdown_at_worst_tj']['cond_W']} / "
                             f"{max(s['breakdown_at_worst_tj']['sw_dead_W_legA'], s['breakdown_at_worst_tj']['sw_dead_W_legB'])})"
                             f" | **{s['tj_max']}** | {row['tj_limit_C']} | {s['psink']} | " if "tj_max" in s
                             else f"runaway at {s['runaway_at_f'] / 1e3:.0f} kHz | | {row['tj_limit_C']} | | ")
                          + (f"{b['p_worst_W']} | **{b['tj_max']}** | {b['ts']} |" if "tj_max" in b
                             else f"runaway at {b['runaway_at_f'] / 1e3:.0f} kHz | | |"))
        out["devices"][name] = res
    (C55 / "results").mkdir(exist_ok=True)
    (C55 / "results/loss_thermal.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    (C55 / "results/loss_thermal.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
