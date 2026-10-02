#!/usr/bin/env python3
"""Round 17 campaign on the remote box: leg-A 4 x 4 inductance matrices.

For each (arch height h, edge size e): mesh with mesh25d_hybrid.py, run the
mesh gates (no PEC columns, zero port leakage, every closure end on one PEC
body), solve each port alone with Hypre GMRES(100) + singular AMS at 1 A
with --vtu, then build the full matrix by reciprocity (inductance_matrix.py).
Resumable: a mesh or solve whose output already exists is not redone, and
only converged solves count. Solves run one at a time (memory).

Observability: while a solve runs, its Hypre residual history is read every
30 s. WORKDIR/status.json always holds the current state (case, port,
iteration, residual, rate, ETA, memory, completed solves); every 5 min a
PROGRESS line goes to stdout (campaign.log). ETA extrapolates the log of the
residual over the last ~500 iterations to the tolerance. `status.py WORKDIR`
prints a dashboard.

    campaign.py WORKDIR --cases 1:0.35 2:0.35 3:0.35 1:0.5 1:0.7
"""
from __future__ import annotations

import argparse
import json
import math
import re
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


HYPRE_LINE = re.compile(rb"^\s*(\d+)\s+([0-9.e+-]+)\s+[0-9.]+\s+([0-9.e+-]+)\s*$", re.M)


def hypre_history(log: Path) -> list[tuple[int, float]]:
    """(iteration, relative residual) from Hypre's per-iteration print."""
    try:
        data = log.read_bytes()
    except FileNotFoundError:
        return []
    return [(int(m[1]), float(m[3])) for m in HYPRE_LINE.finditer(data)]


def eta(hist: list[tuple[int, float]], tol: float, rate: float) -> float | None:
    """Seconds to reach tol: fit log10(residual) vs iteration over the last ~500."""
    tail = [(i, r) for i, r in hist if r > 0][-500:]
    if len(tail) < 50 or rate <= 0:
        return None
    n = len(tail)
    xs = [i for i, _ in tail]
    ys = [math.log10(r) for _, r in tail]
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0.0
    if slope >= 0:
        return None
    return max(0.0, (math.log10(tol) - ys[-1]) / slope / rate)


def bar(res: float, tol: float, width: int = 30) -> str:
    """Progress in orders of magnitude from residual 1 to tol."""
    frac = min(1.0, max(0.0, -math.log10(max(res, 1e-300)) / -math.log10(tol)))
    k = int(frac * width)
    return "[" + "#" * k + "." * (width - k) + f"] {100 * frac:3.0f}%"


def rss_gb() -> float:
    out = subprocess.run(["ps", "-C", "ElmerSolver_mpi", "-o", "rss="], capture_output=True, text=True).stdout
    return sum(int(x) for x in out.split()) / 1e6


def hms(s: float | None) -> str:
    if s is None:
        return "?"
    s = int(s)
    return f"{s // 3600}h{s % 3600 // 60:02d}m"


def solve_observed(cmd: list[str], out: Path, rd: Path, status: dict, work: Path, tol: float) -> int:
    """Run one solve, updating status.json every 30 s and printing PROGRESS every 5 min."""
    t0 = time.time()
    last_print = 0.0
    samples: list[tuple[float, int]] = []            # (time, iteration) for the recent rate
    with open(out, "w") as fh:
        proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT)
        while proc.poll() is None:
            time.sleep(30)
            hist = hypre_history(rd / "solver.log")
            el = time.time() - t0
            cur = {"state": "solving", "run": rd.name, "elapsed_s": round(el), "rss_GB": round(rss_gb(), 1)}
            if hist:
                it, res = hist[-1]
                recent = [h for h in hist if h[0] > it - 500]
                now = time.time()
                samples.append((now, it))
                samples[:] = [x for x in samples if now - x[0] <= 600]     # last 10 min
                dt = samples[-1][0] - samples[0][0]
                rate = (samples[-1][1] - samples[0][1]) / dt if dt > 0 else it / max(el - status.get("_setup_s", 0.0), 1.0)
                cur |= {"iteration": it, "residual": res, "its_per_s": round(rate, 3),
                        "eta_s": (lambda e: round(e) if e is not None else None)(eta(recent, tol, rate))}
            else:
                cur |= {"iteration": 0, "residual": None, "phase": "setup (mesh partition, assembly, AMS setup)"}
                status["_setup_s"] = el
            status["current"] = cur
            (work / "status.json").write_text(json.dumps({k: v for k, v in status.items() if not k.startswith("_")}, indent=1))
            if time.time() - last_print >= 300:
                last_print = time.time()
                if cur.get("residual"):
                    print(f"PROGRESS {rd.name} it {cur['iteration']} res {cur['residual']:.2e} "
                          f"{bar(cur['residual'], tol)} {cur['its_per_s']} it/s elapsed {hms(el)} "
                          f"eta {hms(cur['eta_s'])} mem {cur['rss_GB']} GB", flush=True)
                else:
                    print(f"PROGRESS {rd.name} setup elapsed {hms(el)} mem {cur['rss_GB']} GB", flush=True)
        status.pop("_setup_s", None)
        return proc.returncode


