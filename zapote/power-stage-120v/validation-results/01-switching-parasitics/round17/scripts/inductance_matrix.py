#!/usr/bin/env python3
"""Full port inductance matrix from single-port Elmer solves (round 17).

For lowest-order edge elements the stiffness form is
x_i^T K x_j = (1/mu0) * integral of B_i . B_j dV, and K x_j = b_j, so with
each port driven alone at 1 A:

    L_ij = (1/mu0) * sum over tets of vol * B_i . B_j        (exact in FE)

B = curl A is constant in each tetrahedron. Elmer writes it as the elemental
field "magnetic flux density e" (run_elmer.py --vtu: Discontinuous Galerkin,
bulk only). One defect: at nodes on an interior boundary (the port sheets)
the written value comes from the tet on the other side, so each tet's B is
taken from its nodes that are not on a port sheet (every non-degenerate tet
has one). The within-tet spread of the remaining nodes is reported; it must
be at round-off.

Checked exactly on the two-port plate section (L11 3.141593, L22 1.884956,
M 1.884956 nH). The diagonal must also match each solve's own 2W/I^2.

    inductance_matrix.py MESH.msh --port 10 RUN_DIR_P1 --port 11 RUN_DIR_P2 ...

RUN_DIR is a run_elmer.py work directory (VTU under RUN_DIR/mesh). All runs
must use the same mesh and the same number of MPI ranks (same partitions).
"""
from __future__ import annotations

import argparse
import glob
import json
import meshio
import numpy as np

from check_ports import read_msh

MU0 = 4e-7 * np.pi


def vtus(run: str) -> list[str]:
    files = sorted(glob.glob(f"{run}/mesh/**/case*.vtu", recursive=True))
    assert files, f"no vtu in {run}"
    return files


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("msh")
    ap.add_argument("--port", nargs=2, action="append", required=True, metavar=("PHYS", "RUN_DIR"))
    ap.add_argument("--scale", type=float, default=1e-3)
    ap.add_argument("--port-groups", type=int, nargs="*", default=None,
                    help="all port physical groups in the mesh (default: every group >= 10)")
    a = ap.parse_args()
    nodes, tris = read_msh(a.msh)
    groups = set(a.port_groups) if a.port_groups else {p for p, _ in tris if p >= 10}
    q = 1e-9
    port_pts = {tuple(np.round(np.array(nodes[v]) * a.scale / q).astype(np.int64))
                for p, t in tris if p in groups for v in t}
    names = [p for p, _ in a.port]
    runs = [r for _, r in a.port]
    files = [vtus(r) for r in runs]
    assert len({len(f) for f in files}) == 1, "runs have different partition counts"
    n = len(runs)
    L = np.zeros((n, n))
    dev, bmax = 0.0, 0.0            # largest within-tet deviation, largest |B| (all runs)
    ntet = 0
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
            R = np.round(m.points / q).astype(np.int64)
            on = np.fromiter((tuple(r) in port_pts for r in map(tuple, R)), bool, len(R))[tet]
            w = (~on).astype(float)
            assert (w.sum(1) > 0).all(), "a tet has every node on a port sheet"
            B = m.point_data["magnetic flux density e"][tet]
            Bt = (B * w[:, :, None]).sum(1) / w.sum(1)[:, None]
            bmax = max(bmax, float(np.abs(B).max()))
            dev = max(dev, float(np.abs((B - Bt[:, None, :]) * w[:, :, None]).max()))
            Bs.append(Bt)
        ntet += len(vol)
        for i in range(n):
            for j in range(i, n):
                L[i, j] += float((vol * (Bs[i] * Bs[j]).sum(1)).sum()) / MU0
    L = np.triu(L) + np.triu(L, 1).T
    spread = dev / bmax
    res = {"ports": names, "L_nH": (L * 1e9).round(6).tolist(), "tets": ntet,
           "partitions": len(files[0]), "max_within_tet_spread": spread}
    print("RESULT " + json.dumps(res))
    if spread > 1e-6:
        raise SystemExit(f"elemental B not constant per tet (spread {spread:.3g})")


if __name__ == "__main__":
    main()
