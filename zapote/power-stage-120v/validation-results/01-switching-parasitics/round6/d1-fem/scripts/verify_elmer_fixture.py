"""Classify an Elmer coax solve; `ALL DONE` alone is not convergence.

This is a local evidence check for the round-6 fixture, not a permanent
engineering verdict.  Hypre can emit `ALL DONE` and exit zero after a
stagnated solve; its verbose residual must be checked separately.
"""

import argparse
import json
import math
import re
from pathlib import Path

ENERGY = re.compile(r"Magnetic Field Energy:\s+(\S+)")
RESIDUAL_ROW = re.compile(r"^\s*(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$", re.MULTILINE)
ANALYTIC_NH = 13.862943611198905


def classify(log_path: Path, iterative: bool, tolerance: float) -> dict:
    content = log_path.read_text()
    reasons = []
    if not math.isfinite(tolerance) or tolerance <= 0:
        reasons.append("requested relative tolerance must be finite and positive")
    if "MAIN: *** Elmer Solver: ALL DONE ***" not in content:
        reasons.append("Elmer did not print ALL DONE")
    if re.search(r"(?:ERROR::|\bFATAL\b|\bSTOP\s+[1-9]\b)", content, re.IGNORECASE):
        reasons.append("solver log contains an error, fatal marker, or nonzero STOP")
    matches = ENERGY.findall(content)
    try:
        energy_j = float(matches[-1]) if matches else None
    except ValueError:
        energy_j = None
    if energy_j is None or not math.isfinite(energy_j) or energy_j <= 0:
        reasons.append("magnetic energy is missing, nonfinite, or nonpositive")
        energy_j = None
    residual = None
    iterations = None
    if iterative:
        hypre_start = "SolveHypre: Solving linear system"
        hypre_end = "SolveHypre: Required iterations"
        if hypre_start in content and hypre_end in content:
            hypre_history = content.rsplit(hypre_start, 1)[-1].split(hypre_end, 1)[0]
        else:
            hypre_history = ""
        rows = RESIDUAL_ROW.findall(hypre_history)
        if not rows:
            reasons.append("no Hypre relative-residual history; convergence unknown")
        else:
            iterations = int(rows[-1][0])
            try:
                residual = float(rows[-1][3])
            except ValueError:
                residual = None
                reasons.append("last Hypre relative residual token is not numeric")
            if residual is not None and (not math.isfinite(residual) or residual < 0):
                reasons.append("last Hypre relative residual is nonfinite or negative")
                residual = None
            elif residual is not None and math.isfinite(tolerance) and residual > tolerance:
                reasons.append(f"last Hypre relative residual {residual:g} exceeds {tolerance:g}")
        if "Required iterations 0" in content:
            reasons.append("Hypre wrapper reports zero required iterations / norm 1")
    inductance_nh = 2 * energy_j * 1e9 if energy_j is not None else None
    analytic_error_pct = ((inductance_nh / ANALYTIC_NH - 1) * 100
                          if inductance_nh is not None else None)
    if inductance_nh is not None and abs(analytic_error_pct) > 2:
        reasons.append(f"coax analytic error {analytic_error_pct:.3f}% exceeds 2%")
    return {"log": str(log_path), "iterative": iterative,
            "screen_scope": "nominal-1A numerical log only; source continuity and full fixture pipeline are separate",
            "magnetic_energy_J": energy_j,
            "nominal_inductance_nH": inductance_nh, "analytic_error_pct": analytic_error_pct,
            "last_hypre_iteration": iterations, "last_hypre_relative_residual": residual,
            "nominal_log_screen_pass": not reasons, "reasons": reasons}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    parser.add_argument("--iterative", action="store_true")
    parser.add_argument("--tolerance", type=float, default=1e-9)
    args = parser.parse_args()
    result = classify(args.log, args.iterative, args.tolerance)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["nominal_log_screen_pass"] else 1)