def result(path: Path) -> dict:
    """The RESULT line (gate and mesher scripts), else the last JSON line (run_elmer.py)."""
    lines = path.read_text().splitlines()
    for line in lines:
        if line.startswith("RESULT "):
            return json.loads(line[7:])
    for line in reversed(lines):
        if line.startswith("{"):
            return json.loads(line)
    raise ValueError(f"no result in {path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--cases", nargs="+", required=True, help="arch_h:h_edge pairs, in order")
    ap.add_argument("--elmer", required=True)
    ap.add_argument("--np", type=int, default=12)
    ap.add_argument("--leg", choices=("A", "B"), default="A")
    ap.add_argument("--margin", type=float, default=10.0, help="crop margin around the leg (mm)")
    ap.add_argument("--air", type=float, default=10.0, help="air box beyond the crop (mm)")
    ap.add_argument("--tol", type=float, default=1e-8)
    ap.add_argument("--maxit", type=int, default=40000)
    a = ap.parse_args()
    work = Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    status = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "leg": a.leg, "cases": a.cases, "tol": a.tol, "np": a.np,
              "done": [], "current": {"state": "starting"}}
    (work / "status.json").write_text(json.dumps(status, indent=1))
    while subprocess.run(["pgrep", "-x", "ElmerSolver_mpi"], capture_output=True).returncode == 0:
        time.sleep(60)                                   # one solve at a time (memory)
    for case in a.cases:
        h, e = case.split(":")
        tag = f"leg{a.leg}-h{h}-e{e.replace('.', 'p')}"
        if a.margin != 10.0 or a.air != 10.0:
            tag += f"-m{a.margin:g}-a{a.air:g}"
        msh, mlog = work / f"{tag}.msh", work / f"{tag}.log"
        if not msh.exists():
            rc = run([py, str(HERE / "mesh25d_hybrid.py"), str(EXPORT), str(msh), "--leg", a.leg,
                      "--closures", str(ROOT / f"closures-leg{a.leg}.json"), "--arch-h", h, "--h-edge", e,
                      "--h-far", "4", "--dz-max", "0.45", "--simplify", "0.05",
                      "--margin", str(a.margin), "--air", str(a.air)], mlog)
            if rc:
                print(f"FAIL {tag}: mesh failed, see {mlog}", flush=True)
                continue
        info = result(mlog)
        gates = {}
        for name, cmd in (("columns", [py, str(HERE / "pec_columns.py"), str(msh)]),
                          ("loops", [py, str(HERE / "port_loops.py"), str(msh), str(mlog),
                                     "--closures", str(ROOT / f"closures-leg{a.leg}.json")])):
            g = work / f"{tag}.{name}.txt"
            if not g.exists():
                run(cmd, g)
            gates[name] = result(g)
        ok = (gates["columns"]["inner_farfield_triangles"] == 0
              and all(p["leak_A"] <= 1e-9 for p in info["port_leak_A"])
              and all(p["closed_loop"] for p in gates["loops"]["ports"]))
        print(f"{'GATES' if ok else 'FAIL'} {tag}: {info['tets']} tets, gates {'pass' if ok else 'FAIL'}", flush=True)
        if not ok:
            continue
        runs = []
        for p in info["ports"]:
            k = [c * p["k_A_per_m"] for c in p["direction"]]
            rd = work / f"{tag}-{p['name']}"
            out = rd.with_suffix(".out")
            try:
                done = out.exists() and bool(result(out).get("converged"))
            except ValueError:                       # interrupted run: no result line
                done = False
            if not done:
                if rd.exists():
                    subprocess.run(["rm", "-rf", str(rd)])
                print(f"START {rd.name} ({info['tets']} tets)", flush=True)
                solve_observed([py, str(HERE / "run_elmer.py"), "--elmer", a.elmer, str(msh), str(rd),
                                "--pec", "2", "3", "--port", str(p["physical"]), "--k", *map(str, k),
                                "--hypre-ams", "--hypre-method", "8", "--ams-singular", "--tol", str(a.tol),
                                "--maxit", str(a.maxit), "--np", str(a.np), "--vtu", "--label", rd.name],
                               out, rd, status, work, a.tol)
            r = result(out)
            if r["converged"]:
                # Field-output gate right away (not after all four ports): the
                # self-inductance from the VTU B field must equal the energy.
                chk = rd.with_suffix(".bcheck.txt")
                rc = run([py, str(HERE / "inductance_matrix.py"), str(msh), "--port", str(p["physical"]), str(rd)], chk)
                if rc:
                    print(f"FAIL {rd.name}: field-output gate: {chk.read_text().strip()[-400:]}", flush=True)
                    status["current"] = {"state": f"stopped: field-output gate failed for {rd.name}"}
                    (work / "status.json").write_text(json.dumps(status, indent=1))
                    sys.exit(1)
            status["done"].append({"run": rd.name, "converged": r["converged"], "L_nH": r["inductance_nH"],
                                   "iterations": r["last_iteration"], "wall_s": r["wall_s"]})
            status["current"] = {"state": "between solves"}
            (work / "status.json").write_text(json.dumps(status, indent=1))
            print(f"DONE {rd.name}: converged={r['converged']} L={r['inductance_nH']} "
                  f"its={r['last_iteration']} wall={r['wall_s']}", flush=True)
            if r["converged"]:
                runs += ["--port", str(p["physical"]), str(rd)]
        if len(runs) == 3 * len(info["ports"]):
            mat = work / f"{tag}.matrix.txt"
            rc = run([py, str(HERE / "inductance_matrix.py"), str(msh)] + runs, mat)
            print(f"{'MATRIX' if rc == 0 else 'FAIL matrix'} {tag}: {mat.read_text().strip()[:700]}", flush=True)
    status["current"] = {"state": "campaign finished"}
    (work / "status.json").write_text(json.dumps(status, indent=1))
    print("CAMPAIGN FINISHED", flush=True)


if __name__ == "__main__":
    main()
