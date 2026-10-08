#!/usr/bin/env python3
"""Round 18 (speed-up), 4a: one table of every past Elmer solve on the remote box.

    python3 history.py ~/temper-fem/r16 ~/temper-fem/r17 ... > history.tsv

Walks the given roots for run directories (case.sif + solver.log written by
round 16/17 run_elmer.py) and prints one TSV row per run:

  run, tets, nodes, est_dofs, np, method, tol, iterations, final_norm,
  load_s, assembly_s, ams_setup_s, hypre_setup_s, krylov_s, post_s, total_s, wall_s,
  it_per_s, s_per_it_per_Mtet_rank, rank_maxrss_GB, converged, exit_code, L_nH

Sources: elmergrid.log (tets = elements - lower-dimensional elements; nodes =
knots), solver.log (rank-0 timing lines and Hypre's own summary), result.json
(np, energy, exit code, max RSS, wall). est_dofs = nodes + tets is the Euler
estimate of the edge count of a tetrahedral mesh (E ~ V + T): an estimate,
not a count. post_s = total - (load + assembly + AMS setup + Hypre setup +
Krylov): field calculation, VTU output and teardown. rank_maxrss_GB is GNU
time's ru_maxrss under mpirun, i.e. the largest single rank, not the total.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def num(pat: str, text: str, cast=float, last=False):
    m = re.findall(pat, text, re.M)
    if not m:
        return None
    v = m[-1] if last else m[0]
    if isinstance(v, tuple):
        v = v[0]
    try:
        return cast(v)
    except ValueError:
        return None


def row(d: Path) -> dict:
    sif = (d / "case.sif").read_text(errors="replace")
    log = (d / "solver.log").read_text(errors="replace")
    eg = (d / "elmergrid.log").read_text(errors="replace") if (d / "elmergrid.log").exists() else ""
    res = {}
    if (d / "result.json").exists():
        try:
            res = json.loads((d / "result.json").read_text())
        except ValueError:
            res = {}
    elems = num(r"Allocating for \d+ knots and (\d+) elements", eg, int)
    low = num(r"There are (\d+) \(out of \d+\) lower dimensional elements", eg, int)
    nodes = num(r"Allocating for (\d+) knots", eg, int)
    tets = elems - low if elems is not None and low is not None else None
    hidx = num(r"Hypre Index = Integer (\d+)", sif, int)
    method = {6: "PCG", 7: "BiCGStab", 8: "GMRES", 9: "FlexGMRES", 10: "LGMRES", 11: "COGMRES"}.get(hidx, None)
    if method is None:
        m = re.search(r"Linear System Solver = (\w+)", sif)
        method = (m[1] if m else "?")
        if method.lower() == "direct":
            method = "direct"
        else:
            m = re.search(r"Iterative Method = (\w+)", sif)
            method = m[1] if m else method
    if "Linear System Use Hypre" in sif:
        prec = re.search(r"Linear System Preconditioning = (\w+)", sif)
        method += "+" + (prec[1] if prec else "?")
    tol = num(r"Linear System Convergence Tolerance = (\S+)", sif)
    hy = re.findall(r"SolveHypre: Required iterations (\d+) \(method \d+\) to norm (\S+)", log)
    its = int(hy[0][0]) if hy else None
    norm = float(hy[0][1]) if hy else None
    load = num(r"LoadMesh: Elapsed REAL time:\s+(\S+)", log)
    asm = num(r"MGDynAssembly: Elapsed REAL time:\s+(\S+)", log)
    ams = num(r"AMS preconditioner setup time: (\S+)", log)
    hset = num(r"SolveHypre: setup time \(method \d+\): (\S+)", log)
    kry = num(r"SolveHypre: Solution time \(method \d+\): (\S+)", log)
    tot = num(r"SOLVER TOTAL TIME\(CPU,REAL\):\s+\S+\s+(\S+)", log)
    parts = [x for x in (load, asm, ams, hset, kry) if x is not None]
    post = tot - sum(parts) if tot is not None and kry is not None else None
    np_ = res.get("np") or 1
    ips = its / kry if its and kry else None
    norm_cost = (kry / its) * np_ / (tets / 1e6) if its and kry and tets else None
    return {"run": str(d), "tets": tets, "nodes": nodes,
            "est_dofs": (tets + nodes) if tets and nodes else None, "np": np_, "method": method, "tol": tol,
            "iterations": its, "final_norm": norm, "load_s": load, "assembly_s": asm, "ams_setup_s": ams,
            "hypre_setup_s": hset, "krylov_s": kry, "post_s": round(post, 1) if post is not None else None,
            "total_s": tot, "wall_s": res.get("wall_s"), "it_per_s": round(ips, 3) if ips else None,
            "s_per_it_per_Mtet_rank": round(norm_cost, 3) if norm_cost else None,
            "rank_maxrss_GB": res.get("max_rss_GB"), "converged": res.get("converged"),
            "exit_code": res.get("exit_code"), "L_nH": res.get("inductance_nH"),
            "scaling": ("False" if re.search(r"Linear System Scaling = (Logical )?False", sif, re.I) else "default"),
            "solver_lines": ";".join(res.get("solver_lines") or [])}


def main() -> None:
    rows = []
    for root in sys.argv[1:]:
        for log in sorted(Path(root).expanduser().rglob("solver.log")):
            d = log.parent
            if (d / "case.sif").exists():
                rows.append(row(d))
    keys = list(rows[0].keys())
    print("\t".join(keys))
    for r in rows:
        print("\t".join("" if r[k] is None else str(r[k]) for k in keys))


if __name__ == "__main__":
    main()
