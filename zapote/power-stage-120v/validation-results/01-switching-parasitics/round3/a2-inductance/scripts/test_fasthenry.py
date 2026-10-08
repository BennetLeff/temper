#!/usr/bin/env python3
"""Write independent FastHenry fixtures and check a solver if available.

The checks intentionally report UNRUN without a solver. Analytic values alone
cannot validate a field solver or certify a board inductance.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

MU0 = 4 * math.pi * 1e-7


def plane_pair_nh(width_mm: float, length_mm: float, gap_mm: float) -> float:
    """Infinite-width approximation, excluding finite-edge fringing."""
    return MU0 * (gap_mm * 1e-3) * (length_mm * 1e-3) / (width_mm * 1e-3) * 1e9


def round_wire_nh(length_mm: float, radius_mm: float, *, dc_internal: bool) -> float:
    """Long, isolated round-wire partial self L, with optional DC internal L.

    External partial L uses the finite-wire long-aspect approximation
    mu0*l/(2*pi)*(ln(2*l/r)-1). The DC internal addition is mu0*l/(8*pi).
    Neither expression is a closed-loop inductance.
    """
    length_m = length_mm * 1e-3
    external = MU0 * length_m / (2 * math.pi) * (math.log(2 * length_mm / radius_mm) - 1)
    internal = MU0 * length_m / (8 * math.pi) if dc_internal else 0.0
    return (external + internal) * 1e9


def write_fixtures(out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}
    for segments in (20, 40):
        name = f"plane_pair_{segments}.inp"
        deck = f"""* 10 x 50 mm finite copper plane pair, 0.5 mm dielectric gap
.units mm
.default sigma=5.8e7
g1 x1=0 y1=0 z1=0 x2=50 y2=0 z2=0 x3=50 y3=10 z3=0
+ thick=0.061 seg1={segments} seg2={segments // 2}
+ n1s (0,5,0) n1e (50,5,0)
g2 x1=0 y1=0 z1=0.5 x2=50 y2=0 z2=0.5 x3=50 y3=10 z3=0.5
+ thick=0.061 seg1={segments} seg2={segments // 2}
+ n2s (0,5,0.5) n2e (50,5,0.5)
.equiv n1e n2e
.external n1s n2s
.freq fmin=1e7 fmax=1e7 ndec=1
.end
"""
        (out_dir / name).write_text(deck)
        files[name] = deck
    for subdivisions in (4, 8):
        name = f"straight_wire_{subdivisions}.inp"
        deck = f"""* 50 mm x 1 mm square straight conductor; partial self L
.units mm
.default sigma=5.8e7
N1 x=0 y=0 z=0
N2 x=50 y=0 z=0
E1 N1 N2 w=1 h=1 nwinc={subdivisions} nhinc={subdivisions}
.external N1 N2
.freq fmin=1e7 fmax=1e7 ndec=1
.end
"""
        (out_dir / name).write_text(deck)
        files[name] = deck
    return files


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--solver", type=Path)
    args = parser.parse_args()
    write_fixtures(args.out)
    result = {
        "analytic_reference": {
            "plane_pair_nH": plane_pair_nh(10, 50, 0.5),
            "wire_partial_external_nH": round_wire_nh(50, 0.5, dc_internal=False),
            "wire_partial_with_dc_internal_nH": round_wire_nh(50, 0.5, dc_internal=True),
            "frequency_Hz": 1e7,
            "wire_shape_note": "The deck is square-section; the round-wire expression is a scale check, not an exact 5% oracle for that cross-section.",
        },
        "solver_status": "UNRUN_NO_EXECUTABLE" if args.solver is None else "UNIMPLEMENTED_OUTPUT_CHECK",
        "solver_validation_within_5_percent": None,
        "two_mesh_convergence_within_5_percent": None,
        "note": "Generated decks are not solver results. Do not infer a FastHenry validation pass from analytic values.",
    }
    if args.solver is not None:
        raise SystemExit("Solver output parser must be implemented and verified before reporting a pass")
    args.report.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
