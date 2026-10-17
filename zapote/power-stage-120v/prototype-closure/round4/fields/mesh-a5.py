#!/usr/bin/env python3
"""Delegate the existing A5 bulk-port geometry using exact native19 C6 pads.

This is one local bulk mode, not the C5/full-board or cross-leg problem.
"""

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    baseline = here / "../../round2/d17"
    extraction = baseline / "evidence/extraction"
    manifest = json.loads((baseline / "upstream-inputs.json").read_text())
    relative = "zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/scripts/mesh25d_hybrid.py"
    upstream = args.oracle / relative
    if hashlib.sha256(upstream.read_bytes()).hexdigest() != manifest[relative]:
        raise ValueError("mesher hash mismatch")
    receipt = json.loads((extraction / "extraction.json").read_text())
    if receipt["board_sha256"] != "3557aa444873fa8b45eb7e0ae8ec3a4bc2b5cd526826b338b58d50e57747430b":
        raise ValueError("not native19")
    for name, expected in receipt["files"].items():
        if hashlib.sha256((extraction / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"extraction changed: {name}")
    pads = json.loads((extraction / "pads.json").read_text())
    if pads["C6.1"]["net"] != "bus_p" or pads["C6.3"]["net"] != "hv_ret":
        raise ValueError("C6 bulk-port net identity changed")
    closures = json.loads((extraction / "closures-legA.json").read_text())
    closures.append({"name": "P5_C6_bulk", "kind": "port", "level": 0,
                     "a": pads["C6.1"]["xy_mm"], "b": pads["C6.3"]["xy_mm"],
                     "native19_pads": ["C6.1", "C6.3"],
                     "native19_nets": ["bus_p", "hv_ret"]})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    closure_path = args.out.with_suffix(".closures.json")
    closure_path.write_text(json.dumps(closures, indent=2) + "\n")
    spec = importlib.util.spec_from_file_location("pinned_a5_mesher", upstream)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.LOOP_NETS["A5"] |= {"ocp_kelvin_p", "ocp_kelvin_n"}
    sys.argv = [str(upstream), str(extraction / "native19-all-copper.json.gz"),
                str(args.out), "--leg", "A5", "--closures", str(closure_path),
                "--margin", "20", "--arch-h", "1", "--h-edge", "4", "--dz-max", "1", "--h-far", "4"]
    module.main()


if __name__ == "__main__":
    main()
