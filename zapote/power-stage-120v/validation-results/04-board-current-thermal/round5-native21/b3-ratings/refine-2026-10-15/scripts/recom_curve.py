#!/usr/bin/env python3
"""Check the U41/U42 module-loss row of record against the RECOM R24C2T25/R curves.

Source: dl/recom/R24C2T25_R.pdf (RECOM R24C2T25/R, Rev. 1-2024), page 2, "Efficiency vs. Output current" and
"Power Dissipation" against Output Load [%], one curve per input voltage (21 / 22.5 / 24 / 25.5 / 27 V), typical, 25 C.
The page was rendered at 400 dpi (pdftoppm -r 400 -f 2 -l 2) and read by eye: grid 10 % x 0.2 W / 10 %. A read is good
to about +/- 0.02 W and +/- 1 %. The points are below. The dissipation curves are straight lines, so two points
define each one.

Full load (100 %) is not stated on the page. It is fixed here from the two curves' consistency, P_out = Pd eta / (1 - eta),
at 20 / 30 / 50 / 100 % on the 24 V curve: 1.68-1.76 W, i.e. IOUT+ 100 mA (selection guide p.1) x 17 V = 1.70 W.

Load of record: 17 V x I_ch with I_ch = Q f + 22.9 mA (bias_sizing.py), Q = the deck worst edge 382.6 nC, f = 60 kHz.
    python3 -I recom_curve.py <job dir>  ->  results/recom_curve.json
"""
import hashlib
import json
import sys
from pathlib import Path

JOB = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
PDF = JOB / "dl/recom/R24C2T25_R.pdf"
SHA = "2e8133d235cbb96286937284e6485b40b6a8285a33f28ae68c8b75baf826272f"

PD = {21.0: (0.31, 1.41), 24.0: (0.33, 1.52), 27.0: (0.37, 1.72)}           # W at 0 % and 100 % load (p.2, read)
ETA24 = {10: 29.0, 20: 38.0, 30: 43.5, 40: 46.5, 50: 48.5, 60: 49.5, 70: 50.5, 80: 51.2, 90: 52.0, 100: 52.5}
ETA27 = {10: 27.0, 20: 35.5, 30: 41.5, 40: 44.3, 50: 46.0, 60: 47.0, 70: 48.0, 80: 48.5, 90: 49.0, 100: 49.3}
SWING, CH_FIXED, F = 17.0, 0.0044 + 0.003 + 0.0015 + 0.014, 60e3
Q = {"deck_worst_S2": 382.6e-9, "deck_S1_ZVS": 370.0e-9, "allocation": 740e-9}


def interp(tab, x):
    ks = sorted(tab)
    for a, b in zip(ks, ks[1:]):
        if a <= x <= b:
            return tab[a] + (tab[b] - tab[a]) * (x - a) / (b - a)
    raise ValueError(x)


def pd(vin, load):
    a, b = PD[vin]
    return a + (b - a) * load


def main():
    assert hashlib.sha256(PDF.read_bytes()).hexdigest() == SHA
    full = {}
    for pct in (20, 30, 50, 100):
        e = ETA24[pct] / 100
        full[pct] = pd(24.0, pct / 100) * e / (1 - e) / (pct / 100)
    p_full = SWING * 0.100
    assert all(abs(v - p_full) / p_full < 0.04 for v in full.values()), full
    out = {"source": "RECOM R24C2T25/R Rev. 1-2024 p.2 (dl/recom/R24C2T25_R.pdf, sha256 " + SHA + ")",
           "full_load_W_from_curve_consistency": {str(k): round(v, 3) for k, v in full.items()}, "full_load_W": p_full,
           "rows": {}}
    for name, q in Q.items():
        p_out = SWING * (q * F + CH_FIXED)
        load = p_out / p_full
        row = {"Q_nC": q * 1e9, "P_out_W": round(p_out, 4), "load_pct": round(100 * load, 1),
               "loss_45pct_allocation_W": round(p_out * (1 / 0.45 - 1), 4),
               "loss_53pct_typ_W": round(p_out * (1 / 0.53 - 1), 4)}
        if load <= 1.0:
            row.update({f"curve_Pd_{v:g}V_W": round(pd(v, load), 3) for v in PD})
            row["curve_eta_24V_pct"] = round(interp(ETA24, 100 * load), 1)
            row["curve_eta_27V_pct"] = round(interp(ETA27, 100 * load), 1)
            row["loss_from_eta_24V_W"] = round(p_out * (100 / row["curve_eta_24V_pct"] - 1), 3)
            row["loss_from_eta_27V_W"] = round(p_out * (100 / row["curve_eta_27V_pct"] - 1), 3)
        out["rows"][name] = row
    r = out["rows"]["deck_worst_S2"]
    out["finding"] = (f"At 60 kHz the deck worst edge loads the module to {r['P_out_W']} W ({r['load_pct']} % of 1.70 W). The "
                      f"dissipation curve gives {r['curve_Pd_24V_W']} W at 24 V in and {r['curve_Pd_27V_W']} W at 27 V. The "
                      f"45 % allocation row of record ({r['loss_45pct_allocation_W']} W) sits between them, while the 53 % "
                      f"typical full-load figure ({r['loss_53pct_typ_W']} W) is below the curve at this load "
                      f"(efficiency at 24 V {r['curve_eta_24V_pct']} %).")
    (JOB / "results").mkdir(exist_ok=True)
    (JOB / "results/recom_curve.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
