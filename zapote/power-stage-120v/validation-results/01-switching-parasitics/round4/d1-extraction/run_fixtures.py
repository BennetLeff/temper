#!/usr/bin/env python3
"""Rerun HISTORICAL, PHYSICALLY UNQUALIFIED FastHenry fixtures.

These input decks use a conductivity 1000 times too high with ``.units mm``.
Equality to their pinned impedance values is only an executable regression.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[3]
SOURCE_COMMIT = "363e43ed57ad3b9affa11cba5a86624fad0edaa9"
SOURCE_SHA = "94eb918fd62c4c6e5db022608282ac32ba495952744a8f12c1888d1a967f75e6"
BOARD_SHA = "a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155"
NAMES = ("straight_wire_4", "straight_wire_8", "plane_pair_20", "plane_pair_40", "plane_pair_80")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_z(path: Path) -> tuple[float, float]:
    match = re.search(r"^\s*([-+\d.eE]+)\s+([+-]\s*[-+\d.eE]+)j\s*$", path.read_text(), re.M)
    if not match:
        raise ValueError(f"unrecognized FastHenry Zc.mat: {path}")
    return float(match[1]), float(match[2].replace(" ", ""))


def historical_z(value: str) -> tuple[float, float]:
    match = re.search(r"^\s*([-+\d.eE]+)\s+([+-]\s*[-+\d.eE]+)j\s*$", value, re.M)
    if not match:
        raise ValueError("unrecognized pinned FastHenry fixture matrix")
    return float(match[1]), float(match[2].replace(" ", ""))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver", type=Path, required=True)
    args = parser.parse_args()
    solver = args.solver.resolve(strict=True)
    source = solver.parent.parent
    got_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    if got_commit != SOURCE_COMMIT or digest(source / "src/fasthenry/induct.c") != SOURCE_SHA:
        raise ValueError("FastHenry source identity differs from the pinned official revision")
    board = UNIT / "native-15/section.kicad_pcb"
    if digest(board) != BOARD_SHA:
        raise ValueError("native-15 board differs from the frozen D1 board")
    fixtures = UNIT / "validation-results/01-switching-parasitics/round3/a2-inductance/fixtures"
    history = UNIT / "validation-results/round3-coordination/decision-review/fieldsolver"
    old = json.loads((history / "fixture-results.json").read_text())
    report: dict[str, object] = {"status": "HISTORICAL_UNQUALIFIED_REGRESSION_ONLY",
                                 "reason": "legacy .units mm sigma=5.8e7 is 1000x physical copper conductivity",
                                 "solver_source_commit": got_commit,
                                 "source_induct_c_sha256": SOURCE_SHA,
                                 "solver_binary_sha256": digest(solver),
                                 "board_sha256": BOARD_SHA,
                                 "frequency_hz": 10_000_000,
                                 "fixtures": {}}
    for name in NAMES:
        src = (history / name / f"{name}.inp") if name == "plane_pair_80" else (fixtures / f"{name}.inp")
        directory = HERE / "extraction/fixtures" / name
        directory.mkdir(parents=True, exist_ok=True)
        deck = directory / src.name
        deck.write_bytes(src.read_bytes())
        result = subprocess.run([str(solver), str(deck)], cwd=directory,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=60, check=False)
        (directory / "solver.log").write_text(result.stdout)
        if result.returncode != 0:
            raise RuntimeError(f"FastHenry {name} exited {result.returncode}")
        measured = read_z(directory / "Zc.mat")
        pinned = read_z(history / name / "Zc.mat") if name == "plane_pair_80" else historical_z(old[name]["z"])
        deltas = [abs(a - b) / abs(b) * 100 for a, b in zip(measured, pinned, strict=False)]
        if any(delta > 0.1 for delta in deltas):
            raise RuntimeError(f"{name} differs from pinned values by {deltas} %")
        report["fixtures"][name] = {"input_sha256": digest(src),
                                    "R_ohm": measured[0], "X_ohm": measured[1],
                                    "L_nH": measured[1] / (2 * math.pi * 10_000_000) * 1e9,
                                    "R_delta_percent": deltas[0], "X_delta_percent": deltas[1],
                                    "status": "HISTORICAL_MATCH_WITHIN_0.1_PERCENT_NOT_PHYSICS"}
    (HERE / "extraction/fixture-rerun.json").write_text(json.dumps(report, indent=2) + "\n")
    print("HISTORICAL/UNQUALIFIED FIXTURE REGRESSION: 5/5 within 0.1%; wrong conductivity units")


if __name__ == "__main__":
    main()
