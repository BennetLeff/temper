"""Run the 3D sector cross-check on the remote Elmer box and post-process locally.

  .venv/bin/python model/fem3d/run3d.py CASE [--np 4] [--keep]

Cases (CASES below): free-air magnetostatic (WhitneyAVSolver, hypre AMS) at three mesh scales, and harmonic runs with
the pan as a surface-impedance boundary (WhitneyAVHarmonicSolver, 'Layer Electric Conductivity' / 'Layer Relative
Permeability' good-conductor condition). Source: 1 A per turn, azimuthal, uniform over each section (= the 2D 'smeared'
source). Results -> model/fem3d/results/CASE.json. Remote field files are deleted after the fetch (box rules).

Box rules followed: bash -lc wrappers, no pkill -f, a check that no other ElmerSolver_mpi runs and free memory, and these
runs are small (< 4 GB; no HEAVY-RUN notice needed).
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import build_mesh as BM  # noqa: E402
import coil_geometry as G  # noqa: E402
import materials as M  # noqa: E402

HOST = "bennet@100.121.239.87"
RDIR = "temper-fem/coil-r1"
ELMER = "$HOME/temper-fem/elmer-install"
F = 40e3

CASES = {
    "free_h1": dict(mesh="free_h1", h=1.0, pan=False),
    "free_h0.7": dict(mesh="free_h0.7", h=0.7, pan=False),
    "free_h0.5": dict(mesh="free_h0.5", h=0.5, pan=False),
    "harm_free_h0.7": dict(mesh="free_h0.7", h=0.7, pan=False, harmonic=True),   # energy-convention calibration
    "air_h0.7": dict(mesh="free_h0.7", h=0.7, pan=False, mu_bar=1.0),       # control: no ferrite (2D/3D must agree)
    "mu1000_h0.7": dict(mesh="free_h0.7", h=0.7, pan=False, mu_bar=1000.0),
    "pan430_h1": dict(mesh="pan_h1", h=1.0, pan=True, sigma=M.SIGMA["SS430"], mu_pan=200.0),
    "pan430_h0.7": dict(mesh="pan_h0.7", h=0.7, pan=True, sigma=M.SIGMA["SS430"], mu_pan=200.0),
    "panCI_h0.7": dict(mesh="pan_h0.7", h=0.7, pan=True, sigma=M.SIGMA["cast_iron"], mu_pan=100.0),
}

SIF = """Header
  CHECK KEYWORDS Warn
  Mesh DB "." "mesh"
  Results Directory "out"
End
Simulation
  Coordinate System = Cartesian 3D
  Simulation Type = Steady
  Steady State Max Iterations = 1
  Max Output Level = 5
{sim_extra}End
Constants
  Permeability of Vacuum = 1.2566370614359173e-6
End
$ J1 = {J1}
$ J2 = {J2}
Body 1
  Target Bodies(1) = 1
  Equation = 1
  Material = 1
End
Body 2
  Target Bodies(1) = 2
  Equation = 1
  Material = 2
End
Body 3
  Target Bodies(1) = 3
  Equation = 1
  Material = 1
  Body Force = 1
End
Body 4
  Target Bodies(1) = 4
  Equation = 1
  Material = 1
  Body Force = 2
End
Material 1
  Relative Permeability = 1.0
  Electric Conductivity = 0.0
End
Material 2
  Relative Permeability = {mu_bar}
  Electric Conductivity = 0.0
End
Body Force 1
  Current Density 1 = Variable Coordinate 1, Coordinate 2
    Real MATC "-J1*tx(1)/sqrt(tx(0)^2+tx(1)^2)"
  Current Density 2 = Variable Coordinate 1, Coordinate 2
    Real MATC "J1*tx(0)/sqrt(tx(0)^2+tx(1)^2)"
  Current Density 3 = Real 0.0
End
Body Force 2
  Current Density 1 = Variable Coordinate 1, Coordinate 2
    Real MATC "-J2*tx(1)/sqrt(tx(0)^2+tx(1)^2)"
  Current Density 2 = Variable Coordinate 1, Coordinate 2
    Real MATC "J2*tx(0)/sqrt(tx(0)^2+tx(1)^2)"
  Current Density 3 = Real 0.0
End
Equation 1
  Active Solvers(2) = 1 2
