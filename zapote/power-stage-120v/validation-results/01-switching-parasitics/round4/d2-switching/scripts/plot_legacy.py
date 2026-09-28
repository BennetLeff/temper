#!/usr/bin/env python3
"""Plot the diagnostic windows from both completed heuristic replay runs."""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
RESULT = HERE.parent
UNIT = HERE.parents[4]
sys.path.insert(0, str(UNIT / "validation-plan/sim-kit/common"))
from run_ngspice import read_raw  # noqa: E402


def load(name: str) -> dict[str, np.ndarray]:
    path = RESULT / "outputs/runs" / f"{name}_0.1" / "waves.raw"
    return {key: np.asarray(value) for key, value in read_raw(path).items()}


def main() -> None:
    base = load("extended_instrumented")
    clamp = load("heuristic_ideal_offgate")
    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True, layout="constrained")
    for name, wave, style in (("A2 heuristic replay", base, "-"),
                              ("delayed die-gate clamp", clamp, "--")):
        t_us = wave["time"] * 1e6
        mask = (t_us >= 2.25) & (t_us <= 2.55)
        axes[0].plot(t_us[mask], (wave["v(xql.dd)"] - wave["v(xql.s)"])[mask], style, label=name)
        axes[1].plot(t_us[mask], (wave["v(xql.g)"] - wave["v(xql.s)"])[mask], style, label=name)
        axes[2].plot(t_us[mask], wave["i(vids)"][mask], style, label=name)
    for ax in axes:
        ax.axvline(2.30866, color="gray", alpha=.5, linewidth=1, label="original first VGS<3V")
        ax.axvline(2.345, color="purple", alpha=.5, linewidth=1, label="clamp centre")
        ax.axvline(2.3505, color="black", alpha=.5, linewidth=1, label="HS command on")
        ax.grid(alpha=.25)
    axes[0].axhline(520, color="red", linestyle=":", linewidth=1, label="S1 520V")
    axes[0].axhline(585, color="orange", linestyle=":", linewidth=1, label="S2 585V")
    axes[0].set_ylabel("LS die VDS (V)")
    axes[1].set_ylabel("LS die VGS (V)")
    axes[2].set_ylabel("LS external drain (A)")
    axes[2].set_xlabel("Time (µs)")
    axes[0].legend(loc="upper right", fontsize=8)
    axes[1].legend(loc="upper right", fontsize=8)
    fig.suptitle("Unqualified A2 scalar case: 170V, 37A, DIR0, 348ns, 0.1ns step")
    out = RESULT / "outputs/legacy-counterfactual.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    print(out)


if __name__ == "__main__":
    main()
