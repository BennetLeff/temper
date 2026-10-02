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
import hashlib
import json
import re
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


def run_result(run: str) -> dict | None:
    """run_elmer.py's result (receipt) for a run directory: <run>/result.json, else the .out file."""
    rj = Path(run) / "result.json"
    if rj.exists():
        return json.loads(rj.read_text())
    out = Path(run).with_suffix(".out")
    if not out.exists():
        return None
    for line in reversed(out.read_text().splitlines()):
        if line.startswith("{"):
            return json.loads(line)
    return None


def energy_L(run: str) -> float | None:
    r = run_result(run)
    return r.get("inductance_nH") if r else None


def sif_port(run: str) -> tuple[int, list[float]]:
    """The single driven port's physical id and K vector from the run's case.sif."""
    txt = (Path(run) / "case.sif").read_text()
    blocks = re.findall(r"Boundary Condition \d+\n  Target Boundaries\(1\) = (\d+)\n"
                        r"  Magnetic Field Strength 1 = Real (\S+)\n  Magnetic Field Strength 2 = Real (\S+)\n"
                        r"  Magnetic Field Strength 3 = Real (\S+)", txt)
    if len(blocks) != 1:
        raise SystemExit(f"{run}: expected exactly one driven port in case.sif, found {len(blocks)}")
    b = blocks[0]
    return int(b[0]), [float(b[1]), float(b[2]), float(b[3])]


def mesh_ports(msh: str) -> dict[int, dict]:
    """Port definitions the mesher recorded (RESULT line in <mesh>.log): physical -> name, K."""
    log = Path(msh).with_suffix(".log")
    if not log.exists():
        raise SystemExit(f"mesher log {log} not found: cannot check port identity")
    for line in log.read_text().splitlines():
        if line.startswith("RESULT "):
            return {p["physical"]: {"name": p["name"], "k": [c * p["k_A_per_m"] for c in p["direction"]]}
                    for p in json.loads(line[7:])["ports"]}
    raise SystemExit(f"no RESULT line in {log}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("msh", help="the gmsh mesh; must exist, with its mesher log beside it")
    ap.add_argument("--port", nargs=2, action="append", required=True, metavar=("PHYS", "RUN_DIR"))
    ap.add_argument("--legacy-no-receipt", action="store_true",
                    help="accept runs made before run_elmer.py recorded mesh/SIF hashes (recorded in the output)")
    a = ap.parse_args()
    names = [p for p, _ in a.port]
    runs = [r for _, r in a.port]
    # Identity (D-4 review, P2): the energy and within-tet gates are blind to a
    # reversed or swapped excitation, so check every run against the mesh's
    # own port record: driven physical id and signed K must match exactly.
    if not Path(a.msh).exists():
        raise SystemExit(f"mesh {a.msh} not found")
    mp = mesh_ports(a.msh)
    # Receipts (D-9 review, P2): each run must have been solved on this exact
    # mesh, with the SIF that is in its directory now.
    mesh_sha = hashlib.sha256(Path(a.msh).read_bytes()).hexdigest()
    legacy = []
    for run in runs:
        r = run_result(run) or {}
        if "mesh_sha256" not in r:
            if not a.legacy_no_receipt:
                raise SystemExit(f"{run}: no run receipt (mesh hash); pass --legacy-no-receipt to accept and record it")
            legacy.append(run)
            continue
        if r["mesh_sha256"] != mesh_sha:
            raise SystemExit(f"{run}: solved on mesh {r['mesh_sha256'][:12]}, not {Path(a.msh).name} {mesh_sha[:12]}")
        if r.get("sif_sha256") != hashlib.sha256((Path(run) / "case.sif").read_bytes()).hexdigest():
            raise SystemExit(f"{run}: case.sif changed since the solve")
    port_ids = []
    for phys, run in zip(names, runs):
        pid, k = sif_port(run)
        if pid != int(phys):
            raise SystemExit(f"{run}: drives port {pid}, but was given as port {phys}")
        if pid not in mp or not np.allclose(k, mp[pid]["k"], rtol=1e-9, atol=1e-6):
            raise SystemExit(f"{run}: K {k} does not match the mesh's port {pid} "
                             f"{mp.get(pid, {}).get('name')} K {mp.get(pid, {}).get('k')}")
        port_ids.append({"physical": pid, "name": mp[pid]["name"], "k_A_per_m": k,
                         "sif_sha256": hashlib.sha256((Path(run) / "case.sif").read_bytes()).hexdigest()})
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
    res = {"ports": names, "port_identity": port_ids,
           "mesh_sha256": mesh_sha, "legacy_runs_without_receipt": legacy,
           "L_nH": (L * 1e9).round(6).tolist(), "tets": ntet,
           "partitions": len(files[0]), "max_within_tet_spread": spread, "diagonal_vs_energy": diag_check}
    print("RESULT " + json.dumps(res))
    if spread > SPREAD_MAX:
        raise SystemExit(f"elemental B not constant per tet (spread {spread:.3g})")
    bad = [d for d in diag_check if d["rel_diff"] is None or d["rel_diff"] > DIAG_REL_MAX]
    if bad:
        raise SystemExit(f"diagonal does not match the solver energy: {bad}")


if __name__ == "__main__":
    main()
