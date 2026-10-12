#!/usr/bin/env python3
"""Half-cycle RMS estimator scatter in the rms-alternatives study's own model (17 windows, AD8436
chain, 625 us slots), before and after time weighting; and the crest ratios used to justify the
stuck-low plausibility bound.

Needs the study's model, which lives on branch controller-layout (not in this tree):

  d=$(mktemp -d)
  for f in rms_alternatives.py lcsc-snapshot-2026-10-12.json; do
    git show controller-layout:zapote/controller/evidence/rms-alternatives/$f > $d/$f; done
  python3 -I firmware/build-evidence/rms-estimator/study_model_scatter.py $d

numpy only, about 1 s. The weights are exactly those of n21_half_close() (n21_signal.c): mid-point
rule between neighbouring readings, first and last held to the opening / closing zero.
"""
import importlib.util
import os
import sys

import numpy as np

study_dir = os.path.abspath(sys.argv[1])
spec = importlib.util.spec_from_file_location("study", os.path.join(study_dir, "rms_alternatives.py"))
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)

OFFS = np.arange(0.0, 625e-6, 25e-6)   # 25 slot phases against LINE_ZC


def estimate(s, t, h0, h1, weighted):
    v = s ** 2
    if not weighted:
        return np.sqrt(v.mean())                      # the pre-fix estimator
    lo = np.r_[h0, 0.5 * (t[:-1] + t[1:])]
    hi = np.r_[0.5 * (t[:-1] + t[1:]), h1]
    w = hi - lo
    return np.sqrt((w * v).sum() / w.sum())          # n21_half_close() + input_limits_half_cycle()


rows = {False: [], True: []}
for c in S.build_cases():
    for h in ([8, 11] if c["env"] == "burst" else [10]):
        t0, t = S.window_grid(h)
        g = 1.0 / np.sqrt(1.0 + (c["ns"] * c["f"] / S.AD_FC) ** 2)
        v = S.current(t, c, harm_gain=g) * S.V_PER_A
        y2 = S.lpf1(v * v, S.DT, S.AD_TAU_AVG)
        vadc = S.lpf1(np.sqrt(np.maximum(y2, 0)), S.DT, S.AD_TAU_OUT) * 4.0
        fine = S.pooled(vadc, t0, h, True, False)[0]          # exact-window converter output
        true = S.true_rms(c, h)
        for off in OFFS:
            ts = S.slot_times(h * S.HALF, off)
            s = S.sample(vadc, t0, ts)
            lsb = 3.3 / 4096.0
            s = np.round(s / lsb) * lsb                         # MCP3202-class quantisation
            for wt in (False, True):
                e = estimate(s, ts, h * S.HALF, (h + 1) * S.HALF, wt) / S.RMS_V_PER_A
                rows[wt].append((c["name"], h, off, (e / fine - 1) * 100, (e / true - 1) * 100))

for wt, label in ((False, "equal weights (pre-fix)"), (True, "time weighted (fix)")):
    a = np.array([r[3] for r in rows[wt]])
    b = np.array([r[4] for r in rows[wt]])
    print(f"{label:26s} estimator scatter vs exact-window converter: {a.min():+.2f} .. {a.max():+.2f} %"
          f"   whole chain vs true half RMS: {b.min():+.2f} .. {b.max():+.2f} %"
          f"   ({len(a)} estimates)")
print()
print("peak |i| / true half-cycle RMS per study waveform (crest the plausibility bound must clear):")
res = []
for c in S.build_cases():
    for h in ([8, 11] if c["env"] == "burst" else [10]):
        t0, t = S.window_grid(h)
        i = S.current(t, c)
        m = (t >= h * S.HALF) & (t < (h + 1) * S.HALF)
        res.append((np.abs(i[m]).max() / S.true_rms(c, h), c["name"], h))
for r, n, h in sorted(res, reverse=True):
    print(f"  {r:.3f}  {n} (window {h})")
