#!/usr/bin/env python3
"""Round 18: what our 2-rank experiments cost the live chain (passive, from its own logs).

    chain_rate.py CAMPAIGN_DIR SPEEDUP_DIR

The chain's campaign.log prints "PROGRESS <run> it N ... R it/s elapsed XhYYm"
every 5 min, R being its iteration rate over the last 10 min. Absolute time =
birth time of the <run> directory (run_elmer.py creates it right after the
campaign starts the solve and its clock) + elapsed. Our runs'
busy windows = [case.sif mtime, result.json mtime] under SPEEDUP_DIR/runs
(a run still going ends "now"). Each PROGRESS sample is labelled by the
fraction of its 10-min rate window that overlapped one of our runs; the
script prints the mean chain rate for samples fully inside vs fully outside
our windows, per chain run (the same mesh and port, so the same per-iteration
work).
"""
import re
import subprocess
import sys
import time
from pathlib import Path

camp, sp = Path(sys.argv[1]), Path(sys.argv[2])
busy = []
for d in (sp / "runs").iterdir():
    if d.is_dir() and (d / "case.sif").exists():
        t0 = int(subprocess.run(["stat", "--format=%W", str(d)], capture_output=True, text=True).stdout)
        t1 = (d / "result.json").stat().st_mtime if (d / "result.json").exists() else time.time()
        busy.append((t0, t1, d.name))
pat = re.compile(r"PROGRESS (\S+) it (\d+) res \S+ \[.*?\]\s+\d+% ([\d.]+) it/s elapsed (\d+)h(\d+)m")
rows = {}
for line in (camp / "campaign.log").read_text().splitlines():
    m = pat.search(line)
    if not m:
        continue
    run, rate, el = m[1], float(m[3]), int(m[4]) * 3600 + int(m[5]) * 60
    d = camp / run
    if not d.exists():
        continue
    born = int(subprocess.run(["stat", "--format=%W", str(d)], capture_output=True, text=True).stdout)
    t = born + el
    w0 = t - 600
    ov = sum(max(0.0, min(t, b1) - max(w0, b0)) for b0, b1, _ in busy) / 600
    rows.setdefault(run, []).append((t, rate, min(ov, 1.0)))
print("chain_run\tn_quiet\trate_quiet\tn_busy\trate_busy\tslowdown")
for run, rs in rows.items():
    q = [r for _, r, o in rs if o == 0 and _ > 0]
    b = [r for _, r, o in rs if o >= 0.999]
    mq = sum(q) / len(q) if q else float("nan")
    mb = sum(b) / len(b) if b else float("nan")
    print(f"{run}\t{len(q)}\t{mq:.3f}\t{len(b)}\t{mb:.3f}\t{(1 - mb / mq) * 100 if q and b else float('nan'):.1f}%")
