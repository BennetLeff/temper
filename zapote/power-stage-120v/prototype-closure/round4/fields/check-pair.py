#!/usr/bin/env python3
"""Delegate the pinned upstream independent pair-energy verifier only.

The upstream shell also launches and removes runs; those actions are not used.
Its embedded verifier is invoked unchanged, after extra receipt/unit checks.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--tag", required=True, help="mesh stem; .matrix.txt must contain its RESULT")
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--ports", type=int, nargs=2, required=True)
    args = parser.parse_args()
    path = args.oracle / "zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/scripts/pair_check.sh"
    source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != "c978c2a7a273609efc40973eed1db97dde7d6b32aa553f7ab9c3ca87dae749f9":
        raise ValueError("pair verifier source changed")
    record = json.loads((args.run / "result.json").read_text())
    if record.get("scale_m") != 0.001 or not record.get("converged") or record.get("exit_code") != 0:
        raise ValueError("failed, unconverged or wrong-unit pair solve")
    if hashlib.sha256((args.run / "case.sif").read_bytes()).hexdigest() != record["sif_sha256"]:
        raise ValueError("pair SIF differs from solved receipt")
    marker = "<<'PY' || FAILED=1\n"
    if source.decode().count(marker) != 1:
        raise ValueError("pair verifier extraction is ambiguous")
    verifier = source.decode().split(marker)[1].split("\nPY\n")[0]
    subprocess.run([sys.executable, "-c", verifier, args.tag, *map(str, args.ports), str(args.run), "0"], check=True)


if __name__ == "__main__":
    main()
