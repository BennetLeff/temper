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
import sys
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
  Max Output Level = {outlevel}
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
{calc_extra}  Linear System Solver = Iterative
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
{extra}{vtu}"""
VTU = """Solver 3
  Exec Solver = After Saving
  Equation = "ResultOutput"
  Procedure = "ResultOutputSolve" "ResultOutputSolver"
  Output File Name = "case"
  Vtu Format = Logical True
  Discontinuous Galerkin = Logical True
  Save Bulk Only = Logical True
  Scalar Field 1 = String "none"
  Vector Field 1 = String "magnetic flux density e"
  Save Geometry Ids = Logical True
End
"""
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
    ap.add_argument("--elmer", default=str(ELMER), help="Elmer install prefix")
    ap.add_argument("--hypre-ams", action="store_true", help="Hypre BiCGStab + AMS (edge-element AMG), as Elmer's mgdyn_hypre_ams test")
    ap.add_argument("--hypre-method", type=int, default=7, help="Hypre Krylov index: 6 PCG, 7 BiCGStab, 8 GMRES")
    ap.add_argument("--ams-singular", action="store_true", help="AMS Singular Matrix (zero conductivity everywhere)")
    ap.add_argument("--solver-line", action="append", default=[],
                    help="extra line for the AV solver section, e.g. 'AMS Cycle Type = Integer 13' (repeatable)")
    ap.add_argument("--vtu", action="store_true",
                    help="write the elemental vector potential (Magnetic Vector Potential E) to VTU, for mutuals by reciprocity")
    ap.add_argument("--np", type=int, default=1, help="MPI ranks (ElmerGrid METIS partition + ElmerSolver_mpi)")
    ap.add_argument("--tree-gauge", action="store_true", help="iterative solve with Elmer's tree gauge (removes the gradient null space)")
    a = ap.parse_args()
    elmer = Path(a.elmer)
    work = Path(a.work)
    work.mkdir(parents=True, exist_ok=False)
    part = ["-partdual", "-metiskway", str(a.np)] if a.np > 1 else []
    grid = subprocess.run([str(elmer / "bin/ElmerGrid"), "14", "2", str(Path(a.mesh).resolve()),
                           "-out", "mesh", "-scale", str(a.scale), str(a.scale), str(a.scale)] + part,
                          cwd=work, capture_output=True, text=True)
    (work / "elmergrid.log").write_text(grid.stdout + grid.stderr)
    if grid.returncode:
        raise SystemExit(f"ElmerGrid failed: {grid.returncode}")
    if a.hypre_ams:
        linear = "\n".join([
            '  Linear System Solver = Iterative',
            '  Linear System Use Hypre = Logical True',
            '  Linear System Preconditioning = ams',
            f'  Linear System Method Hypre Index = Integer {a.hypre_method}',
            f'  AMS Singular Matrix = Logical {a.ams_singular}',
            '  Linear System Symmetric = True',
            '  Edge Basis = Logical True',
            f'  Linear System Convergence Tolerance = {a.tol}',
            f'  Linear System Max Iterations = {a.maxit}',
            '  Linear System Residual Output = 10',
            '  Linear System Abort Not Converged = True',
            '  Use Tree Gauge = False'] + ['  ' + l_ for l_ in a.solver_line])
        a.iterative = {6: "Hypre PCG", 7: "Hypre BiCGStab", 8: "Hypre GMRES(100)"}[a.hypre_method]
        a.precond = "AMS"
    elif a.iterative:
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
            '  Use Tree Gauge = ' + ('True' if a.tree_gauge else 'False')])
    else:
        linear = "  Linear System Solver = Direct\n  Linear System Direct Method = Big Umfpack"
    # Hypre reports its own convergence only at output level >= 10 (per-iteration print)
    (work / "case.sif").write_text(SIF.format(outlevel=10 if a.hypre_ams else 5, linear=linear, npec=len(a.pec), pec=" ".join(map(str, a.pec)),
                                              port=a.port, k0=a.k[0], k1=a.k[1], k2=a.k[2],
                                              extra=PORT2.format(port=a.port2, k0=a.k2[0], k1=a.k2[1], k2=a.k2[2])
                                              if a.port2 else "",
                                              calc_extra="  Calculate Magnetic Vector Potential = Logical True\n" if a.vtu else "",
                                              vtu=VTU if a.vtu else ""))
    linux = sys.platform.startswith("linux")
    solver = (f"mpirun -np {a.np} {elmer}/bin/ElmerSolver_mpi" if a.np > 1 else f"{elmer}/bin/ElmerSolver")
    if a.np > 1:
        (work / "ELMERSOLVER_STARTINFO").write_text("case.sif\n")
    cmd = (f"ulimit -Ss 65520; /usr/bin/time {'-v' if linux else '-l'} env ELMER_HOME={elmer} OPENBLAS_NUM_THREADS=1 "
           f"OMP_NUM_THREADS=1 {solver}{'' if a.np > 1 else ' case.sif'} > solver.log 2> time.log")
    rc = subprocess.run(["/bin/bash" if linux else "/bin/zsh", "-c", cmd], cwd=work).returncode
    log = (work / "solver.log").read_text(errors="replace")
    tlog = (work / "time.log").read_text(errors="replace")
    m = re.search(r"Magnetic Field Energy:\s+(\S+)", log)
    # Fortran drops the E for 3-digit exponents ("1.128281+206"); a diverged
    # solve shows up that way, so parse it rather than crash.
    energy = float(re.sub(r"(?<=\d)([+-]\d{3})$", r"E\1", m[1])) if m else None
    if linux:                    # GNU time -v: kbytes (largest single process under mpirun), h:mm:ss
        k = re.search(r"Maximum resident set size \(kbytes\): (\d+)", tlog)
        peak_b = rss_b = int(k[1]) * 1000 if k else None
        w = re.search(r"Elapsed \(wall clock\) time.*: (?:(\d+):)?(\d+):([\d.]+)", tlog)
        wall_s = int(w[1] or 0) * 3600 + int(w[2]) * 60 + float(w[3]) if w else None
    else:                        # BSD time -l: bytes
        k = re.search(r"(\d+)\s+peak memory footprint", tlog)
        peak_b = int(k[1]) if k else None
        k = re.search(r"(\d+)\s+maximum resident set size", tlog)
        rss_b = int(k[1]) if k else None
        w = re.search(r"([\d.]+) real", tlog)
        wall_s = float(w[1]) if w else None
    # Last residual line of the AV solve ("iter  residual  ..."), when iterative.
    its = re.findall(r"^\s+(\d+)\s+([0-9.]+E[+-]\d+)\s+[0-9.]+E[+-]\d+\s*$", log, re.M)
    if a.hypre_ams:
        # Elmer ignores Abort Not Converged on the Hypre path, and the residual
        # lines in the log belong to the field-calculation CG solve, so gate on
        # Hypre's own summary of the AV solve.
        its = re.findall(r"SolveHypre: Required iterations (\d+) \(method \d+\) to norm (\S+)", log)
    result = {"label": a.label or Path(a.mesh).stem, "mesh": str(a.mesh), "exit_code": rc,
              "all_done": "ALL DONE" in log, "energy_J": energy,
              "inductance_nH": 2 * energy * 1e9 if energy is not None else None,
              "peak_memory_GB": peak_b / 1e9 if peak_b else None,
              "max_rss_GB": rss_b / 1e9 if rss_b else None,
              "wall_s": wall_s, "np": a.np,
              "solver": ("iterative " + a.iterative + " + " + a.precond) if a.iterative else "direct Big Umfpack",
              "tol": a.tol if a.iterative else None,
              "solver_lines": a.solver_line,
              "tree_gauge": bool(a.tree_gauge) if a.iterative else True,
              "last_iteration": int(its[-1][0]) if its else None,
              "last_residual": float(its[-1][1]) if its else None,
              # Iterative: Elmer aborts (nonzero exit) unless the solve reaches the
              # tolerance (Abort Not Converged = True; negative control in round 12).
              # Residuals print every 10 iterations, so the last printed one is
              # allowed up to 10x the tolerance.
              "converged": (rc == 0 and "ALL DONE" in log and bool(its) and energy is not None
                            and 0 < energy < 1.0 and
                            ((int(its[-1][0]) < a.maxit and float(its[-1][1]) <= a.tol) if a.hypre_ams
                             else float(its[-1][1]) <= 10 * a.tol))
              if a.iterative else (rc == 0 and "ALL DONE" in log),
              "k_A_per_m": a.k, "pec": a.pec, "port": a.port,
              "port2": a.port2, "k2_A_per_m": a.k2, "scale_m": a.scale}
    (work / "result.json").write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
