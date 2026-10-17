#!/usr/bin/env python3
"""Test whether tiling uniform FastHenry G elements preserves one holed plane."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from run_fixtures import read_z

HERE = Path(__file__).resolve().parent


def run(solver: Path, label: str, deck: str) -> tuple[float, float]:
    directory = HERE / "extraction/seam-prototype" / label
    directory.mkdir(parents=True, exist_ok=True)
    input_file = directory / "model.inp"
    input_file.write_text(deck)
    result = subprocess.run([str(solver), str(input_file)], cwd=directory,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, timeout=60, check=False)
    (directory / "solver.log").write_text(result.stdout)
    if result.returncode:
        raise RuntimeError(f"FastHenry {label} exited {result.returncode}")
    return read_z(directory / "Zc.mat")


def common() -> str:
    return "* Synthetic 10 x 10 mm holed 61 um copper plane; NOT board geometry\n.units mm\n.default sigma=5.8e4\n"


def full() -> str:
    return common() + """gfull x1=0 y1=0 z1=0 x2=10 y2=0 z2=0 x3=10 y3=10 z3=0
+ thick=0.061 seg1=20 seg2=20
+ nin (0,5,0) nout (10,5,0)
+ hole rect (4,4,0,6,6,0)
.external nin nout
.freq fmin=1e7 fmax=1e7 ndec=1
.end
"""


def split(*, mixed_pitch: bool = False) -> str:
    lines = [common(), "gl x1=0 y1=0 z1=0 x2=5 y2=0 z2=0 x3=5 y3=10 z3=0",
             "+ thick=0.061 seg1=10 seg2=20", "+ nin (0,5,0)",
             "+ hole rect (4,4,0,5,6,0)"]
    for idx in range(21):
        y = idx / 2
        if y < 4 or y > 6:
            lines.append(f"+ nl{idx} (5,{y},0)")
    lines.extend(["gr x1=5 y1=0 z1=0 x2=10 y2=0 z2=0 x3=10 y3=10 z3=0",
                  f"+ thick=0.061 seg1=10 seg2={10 if mixed_pitch else 20}", "+ nout (10,5,0)",
                  "+ hole rect (5,4,0,6,6,0)"])
    for idx in range(21):
        y = idx / 2
        if (y < 4 or y > 6) and (not mixed_pitch or idx % 2 == 0):
            lines.append(f"+ nr{idx} (5,{y},0)")
    for idx in range(21):
        y = idx / 2
        if (y < 4 or y > 6) and (not mixed_pitch or idx % 2 == 0):
            lines.append(f".equiv nl{idx} nr{idx}")
    lines.extend([".external nin nout", ".freq fmin=1e7 fmax=1e7 ndec=1", ".end"])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver", required=True, type=Path)
    args = parser.parse_args()
    solver = args.solver.resolve(strict=True)
    a = run(solver, "full", full())
    b = run(solver, "split", split())
    c = run(solver, "split_mixed", split(mixed_pitch=True))
    delta = [abs(x-y)/abs(x)*100 for x,y in zip(a,b, strict=False)]
    mixed_delta = [abs(x-y)/abs(x)*100 for x,y in zip(a,c, strict=False)]
    report = {"scope": "synthetic uniform G seam plus one rectangular hole; no native board extraction",
              "frequency_hz": 10_000_000, "full_R_X_ohm": a,
              "split_R_X_ohm": b, "split_delta_percent_R_X": delta,
              "mixed_pitch_R_X_ohm": c, "mixed_pitch_delta_percent_R_X": mixed_delta,
              "mixed_pitch_method": "right 0.5mm x/1mm y, left 0.5mm x/y; only coincident integer-mm seam nodes are .equiv",
              "seam_method": "two non-overlapping 5x10mm G patches; 0.5mm aligned grids; matching surviving seam nodes paired with .equiv",
              "does_not_test": ["irregular native-15 filled polygon contours", "via or through-hole barrel contacts", "complex native seam and antipads", "coupled 12-port matrix"]}
    dest = HERE / "extraction/seam-prototype/result.json"
    dest.write_text(json.dumps(report, indent=2) + "\n")
    print(f"SEAM PROTOTYPE: aligned X delta {delta[1]:.3f}%; mixed-pitch X delta {mixed_delta[1]:.3f}%")


if __name__ == "__main__":
    main()