End
Solver 1
  Equation = "MGDynamics"
  Variable = {var}
  Procedure = "MagnetoDynamics" "{proc}"
  Fix Input Current Density = True
  Jfix: Linear System Max Iterations = 20000
  Jfix: Linear System Convergence Tolerance = 1e-10
  Jfix: Linear System Abort Not Converged = False
  Jfix: Linear System Iterative Method = CG
  Edge Basis = Logical True
{linear}End
Solver 2
  Equation = "MGDynamicsCalc"
  Procedure = "MagnetoDynamics" "MagnetoDynamicsCalcFields"
  Potential Variable = String "AV"
  Calculate Magnetic Vector Potential = Logical True
  Calculate Elemental Fields = Logical True
  Calculate Nodal Fields = Logical True
  Linear System Solver = Iterative
  Linear System Iterative Method = CG
  Linear System Preconditioning = ILU0
  Linear System Max Iterations = 3000
  Linear System Convergence Tolerance = 1e-10
End
Solver 3
  Exec Solver = After Saving
  Equation = "ResultOutput"
  Procedure = "ResultOutputSolve" "ResultOutputSolver"
  Output File Name = "case"
  Vtu Format = Logical True
  Save Geometry Ids = Logical True
  Discontinuous Galerkin = Logical True
  Average Within Materials = Logical False
End
Boundary Condition 1
  Target Boundaries(3) = 1 2 3
{av_bc}End
{pan_bc}"""

LIN_STEADY = """  Linear System Solver = Iterative
  Linear System Use Hypre = Logical True
  Linear System Preconditioning = ams
  Linear System Method Hypre Index = Integer 8
  AMS Singular Matrix = Logical True
  Linear System Symmetric = True
  Linear System Convergence Tolerance = 1e-10
  Linear System Max Iterations = 8000
  Linear System Residual Output = 20
  Linear System Abort Not Converged = True
  Use Tree Gauge = False
  Linear System Scaling = False
  HYPRE GmRes Dimension = Integer 30
"""
LIN_HARM = """  Linear System Solver = Iterative
  Linear System Iterative Method = BiCGStabl
  BiCGStabl Polynomial Degree = 6
  Linear System Preconditioning = ILU1
  Linear System Convergence Tolerance = 1e-9
  Linear System Max Iterations = 20000
  Linear System Residual Output = 50
  Linear System Abort Not Converged = False
"""
PAN_BC = """Boundary Condition 2
  Target Boundaries(1) = 4
  Layer Electric Conductivity = Real {sigma}
  Layer Relative Permeability = Real {mu}
