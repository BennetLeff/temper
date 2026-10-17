#!/usr/bin/env python3
"""Solve one magnetostatic fixture with Elmer and report L (direct or iterative).

    python3 run_elmer_fixture.py MESH.msh WORKDIR --pec 2 --port 4 --k 0 0 100 [--label NAME]

MESH is gmsh MSH 2.2 ASCII in mm with physical groups: 1 air (volume),
PEC surface group(s), and the port. Groups not named get Elmer's natural
condition. The port is a surface-current load K (A/m), applied the way the
round-7/8 plate fixtures did (Elmer's WhitneyAVSolver load vector), so a
1 A port of width w needs |K| = 1/w. L = 2E/I^2 with I = 1 A.
Records ElmerSolver's exit code, the energy line, and /usr/bin/time -l
peak memory.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ELMER = Path("/tmp/ps-r6-fem-elmer-install")

SIF = """! Round-10 magnetostatic fixture, 1 A port. Coordinates in metres after ElmerGrid -scale; L = 2E/I^2 with 1 A per driven port.
Header
  CHECK KEYWORDS Warn
  Mesh DB "." "mesh"
  Results Directory "mesh"
End
Simulation
  Coordinate System = Cartesian 3D
  Simulation Type = Steady
  Steady State Max Iterations = 1
  Max Output Level = 5
End
Constants
  Permeability of Vacuum = 1.2566370614359173e-6
End
Body 1
  Target Bodies(1) = 1
  Equation = 1
  Material = 1
End
Material 1
  Relative Permeability = 1.0
  Relative Permittivity = 1.0
  Electric Conductivity = 0.0
End
Equation 1
  Active Solvers(2) = 1 2
End
Solver 1
  Equation = "MGDynamics"
  Variable = "AV"
  Procedure = "MagnetoDynamics" "WhitneyAVSolver"
  Edge Basis = Logical True
{linear}
End
Solver 2
  Equation = "MGDynamicsCalc"
  Procedure = "MagnetoDynamics" "MagnetoDynamicsCalcFields"
  Potential Variable = String "AV"
  Calculate Magnetic Field Strength = Logical True
  Calculate Elemental Fields = Logical True
  Separate Magnetic Energy = Logical True
  Linear System Solver = Iterative
  Linear System Iterative Method = CG
  Linear System Preconditioning = ILU0
  Linear System Max Iterations = 2000
  Linear System Convergence Tolerance = 1e-9
End
Boundary Condition 1
  Target Boundaries({npec}) = {pec}
  AV {{e}} = Real 0.0
End
Boundary Condition 2
  Target Boundaries(1) = {port}
  Magnetic Field Strength 1 = Real {k0}
  Magnetic Field Strength 2 = Real {k1}
  Magnetic Field Strength 3 = Real {k2}
End
{extra}"""
PORT2 = """Boundary Condition 3
  Target Boundaries(1) = {port}
  Magnetic Field Strength 1 = Real {k0}
  Magnetic Field Strength 2 = Real {k1}
  Magnetic Field Strength 3 = Real {k2}
