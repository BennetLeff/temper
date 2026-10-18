"""Plot the h_c = 300 and 3000 traces for tri-ply clad from traces.json -> traces.png.

Run after estimator_study.py: python plot_traces.py
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

here = Path(__file__).parent
d = json.loads((here / "traces.json").read_text())
col = {c: i for i, c in enumerate(d["columns"])}
modes = ("perfect", "raw", "kf_nopower", "ekf_power")
fig, axes = plt.subplots(2, 2, figsize=(13, 8), sharex=True)
for row, h in enumerate(("300", "3000")):
    for c, what in enumerate(("T_c", "err")):
        ax = axes[row, c]
        for mode in modes:
            tr = d["traces"][f"triply_clad_24|{h}|{mode}"]
            t = [r[col["t"]] for r in tr]
            if what == "T_c":
                ax.plot(t, [r[col["T_c"]] for r in tr], label=f"true T_c, loop on {mode}")
            else:
                ax.plot(t, [r[col["T_hat"]] - r[col["T_c"]] for r in tr], label=f"{mode}: estimate - T_c")
        if what == "T_c":
            sp = d["traces"][f"triply_clad_24|{h}|perfect"]
            ax.plot(t, [r[col["sp"]] for r in sp], "k--", lw=0.8, label="setpoint")
            ax.set_ylabel("°C")
            ax.set_ylim(20, 240)
        else:
            ax.axhspan(-3, 3, color="0.85", label="A1 ±3 K")
            ax.set_ylim(-40, 60)
            ax.set_ylabel("K")
        ax.set_title(f"tri-ply clad, eta 0.82, noise 0.2 K, h_c = {h} W/m²K")
        ax.legend(fontsize=7, loc="lower right")
        ax.grid(alpha=0.3)
for ax in axes[1]:
    ax.set_xlabel("s")
fig.tight_layout()
fig.savefig(here / "traces.png", dpi=110)
