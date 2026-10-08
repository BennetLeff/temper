#!/usr/bin/env python3
"""Rerun corrected-unit FastHenry wire and plane fixtures in this task's raw tree."""
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
BINARY_SHA = "79c7faac90f8aeb2ac5d805b66f2e4dd70baf3988af0fe3444e3d1fcf83184a4"
SOURCE_SHA = "94eb918fd62c4c6e5db022608282ac32ba495952744a8f12c1888d1a967f75e6"
PLANE_SHA = "9042d1fabdeb01aa9c7c5055d67b60969817264f46f22a627077052a60f9a5fa"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def impedance(path: Path) -> complex:
    match = re.search(r"^\s*([-+\d.eE]+)\s+([+-]\s*[-+\d.eE]+)j\s*$", path.read_text(), re.M)
    if not match:
        raise ValueError(f"unrecognized impedance matrix: {path}")
    return complex(float(match[1]), float(match[2].replace(" ", "")))


def solve(solver: Path, name: str, deck_text: str) -> dict:
    out = HERE / "extraction" / "fixtures" / name
    out.mkdir(parents=True, exist_ok=True)
    deck = out / "fixture.inp"
    deck.write_text(deck_text)
    with (out / "solver.log").open("w") as log:
        run = subprocess.run([str(solver), str(deck)], cwd=out, stdout=log,
                             stderr=subprocess.STDOUT, timeout=120, check=False)
    result = {"deck_sha256": sha(deck), "exit_code": run.returncode,
              "log_sha256": sha(out / "solver.log")}
    if run.returncode != 0:
        raise RuntimeError(f"{name}: solver exited {run.returncode}")
    z = impedance(out / "Zc.mat")
    result.update(R_ohm=z.real, X_ohm=z.imag, z_sha256=sha(out / "Zc.mat"))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver", required=True, type=Path)
    args = parser.parse_args()
    solver = args.solver.resolve(strict=True)
    source = solver.parent.parent
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if (commit != SOURCE_COMMIT or sha(solver) != BINARY_SHA
            or sha(source / "src/fasthenry/induct.c") != SOURCE_SHA):
        raise ValueError("FastHenry source or binary differs from pinned tool")
    plane = UNIT / "validation-results/round3-coordination/decision-review/fieldsolver/plane_pair_80/plane_pair_80.inp"
    if sha(plane) != PLANE_SHA:
        raise ValueError("plane fixture source differs from pinned input")
    report = {"solver_commit": commit, "solver_sha256": sha(solver),
              "source_induct_c_sha256": SOURCE_SHA, "source_plane_sha256": sha(plane),
              "sigma_S_per_m": 5.8e7, "sigma_input_S_per_mm": 5.8e4, "runs": {}}
    wire = "\n".join(("* 50 mm x 1 mm x 1 mm wire", ".units mm", ".default sigma=5.8e4",
                     "n1 x=0 y=0 z=0", "n2 x=50 y=0 z=0",
                     "e1 n1 n2 w=1 h=1 nwinc=4 nhinc=4", ".external n1 n2",
                     ".freq fmin=1 fmax=1 ndec=1", ".end", ""))
    report["runs"]["wire"] = solve(solver, "wire", wire)
    expected_r = 0.05 / (5.8e7 * 0.001**2)
    report["wire_analytic_R_ohm"] = expected_r
    report["wire_R_error_percent"] = 100 * (report["runs"]["wire"]["R_ohm"] / expected_r - 1)
    raw = plane.read_text()
    if raw.count("sigma=5.8e7") != 1 or raw.count("seg1=80 seg2=40") != 2:
        raise ValueError("plane source format changed")
    for n in (20, 40, 80):
        deck = raw.replace("sigma=5.8e7", "sigma=5.8e4").replace("seg1=80 seg2=40", f"seg1={n} seg2={n//2}")
        row = solve(solver, f"plane_{n}", deck)
        row["L_nH"] = 1e9 * row["X_ohm"] / (2 * math.pi * 1e7)
        report["runs"][f"plane_{n}"] = row
    fine = report["runs"]["plane_80"]
    medium = report["runs"]["plane_40"]
    dc_floor = 2 * 0.05 / (5.8e7 * 0.01 * 0.000061)
    report["plane_dc_R_floor_ohm"] = dc_floor
    report["plane_40_to_80_L_change_percent"] = 100 * (fine["L_nH"] / medium["L_nH"] - 1)
    report["status"] = ("PASS_DIMENSIONAL_SANITY" if abs(report["wire_R_error_percent"]) < 1
                        and fine["R_ohm"] >= dc_floor
                        and abs(report["plane_40_to_80_L_change_percent"]) < 5 else "FAIL")
    (HERE / "fixture-results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if report["status"] != "PASS_DIMENSIONAL_SANITY":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
