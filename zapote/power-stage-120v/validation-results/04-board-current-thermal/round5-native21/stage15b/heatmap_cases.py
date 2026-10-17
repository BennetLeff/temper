#!/usr/bin/env python3
"""Per-case A4 Joule heat maps (c28-scaled W/mm^2) on F.Cu and B.Cu over the FET row, plus binned sums.

    python3 heatmap_cases.py [A4_DIR] [tag] -> png/heat_<tag>.png, out/heat_bins_<tag>.json
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "model/b3"))
import run_study as rs  # noqa: E402

A4 = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "model/outputs"
TAG = sys.argv[2] if len(sys.argv) > 2 else "base"
scale = {c.rsplit(":", 1)[0]: float(c.rsplit(":", 1)[1]) for c in rs.cases("c28").split(",")}
CASES = ["sw_a-p00625-pl18", "sw_a_low-p00625-pl18", "leg_a_18p7-p00625-pl18", "bus_mixed_q2-p0125-pl18",
         "sw_b_high-p00625-pl18", "sw_b_low-p00625-pl18"]
WIN = (0, 0, 82, 16)
fig, axs = plt.subplots(len(CASES), 2, figsize=(18, 2.2 * len(CASES)))
bins = {}
for r, case in enumerate(CASES):
    z = np.load(A4 / f"{case}-heat.npz")
    bins[case] = {}
    for c, layer in enumerate(("F_Cu", "B_Cu")):
        ax = axs[r, c]
        key = layer + "_joule_w"
        if key not in z:
            ax.set_axis_off(); continue
        x, y, w = z[layer + "_x_mm"], z[layer + "_y_mm"], z[key] * scale[case]
        p = x[1] - x[0]
        ix = (x >= WIN[0]) & (x <= WIN[2]); iy = (y >= WIN[1]) & (y <= WIN[3])
        dens = w[np.ix_(ix, iy)] / p ** 2
        ax.imshow(np.log10(dens.T + 1e-6), origin="lower", extent=(x[ix][0], x[ix][-1], y[iy][0], y[iy][-1]),
                  vmin=-4, vmax=-0.5, cmap="inferno", aspect="equal")
        ax.set_title(f"{case} {layer} (log10 W/mm2 at c28)", fontsize=7); ax.tick_params(labelsize=5)
        ax.set_xticks(range(0, 83, 2))
        # 4 mm x-bins over y 0-16
        for x0 in range(0, 82, 4):
            m = (x >= x0) & (x < x0 + 4)
            s = float(w[np.ix_(m, iy)].sum())
            if s > 1e-3:
                bins[case][f"{layer} x{x0}-{x0+4}"] = round(s, 4)
fig.tight_layout(); fig.savefig(HERE / f"png/heat_{TAG}.png", dpi=110)
(HERE / "out").mkdir(exist_ok=True)
(HERE / f"out/heat_bins_{TAG}.json").write_text(json.dumps(bins, indent=1) + "\n")
for k, v in bins.items():
    print(k, sorted(v.items(), key=lambda kv: -kv[1])[:6])
