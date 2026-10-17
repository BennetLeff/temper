#!/usr/bin/env python3
"""Reconstruct settled series-RLC current from periodic voltage harmonics."""

import json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent


def tank_current(voltage_peak, frequency, resistance):
    n = (len(voltage_peak) - 1) * 2
    omega = 2 * np.pi * frequency * np.arange(1, len(voltage_peak))
    impedance = resistance + 1j * (omega * 70e-6 - 1 / (omega * 0.54e-6))
    current_peak = np.zeros_like(voltage_peak)
    current_peak[1:] = voltage_peak[1:] / impedance
    return np.fft.irfft(current_peak * n / 2, n=n)


def main():
    result = []
    for path in sorted((HERE / "periodic-runs").glob("*.json")):
        row = json.loads(path.read_text())
        if row["status"] != "complete":
            continue
        with np.load(path.parent / (row["tag"] + "-fft.npz")) as data:
            i = tank_current(
                data["v(swa)"] - data["v(swb)"], row["frequency_Hz"], row["tank_R_ohm"]
            )
        rms = float(np.sqrt(np.mean(i * i)))
        loss = rms * rms * row["tank_R_ohm"]
        result.append(
            {
                "case": row["tag"],
                "tank_current_reconstructed_peak_A": float(np.max(abs(i))),
                "tank_current_reconstructed_RMS_A": rms,
                "current_at_first_off_command_A": float(i[0]),
                "current_at_opposite_off_command_A": float(i[len(i) // 2]),
                "tank_resistor_power_W": loss,
                "inverter_input_estimate_W": row["mean_input_power_estimate_W"],
                "input_minus_tank_estimate_W": row["mean_input_power_estimate_W"] - loss,
            }
        )
    (HERE / "source-metrics.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
