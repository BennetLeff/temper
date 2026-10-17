#!/usr/bin/env python3
"""Task B: high-side bias power per channel, RECOM module heat vs a discrete UCC25800-Q1 LLC supply, per gate charge.

    python3 -I bias.py      -> ../results/bias.json, ../results/bias.md

Control: the as-built allocation (740 nC edge allowance, 14 mA monitor, 4.4 / 3 / 1.5 mA) must reproduce the committed
native-21 bias_sizing.py rows (validation-results/01-switching-parasitics/round17/delegation/out-D33/bias-sizing.json:
channel_current_A at 33 / 40 / 80 kHz) and ALT-BIAS 3.2 module loss 0.98 / 1.09 / 1.71 W at the 45 % allocation.

Per channel (one high side; the low side is fed from U26 and is outside Task B):
  I_ch = Q_edge * f + I_drv + I_bleed + I_Rgs + I_mon            (bias_sizing.py)
  P_out = 17.0 V * I_ch                                           (span; 16.91 V RECOM set point, ALT-BIAS 3.1)
RECOM R24C2T25/R module loss = P_out (1/eta - 1), eta 0.45 allocation (ALT-BIAS) / 0.53 typ (RECOM sheet, ALT-BIAS 3.1)
Discrete per channel (UCC25800-Q1 + WE 750319833, voltage doubler, LP-class LDO to the 17.0 V span):
  IC: 24 V * IVCCRUN (14 mA typ / 20 mA max at 1.2 MHz, SLUSDX3C 7.5 p.6; conservative at 500 kHz)
  LLC + doubler: V_raw = 24 V / 1.2 - 2 * 0.45 V (Schottky, estimate); stage efficiency 0.85 (ESTIMATE, bench item)
  LDO: (V_raw - 17.0) * I_ch
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
POWER = Path(__file__).resolve().parents[4]   # zapote/power-stage-120v (committed copy, DECISIONS 49)
SIZING = POWER / "validation-results/01-switching-parasitics/round17/delegation/out-D33/bias-sizing.json"

SPAN = 17.0
I_DRV, I_BLEED, I_RGS = 0.0044, 0.003, 0.0015      # bias_sizing.py allowances (driver, split bleed, Rgs at +15 V)
I_MON_ALLOC, I_MON_ALTBIAS = 0.014, 0.010           # bias_sizing 14 mA allocation; ALT-BIAS 4: actual ~10 mA
FREQS = (33e3, 40e3, 50e3, 60e3, 80e3)              # nominal, 40 kHz (B3 worst row), c28 50 kHz, control ceiling, F6 alloc
VIN, NTURN, VF = 24.0, 1.2, 0.45
I_IC_TYP, I_IC_MAX = 0.014, 0.020
ETA_LLC = 0.85


def ch_current(q, f, mon=I_MON_ALLOC):
    return q * f + I_DRV + I_BLEED + I_RGS + mon


def module_loss(p_out, eta):
    return p_out * (1 / eta - 1)


def discrete_loss(i_ch, shared_ic=False):
    v_raw = VIN / NTURN - 2 * VF
    p_ldo = (v_raw - SPAN) * i_ch
    p_llc = v_raw * i_ch * (1 / ETA_LLC - 1)
    p_ic = VIN * I_IC_TYP * (0.5 if shared_ic else 1.0)
    return {"v_raw_V": round(v_raw, 2), "ldo_W": round(p_ldo, 3), "llc_stage_W": round(p_llc, 3),
            "ic_W_typ": round(p_ic, 3), "ic_W_max": round(VIN * I_IC_MAX * (0.5 if shared_ic else 1.0), 3),
            "total_W_typ": round(p_ldo + p_llc + p_ic, 3),
            "input_W": round(VIN * I_IC_TYP * (0.5 if shared_ic else 1.0) + v_raw * i_ch / ETA_LLC, 3)}


def control():
    ref = {r["frequency_Hz"]: r["channel_current_A"] for r in json.loads(SIZING.read_text())["rows"]}
    worst = max(abs(ch_current(740e-9, f) - i) for f, i in ref.items())
    loss = {int(f / 1e3): round(module_loss(SPAN * ch_current(740e-9, f), 0.45), 3) for f in (33e3, 40e3, 80e3)}
    alt = {33: 0.98, 40: 1.09, 80: 1.71}
    ok = worst < 1e-12 and all(abs(loss[k] - alt[k]) <= 0.006 for k in alt)
    return {"channel_current_max_abs_delta_A": worst, "module_loss_45pct_W": loss, "ALT-BIAS_3.2_W": alt, "pass": ok}


def main():
    c = control()
    print("control", c)
    assert c["pass"], c
    sw = json.loads((ROOT / "results" / "switching.json").read_text())
    q = {"allocation_740nC (as-built sizing, covers S2/S4/S5 extremes)": 740e-9}
    # deck-measured gate-loop charge per edge, ZVS S1 rows (incoming turn-on / outgoing turn-off, worst of both)
    for dev, d in sw.items():
        g = d.get("gate_charge_zvs_sweep", {}).get("S1") or d.get("gate_charge", {}).get("S1")
        if g:
            q[f"{dev} deck ZVS S1 max"] = g["max_nC"] * 1e-9
        g4 = d.get("gate_charge", {})
        for case in ("S2", "S4", "S5"):
            if case in g4:
                q[f"{dev} deck {case} max"] = g4[case]["max_nC"] * 1e-9
    # CM8 estimate: the 029 model's ZVS charge scaled by datasheet Qg 173/145 (IPW65R018CM8 Rev 2.1 p.6 Table 6;
    # IPW65R029CFD7 Rev 2.1 p.5); and the 018 deck charge scaled by 173/234 (IPW65R018CFD7 Rev 2.0 p.5)
    if "IPW65R029CFD7_L1 deck ZVS S1 max" in q:
        q["IPW65R018CM8 est (029 deck x 173/145)"] = q["IPW65R029CFD7_L1 deck ZVS S1 max"] * 173 / 145
    if "IPW65R018CFD7_L1 deck ZVS S1 max" in q:
        q["IPW65R018CM8 est (018 deck x 173/234)"] = q["IPW65R018CFD7_L1 deck ZVS S1 max"] * 173 / 234
        q["IPW65R018CM8 allocation (740 x 173/234)"] = 740e-9 * 173 / 234
    rows = []
    for name, qe in q.items():
        for f in FREQS:
            for mon_name, mon in (("mon14", I_MON_ALLOC), ("mon10", I_MON_ALTBIAS)):
                i = ch_current(qe, f, mon)
                p = SPAN * i
                rows.append({"q_basis": name, "q_nC": round(qe * 1e9, 1), "f_kHz": f / 1e3, "monitor": mon_name,
                             "I_ch_mA": round(i * 1e3, 2), "P_out_W": round(p, 3),
                             "pct_of_2W_knee": round(100 * p / 2.0, 1),
                             "RECOM_loss_W_eta45": round(module_loss(p, 0.45), 3),
                             "RECOM_loss_W_eta53": round(module_loss(p, 0.53), 3),
                             "discrete_per_ch": discrete_loss(i),
                             "discrete_per_ch_shared_ic": discrete_loss(i, True)})
    out = {"control": c, "rows": rows, "q_bases_nC": {k: round(v * 1e9, 1) for k, v in q.items()}}
    (ROOT / "results" / "bias.json").write_text(json.dumps(out, indent=1) + "\n")
    lines = ["| Q basis | Q nC | f kHz | I_ch mA | P_out W | % 2 W knee | RECOM loss W (45/53 %) | discrete W (own IC / shared IC) |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["monitor"] != "mon14":
            continue
        lines.append(f"| {r['q_basis']} | {r['q_nC']} | {r['f_kHz']:.0f} | {r['I_ch_mA']} | {r['P_out_W']} | {r['pct_of_2W_knee']} | "
                     f"{r['RECOM_loss_W_eta45']} / {r['RECOM_loss_W_eta53']} | {r['discrete_per_ch']['total_W_typ']} / "
                     f"{r['discrete_per_ch_shared_ic']['total_W_typ']} |")
    (ROOT / "results" / "bias.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
