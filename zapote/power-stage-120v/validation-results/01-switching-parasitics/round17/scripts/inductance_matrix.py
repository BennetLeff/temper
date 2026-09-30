#!/usr/bin/env python3
"""Full port inductance matrix from single-port Elmer solves (round 17).

For lowest-order edge elements the stiffness form is
x_i^T K x_j = (1/mu0) * integral of B_i . B_j dV, and K x_j = b_j, so with
each port driven alone at 1 A:

    L_ij = (1/mu0) * sum over tets of vol * B_i . B_j        (exact in FE)

B = curl A is constant in each tetrahedron. Elmer writes it as the elemental
field "magnetic flux density e" (run_elmer.py --vtu: Discontinuous Galerkin,
bulk only, Average Within Materials = False — the writer's default averages
DG fields within each body, which smooths the per-tet values; round 17 found
that only on a non-uniform field, the uniform plate fixture cannot show it).

Two gates, either failing exits nonzero:
- the within-tet spread of B (largest deviation / largest |B|) is at
  round-off, so B really is per-tet constant;
- each diagonal L_ii matches that solve's own 2W/I^2 (run_elmer.py .out
  file next to RUN_DIR) to 1e-5 relative.

    inductance_matrix.py MESH.msh --port 10 RUN_DIR_P1 [--port 11 RUN_DIR_P2 ...]

RUN_DIR is a run_elmer.py work directory (VTU under RUN_DIR/mesh). All runs
must use the same mesh and the same number of MPI ranks (same partitions).
"""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

import meshio
import numpy as np

MU0 = 4e-7 * np.pi
SPREAD_MAX = 1e-9
DIAG_REL_MAX = 1e-5


def vtus(run: str) -> list[str]:
    files = sorted(glob.glob(f"{run}/mesh/**/case*.vtu", recursive=True))
    assert files, f"no vtu in {run}"
    return files


def energy_L(run: str) -> float | None:
    out = Path(run).with_suffix(".out")
    if not out.exists():
        return None
    for line in reversed(out.read_text().splitlines()):
        if line.startswith("{"):
            return json.loads(line).get("inductance_nH")
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("msh", help="the gmsh mesh (recorded for provenance)")
    ap.add_argument("--port", nargs=2, action="append", required=True, metavar=("PHYS", "RUN_DIR"))
    a = ap.parse_args()
    names = [p for p, _ in a.port]
    runs = [r for _, r in a.port]
    files = [vtus(r) for r in runs]
    assert len({len(f) for f in files}) == 1, "runs have different partition counts"
    n = len(runs)
    L = np.zeros((n, n))
    dev, bmax, ntet = 0.0, 0.0, 0
    for part in range(len(files[0])):
        Bs, vol, cref = [], None, None
        for i in range(n):
            m = meshio.read(files[i][part])
            tet = next(c.data for c in m.cells if c.type == "tetra")
            P = m.points[tet]
            c = P.mean(1)
            if cref is None:
                cref = c
                vol = np.abs(np.einsum("ij,ij->i", P[:, 1] - P[:, 0],
                                       np.cross(P[:, 2] - P[:, 0], P[:, 3] - P[:, 0]))) / 6
            else:
                assert c.shape == cref.shape and np.allclose(c, cref), "tets differ between runs"
            B = m.point_data["magnetic flux density e"][tet]
            Bt = B.mean(1)
            bmax = max(bmax, float(np.abs(B).max()))
            dev = max(dev, float(np.abs(B - Bt[:, None, :]).max()))
            Bs.append(Bt)
        ntet += len(vol)
        for i in range(n):
            for j in range(i, n):
                L[i, j] += float((vol * (Bs[i] * Bs[j]).sum(1)).sum()) / MU0
    L = np.triu(L) + np.triu(L, 1).T
    spread = dev / bmax
    diag_check = []
    for i, r in enumerate(runs):
        e = energy_L(r)
        rel = abs(L[i, i] * 1e9 - e) / e if e else None
        diag_check.append({"port": names[i], "L_from_B_nH": round(L[i, i] * 1e9, 6), "L_energy_nH": e,
                           "rel_diff": rel})
    res = {"ports": names, "L_nH": (L * 1e9).round(6).tolist(), "tets": ntet,
           "partitions": len(files[0]), "max_within_tet_spread": spread, "diagonal_vs_energy": diag_check}
    print("RESULT " + json.dumps(res))
    if spread > SPREAD_MAX:
        raise SystemExit(f"elemental B not constant per tet (spread {spread:.3g})")
    bad = [d for d in diag_check if d["rel_diff"] is None or d["rel_diff"] > DIAG_REL_MAX]
    if bad:
        raise SystemExit(f"diagonal does not match the solver energy: {bad}")


if __name__ == "__main__":
    main()
