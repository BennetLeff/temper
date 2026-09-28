#!/usr/bin/env python3
"""Coherent trapezoid-harmonic EMI scenarios, without a regulatory verdict.

AC source responses are combined with exact Fourier coefficients of periodic
linear-edge trapezoids. These are peak line voltages, not quasi-peak or average
detector readings. Bus-ripple DM current is unknown and omitted.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from check_topology import ROOT, run_case


OUTPUT = ROOT / "outputs"
VBUS = 170.0


def trapezoid_peak_phasor(harmonic: np.ndarray, fs: float, edge_s: float,
                         shift_s: float = 0.0) -> np.ndarray:
    """Peak phasor (2*c_n) for 0-to-VBUS, 50%-duty linear-edge waveform."""
    period = 1 / fs
    omega = 2 * np.pi * harmonic * fs
    ramp = (1 - np.exp(-1j * omega * edge_s)) / (1j * omega * edge_s)
    derivative_integral = VBUS * ramp * (1 - np.exp(-1j * omega * period / 2))
    coefficient = derivative_integral / (1j * omega * period)
    return 2 * coefficient * np.exp(-1j * omega * shift_s)


def interpolate(waves: dict[str, np.ndarray], f: np.ndarray, key: str) -> np.ndarray:
    grid = waves["frequency"].real
    values = waves[key]
    return np.interp(f, grid, values.real) + 1j * np.interp(f, grid, values.imag)


def simulate(name: str, settings: dict[str, float], edge_v_per_ns: float,
             edge_b_factor: float) -> list[dict[str, float | str]]:
    a = run_case({**settings, "EXC_A": 1, "EXC_B": 0})
    b = run_case({**settings, "EXC_A": 0, "EXC_B": 1})
    rows: list[dict[str, float | str]] = []
    for fs in (35e3, 60e3):
        harmonic = np.arange(int(np.ceil(150e3 / fs)), int(np.floor(30e6 / fs)) + 1)
        frequency = harmonic * fs
        edge_a = VBUS / (edge_v_per_ns * 1e9)
        va = trapezoid_peak_phasor(harmonic, fs, edge_a)
        vb = trapezoid_peak_phasor(harmonic, fs, edge_a * edge_b_factor, 0.5 / fs)
        line = (interpolate(a, frequency, "v(lisn_l)") * va
                + interpolate(b, frequency, "v(lisn_l)") * vb)
        neutral = (interpolate(a, frequency, "v(lisn_n)") * va
                   + interpolate(b, frequency, "v(lisn_n)") * vb)
        cm = abs((line + neutral) / 2)
        dm_from_tab = abs((line - neutral) / 2)
        for f, n, vl, vn, c, d in zip(frequency, harmonic, abs(line), abs(neutral), cm, dm_from_tab,
                                       strict=True):
            rows.append({"scenario": name, "switching_hz": fs, "harmonic": int(n),
                         "frequency_hz": float(f), "line_peak_dbuv": float(20 * np.log10(max(vl, 1e-30) / 1e-6)),
                         "neutral_peak_dbuv": float(20 * np.log10(max(vn, 1e-30) / 1e-6)),
                         "cm_peak_dbuv": float(20 * np.log10(max(c, 1e-30) / 1e-6)),
                         "dm_from_tab_peak_dbuv": float(20 * np.log10(max(d, 1e-30) / 1e-6))})
    return rows


def main() -> None:
    # Numerical FFT oracle for the peak-line convention used below.
    fs_check = 35e3
    edge_check = VBUS / (5e9)
    samples = 262144
    phase = np.arange(samples) / samples
    edge_phase = edge_check * fs_check
    waveform = VBUS * np.where(
        phase < edge_phase, phase / edge_phase,
        np.where(phase < 0.5, 1.0,
                 np.where(phase < 0.5 + edge_phase,
                          1.0 - (phase - 0.5) / edge_phase, 0.0)),
    )
    fft = 2 * np.fft.fft(waveform) / samples
    check_harmonics = np.array([5, 51, 501])
    exact = trapezoid_peak_phasor(check_harmonics, fs_check, edge_check)
    fft_relative_error = abs(fft[check_harmonics] - exact) / abs(exact)
    if float(max(fft_relative_error)) > 0.01:
        raise AssertionError(f"trapezoid Fourier/FFT mismatch: {fft_relative_error}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "fourier_fft_check.json").write_text(json.dumps({
        "sample_count": samples, "fs_hz": fs_check, "edge_s": edge_check,
        "harmonics": check_harmonics.tolist(),
        "max_relative_complex_error": float(max(fft_relative_error)),
        "convention": "2*abs(FFT coefficient) is sinusoidal peak line voltage",
    }, indent=2) + "\n")
    # All electrical unknowns below are scenarios, including RF pad epsilon,
    # rectifier capacitance at reverse bias and winding response above 847 kHz.
    cases = {
        "balanced": ({"CTABA": 42e-12, "CTABB": 42e-12}, 5.0, 1.0),
        "tab_mismatch_20pct": ({"CTABA": 50.4e-12, "CTABB": 33.6e-12}, 5.0, 1.0),
        "edge_mismatch_20pct": ({"CTABA": 42e-12, "CTABB": 42e-12}, 5.0, 1.2),
        "both_mismatches": ({"CTABA": 50.4e-12, "CTABB": 33.6e-12}, 5.0, 1.2),
        "coil_pe_10pf": ({"CTABA": 50.4e-12, "CTABB": 33.6e-12,
                           "CCOILA": 5e-12, "CCOILB": 5e-12}, 5.0, 1.2),
        "coil_pe_100pf": ({"CTABA": 50.4e-12, "CTABB": 33.6e-12,
                            "CCOILA": 50e-12, "CCOILB": 50e-12}, 5.0, 1.2),
        "choke_l_minus_30pct": ({"CTABA": 50.4e-12, "CTABB": 33.6e-12,
                                 "LCM": 1.12e-3}, 5.0, 1.2),
        "edge_1v_per_ns": ({"CTABA": 50.4e-12, "CTABB": 33.6e-12}, 1.0, 1.2),
        "edge_20v_per_ns": ({"CTABA": 50.4e-12, "CTABB": 33.6e-12}, 20.0, 1.2),
    }
    rows: list[dict[str, float | str]] = []
    for name, (settings, slope, b_factor) in cases.items():
        rows.extend(simulate(name, settings, slope, b_factor))
    path = OUTPUT / "assumed_peak_lines.csv"
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = []
    for name in cases:
        for fs in (35e3, 60e3):
            part = [row for row in rows if row["scenario"] == name and row["switching_hz"] == fs]
            peak = max(part, key=lambda row: float(row["cm_peak_dbuv"]))
            summary.append({"scenario": name, "switching_hz": fs,
                            "max_cm_peak_dbuv": peak["cm_peak_dbuv"],
                            "at_hz": peak["frequency_hz"]})
    (OUTPUT / "assumed_spectrum_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    for axis, fs in zip(axes, (35e3, 60e3), strict=True):
        for name in ("balanced", "tab_mismatch_20pct", "edge_mismatch_20pct", "both_mismatches"):
            part = [row for row in rows if row["scenario"] == name and row["switching_hz"] == fs]
            axis.plot([row["frequency_hz"] / 1e6 for row in part],
                      [row["cm_peak_dbuv"] for row in part], '.', markersize=1.4, label=name)
        axis.axvline(0.8465, color="gray", linestyle="--", linewidth=0.8)
        axis.set_title(f"{fs / 1e3:.0f} kHz; ASSUMED 5 V/ns edges, 170 V crest")
        axis.set_ylabel("CM peak line dBµV")
        axis.set_xscale("log")
        axis.grid(True, which="both", alpha=0.2)
    axes[0].legend(fontsize=8)
    axes[-1].set_xlabel("Frequency (MHz); right of dashed line is beyond choke first resonance")
    fig.suptitle("Model scenarios only — no DM bus ripple, no QP detector, no compliance margin")
    fig.tight_layout()
    fig.savefig(OUTPUT / "assumed_cm_peak_lines.png", dpi=170)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
