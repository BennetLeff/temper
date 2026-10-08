#!/usr/bin/env python3
"""Run the pinned mesher on native19 export and actual pad closures.

Adds both floating Kelvin nets to the copper census, without shorting them.
Four ports do not characterize reference-current or common-mode impedance.
"""

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1] / "round2/d17"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--oracle", type=Path, required=True)
    ap.add_argument("--extraction", type=Path, required=True)
    ap.add_argument("--leg", choices=("A", "B"), required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--edge", type=float, default=1.0)
    ap.add_argument("--height", type=float, default=1.0)
    ap.add_argument("--dz", type=float, default=1.0)
    ap.add_argument("--far", type=float, default=6.0)
    ap.add_argument("--margin", type=float, default=20.0)
    ap.add_argument("--air", type=float, default=10.0)
    a = ap.parse_args()
    manifest = json.loads((BASE / "upstream-inputs.json").read_text())
    rel = "zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/scripts/mesh25d_hybrid.py"
    path = a.oracle / rel
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest[rel]:
        raise ValueError("mesher hash mismatch")
    receipt = json.loads((a.extraction / "extraction.json").read_text())
    if (
        receipt["board_sha256"]
        != "3557aa444873fa8b45eb7e0ae8ec3a4bc2b5cd526826b338b58d50e57747430b"
    ):
        raise ValueError("extraction is not the reviewed native19 board")
    if receipt["adapter_sha256"] != hashlib.sha256((BASE / "extract.py").read_bytes()).hexdigest():
        raise ValueError("extraction adapter changed; regenerate inputs")
    for name, expected in receipt["files"].items():
        if hashlib.sha256((a.extraction / name).read_bytes()).hexdigest() != expected:
            raise ValueError("extraction input changed: " + name)
    spec = importlib.util.spec_from_file_location("audited_mesher", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.LOOP_NETS[a.leg] |= {"ocp_kelvin_p", "ocp_kelvin_n"}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    sys.argv = [
        str(path),
        str(a.extraction / "native19-all-copper.json.gz"),
        str(a.out),
        "--leg",
        a.leg,
        "--closures",
        str(a.extraction / f"closures-leg{a.leg}.json"),
        "--margin",
        str(a.margin),
        "--arch-h",
        str(a.height),
        "--h-edge",
        str(a.edge),
        "--dz-max",
        str(a.dz),
        "--h-far",
        str(a.far),
        "--air",
        str(a.air),
    ]
    mod.main()


if __name__ == "__main__":
    main()
