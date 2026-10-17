"""Exercise fail-closed paths on captured Elmer logs without rerunning FEM."""

import argparse
import json
import math
import re
import tempfile
from pathlib import Path

from verify_elmer_fixture import classify


def check(direct: Path, ams: Path) -> dict:
    direct_text = direct.read_text()
    ams_text = ams.read_text()
    results = {}
    with tempfile.TemporaryDirectory(prefix="ps-r6-fem-verifier-") as directory:
        probe = Path(directory) / "mutated.log"
        probe.write_text(direct_text)
        result = classify(probe, False, math.nan)
        results["nonfinite_tolerance_rejected"] = not result["nominal_log_screen_pass"]
        probe.write_text(direct_text + "\nERROR:: injected failed solver\n")
        result = classify(probe, False, 1e-9)
        results["error_marker_rejected"] = not result["nominal_log_screen_pass"]
        probe.write_text(ams_text.replace("1.025604E-05", "6.839985E-09"))
        result = classify(probe, True, 1e-9)
        results["plausible_energy_high_residual_rejected"] = (
            not result["nominal_log_screen_pass"] and result["last_hypre_relative_residual"] > 1)
        no_history = re.sub(r"SolveHypre: Solving linear system.*?SolveHypre: Required iterations",
                            "SolveHypre: Required iterations", ams_text, count=1, flags=re.DOTALL)
        probe.write_text(no_history.replace("1.025604E-05", "6.839985E-09"))
        result = classify(probe, True, 1e-9)
        results["missing_residual_history_rejected"] = (
            not result["nominal_log_screen_pass"] and result["last_hypre_relative_residual"] is None)
        probe.write_text(direct_text.replace(
            "Magnetic Field Energy:    6.872621E-09",
            "Magnetic Field Energy:    6.872621E-09\nMagnetic Field Energy: NaN"))
        result = classify(probe, False, 1e-9)
        results["final_nan_energy_after_valid_energy_rejected"] = (
            not result["nominal_log_screen_pass"] and result["magnetic_energy_J"] is None)
        good_then_nan = re.sub(
            r"SolveHypre: Solving linear system.*?SolveHypre: Required iterations",
            "SolveHypre: Solving linear system\n  1 1e-10 0.1 1e-10\n"
            "  2 NaN 1.0 NaN\nSolveHypre: Required iterations",
            ams_text,
            count=1,
            flags=re.DOTALL,
        ).replace("1.025604E-05", "6.839985E-09")
        probe.write_text(good_then_nan)
        result = classify(probe, True, 1e-9)
        results["final_nan_residual_after_valid_residual_rejected"] = (
            not result["nominal_log_screen_pass"] and result["last_hypre_relative_residual"] is None)
    if not all(results.values()):
        raise AssertionError(results)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("direct", type=Path)
    parser.add_argument("ams", type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.direct, args.ams), indent=2))
