#!/usr/bin/env python3
"""What would widen the map: calibration and capture changes, tested at the edges of accuracy_map.py.

V0  as accuracy_map.py (the committed host and kit);
Vn  V0 without the per-session reference check (shows what the check removes, e.g. coupling-capacitor
    drift at low frequency);
V1  host takes characterized complex standards: standard self-capacitance and short inductance known,
    residual uncertainty STD_C_RESID / SHORT_L_RESID (ESTIMATE: an LCR-meter or VNA characterization);
V2  V1 + a 1 MOhm characterized standard on the 100 kOhm range (standards 20 kOhm, 1 MOhm);
V3  V2 + captures 10x longer (2.5 s per point).
Cells: E typical / corner, worst of the three DUT phases, |Z| and phase, range fixed per row.

    variants.py -> results/variants.json, table on stdout
"""
import json
import math

import numpy as np

import accuracy_map as m

s = m.s
STD_C_RESID = 0.05e-12           # ESTIMATE: residual after characterizing each standard's capacitance
SHORT_L_RESID = 0.5e-9           # ESTIMATE: residual after characterizing the short's inductance
ROWS = [(100, 0.01), (100, 0.1), (100, 10.0), (5000, 1e3), (100000, 1e5), (100000, 1e6), (100000, 1e7)]
FREQS = (50, 1e3, 20e3, 85e3)
VARIANTS = {
    "V0": dict(),
    "Vn": dict(noref=True),
    "V1": dict(std_c=STD_C_RESID, short=True),
    "V2": dict(std_c=STD_C_RESID, short=True, std100k=(20e3, 1e6)),
    "V3": dict(std_c=STD_C_RESID, short=True, std100k=(20e3, 1e6), capture=2.5),
}


def apply(v):
    saved = (m.STD_C, s.SHORT_4T, dict(m.STDS), m.CAPTURE_S, m.CFG)
    if v.get("noref"):
        m.CFG = s.replace(m.CFG, ref=False)
    if "std_c" in v:
        m.STD_C = v["std_c"]
    if v.get("short"):
        s.SHORT_4T = tuple((r, SHORT_L_RESID * (1 + k)) for k, (r, _) in enumerate(s.SHORT_4T))
    if "std100k" in v:
        m.STDS[100000] = v["std100k"]
    if "capture" in v:
        m.CAPTURE_S = v["capture"]
    return saved


def restore(saved):
    m.STD_C, s.SHORT_4T, std, m.CAPTURE_S, m.CFG = saved
    m.STDS.clear()
    m.STDS.update(std)


def e_worst(r, f, z, corner):
    zs = [z * complex(math.cos(t), math.sin(t)) for t in m.PHASES.values()]
    return max(max(m.stats(np.abs(zm) / abs(zt) - 1), m.stats(np.angle(zm / zt)))
               for zt, zm in zip(zs, m.run_point(r, f, zs, corner)))


def main():
    out = {}
    for name, v in VARIANTS.items():
        saved = apply(v)
        try:
            out[name] = {f"{r}|{z:g}|{f:g}": [e_worst(r, f, z, c) for c in (False, True)]
                         for r, z in ROWS for f in FREQS}
        finally:
            restore(saved)
    (m.RES / "variants.json").write_text(json.dumps(dict(variants=VARIANTS, std_c_resid=STD_C_RESID,
                                                         short_l_resid=SHORT_L_RESID, e=out), indent=1))
    print("| Range | \\|Z\\| | f | " + " | ".join(VARIANTS) + " |")
    print("|---" * (len(VARIANTS) + 3) + "|")
    for r, z in ROWS:
        for f in FREQS:
            k = f"{r}|{z:g}|{f:g}"
            print(f"| {m.rng_label(r)} | {m.zlabel(z)} | {m.flabel(f)} | "
                  + " | ".join(f"{m.pct(out[n][k][0])} / {m.pct(out[n][k][1])}" for n in VARIANTS) + " |")


if __name__ == "__main__":
    main()
