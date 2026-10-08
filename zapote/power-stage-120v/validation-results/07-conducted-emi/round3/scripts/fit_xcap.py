#!/usr/bin/env python3
"""Fit a scenario RLC to K-SIM's related-series, zero-bias R46 export.

The exported ESR is frequency-dependent; a single ESR cannot reproduce it.
This script reports the full table and a separate high-frequency ESL fit.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources/Imp-ESR_R46KN4100JHP1M.csv"
OUTPUT = ROOT / "outputs/xcap_fit.json"


def main() -> None:
    series: dict[str, list[tuple[float, float]]] = {"Impedance": [], "ESR": []}
    with SOURCE.open(newline="") as stream:
        for row in csv.DictReader(stream):
            series[row["y_label"]].append((float(row["x"]), float(row["y"])))
    frequency = np.array([f for f, _ in series["Impedance"]])
    impedance = np.array([z for _, z in series["Impedance"]])
    esr = np.array([r for _, r in series["ESR"]])
    assert np.allclose(frequency, [f for f, _ in series["ESR"]])
    capacitance = 1.0000040902014007e-6  # vendor's 10-kHz CKT, related part
    high = frequency >= 1.5e6
    reactance = np.sqrt(np.maximum(impedance[high] ** 2 - esr[high] ** 2, 0))
    omega = 2 * np.pi * frequency[high]
    # Above self resonance, X = omega*L - 1/(omega*C).
    inductance = float(np.sum(omega * (reactance + 1 / (omega * capacitance))) / np.sum(omega**2))
    fit_error = float(np.sqrt(np.mean((reactance - (omega * inductance - 1 / (omega * capacitance))) ** 2)))
    # Compact monotonic ESR scenario for a SPICE behavioral resistor is useful;
    # retain all raw table points since this fit is only an approximation.
    band = frequency >= 1.5e5
    def model(params: np.ndarray, f: np.ndarray) -> np.ndarray:
        return params[0] + params[1] * np.sqrt(f / 1e6) + params[2] / np.sqrt(f / 1e6)
    fit = least_squares(lambda p: model(p, frequency[band]) - esr[band],
                        x0=[0.01, 0.02, 0.005], bounds=(0, np.inf))
    predicted = model(fit.x, frequency[band])
    data = {
        "part": "R46KN4100JHP1M (related series only; not board R463N410000N1M)",
        "condition": "K-SIM 3.0.7.15, 25 deg C, 0 V DC bias",
        "frequency_range_hz": [float(frequency[0]), float(frequency[-1])],
        "capacitance_f": capacitance,
        "self_resonance_hz_from_rlc": float(1 / (2 * np.pi * np.sqrt(inductance * capacitance))),
        "esl_fit_h": inductance,
        "esl_fit_band_hz": [float(frequency[high][0]), float(frequency[high][-1])],
        "reactance_fit_rmse_ohm": fit_error,
        "esr_fit_formula_ohm": "a + b*sqrt(f/1e6) + c/sqrt(f/1e6)",
        "esr_fit_abc_ohm": fit.x.tolist(),
        "esr_fit_band_hz": [float(frequency[band][0]), float(frequency[band][-1])],
        "esr_fit_rmse_ohm": float(np.sqrt(np.mean((predicted-esr[band])**2))),
        "sampled": [
            {"frequency_hz": float(frequency[i]), "impedance_ohm": float(impedance[i]), "esr_ohm": float(esr[i])}
            for i in range(0, len(frequency), 25)
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps({k: v for k, v in data.items() if k != "sampled"}, indent=2))


if __name__ == "__main__":
    main()
