#!/usr/bin/env python3
"""RMS current through the X2 capacitors C1 / C2 (R463N410050N1K) at the switching harmonics, from the stage-19b
conducted-EMI network (validation-results/07-conducted-emi/s19b/emi_s19b.py), re-parameterised to the native-21 board.

    python3 -I validation-results/11-candidates/c54-ledger-desk/scripts/cx_current.py

Method: emi_s19b.build() is the linear AC network (LISN, inlet module, board filter C1 / RV1 / L1 / C2 / Y, rectifier
conducting pair at the line crest, DC link, the two switch-node sources and the bus-current source). The same
source spectra as the EMI run (source_spectra: trapezoidal legs + the rectified tank current at the crest, CASES at
Vc 170 / 198 V) excite it; the voltage across each X cap's series R-L-C branch divided by that branch impedance is
the cap current per harmonic, and the RMS is the root-sum-square of the harmonic peak phasors / sqrt 2, harmonics
1..(2 MHz / fs). The mains (60 Hz) component is added in quadrature at the 139.7 Vrms line-high corner.
The EMI cases put the tank current at the LINE CREST (peak = 2.17 x the line-RMS ceiling). Both sources (switch-node
amplitude ~ Vc and tank current) follow |sin| of the line angle, so in this linear model the cap current does too and
its RMS over a mains cycle (the thermal quantity for a film cap) is the crest value / sqrt 2 ("line-cycle RMS"); the
fs used at the crest is held for the whole cycle (the worst fs is taken). A release case (pan, 18.375 A trip of the
17.5 A release ceiling, b3_ratings_gate.py:29-30) is added to emi_s19b's CASES.

Board overrides (native-21, stage 53): L1 = B82726S2243A020 (0.75 mH, 8 uH typ stray, TDK p.4; ledger L1 entry);
DC link C5 + C6 = 2 x 9 uF B32676G (ESR 5.1 mOhm, ESL 12 nH each, TDK p.10; ledger B32676G1905K000) plus the 0.4 uF
local group of s19b. Variants: with / without the declared inlet module (DECISIONS "EMI below 150 kHz" item 4), the
L1 stray at 8 and 18 uH, and the DC-link ESR at the TDK value and at s19b's 20 mOhm (a higher ESR pushes more ripple
into C2). The worst over fs 35..60 kHz (1 kHz steps), every case and every variant is reported.

Limits (honest): a linear small-signal model at the line crest with the rectifier conducting; the bridge's
non-conducting intervals (which isolate C2 from the DC link) are not modelled, so the C2 share is the crest
condition. It is a model estimate, not a measurement; the bench closes it (current probe on a C2 lead).
Writes results/cx_current.json and results/cx_current.md.
"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[3]
S19B = UNIT / "validation-results/07-conducted-emi/s19b"
sys.path.insert(0, str(S19B))
import emi_s19b as e  # noqa: E402

OUT = HERE.parent / "results"
F_MAX = 2e6
V_LINE = 139.7  # Vrms, 127 V + 10 % (DECISIONS.md:306)


def x_current(params, module, vc, case, fs):
    h = np.arange(1, int(F_MAX / fs) + 1)
    f = h * fs
    p = {**params, **e.tank_for(vc, e.case_at(vc, case, fs), fs)}
    net = e.build(p, module)
    outs = {"x1": ("lm", "nm") if module else ("line_in", "neut_in"), "x2": ("line_f", "neut_f")}
    tr = net.solve(f, e.EXC, outs)
    va, vb, ib, *_ = e.source_spectra(fs, h, vc, e.case_at(vc, case, fs))
    pp = {**e.BASE, **p}
    w = 2 * np.pi * f
    zx = pp["ESRX"] + 1j * w * pp["ESLX"] + 1 / (1j * w * pp["CX"])
    res = {}
    for k in outs:
        v = tr["A"][k] * va + tr["B"][k] * vb + tr["DM"][k] * ib
        i = v / zx
        irms_hf = float(np.sqrt(np.sum(np.abs(i) ** 2) / 2))
        top = int(np.argmax(np.abs(i)))
        res[k] = {"irms_hf_A": irms_hf, "top_harmonic": int(h[top]), "top_f_kHz": float(f[top] / 1e3),
                  "top_A_rms": float(np.abs(i[top]) / np.sqrt(2))}
    return res


def main():
    cm = e.cm_capacitances()
    nom = e.nominal_params(cm)
    board = {"LCM": 0.75e-3, "CBULK": 18e-6, "LBULK": 6e-9}
    variants = {
        "module, L1 8 uH, ESR 2.55 mOhm": ({**board, "LDM": 8e-6, "RBULK": 2.55e-3}, True),
        "module, L1 8 uH, ESR 20 mOhm": ({**board, "LDM": 8e-6, "RBULK": 20e-3}, True),
        "module, L1 18 uH, ESR 20 mOhm": ({**board, "LDM": 18e-6, "RBULK": 20e-3}, True),
        "no module, L1 8 uH, ESR 20 mOhm": ({**board, "LDM": 8e-6, "RBULK": 20e-3}, False),
    }
    cases = dict(e.CASES)
    cases["pan_18.375A"] = dict(irms=18.375, phi=np.radians(50.0), ipk=2.17 * 18.375,
                                note="release ceiling 17.5 A at its 18.375 A trip, pan present")
    i60 = V_LINE * 2 * np.pi * 60 * 1e-6 * 1.1  # +10 % tolerance
    rows = []
    for vn, (ov, module) in variants.items():
        params = {**nom, **ov}
        for vc in (170.0, 198.0):
            for cn, case in cases.items():
                for fs in np.arange(35e3, 60e3 + 1, 1e3):
                    r = x_current(params, module, vc, case, fs)
                    for k, v in r.items():
                        rows.append({"variant": vn, "vc": vc, "case": cn, "fs_kHz": fs / 1e3, "cap": k,
                                     **v, "irms_total_A": float(np.hypot(v["irms_hf_A"], i60)),
                                     "irms_line_cycle_A": float(np.hypot(v["irms_hf_A"] / np.sqrt(2), i60))})
    worst = {}
    for k in ("x1", "x2"):
        rk = [r for r in rows if r["cap"] == k]
        worst[k] = max(rk, key=lambda r: r["irms_total_A"])
        for cn in cases:
            for mod, lab in ((True, "with module"), (False, "board alone")):
                worst[f"{k} {cn} {lab}"] = max((r for r in rk if r["case"] == cn and r["variant"].startswith("module") == mod),
                                               key=lambda r: r["irms_total_A"])
    OUT.mkdir(exist_ok=True)
    (OUT / "cx_current.json").write_text(json.dumps({"i_60Hz_A": i60, "worst": worst, "rows": rows}, indent=1) + "\n")
    lines = ["# cx_current.md (generated by scripts/cx_current.py; do not edit)",
             f"60 Hz component at 139.7 Vrms, 1.1 uF: {i60:.4f} A rms",
             *(f"worst {k}: crest {v['irms_total_A']:.4f} A rms ({v['irms_hf_A']:.4f} A HF; top harmonic "
               f"{v['top_harmonic']} at {v['top_f_kHz']:.1f} kHz, {v['top_A_rms']:.4f} A); line-cycle RMS {v['irms_line_cycle_A']:.4f} A - {v['variant']}, Vc {v['vc']:.0f} V, "
               f"{v['case']}, fs {v['fs_kHz']:.0f} kHz" for k, v in worst.items())]
    (OUT / "cx_current.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
