#!/usr/bin/env python3
"""Gate-drive heat per candidate on the B3 basis: R_on resistor (R10 / R12 / R18 / R20), driver, bias channel current.

The B3 heat file's formula is replicated here (round5-native21/b3/make_heat_sources.py, gate_split() and the lines
that follow; that module writes files when imported, so it is not imported): per FET, Q x SWING x f, half on turn-on
(R_SRC + R_on + Rg,int), half on turn-off (Rg,int + [R_on || PMEG branch] + R_SNK, less the diode's forward-drop share);
an external Cgs adds its own charge through the driver and R_on only. f = 60 kHz (window top).
Control: the CFD7 on the s42 network (68 ohm, 4.7 nF, Q 382.6 nC + 61 nC) gives R10 = 0.217 W, the s53 B3 c17.5 row.

Q per candidate = the worst S2 gate-loop charge on the as-built 8.2 ohm / 1 nF network (trade.py s2q on '<dev>__q'),
the same basis as B3's 382.6 nC. Cgs charge over the 1 nF basis: 4.7 nF adds 61 nC at the 17 V swing (B3
Q_CGS_EXTRA), i.e. 16.5 nC per nF; other values scale linearly in C and swing [EST].

R10 effect: the 25121WF derating line (1 W at 70 C to 0 at 155 C) read with the 80 % rule sets the allowed terminal
temperature at 155 - 106.25 K/W x P (c54-release-margins README section 1: 131.94 C at 0.21699 W). A lower R_on power
raises that limit by 106.25 K/W x dP; the terminal's own self-heating drop comes on top and is not counted, so the R10
margin gain is a lower bound. The tank-current equivalent uses the DECISIONS 61 slope (R10 margin +4.1 K at 16.5 A,
-0.7 K at 18 A: 3.2 K/A) [EST, linear]. It is not a ceiling claim: the next B3 rows (laminate at the R12 gate pad
+3.8 K, R20 +4.2 K; s53 margins c17.5_h10) are not re-solved here.

    python3 -I c40_gate_heat.py   -> ../results/gate_heat.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import C55, SIMS  # noqa: E402

F_WIN = 60e3
R_SRC, R_SNK, R_BR, VF_OFF = 0.95, 0.39, 1.0 + 0.1, 0.35
SWING0 = 17.0
Q_PER_F_17 = 61e-9 / 3.7e-9                    # C of extra charge per F over 1 nF, at 17 V
DERATE_K_PER_W = (155 - 70) / (0.8 * 1.0)      # B3 reads the curve with the 80 % rule (c54 README section 1)
R10_K_PER_A = (4.1 - (-0.7)) / (18.0 - 16.5)
R10_MARGIN_K = 1.3                     # s53 margins.json c17.5_h10, reproduced by c54-release-margins section 1


def gate_split(r_on, rg_int, swing):
    on = R_SRC + r_on + rg_int
    vf = VF_OFF / (0.5 * swing)
    rpar = r_on * R_BR / (r_on + R_BR)
    tot, res = rg_int + rpar + R_SNK, 1.0 - vf
    p_par = res * rpar / tot
    return {"rg": 0.5 * r_on / on + 0.5 * p_par * R_BR / (r_on + R_BR),
            "roff": 0.5 * p_par * r_on / (r_on + R_BR) * 1.0 / R_BR,
            "drv": 0.5 * R_SRC / on + 0.5 * res * R_SNK / tot}


def q_of(dev_q):
    p = SIMS / dev_q / "s2q/results.json"
    rows = [r for r in json.loads(p.read_text())["rows"] if r["status"] == "complete" and r.get("q_gate_hs_C") is not None]
    return max(max(abs(r["q_gate_hs_C"]), abs(r["q_gate_ls_C"] or 0)) for r in rows)


def heat(q, r_on, cgs, rg_int, swing):
    q_ext = (cgs - 1e-9) * Q_PER_F_17 * swing / SWING0
    e_f, e_x = q * swing * F_WIN, q_ext * swing * F_WIN
    s, sx = gate_split(r_on, rg_int, swing), gate_split(r_on, 0.0, swing)
    i_ch = (q + q_ext) * F_WIN + 0.0044 + 0.003 + 0.0015 + 0.014
    return {"Q_nC": round(q * 1e9, 1), "Q_ext_nC": round(q_ext * 1e9, 1), "P_Ron_W": round(s["rg"] * e_f + sx["rg"] * e_x, 4),
            "P_driver_ch_W": round(s["drv"] * e_f + sx["drv"] * e_x, 4), "P_gate_total_per_FET_W": round(e_f + e_x, 4),
            "I_bias_channel_mA": round(i_ch * 1e3, 2)}


# (label, charge config, R_on, Cgs, Rg,int (datasheet), swing) ; Rg,int: CFD7 2.7 (p.5), CM8 1.0 (p.5),
# IMW65R026M2H 2.9 (p.6), RC-H6 internal gate resistance not stated (0 used: all charge in the external path)
CASES = [
    ("CFD7 s42 network (control)", "cfd7_c39__q", 68, 4.7e-9, 2.7, 17.0),
    ("CM8 + 39 ohm / 1 nF", "cm8_r39__q", 39, 1e-9, 1.0, 17.0),
    ("CM8 on the s42 network (68 ohm / 4.7 nF)", "cm8_r39__q", 68, 4.7e-9, 1.0, 17.0),
    ("CM8 + 100 ohm / 1 nF (representative)", "cm8_r39__q", 100, 1e-9, 1.0, 17.0),
    ("CM8 + 150 ohm / 1 nF", "cm8_r39__q", 150, 1e-9, 1.0, 17.0),
    ("IMW65R026M2H 15 V, 8.2 ohm / 1 nF", "sic26_15_r8p2__q", 8.2, 1e-9, 2.9, 17.0),
    ("IMW65R026M2H 18 V, 8.2 ohm / 1 nF", "sic26_18_r8p2__q", 8.2, 1e-9, 2.9, 19.6),
    ("IMW65R026M2H 15 V, s42 network 68 ohm / 4.7 nF", "sic26_15_r8p2__q", 68, 4.7e-9, 2.9, 17.0),
    ("IHW40N65R6 8.2 ohm / 1 nF", "rch6_r8p2__q", 8.2, 1e-9, 0.0, 17.0),
]


def main():
    out = {"basis": "B3 make_heat_sources gate_split replicated; 60 kHz; Q = worst S2 charge on the 8.2 ohm / 1 nF deck",
           "rows": []}
    base = None
    for label, qdev, r_on, cgs, rg, sw in CASES:
        if not (SIMS / qdev / "s2q/results.json").is_file():
            out["rows"].append({"case": label, "missing": qdev})
            continue
        h = heat(q_of(qdev), r_on, cgs, rg, sw)
        h.update(case=label, q_config=qdev, R_on=r_on, Cgs_nF=cgs * 1e9, Rg_int=rg, swing_V=sw)
        if base is None:
            base = h
            assert abs(h["P_Ron_W"] - 0.217) < 0.0015, ("control: s53 B3 R10 0.217 W", h["P_Ron_W"])
            h["control_vs_B3_R10_0.217W"] = "PASS"
        d = base["P_Ron_W"] - h["P_Ron_W"]
        h["dP_Ron_vs_s42_W"] = round(-d, 4)
        h["R10_limit_gain_K_lower_bound"] = round(DERATE_K_PER_W * d, 2)
        h["R10_margin_at_17.5A_K_est"] = round(R10_MARGIN_K + DERATE_K_PER_W * d, 2)
        h["R10_ceiling_shift_A_est"] = round(DERATE_K_PER_W * d / R10_K_PER_A, 2)
        out["rows"].append(h)
    (C55 / "results").mkdir(exist_ok=True)
    (C55 / "results/gate_heat.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
