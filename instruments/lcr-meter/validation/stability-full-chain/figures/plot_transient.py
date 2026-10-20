"""Render validated transient data; numerical acceptance remains in the Rust audit."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parent


def trace(filename: str) -> tuple[list[float], list[float]]:
    """Convert the saved TIA waveform to a plotted increment after the 1 us edge."""
    rows = [
        [float(value) for value in line.split()]
        for line in (ROOT / filename).read_text().splitlines()[1:]
    ]
    baseline = next(row[3] for row in reversed(rows) if row[0] <= 0.9e-6)
    selected = [row for row in rows if 0.98e-6 <= row[0] <= 6.2e-6]
    return (
        [(row[0] - 1e-6) * 1e6 for row in selected],
        [-(row[3] - baseline) * 1e3 for row in selected],
    )


def main() -> None:
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    fig, ax = plt.subplots(figsize=(9, 5.3), layout="constrained")
    for filename, label, color in [
        ("pulse5k_cf0.dat", "Original feedback: no capacitor", "#be4b23"),
        ("pulse5k_cf100_local.dat", "Local feedback: 100 pF", "#176b9d"),
    ]:
        x, y = trace(filename)
        ax.plot(x, y, label=label, color=color, linewidth=1.9)
    ax.axhline(2.5, color="#606973", linestyle="--", linewidth=1, label="Final increment: 2.5 mV")
    ax.set(xlim=(-0.05, 5.2), ylim=(-0.12, 5.1), xlabel="Time after diagnostic step (µs)", ylabel="Negative TIA output increment (mV)")
    ax.set_title("5 kΩ range: full-model step response", loc="left", fontweight="bold", pad=28)
    ax.text(0, 1.025, "1 µA / 1 ns edge · 5 kΩ DUT · 100 nH RF lead / 5 nH local-CF lead · TI models at 27 °C", transform=ax.transAxes, color="#46515c", fontsize=9)
    ax.text(0.40, 0.76, "No capacitor: 94.6% overshoot\nLocal 100 pF: <0.001% overshoot\n1% settling: 2.30 µs", transform=ax.transAxes, fontsize=10)
    inset = ax.inset_axes([0.49, 0.44, 0.47, 0.24])
    for name, color in [("pulse5k_cf0.dat", "#be4b23"), ("pulse5k_cf100_local.dat", "#176b9d")]:
        x, y = trace(name)
        inset.plot(x, y, color=color, linewidth=1.1)
    inset.set(xlim=(-0.01, 0.35), ylim=(-0.1, 5.1))
    inset.set_title("First 0.35 µs", fontsize=8, loc="left", pad=2)
    inset.tick_params(labelsize=7)
    inset.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    ax.grid(axis="y", color="#dbe0e5", linewidth=0.7)
    ax.spines[["top", "right"]].set_visible(False)
    fig.supxlabel("Simulation only. Full FDA bias/loading retained; valid DC checked. Hardware qualification remains required.", fontsize=8, color="#46515c")
    for suffix in ("png", "svg", "pdf"):
        fig.savefig(ROOT / f"5k-before-after.{suffix}", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
