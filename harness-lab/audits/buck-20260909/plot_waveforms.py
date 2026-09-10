"""Plot retained native ngspice binary output; this tool makes no pass/fail judgments.

Run with an isolated matplotlib environment. Input is ngspice's real, native
float64 binary format on this host; the simulator remains the measurement tool.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def plot(raw: Path, output: Path, title: str) -> None:
    header, data = raw.read_bytes().split(b"Binary:\n", 1)
    text = header.decode("utf-8")
    if "Flags: real" not in text:
        raise ValueError("only real ngspice waveforms are supported")
    count = int(text.split("No. Variables:", 1)[1].splitlines()[0])
    points = int(text.split("No. Points:", 1)[1].splitlines()[0])
    names = [
        line.split()[1] for line in text.split("Variables:\n", 1)[1].splitlines() if line.strip()
    ]
    values = np.frombuffer(data, dtype="=f8").reshape(points, count)
    if len(names) != count or not np.isfinite(values).all():
        raise ValueError("malformed or nonfinite waveform")
    columns = {name: values[:, i] for i, name in enumerate(names)}
    t = columns["time"]
    if np.any(np.diff(t) <= 0):
        raise ValueError("waveform time is not strictly increasing")
    fig, axes = plt.subplots(3, 1, figsize=(11, 8), constrained_layout=True)
    fig.suptitle(title + "\nDatasheet-derived behavioral model · exploratory", fontsize=15)
    # Matplotlib draws the actual adaptive samples; no smoothed or invented trace.
    axes[0].plot(t * 1e3, columns["v(out)"], color="#087f8c", linewidth=0.9)
    axes[0].set(ylabel="Output (V)", xlabel="Time (ms)")
    axes[1].plot(t * 1e3, columns["i(l_out)"], color="#b56b08", linewidth=0.5)
    axes[1].set(ylabel="Inductor current (A)", xlabel="Time (ms)")
    window = t >= t[-1] - 20e-6
    axes[2].plot(
        (t[window] - t[-1]) * 1e6,
        columns["v(sw)"][window],
        color="#7051a8",
        linewidth=0.8,
    )
    axes[2].set(ylabel="Switch node (V)", xlabel="Final 20 µs")
    for ax in axes:
        ax.grid(alpha=0.2)
        ax.spines[["top", "right"]].set_visible(False)
    fig.savefig(output, dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--title", default="Buck converter simulation")
    args = parser.parse_args()
    plot(args.raw, args.output, args.title)
