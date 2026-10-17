#!/usr/bin/env python3
"""Rerunnable D7 source identities and SRF/ESL arithmetic; no vendor-fit claims."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import platform


def esl_nh(capacitance_nf: float, srf_mhz: float) -> float:
    if not all(math.isfinite(x) and x > 0 for x in (capacitance_nf, srf_mhz)):
        raise ValueError("capacitance and SRF must be finite and positive")
    return 1e6 / ((2 * math.pi * srf_mhz) ** 2 * capacitance_nf)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capacitance-nf", type=float)
    parser.add_argument("--srf-mhz", type=float)
    args = parser.parse_args()
    if (args.capacitance_nf is None) != (args.srf_mhz is None):
        parser.error("supply both --capacitance-nf and --srf-mhz")
    if args.srf_mhz is not None:
        print(json.dumps({"capacitance_nf": args.capacitance_nf,
                          "srf_mhz": args.srf_mhz,
                          "derived_esl_nh": esl_nh(args.capacitance_nf, args.srf_mhz)}, indent=2))
        return

    root = next(p for p in Path(__file__).resolve().parents if (p / "zapote/power-stage-120v/frozen/default.csv").is_file())
    base = root / "zapote/power-stage-120v"
    files = ["frozen/default.csv", "frozen/default.net", "native-17/section.kicad_pcb",
             "validation-results/01-switching-parasitics/round17/d2/leg_matrix5.cir"]
    hashes = {name: hashlib.sha256((base / name).read_bytes()).hexdigest() for name in files}
    with (base / files[0]).open(newline="") as handle:
        bom = list(csv.DictReader(handle))
    net = (base / files[1]).read_text()
    board = (base / files[2]).read_text()
    rows = []
    for part, capacitance in [("B32652A0104K000", 100.0), ("B32656G0275J000", 2700.0)]:
        entry, = [row for row in bom if row["Comment"] == part]
        refs = entry["Designator"].split(",")
        for ref in refs:
            # Restrict matches to a component/footprint block before matching its part.
            net_block, = [block for block in net.split('    (comp (ref ')[1:]
                          if block.startswith(f'"{ref}")')]
            if f'(part "{part}")' not in net_block:
                raise ValueError(f"netlist part mismatch: {ref}")
            board_block, = [block for block in board.split('\n\t(footprint ')[1:]
                            if f'(property "Reference" "{ref}"' in block]
            if f'(property "MPN" "{part}"' not in board_block:
                raise ValueError(f"board MPN mismatch: {ref}")
        rows.append({"part": part, "references": refs, "capacitance_nf": capacitance,
                     "illustrative_assumed_esl_nh": [5, 10, 20],
                     "implied_srf_mhz_NOT_measured": [
                         math.sqrt(1e6 / (capacitance * value)) / (2 * math.pi)
                         for value in (5, 10, 20)]})
    print(json.dumps({"evidence_class": "identity audit and assumed-sweep arithmetic; no measured/model ESL",
                      "source_revision": "f9b13b483d6d4ed52439d4da419c7670bab6966c",
                      "runtime": platform.python_version(), "sha256": hashes,
                      "parts": rows}, indent=2))


if __name__ == "__main__":
    main()
