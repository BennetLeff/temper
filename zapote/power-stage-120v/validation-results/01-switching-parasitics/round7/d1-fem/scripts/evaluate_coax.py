"""Evaluate the D1 coax fixture with sampled source-current uncertainty.

This is a one-off simulation assessment. The extrema are sampled cuts, not a
rigorous bound over every possible cut of the port surface.
"""

import json
import math
from pathlib import Path

MU0_H_PER_M = 1.2566370614359173e-6
EXACT_NH = MU0_H_PER_M * 0.05 * math.log(2.0 / 0.5) / (2 * math.pi) * 1e9
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw" / "fixtures"
CASES = ("coax-port0p10-vol0p30", "coax-port0p08-vol0p25")


def assess(label: str) -> dict:
    verification = json.loads((RAW / f"{label}-nominal-verification.json").read_text())
    source = json.loads((RAW / f"{label}-source.json").read_text())
    mesh = json.loads((RAW / f"{label}-mesh.json").read_text())
    if not verification["nominal_log_screen_pass"]:
        raise ValueError(f"{label}: numerical log screen failed")
    if mesh["min_jacobian_mm3"] <= 0:
        raise ValueError(f"{label}: nonpositive mesh Jacobian")
    cuts = source["circular_cuts"]
    if len(cuts) < 4 or any(not math.isfinite(value) or value <= 0 for value in cuts.values()):
        raise ValueError(f"{label}: invalid or incomplete current cuts")
    current_min = min(cuts.values())
    current_max = max(cuts.values())
    nominal = verification["nominal_inductance_nH"]
    lower = nominal / current_max**2
    upper = nominal / current_min**2
    error_lower_pct = 100 * (lower / EXACT_NH - 1)
    error_upper_pct = 100 * (upper / EXACT_NH - 1)
    return {
        "label": label,
        "tetrahedra": mesh["tetrahedra"],
        "min_jacobian_mm3": mesh["min_jacobian_mm3"],
        "source_cut_currents_A": cuts,
        "source_current_sampled_range_A": [current_min, current_max],
        "source_current_sampled_spread_A": current_max - current_min,
        "nominal_inductance_nH": nominal,
        "current_normalized_inductance_sampled_range_nH": [lower, upper],
        "error_sampled_range_pct": [error_lower_pct, error_upper_pct],
        "full_sampled_current_2pct_criterion_pass":
            error_lower_pct >= -2 and error_upper_pct <= 2,
    }


def main() -> None:
    results = [assess(label) for label in CASES]
    coarse, fine = results
    change = fine["nominal_inductance_nH"] - coarse["nominal_inductance_nH"]
    change_pct = 100 * change / coarse["nominal_inductance_nH"]
    output = {
        "evidence_class": "simulation/model-based",
        "exact_analytic_inductance_nH": EXACT_NH,
        "cut_scope": "four sampled circular cuts per mesh; extrema are not global bounds",
        "cases": results,
        "fine_minus_coarse_nominal_nH": change,
        "fine_minus_coarse_relative_pct": change_pct,
        "both_meshes_pass_full_sampled_current_2pct_criterion":
            all(row["full_sampled_current_2pct_criterion_pass"] for row in results),
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
