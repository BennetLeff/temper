#!/usr/bin/env python3
"""OPEN-ITEMS S33: candidate mains fuses against the corrected drain-pin copper (DECISIONS 88) and f1_decision.py's other gates.

    python3 -I fuse_vs_neck.py      -> ../fuse-vs-neck.json

Sources: KLDR / Bel as 12-decisions/f1-data. CCMR020: Littelfuse CCMR sheet rev 10/10/2022 p.4 (sha a63cfddb1077): 918 A2s at 200 kA, no
melting figure. FWC-25A10F: Eaton 720011 Nov 2017 p.2 (sha f0cdada2fa5d): pre-arc 60, clearing 390 at 600 V and 15 % pf, class aR, UL
Recognised; its correction curve reads K ~ 0.57 at 140 V [PLOT, by eye], not used for the gate. Mersen A60Q25-2: its data sheet
(sha 057155e5dc54) and product page print NO I2t, so it is left UNKNOWN. Derate at 50 C: KLDR / CCMR 0.90, Bel 0.96 (survey, plots);
KLKR and FWC sheets read print none, so G2 is UNKNOWN for them. Gates are f1_decision.py's: G2 carry >= 15 A, G3 inrush / surge share of the
pre-arc I2t, G4 clearing <= copper, G5 melt >= 2 x F2's 67 A2s, G6 Listed. A gate that cannot be read is UNKNOWN, never PASS."""
import json
from pathlib import Path
H = Path(__file__).resolve().parent
d = json.loads((H.parents[2] / "02-protection-timing/shoot-through-f1/s57_necks_hole.json").read_text())
neck = d["min_ratio_single_layer"] * d["F1_clearing_I2t"]
F2, BR1 = 67.0, 510.0
# name, amps, melt, clearing, derate, listed, fit
F = [("KLDR025.TXP (fitted)", 25, 226.0, 1710.0, 0.90, True, "same clips"),
     ("CCMR020.TXP (TD, Class CC)", 20, None, 918.0, 0.90, True, "same clips"),
     ("KLKR020 (fast, Class CC)", 20, None, 900.0, None, True, "same clips"),
     ("FWC-25A10F (aR, 10 x 38)", 25, 60.0, 390.0, None, False, "same clips, overlap not tested; partial-range fuse"),
     ("A60Q25-2 (10 x 38)", 25, None, None, None, False, "same clips; no published I2t"),
     ("Bel 0ADEC9250-BE (6.3 x 32)", 25, 200.0, 470.0, 0.96, False, "new clips and footprint")]


def g(ok):
    return "UNKNOWN" if ok is None else "PASS" if ok else "FAIL"


rows = []
for n, i, melt, clear, der, listed, fit in F:
    rows.append({"fuse": n, "clearing_I2t": clear, "melt_I2t": melt, "copper_ratio": None if clear is None else round(neck / clear, 2),
                 "carry_A": None if der is None else round(i * 0.75 * der, 2),
                 "G2_carry_15A": g(None if der is None else i * 0.75 * der >= 15), "G3_nuisance": g(None if melt is None else 1.0 <= 0.22 * melt and 12.2 <= 0.38 * melt),
                 "G4_copper": g(None if clear is None else clear <= neck), "G5_F2_selective": g(None if melt is None else melt >= 2 * F2),
                 "G6_listed": "PASS" if listed else "UNKNOWN",
                 "br1_0p5x510": g(None if clear is None else clear <= 0.5 * BR1), "br1_1x510": g(None if clear is None else clear <= BR1), "fit": fit})
cc = json.loads((H.parent / "ccmr020-melt.json").read_text())           # ccmr020_melt.py: estimate, control set of nine KLDR ratings
for r in rows:
    if r["fuse"].startswith("CCMR020"):
        r.update(melt_I2t_range_est=cc["melt_range_A2s"], G3_nuisance=cc["G3_nuisance"] + " (est)", G5_F2_selective=cc["G5_F2_selective"] + " (est)")
by = {r["fuse"].split()[0]: r for r in rows}
assert by["KLDR025.TXP"]["G4_copper"] == "FAIL" and abs(by["KLDR025.TXP"]["copper_ratio"] - 0.64) < 0.01   # reproduces DECISIONS 88
assert by["FWC-25A10F"]["G5_F2_selective"] == "FAIL" and by["A60Q25-2"]["G4_copper"] == "UNKNOWN"          # fail / unknown paths exist
(H.parent / "fuse-vs-neck.json").write_text(json.dumps({"neck_I2t": round(neck, 1), "rows": rows}, indent=1) + "\n")
for r in rows:
    print(f"{r['fuse']:28s} ratio {r['copper_ratio']} carry {r['carry_A']} " + " ".join(f"{k}={v}" for k, v in r.items() if k[:1] == "G" or k.startswith("br1")))
