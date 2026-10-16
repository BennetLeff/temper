#!/usr/bin/env python3
"""VF of the c39 diode models (control + bounding) at 25 C against the datasheet VF / Cd of the D6-D9 candidates.
Datasheet values typed from the LCSC copies in ../sources/diode-*/ds.pdf (page cited). Usage: python3 -I diode_bounds.py OUT.json"""
import json
import math
import sys

VT = 8.617333e-5 * 298.15
BASE = dict(IS=2.201e-6, N=1.021, RS=0.03034, CJO=6.34e-10, VJ=0.3866, M=0.5004)   # repo PMEG6030EP.txt
MODELS = {"pmeg (control)": dict(BASE), "vfhi (IS/4000)": dict(BASE, IS=BASE["IS"] / 4000),
          "cjhi (CJO x1.6)": dict(BASE, CJO=BASE["CJO"] * 1.6)}


def vf(m, i):
    return m["N"] * VT * math.log(i / m["IS"] + 1) + i * m["RS"]


def cj(m, vr):
    return m["CJO"] / (1 + vr / m["VJ"]) ** m["M"]


# datasheet 25 C maxima (VF) and typicals (Cd at VR = 1 / 10 V), page refs
DS = {
    "PMEG6030EP,115 (fitted)": dict(vrrm=60, ifav=3, ifsm=50, tj=150, vf={0.1: .33, 0.5: .40, 1: .44, 1.5: .47, 2: .50, 3: .53},
                                    cd={1: 360, 10: 120}, src="Nexperia 2017-11-07 p.4-5"),
    "PMEG6030EP-QX": dict(vrrm=60, ifav=3, ifsm=50, tj=150, vf={0.1: .33, 0.5: .40, 1: .44, 1.5: .47, 2: .50, 3: .53},
                          cd={1: 360, 10: 120}, src="Nexperia PMEG6030EP-Q 2023-02-20 p.4 (identical tables)"),
    "PMEG4030EP,115": dict(vrrm=40, ifav=3, ifsm=50, tj=150, vf={0.1: .32, 1: .42, 3: .49}, cd={1: 350, 10: 140},
                           src="Nexperia 2023-02-20 p.4"),
    "PMEG6020EP,115": dict(vrrm=60, ifav=2, ifsm=50, tj=150, vf={0.1: .34, 0.5: .42, 1: .46, 1.5: .50, 2: .53},
                           cd={1: 240, 10: 80}, src="Nexperia 2023-02-20 p.4"),
    "PMEG6030ELPX": dict(vrrm=60, ifav=3, ifsm=70, tj=175, vf={0.1: .50, 3: .67}, cd={1: 315, 10: 125},
                         src="Nexperia 2023-02-20 p.2/p.4 (pulsed)"),
    "RBR3LAM60BTR": dict(vrrm=60, ifav=3, ifsm=75, tj=150, vf={3: .56}, cd=None, src="ROHM 2019-05-28 Rev.002 p.1 (Cd curve only)"),
    "RB050LAM-60TR": dict(vrrm=60, ifav=3, ifsm=80, tj=150, vf={2: .52, 3: .56}, cd=None, src="ROHM Rev.002 p.1"),
    "RB058LAM-60TR": dict(vrrm=60, ifav=3, ifsm=90, tj=175, vf={3: .64}, cd=None, src="ROHM 2022-01-18 Rev.004 p.1"),
    "STPS360AFY": dict(vrrm=60, ifav=3, ifsm=65, tj=175, vf={3: .61}, cd=None, src="ST DocID029422 Rev 1 p.2 (SOD128Flat)"),
}
out = {"models": {}, "candidates": {}}
for n, m in MODELS.items():
    out["models"][n] = {"vf_25C": {str(i): round(vf(m, i), 4) for i in (0.1, 0.5, 1, 2, 3, 5)},
                        "cj_pF": {str(v): round(cj(m, v) * 1e12, 1) for v in (1, 10)}}
hi = MODELS["vfhi (IS/4000)"]
for n, d in DS.items():
    cov = all(vf(hi, i) >= v for i, v in d["vf"].items())
    lo_ok = all(vf(MODELS["pmeg (control)"], i) <= v + 1e-9 for i, v in d["vf"].items())
    out["candidates"][n] = dict(d, vf={str(k): v for k, v in d["vf"].items()},
                                cd={str(k): v for k, v in d["cd"].items()} if d["cd"] else None,
                                vf_inside_vfhi_bound=cov,
                                cd_inside_cjhi_bound=(None if not d["cd"] else d["cd"][1] <= cj(MODELS["cjhi (CJO x1.6)"], 1) * 1e12),
                                vrrm_margin_vs_15p5V=round(d["vrrm"] / 15.5, 2))
json.dump(out, open(sys.argv[1], "w"), indent=1)
for n, m in out["models"].items():
    print(n, m)
for n, c in out["candidates"].items():
    print(f"{n:26s} VF-in-bound {c['vf_inside_vfhi_bound']}  Cd-in-bound {c['cd_inside_cjhi_bound']}  Vrrm/15.5V {c['vrrm_margin_vs_15p5V']}")
