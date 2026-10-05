#!/usr/bin/env python3
"""Validate converged receipts, delegate field integration, and gate passivity.

The numerical integration and matrix gate remain in the hash-pinned oracle.
Symmetry follows the field inner product; this is not an independent reciprocity
measurement. Finite closure geometry remains in every matrix.
"""

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--mesh", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--port", nargs=2, action="append", required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    pins = json.loads((here / "../../round2/d17/upstream-inputs.json").read_text())
    prefix = "zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/scripts/"
    for name in ("inductance_matrix.py", "matrix_gate.py"):
        path = args.oracle / prefix / name
        if hashlib.sha256(path.read_bytes()).hexdigest() != pins[prefix + name]:
            raise ValueError(f"changed upstream tool: {name}")
    receipts = []
    command = [sys.executable, str(args.oracle / prefix / "inductance_matrix.py"), str(args.mesh)]
    for port, directory in args.port:
        path = Path(directory) / "result.json"
        result = json.loads(path.read_text())
        if not result.get("converged") or result.get("exit_code") != 0:
            raise ValueError(f"unconverged or failed result: {directory}")
        if result["last_residual"] > result["tol"]:
            raise ValueError(f"residual exceeds requested tolerance: {directory}")
        if result.get("scale_m") != 0.001:
            raise ValueError(f"mesh millimetres were not converted to metres: {directory}")
        receipts.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        command.extend(["--port", port, directory])
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode:
        print(completed.stdout, end="")
        raise SystemExit(completed.stderr)
    matrix = json.loads(next(line[7:] for line in completed.stdout.splitlines() if line.startswith("RESULT ")))
    spec = importlib.util.spec_from_file_location("pinned_matrix_gate", args.oracle / prefix / "matrix_gate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    matrix["minimum_eigenvalue_nH"] = module.check(matrix["L_nH"], str(args.mesh))
    matrix["converged_run_receipts"] = receipts
    matrix["classification"] = "simulated magnetostatic finite-closure matrix; no physical qualification"
    args.out.write_text(json.dumps(matrix, indent=2) + "\n")
    print(completed.stdout, end="")


if __name__ == "__main__":
    main()
