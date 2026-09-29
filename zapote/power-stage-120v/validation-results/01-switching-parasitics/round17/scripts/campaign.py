#!/usr/bin/env python3
"""Round 17 campaign on the remote box: leg-A 4 x 4 inductance matrices.

For each (arch height h, edge size e): mesh with mesh25d_hybrid.py, run the
mesh gates (no PEC columns, zero port leakage, every closure end on one PEC
body), solve each port alone with Hypre GMRES(100) + singular AMS at 1 A
with --vtu, then build the full matrix by reciprocity (inductance_matrix.py).
Resumable: a mesh or solve whose output already exists is not redone, and
only converged solves count. Solves run one at a time (memory).

    campaign.py WORKDIR --cases 1:0.35 2:0.35 3:0.35 1:0.5 1:0.7
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EXPORT = ROOT / "../../04-board-current-thermal/round4/reextract-b3/inputs/native17-all-copper.json.gz"


def run(cmd: list[str], log: Path) -> int:
    with open(log, "w") as fh:
        return subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT).returncode


def result(path: Path) -> dict:
    for line in path.read_text().splitlines():
        if line.startswith("RESULT "):
            return json.loads(line[7:])
        if line.startswith("{"):
            return json.loads(line)
    raise ValueError(f"no result in {path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--cases", nargs="+", required=True, help="arch_h:h_edge pairs, in order")
    ap.add_argument("--elmer", required=True)
    ap.add_argument("--np", type=int, default=12)
    ap.add_argument("--tol", type=float, default=1e-8)
    ap.add_argument("--maxit", type=int, default=40000)
    a = ap.parse_args()
    work = Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    while subprocess.run(["pgrep", "-x", "ElmerSolver_mpi"], capture_output=True).returncode == 0:
        time.sleep(60)                                   # one solve at a time (memory)
    for case in a.cases:
        h, e = case.split(":")
        tag = f"legA-h{h}-e{e.replace('.', 'p')}"
        msh, mlog = work / f"{tag}.msh", work / f"{tag}.log"
        if not msh.exists():
            rc = run([py, str(HERE / "mesh25d_hybrid.py"), str(EXPORT), str(msh), "--leg", "A",
                      "--closures", str(ROOT / "closures-legA.json"), "--arch-h", h, "--h-edge", e,
                      "--h-far", "4", "--dz-max", "0.45", "--simplify", "0.05"], mlog)
            if rc:
                print(f"{tag}: mesh failed, see {mlog}", flush=True)
                continue
        info = result(mlog)
        gates = {}
        for name, cmd in (("columns", [py, str(HERE / "pec_columns.py"), str(msh)]),
                          ("loops", [py, str(HERE / "port_loops.py"), str(msh), str(mlog),
                                     "--closures", str(ROOT / "closures-legA.json")])):
            g = work / f"{tag}.{name}.txt"
            if not g.exists():
                run(cmd, g)
            gates[name] = result(g)
        ok = (gates["columns"]["inner_farfield_triangles"] == 0
              and all(p["leak_A"] <= 1e-9 for p in info["port_leak_A"])
              and all(p["closed_loop"] for p in gates["loops"]["ports"]))
        print(f"{tag}: {info['tets']} tets, gates {'pass' if ok else 'FAIL'}", flush=True)
        if not ok:
            continue
        runs = []
        for p in info["ports"]:
            k = [c * p["k_A_per_m"] for c in p["direction"]]
            rd = work / f"{tag}-{p['name']}"
            out = rd.with_suffix(".out")
            if not (out.exists() and result(out).get("converged")):
                if rd.exists():
                    subprocess.run(["rm", "-rf", str(rd)])
                run([py, str(HERE / "run_elmer.py"), "--elmer", a.elmer, str(msh), str(rd),
                     "--pec", "2", "3", "--port", str(p["physical"]), "--k", *map(str, k),
                     "--hypre-ams", "--hypre-method", "8", "--ams-singular", "--tol", str(a.tol),
                     "--maxit", str(a.maxit), "--np", str(a.np), "--vtu", "--label", rd.name], out)
            r = result(out)
            print(f"  {rd.name}: converged={r['converged']} L={r['inductance_nH']} "
                  f"its={r['last_iteration']} wall={r['wall_s']}", flush=True)
            if r["converged"]:
                runs += ["--port", str(p["physical"]), str(rd)]
        if len(runs) == 3 * len(info["ports"]):
            mat = work / f"{tag}.matrix.txt"
            run([py, str(HERE / "inductance_matrix.py"), str(msh)] + runs, mat)
            print(f"  matrix: {mat.read_text().strip()[:400]}", flush=True)


if __name__ == "__main__":
    main()