End
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mesh")
    ap.add_argument("work")
    ap.add_argument("--pec", type=int, nargs="+", required=True)
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--k", type=float, nargs=3, required=True)
    ap.add_argument("--port2", type=int, default=None, help="second port driven at the same time (for mutuals)")
    ap.add_argument("--k2", type=float, nargs=3, default=None)
    ap.add_argument("--scale", type=float, default=0.001, help="mesh unit in metres (0.001 for mm)")
    ap.add_argument("--iterative", default=None, help="Elmer iterative method (BiCGStabl, GCR, BiCGStab, CG, Idrs); default direct")
    ap.add_argument("--precond", default="ILU1")
    ap.add_argument("--tol", type=float, default=1e-10)
    ap.add_argument("--maxit", type=int, default=5000)
    ap.add_argument("--label", default=None)
    a = ap.parse_args()
    work = Path(a.work)
    work.mkdir(parents=True, exist_ok=False)
    grid = subprocess.run([str(ELMER / "bin/ElmerGrid"), "14", "2", str(Path(a.mesh).resolve()),
                           "-out", "mesh", "-scale", str(a.scale), str(a.scale), str(a.scale)],
                          cwd=work, capture_output=True, text=True)
    (work / "elmergrid.log").write_text(grid.stdout + grid.stderr)
    if grid.returncode:
        raise SystemExit(f"ElmerGrid failed: {grid.returncode}")
    if a.iterative:
        linear = "\n".join([
            '  Linear System Solver = Iterative',
            f'  Linear System Iterative Method = {a.iterative}',
            f'  Linear System Preconditioning = {a.precond}',
            f'  Linear System Convergence Tolerance = {a.tol}',
            f'  Linear System Max Iterations = {a.maxit}',
            '  Linear System Residual Output = 10',
            '  Linear System Abort Not Converged = True',
            '  Linear System GCR Restart = 100',
            '  BiCGStabl Polynomial Degree = 4',
            '  Use Tree Gauge = False'])
    else:
        linear = "  Linear System Solver = Direct\n  Linear System Direct Method = Big Umfpack"
    (work / "case.sif").write_text(SIF.format(linear=linear, npec=len(a.pec), pec=" ".join(map(str, a.pec)),
                                              port=a.port, k0=a.k[0], k1=a.k[1], k2=a.k[2],
                                              extra=PORT2.format(port=a.port2, k0=a.k2[0], k1=a.k2[1], k2=a.k2[2])
                                              if a.port2 else ""))
    cmd = (f"ulimit -Ss 65520; /usr/bin/time -l env ELMER_HOME={ELMER} OPENBLAS_NUM_THREADS=1 "
           f"OMP_NUM_THREADS=1 {ELMER}/bin/ElmerSolver case.sif > solver.log 2> time.log")
    rc = subprocess.run(["/bin/zsh", "-c", cmd], cwd=work).returncode
    log = (work / "solver.log").read_text(errors="replace")
    tlog = (work / "time.log").read_text(errors="replace")
    m = re.search(r"Magnetic Field Energy:\s+([0-9.E+-]+)", log)
    energy = float(m[1]) if m else None
    peak = re.search(r"(\d+)\s+peak memory footprint", tlog)
    rss = re.search(r"(\d+)\s+maximum resident set size", tlog)
    wall = re.search(r"([\d.]+) real", tlog)
    # Last residual line of the AV solve ("iter  residual  ..."), when iterative.
    its = re.findall(r"^\s+(\d+)\s+([0-9.]+E[+-]\d+)\s+[0-9.]+E[+-]\d+\s*$", log, re.M)
    result = {"label": a.label or Path(a.mesh).stem, "mesh": str(a.mesh), "exit_code": rc,
              "all_done": "ALL DONE" in log, "energy_J": energy,
              "inductance_nH": 2 * energy * 1e9 if energy is not None else None,
              "peak_memory_GB": int(peak[1]) / 1e9 if peak else None,
              "max_rss_GB": int(rss[1]) / 1e9 if rss else None,
              "wall_s": float(wall[1]) if wall else None,
              "solver": ("iterative " + a.iterative + " + " + a.precond) if a.iterative else "direct Big Umfpack",
              "tol": a.tol if a.iterative else None,
              "last_iteration": int(its[-1][0]) if its else None,
              "last_residual": float(its[-1][1]) if its else None,
              # Iterative: Elmer aborts (nonzero exit) unless the solve reaches the
              # tolerance (Abort Not Converged = True; negative control in round 12).
              # Residuals print every 10 iterations, so the last printed one is
              # allowed up to 10x the tolerance.
              "converged": (rc == 0 and "ALL DONE" in log and bool(its) and float(its[-1][1]) <= 10 * a.tol)
              if a.iterative else (rc == 0 and "ALL DONE" in log),
              "k_A_per_m": a.k, "pec": a.pec, "port": a.port,
              "port2": a.port2, "k2_A_per_m": a.k2, "scale_m": a.scale}
    (work / "result.json").write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
