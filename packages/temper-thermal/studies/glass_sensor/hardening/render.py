"""Render selected-part results; no physics or acceptance rules live here."""

import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
text = (ROOT.parent / "parts_revision/results/summary.txt").read_text()
rows = re.findall(
    r"^(middle|favorable|weak_partial): t90_final=([\d.]+)s .* error200=([-\d.]+)C$", text, re.M
)
assert len(rows) == 3
values = {name: (float(t), float(e)) for name, t, e in rows}
names = ["favorable", "middle", "weak_partial"]
labels = ["Favorable contact / low heat loss", "Middle assumptions", "Weak force / partial contact"]
colors = ["#27746c", "#b9852b", "#a64837"]
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "svg.fonttype": "none",
        "svg.hashsalt": "temper-glass-hardening",
    }
)
fig, axes = plt.subplots(1, 2, figsize=(12, 3.2), layout="constrained")
for ax, column, limit, title in zip(
    axes,
    [0, 1],
    [3, 5],
    ["t90 of sensor's own final rise · seconds", "Underread at local pan 200°C · °C"],
    strict=True,
):
    vals = [abs(values[name][column]) for name in names]
    ax.barh(labels, vals, color=colors, height=0.55)
    ax.invert_yaxis()
    ax.axvline(limit, color="#555555", ls="--", lw=1)
    ax.set_title(title, loc="left", fontsize=11, pad=16)
    ax.set_xlim(0, 20)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    for i, v in enumerate(vals):
        ax.text(v + 0.2, i, f"{v:.2f}", va="center")
    ax.grid(axis="x", alpha=0.15)
    ax.set_axisbelow(True)
axes[1].set_yticklabels([])
fig.savefig(ROOT / "thermal-scenarios.svg", facecolor="#ffffff", metadata={"Date": None})
svg = ROOT / "thermal-scenarios.svg"
svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
fig.savefig(ROOT / "thermal-scenarios.png", dpi=160, facecolor="#ffffff")