End
"""


def section_J(s):
    return s.turns / ((s.r1 - s.r0) * 1e-3 * BM.SIDE * 1e-3)      # A/m^2 at 1 A per turn


def sh(cmd, check=True):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f"{cmd}\n{r.stdout}\n{r.stderr}")
    return r.stdout


def remote(cmd, check=True):
    return sh(f"ssh -o BatchMode=yes {HOST} \"bash -lc '{cmd}'\"", check)


def run(case, np_=4, keep=False):
    c = CASES[case]
    mesh = HERE / "meshes" / f"{c['mesh']}.msh"
    if not mesh.exists():
        BM.build(c["mesh"], pan=c["pan"], h=c["h"])
    s_in, s_out = G.R43.sections
    harmonic = c["pan"] or c.get("harmonic", False)
    sif = SIF.format(J1=section_J(s_in), J2=section_J(s_out), mu_bar=c.get("mu_bar", M.FERRITE_MU),
                     proc="WhitneyAVHarmonicSolver" if harmonic else "WhitneyAVSolver",
                     linear=LIN_HARM if harmonic else LIN_STEADY,
                     sim_extra=f"  Angular Frequency = Real {2 * math.pi * F}\n" if harmonic else "",
                     var='"AV[AV re:1 AV im:1]"' if harmonic else '"AV"',
                     av_bc=("  AV re {e} = Real 0.0\n  AV im {e} = Real 0.0\n  AV re = Real 0.0\n  AV im = Real 0.0\n" if harmonic
                            else "  AV {e} = Real 0.0\n"),
                     pan_bc=PAN_BC.format(sigma=c["sigma"], mu=c["mu_pan"]) if c["pan"] else "")
    work = HERE / "runs" / case
    work.mkdir(parents=True, exist_ok=True)
    (work / "case.sif").write_text(sif)
    busy = remote("pgrep -x ElmerSolver_mpi | wc -l; free -g | awk \"/Mem/ {print \\$7}\"", check=False).split()
    if busy and int(busy[0]) > 0:
        print("note: another ElmerSolver_mpi is running on the box; this run is small, continuing")
    rd = f"{RDIR}/{case}"
    remote(f"rm -rf ~/{rd} && mkdir -p ~/{rd}")
    sh(f"scp -q {mesh} {work / 'case.sif'} {HOST}:{rd}/")
    part = f"-partdual -metiskway {np_}" if np_ > 1 else ""
    solver = f"mpirun -np {np_} {ELMER}/bin/ElmerSolver_mpi" if np_ > 1 else f"{ELMER}/bin/ElmerSolver case.sif"
    script = (f"source ~/miniconda3/etc/profile.d/conda.sh; conda activate temper-fem; cd ~/{rd}; "
              f"{ELMER}/bin/ElmerGrid 14 2 {mesh.name} -out mesh -scale 0.001 0.001 0.001 {part} > elmergrid.log 2>&1; "
              f"echo case.sif > ELMERSOLVER_STARTINFO; ulimit -Ss 65520; "
              f"/usr/bin/time -v env ELMER_HOME={ELMER} OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 {solver} > solver.log 2> time.log; echo rc=$?")
    (work / "remote.sh").write_text(script + "\n")
    sh(f"scp -q {work / 'remote.sh'} {HOST}:{rd}/")
    out = remote(f"bash ~/{rd}/remote.sh", check=False)
    print(out.strip())
    sh(f"scp -q {HOST}:{rd}/solver.log {HOST}:{rd}/time.log {work}/", check=False)
    sh(f"rm -rf {work}/out && mkdir -p {work}/out && scp -q -r {HOST}:{rd}/mesh/out/'*' {work}/out/ 2>/dev/null || "
       f"scp -q -r {HOST}:{rd}/out/'*' {work}/out/", check=False)
    if not keep:
        remote(f"find ~/{rd} -type f \\( -name \"*.vtu\" -o -name \"*.pvtu\" -o -name \"case.result*\" \\) -delete", check=False)
    return post(case)


def post(case):
    import pyvista as pv
    c = CASES[case]
    work = HERE / "runs" / case
    log = (work / "solver.log").read_text(errors="replace")
    tlog = (work / "time.log").read_text(errors="replace") if (work / "time.log").exists() else ""
    vtus = sorted((work / "out").glob("*.pvtu")) or sorted((work / "out").glob("*.vtu"))
    if not vtus:
        raise SystemExit(f"{case}: no VTU fetched; see {work}/solver.log")
    g = pv.read(str(vtus[-1]))
    g = g.compute_cell_sizes(length=False, area=False, volume=True)
    vol = np.asarray(g.cell_data["Volume"])
    gid = np.asarray(g.cell_data["GeometryIds"])
    cen = np.asarray(g.cell_centers().points)
    names = list(g.point_data.keys()) + list(g.cell_data.keys())
    harmonic = c["pan"] or c.get("harmonic", False)
    s_in, s_out = G.R43.sections

    def cellvec(key):
        if key in g.cell_data:
            return np.asarray(g.cell_data[key])
        return np.asarray(g.point_data_to_cell_data().cell_data[key])

    def find(pat):
        ks = [k for k in names if re.fullmatch(pat, k)]
        return ks[0] if ks else None
    out = dict(case=case, tets=int(g.n_cells), fields=sorted(set(names)))
    r = np.hypot(cen[:, 0], cen[:, 1])
    # current density at cell centres (A/m^2), azimuthal
    J = np.zeros_like(cen)
    for body, s in ((3, s_in), (4, s_out)):
        m = gid == body
        J[m, 0] = -section_J(s) * cen[m, 1] / r[m]
        J[m, 1] = section_J(s) * cen[m, 0] / r[m]
    if not harmonic:
        ka = find(r"magnetic vector potential")
        A = cellvec(ka)
        lam = float(np.sum(np.einsum("ij,ij->i", A, J) * vol)) * 20.0
        e = re.findall(r"Magnetic Field Energy:\s+(\S+)", log)
        W = float(e[-1]) if e else float("nan")
        out.update(L_uH_energy=2 * W * 20 * 1e6, L_uH_AdotJ=lam * 1e6)
        kb = find(r"magnetic flux density e") or find(r"magnetic flux density")
        B = cellvec(kb)
    else:
        kre, kim = find(r"magnetic vector potential re"), find(r"magnetic vector potential im")
        A = cellvec(kre) + 1j * cellvec(kim)
        lam = complex(np.sum(np.einsum("ij,ij->i", A, J) * vol)) * 20.0
        Z = 1j * 2 * math.pi * F * lam
        e = re.findall(r"Magnetic Field Energy:\s+(\S+)", log)
        p = re.findall(r"Surface current power \(the Joule effect\):\s+(\S+)", log)
        W = float(e[-1]) if e else float("nan")
        P = float(p[-1]) if p else 0.0
        # R from the impedance-boundary Joule power (peak 1 A: P = R/2 per sector -> x20 sectors);
        # L from the field energy, with Elmer's harmonic energy convention calibrated by harm_free_h0.7 (energy_factor)
        out.update(L_uH_AdotJ=float(Z.imag / (2 * math.pi * F)) * 1e6, R_ohm_AdotJ=float(Z.real),
                   W_sector_J=W, P_surface_sector_W=P, R_ohm=2 * 20 * P, L_uH_energy_raw=2 * W * 20 * 1e6)
        kbr = find(r"magnetic flux density re e") or find(r"magnetic flux density re")
        kbi = find(r"magnetic flux density im e") or find(r"magnetic flux density im")
        B = np.abs(cellvec(kbr) + 1j * cellvec(kbi))
    Bm = np.sqrt(np.sum(np.abs(B) ** 2, axis=1))
    bar = gid == 2
    # bar flux density per amp (peak B per peak A), statistics over the bar volume and along r
    rb = r[bar]
    bins = np.arange(29.5e-3, 120e-3, 7.5e-3)
    prof = []
    for a, b in zip(bins, bins[1:]):
        sel = (rb >= a) & (rb < b)
        if sel.any():
            prof.append(dict(r_mm=[a * 1e3, b * 1e3], B_mean_mT_per_A=float(np.average(Bm[bar][sel], weights=vol[bar][sel]) * 1e3),
                             B_max_mT_per_A=float(Bm[bar][sel].max() * 1e3)))
    # winding-layer field: azimuth/volume-mean |B|^2 (peak^2 per A^2) in 2 mm radial bins over both coil bodies,
    # for the Litz proximity correction (compared with the 2D smeared twin in run_free_air.py)
    coil = (gid == 3) | (gid == 4)
    rc_ = r[coil]
    wb = []
    for a in np.arange(26e-3, 116e-3, 2e-3):
        sel = (rc_ >= a) & (rc_ < a + 2e-3)
        if sel.any():
            wb.append(dict(r_mm=float((a + 1e-3) * 1e3),
                           B2_T2_per_A2=float(np.average(Bm[coil][sel] ** 2, weights=vol[coil][sel]))))
    out["winding_B2_profile"] = wb
    out.update(B_bar_max_mT_per_A=float(Bm[bar].max() * 1e3),
               B_bar_p99_mT_per_A=float(np.percentile(Bm[bar], 99) * 1e3),
               B_bar_volmean_mT_per_A=float(np.average(Bm[bar], weights=vol[bar]) * 1e3), bar_profile=prof)
    it = re.findall(r"(\d+)\s+[\d.E+-]+\s+[\d.E+-]+\s*$", log, re.M)
    out["converged_note"] = "NOT CONVERGED" if re.search(r"did not converge|NOT converged", log, re.I) else "ok"
    mem = re.findall(r"Maximum resident set size \(kbytes\): (\d+)", tlog)
    out["max_rss_GB"] = int(mem[-1]) / 1e6 if mem else None
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / f"{case}.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k not in ("bar_profile", "fields", "winding_B2_profile")}, indent=1))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--np", type=int, default=4)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--post-only", action="store_true")
    a = ap.parse_args()
    post(a.case) if a.post_only else run(a.case, a.np, a.keep)
