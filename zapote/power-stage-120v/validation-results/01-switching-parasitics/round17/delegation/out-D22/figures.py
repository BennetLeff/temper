#!/usr/bin/env python3
"""Plot the retained finest-source receiver envelope; no qualification is inferred."""

import csv
import gzip
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    summary = json.loads((HERE / "envelope-summary.json").read_text())
    scenarios = json.loads((HERE / "filter-scenarios.json").read_text())
    fig, axes = plt.subplots(2, 1, figsize=(11, 8), sharex=True, layout="constrained")
    for axis, design in zip(axes, ("original", "proposed")):
        for frequency, color in ((35000, "#b45309"), (60000, "#075985")):
            envelopes = []
            for case in summary["cases"]:
                if case["frequency_Hz"] != frequency or "case" not in case:
                    continue
                for scenario in scenarios:
                    if scenario.startswith("original") != (design == "original"):
                        continue
                    path = HERE / "qualified-spectra" / f"{case['case']}-{scenario}.csv.gz"
                    with gzip.open(path, "rt") as stream:
                        rows = list(csv.DictReader(stream))
                    f = np.array([float(r["Hz"]) for r in rows])
                    regulated = np.array([r["regulated"] == "True" for r in rows])
                    margin = np.array([float(r["terminal_AV_margin_dB"]) for r in rows])
                    envelopes.append(np.where(regulated, margin, np.nan))
            if envelopes:
                # Only regulated bins enter the reduction; exclusions stay blank.
                values = np.stack(envelopes)
                usable = np.isfinite(values).any(axis=0)
                envelope = np.full(len(f), np.nan)
                envelope[usable] = np.nanmin(values[:, usable], axis=0)
                axis.semilogx(f / 1e6, envelope, color=color, linewidth=1.0, label=f"{frequency / 1000:g} kHz sources")
        axis.axhline(0, color="black", linewidth=0.8)
        if design == "proposed":
            axis.axhline(7, color="#be123c", linestyle="--", label="6 dB target + 1 dB planning reserve")
        axis.set_title(f"{design.capitalize()} receiver — worst terminal, case and declared sensitivity")
        axis.set_ylabel("AV margin (dB)")
        axis.grid(True, which="both", alpha=0.2)
        axis.legend(loc="best", fontsize=8)
        axis.set_xlim(0.15, 30)
    axes[-1].set_xlabel("Frequency (MHz); excluded ISM bands are blank")
    fig.suptitle(f"D-22 provisional envelope — {summary['numerically_qualified_cases']}/16 source cases numerically qualified")
    fig.savefig(HERE / "margin-envelope.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
