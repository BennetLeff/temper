#!/usr/bin/env python3
"""Check source binding, complete geometry scenarios, and uncertainty flags."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unit", required=True, type=Path)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--outputs", required=True, type=Path)
    args = parser.parse_args()
    result = load(args.outputs / "loop_inductance_fallback_heuristic.json")
    ports = load(args.outputs / "annotated_ports.json")
    analytic = load(args.outputs / "analytic-fixtures.json")
    board_sha = sha(args.unit / "native-15/section.kicad_pcb")
    checks: dict[str, Any] = {}
    checks["board_hash_bound"] = board_sha == result["board_sha256"] == ports["board_sha256"]
    checks["stackup_hash_bound"] = sha(args.unit / "stackup.json") == result["stackup_sha256"]
    checks["input_hashes_bound"] = all(sha(args.inputs / name) == digest
                                       for name, digest in result["inputs_sha256"].items())
    checks["analytic_plane_pair_10x50_0p5_mm"] = math.isclose(
        analytic["analytic_reference"]["plane_pair_nH"], math.pi, rel_tol=1e-9)
    checks["analytic_wire_external_50x1_mm"] = math.isclose(
        analytic["analytic_reference"]["wire_partial_external_nH"],
        10 * (math.log(200) - 1), rel_tol=1e-9)
    checks["internal_L_distinguished"] = math.isclose(
        analytic["analytic_reference"]["wire_partial_with_dc_internal_nH"] -
        analytic["analytic_reference"]["wire_partial_external_nH"], 2.5, rel_tol=1e-9)
    checks["solver_not_misreported"] = result["fasthenry"]["solver_result"] is None and analytic["solver_validation_within_5_percent"] is None
    checks["all_power_routes_connected_at_0p25_mm"] = all(
        value["status"] == "COMPLETE_CONNECTED_ROUTE_HEURISTIC_SCENARIOS"
        for value in result["power_sections"].values())
    checks["all_gate_return_routes_connected_at_0p25_mm"] = all(
        value["status"] == "COMPLETE_CONNECTED_RETURN_GEOMETRY_HEURISTIC_SCENARIOS"
        for value in result["gate_loops"].values())
    checks["all_route_ports_annotated"] = all(
        ref in ports["ports"] for route in result["routes"].values() for ref in route["ports"])
    checks["scenario_ordered"] = all(
        value["scenario_min_nH"] <= value["scenario_max_nH"]
        for value in list(result["power_sections"].values()) + list(result["gate_loops"].values()))
    checks["full_deck_scenarios_present"] = all(
        all(key in case for key in ("LD_HS", "LS_HS", "LD_LS", "LCS", "LS_LS", "LCAP", "LBULK", "LBULK_copper_only", "LG_high_side", "LG_low_side"))
        for leg in result["deck_parameters_heuristic_scenario_nH"].values() for case in leg.values())
    checks["assumed_capacitor_ESL_flagged"] = result["component_assumptions"]["C38-C41_ESL_nH"] == [5, 20]
    checks["bulk_internal_ESL_unresolved"] = result["component_assumptions"]["bulk_cap_internal_ESL_nH"] is None
    checks["Q3_coarse_return_not_claimed_converged"] = not result["routes"]["Q3_return"]["path_converged_within_5_percent"]
    failures = [name for name, ok in checks.items() if not ok]
    report = {"status": "PASS_WITH_EXPLICIT_UNRESOLVED_PHYSICS" if not failures else "FAIL",
              "checks": checks, "failures": failures,
              "physics_unresolved": ["FastHenry build and 5% analytic field-solver validation",
                                     "10 MHz current distribution/mutual inductance and field mesh convergence",
                                     "Q3 return path coarse-raster convergence",
                                     "bulk capacitor internal ESL and physical bounds"]}
    (args.outputs / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    if failures:
        raise SystemExit(f"verification failed: {failures}")


if __name__ == "__main__":
    main()
