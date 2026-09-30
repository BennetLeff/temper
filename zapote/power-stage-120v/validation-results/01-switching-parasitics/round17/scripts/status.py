#!/usr/bin/env python3
"""Dashboard for a campaign.py run: `status.py WORKDIR`.

Shows every planned solve (done with its value, running with progress bar
and ETA, or queued), the matrices built so far, and a rough time-to-finish
(queued solves times the mean wall time of finished ones at the same mesh
size, else of all finished ones). Reads WORKDIR/status.json and the
per-solve .out files; safe to run while the campaign is running.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

PORTS = ["P1_C38", "P2_C39", "P3_gate_high", "P4_gate_low"]


def hms(s) -> str:
    if s is None:
        return "?"
    s = int(s)
    return f"{s // 3600}h{s % 3600 // 60:02d}m"


def bar(res, tol, width=24) -> str:
    if not res:
        return "[" + "." * width + "]   0%"
    frac = min(1.0, max(0.0, -math.log10(res) / -math.log10(tol)))
    k = int(frac * width)
    return "[" + "#" * k + "." * (width - k) + f"] {100 * frac:3.0f}%"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    a = ap.parse_args()
    work = Path(a.work)
    st = json.loads((work / "status.json").read_text())
    tol = st["tol"]
    age = time.time() - (work / "status.json").stat().st_mtime
    print(f"campaign started {st['started']}  tol {tol}  ranks {st['np']}  status.json updated {int(age)} s ago")
    cur = st.get("current", {})
    walls = {}
    queued = []
    print(f"{'solve':34s} {'state':10s} {'L (nH)':>10s} {'its':>6s} {'wall':>7s}  progress")
    for case in st["cases"]:
        h, e = case.split(":")
        tag = f"legA-h{h}-e{e.replace('.', 'p')}"
        for p in PORTS:
            name = f"{tag}-{p}"
            out = work / f"{name}.out"
            r = None
            if out.exists():
                for line in reversed(out.read_text().splitlines()):
                    if line.startswith("{"):
                        r = json.loads(line)
                        break
            if r is not None:
                state = "done" if r["converged"] else "FAILED"
                walls.setdefault(e, []).append(r["wall_s"] or 0)
                print(f"{name:34s} {state:10s} {r['inductance_nH'] or float('nan'):10.4f} "
                      f"{r['last_iteration'] or 0:6d} {hms(r['wall_s']):>7s}")
            elif cur.get("run") == name:
                print(f"{name:34s} {'running':10s} {'':>10s} {cur.get('iteration', 0):6d} {hms(cur.get('elapsed_s')):>7s}  "
                      f"{bar(cur.get('residual'), tol)} res {cur.get('residual') or 0:.1e} "
                      f"{cur.get('its_per_s', '?')} it/s eta {hms(cur.get('eta_s'))} mem {cur.get('rss_GB')} GB"
                      + (f"  {cur['phase']}" if cur.get("phase") else ""))
            else:
                print(f"{name:34s} {'queued':10s}")
                queued.append(e)
        mat = work / f"{tag}.matrix.txt"
        if mat.exists():
            for line in mat.read_text().splitlines():
                if line.startswith("RESULT "):
                    m = json.loads(line[7:])
                    print(f"  matrix {tag} (nH):")
                    for name, row in zip(m["ports"], m["L_nH"]):
                        print("   " + " ".join(f"{v:10.4f}" for v in row))
    allw = [w for ws in walls.values() for w in ws]
    if queued and allw:
        rest = sum((sum(walls[e]) / len(walls[e])) if e in walls else sum(allw) / len(allw) for e in queued)
        rest += max(0, cur.get("eta_s") or 0)
        print(f"queued solves: {len(queued)}; rough time to finish: {hms(rest)} "
              f"(coarser meshes will be faster than this estimate)")
    print(f"state: {cur.get('state')}")


if __name__ == "__main__":
    main()
