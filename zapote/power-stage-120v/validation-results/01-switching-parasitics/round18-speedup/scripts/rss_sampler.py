#!/usr/bin/env python3
"""Round 18, 4b: passive memory timeline of our own experiment runs.

    rss_sampler.py SPEEDUP_DIR [--period 2] [--hours 24]

Every PERIOD seconds, for each ElmerSolver_mpi process whose working directory
is under SPEEDUP_DIR/runs/NAME, reads VmRSS from /proc and appends
"unix_time  total_rss_GB  n_ranks  solver_log_lines  phase" to
SPEEDUP_DIR/logs/rss/NAME.tsv. The phase is the last recognised Elmer log
marker (mesh load, assembly, AMS setup, Krylov, field calculation, VTU output),
so the peak can be attributed to a phase. Only /proc is read; nothing is
signalled. The live chain's ranks (cwd outside SPEEDUP_DIR) are ignored.
"""
import argparse
import os
import time
from pathlib import Path

MARKERS = [("LoadMesh: Elapsed", "mesh loaded"), ("MGDynAssembly", "AV assembled"),
           ("Setting up AMS preconditioner", "AMS setup"), ("Solving linear system with", "Krylov"),
           ("SolveHypre: Required iterations", "Krylov done"), ("MagnetoDynamicsCalcFields: Computing", "field calc"),
           ("WriteVtuFile", "VTU output"), ("ALL DONE", "done")]


def phase(log: Path) -> tuple[int, str]:
    try:
        text = log.read_text(errors="replace")
    except OSError:
        return 0, "start"
    ph = "start"
    for key, name in MARKERS:
        if key in text:
            ph = name
    return text.count("\n"), ph


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--period", type=float, default=2.0)
    ap.add_argument("--hours", type=float, default=24.0)
    a = ap.parse_args()
    runs = Path(a.root).resolve() / "runs"
    out = Path(a.root).resolve() / "logs" / "rss"
    out.mkdir(parents=True, exist_ok=True)
    end = time.time() + 3600 * a.hours
    while time.time() < end:
        per: dict[str, list[int]] = {}
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                if open(f"/proc/{pid}/comm").read().strip() != "ElmerSolver_mpi":
                    continue
                cwd = Path(os.readlink(f"/proc/{pid}/cwd"))
                if runs not in cwd.parents:
                    continue
                name = cwd.relative_to(runs).parts[0]
                rss = next(int(l.split()[1]) for l in open(f"/proc/{pid}/status") if l.startswith("VmRSS"))
            except (OSError, StopIteration, ValueError):
                continue
            per.setdefault(name, []).append(rss)
        for name, rs in per.items():
            n, ph = phase(runs / name / "solver.log")
            with open(out / f"{name}.tsv", "a") as fh:
                fh.write(f"{time.time():.0f}\t{sum(rs) / 1e6:.3f}\t{len(rs)}\t{n}\t{ph}\n")
        time.sleep(a.period)


if __name__ == "__main__":
    main()
