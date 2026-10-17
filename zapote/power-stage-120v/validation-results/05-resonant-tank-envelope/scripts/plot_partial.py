#!/usr/bin/env python3
"""Plot the two retained ideal-drive switching-current examples."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt

TASK = Path(__file__).resolve().parents[1]
CASES = (
    ("cast_iron-low-108v-1710w", "108 V, 1,710 W"),
    ("cast_iron-low-140v-300w", "140 V, 300 W"),
)


def main() -> None:
    fig, ax = plt.subplots(figsize=(8, 4.5), constrained_layout=True)
    for run_id, label in CASES:
        with (TASK / "outputs" / f"{run_id}-switching.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        ax.scatter(
            [float(row["time_s"]) * 1e3 for row in rows],
            [abs(float(row["current_a"])) for row in rows],
            s=5, alpha=0.6, label=label,
        )
    ax.set(xlabel="Time through 60 Hz half-cycle (ms)",
           ylabel="|Tank current| at ideal drive crossing (A)",
           title="Switching-instant current in ideal square-wave tank model")
    ax.grid(True, alpha=0.2)
    ax.legend()
    fig.savefig(TASK / "outputs/switching-current.png", dpi=150)


if __name__ == "__main__":
    main()
