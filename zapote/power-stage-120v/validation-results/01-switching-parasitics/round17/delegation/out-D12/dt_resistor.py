"""D12 evidence calculation; D1 interpolation is an estimate, never a guarantee."""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def estimate(r_kohm: float, tolerance: float, tcr_ppm: float, temp_c: float) -> dict:
    """Apply D1's multiplicative resistance stack and linear timing estimate."""
    drift = tcr_ppm * 1e-6 * abs(temp_c - 25)
    rmin = r_kohm * (1 - tolerance) * (1 - drift)
    rmax = r_kohm * (1 + tolerance) * (1 + drift)
    return {
        "resistor_temperature_C": temp_c,
        "Rmin_kohm": rmin,
        "Rmax_kohm": rmax,
        "DTmin_est_ns": 167 + (rmin - 20) * (399 - 167) / 30,
        "DTnom_fit_ns": 8.6 * r_kohm + 13,
        "DTmax_est_ns": 203 + (rmax - 20) * (487 - 203) / 30,
        "extrapolates_above_50k": rmax > 50,
        "guaranteed_minimum_ns": None,
    }


def main() -> None:
    candidates = [
        ("RC0603FR-0739KL", 39, 0.01, 100),
        ("RC0603FR-0749K9L", 49.9, 0.01, 100),
        ("RC0603FR-0751KL", 51, 0.01, 100),
        ("RT0603BRD0749K9L", 49.9, 0.001, 25),
    ]
    result = {
        "authority": "TI SLUSE89C pp10,25; D1 README; resistor datasheets in SOURCES.md",
        "status": "estimated only; no guaranteed minimum established",
        "required_minimum_ns": 391,
        "D1_stack_required_nominal_kohm": (20 + (391 - 167) * 30 / 232)
        / ((1 - 0.01) * (1 - 100e-6 * 125)),
        "candidates": {
            part: [estimate(r, tol, tcr, t) for t in (-40, 25, 150)]
            for part, r, tol, tcr in candidates
        },
    }
    (HERE / "dt_resistor.json").write_text(json.dumps(result, indent=2) + "\n")
    for part, rows in result["candidates"].items():
        print(
            part,
            "min/nom/max estimate ns:",
            f"{min(r['DTmin_est_ns'] for r in rows):.3f}",
            f"{rows[0]['DTnom_fit_ns']:.3f}",
            f"{max(r['DTmax_est_ns'] for r in rows):.3f}",
        )


if __name__ == "__main__":
    main()
