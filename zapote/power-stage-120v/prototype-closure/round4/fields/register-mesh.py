#!/usr/bin/env python3
"""Run pinned topology instruments and reject their numeric failures.

Their process exit status alone is not an acceptance criterion. This wrapper
does not implement geometry; it validates existing instruments' results.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def result(path: Path):
    rows = [line[7:] for line in path.read_text().splitlines() if line.startswith("RESULT ")]
    if len(rows) != 1:
        raise ValueError(f"expected one RESULT in {path}")
    return json.loads(rows[0])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--mesh", type=Path, required=True)
    parser.add_argument("--closures", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    pins = json.loads((here / "../../round2/d17/upstream-inputs.json").read_text())
    prefix = "zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/scripts/"
    reader = args.oracle / prefix / "check_ports.py"
    if hashlib.sha256(reader.read_bytes()).hexdigest() != pins[prefix + "check_ports.py"]:
        raise ValueError("mesh reader dependency changed")
    mesh_result = result(args.mesh.with_suffix(".log"))
    if mesh_result["zero_volume_tets"] or mesh_result["skipped_area_mm2"]:
        raise ValueError("degenerate or omitted mesh geometry")
    if any(p["leak_A"] != 0 for p in mesh_result["port_leak_A"]):
        raise ValueError("mesher reports a leaky current port")
    gates = {}
    for name in ("pec_columns", "port_divergence", "port_loops"):
        path = args.oracle / prefix / f"{name}.py"
        if hashlib.sha256(path.read_bytes()).hexdigest() != pins[prefix + f"{name}.py"]:
            raise ValueError(f"changed upstream tool: {name}")
        command = [sys.executable, str(path), str(args.mesh)]
        if name != "pec_columns":
            command.append(str(args.mesh.with_suffix(".log")))
        if name == "port_loops":
            command += ["--closures", str(args.closures)]
        log = args.mesh.with_name(args.mesh.stem + f"-{name}.log")
        with log.open("w") as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True)
        gates[name] = result(log)
    if gates["pec_columns"]["inner_farfield_triangles"]:
        raise ValueError("spurious grounded column")
    expected_ports = {port["name"] for port in mesh_result["ports"]}
    if len(expected_ports) not in (4, 5) or any(
        len(rows) != len(expected_ports) or {port["port"] for port in rows} != expected_ports
        for rows in (gates["port_divergence"], gates["port_loops"]["ports"])
    ):
        raise ValueError("missing, unexpected or duplicate port identities")
    expected_closures = {closure["name"] for closure in json.loads(args.closures.read_text())}
    if len(gates["port_loops"]["closure_ends"]) != len(expected_closures) or {
        closure["closure"] for closure in gates["port_loops"]["closure_ends"]
    } != expected_closures:
        raise ValueError("closure census differs from input")
    for port in gates["port_divergence"]:
        if abs(port["port_current_A"] - 1) > 1e-10 or any(
            abs(port[key]) > 1e-10 for key in ("leak_sum_abs_A", "leak_max_A", "pec_net_A")
        ):
            raise ValueError("port current is not a closed 1 A excitation")
    for port in gates["port_loops"]["ports"]:
        if not port["closed_loop"] or any(c["farfield"] for c in port["components"]):
            raise ValueError("open or farfield-grounded current loop")
    for closure in gates["port_loops"]["closure_ends"]:
        if len(closure["a_body"]) != 1 or closure["a_body"] != closure["b_body"]:
            raise ValueError("closure does not terminate on a single connected PEC body")
    receipt = {"name": args.mesh.stem, "mesh": mesh_result,
               "mesh_sha256": hashlib.sha256(args.mesh.read_bytes()).hexdigest(), **gates}
    args.out.write_text(json.dumps({"meshes": [receipt]}, indent=2) + "\n")


if __name__ == "__main__":
    main()
