#!/usr/bin/env python3
"""Calibrated pixel fit of TDK's typical parallel-winding impedance curve.

Points trace the upper (1.6 mH) IND0783-T curve in a TDK-authored 10/08
datasheet archived at alldatasheet. The page bitmap is deliberately not
redistributed. This simple R||L||C fit is a heuristic and cannot qualify
attenuation above the first resonance.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares


ROOT = Path(__file__).resolve().parents[1]
PIXELS = ROOT / "sources/tdk-curve-pixels.csv"
OUTPUT = ROOT / "outputs/tdk_choke_fit.json"

# Pixel calibration on the 892x1263 archive page image:
# x=134,223,312,400 => 10^4,10^5,10^6,10^7 Hz
# y=807,739,671,603,535,466 => 10^1 ... 10^6 ohms.
X0, X1 = 134.0, 400.0
Y0, Y1 = 807.0, 466.0
L_PARALLEL_H = 1.6e-3 * (1 + (1 - 18e-6 / (2 * 1.6e-3))) / 2
R_PARALLEL_DC_OHM = 4.5e-3 / 2


def impedance(frequency: np.ndarray, parallel_r: float, parallel_c: float) -> np.ndarray:
    omega = 2 * np.pi * frequency
    admittance = 1 / (R_PARALLEL_DC_OHM + 1j * omega * L_PARALLEL_H)
    admittance += 1 / parallel_r + 1j * omega * parallel_c
    return abs(1 / admittance)


def main() -> None:
    with PIXELS.open(newline="") as stream:
        pixels = list(csv.DictReader(stream))
    x = np.array([float(row["pixel_x"]) for row in pixels])
    y = np.array([float(row["pixel_y"]) for row in pixels])
    frequency = 10 ** (4 + 3 * (x - X0) / (X1 - X0))
    measured = 10 ** (1 + 5 * (Y0 - y) / (Y0 - Y1))
    def fit_pixels(pixel_x: np.ndarray, pixel_y: np.ndarray) -> np.ndarray:
        f = 10 ** (4 + 3 * (pixel_x - X0) / (X1 - X0))
        z = 10 ** (1 + 5 * (Y0 - pixel_y) / (Y0 - Y1))
        return least_squares(
            lambda p: np.log10(impedance(f, p[0], p[1] * 1e-12) / z),
            x0=[6000, 30], bounds=([100, 1], [1e6, 1000]),
        ).x
    fit = fit_pixels(x, y)
    parallel_r, c_pf = map(float, fit)
    modeled = impedance(frequency, parallel_r, c_pf * 1e-12)
    error_db = 20 * np.log10(modeled / measured)
    # The plotted curve is about 2-4 pixels thick in the archive raster.
    # Perturbing traced points by +/-2 pixels probes digitization sensitivity,
    # not part tolerance or a statistical confidence interval.
    rng = np.random.default_rng(82726)
    perturbations = [(x + dx, y + dy) for dx in (-2, 2) for dy in (-2, 2)]
    perturbations += [(x + rng.uniform(-2, 2, len(x)),
                       y + rng.uniform(-2, 2, len(y))) for _ in range(200)]
    uncertain = np.array([fit_pixels(px, py) for px, py in perturbations])
    c_range_pf = [float(np.min(uncertain[:, 1])), float(np.max(uncertain[:, 1]))]
    r_range_ohm = [float(np.min(uncertain[:, 0])), float(np.max(uncertain[:, 0]))]
    fres_range = [float(1 / (2 * np.pi * np.sqrt(L_PARALLEL_H * c * 1e-12)))
                  for c in reversed(c_range_pf)]
    result = {
        "source_url": "https://www.alldatasheet.com/html-pdf/327493/EPCOS/B82726S2203A020/650/4/B82726S2203A020.html",
        "source_page_image_url": "https://www.alldatasheet.com/htmldatasheet2/327493/EPCOS/B82726S2203A020/650/4/B82726S2203A020.png",
        "source_image_sha256": "c290332c3dd42337bf5c1ec0aff0ee9e193b805e7b9a09cf1646461152aa01e3",
        "source_revision": "TDK/EPCOS 10/08, plot IND0783-T; May 2026 sheet uses same plot identifier but numeric stray L revised 15 to 18 uH",
        "measurement": "typical magnitude, both windings in parallel, 20 C",
        "calibration_pixels": {"x": [[134, 1e4], [400, 1e7]], "y": [[807, 1e1], [466, 1e6]]},
        "fit_kind": "heuristic parallel RLC constrained by May 2026 nominal L and 18-uH stray inductance",
        "parallel_inductance_h": L_PARALLEL_H,
        "parallel_dc_resistance_ohm": R_PARALLEL_DC_OHM,
        "parallel_damping_resistance_ohm": parallel_r,
        "damping_resistance_per_winding_ohm": 2 * parallel_r,
        "parallel_capacitance_f": c_pf * 1e-12,
        "capacitance_per_winding_f": c_pf * 1e-12 / 2,
        "self_resonance_hz": float(1 / (2 * np.pi * np.sqrt(L_PARALLEL_H * c_pf * 1e-12))),
        "fit_rmse_db": float(np.sqrt(np.mean(error_db**2))),
        "fit_max_abs_error_db": float(np.max(abs(error_db))),
        "digitization_sensitivity": {
            "method": "uniform independent +/-2 pixel jitter for 200 seeded trials plus four +/-2-pixel systematic corners; not part tolerance",
            "parallel_capacitance_pf_range": c_range_pf,
            "parallel_damping_resistance_ohm_range": r_range_ohm,
            "self_resonance_hz_range": fres_range,
        },
        "points": [
            {"frequency_hz": float(f), "digitized_impedance_ohm": float(z),
             "fit_impedance_ohm": float(zhat), "fit_error_db": float(e)}
            for f, z, zhat, e in zip(frequency, measured, modeled, error_db, strict=True)
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "points"}, indent=2))


if __name__ == "__main__":
    main()
