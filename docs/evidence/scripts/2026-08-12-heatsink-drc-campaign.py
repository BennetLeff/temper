#!/usr/bin/env python3
"""Run N kicad-cli DRC passes against a board and report per-category spread.

Usage: drc_campaign.py <board.kicad_pcb> <N> [outdir]

Copies the board + its .kicad_pro/.kicad_dru into a scratch dir (kicad-cli
resolves a project by finding <stem>.kicad_pro next to the board; without it
it SILENTLY drops creepage/track_width/missing_courtyard/annular_width).
Uses --all-track-errors, which the Makefile documents as load-bearing for
determinism as much as completeness.
"""
import json
import shutil
import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path

board = Path(sys.argv[1]).resolve()
n = int(sys.argv[2])
outdir = Path(sys.argv[3] if len(sys.argv) > 3 else "/tmp/drc_campaign").resolve()
outdir.mkdir(parents=True, exist_ok=True)

work = outdir / "work"
if work.exists():
    shutil.rmtree(work)
work.mkdir()
shutil.copy(board, work / "board.kicad_pcb")
for ext in ("kicad_pro", "kicad_dru"):
    src = board.with_suffix("." + ext)
    if src.exists():
        shutil.copy(src, work / ("board." + ext))
    else:
        print(f"WARNING: {src.name} absent next to board", file=sys.stderr)

have_pro = (work / "board.kicad_pro").exists()
print(f"project resolvable: {have_pro}  (False => custom DRU rules silently dropped)")

err_samples = []   # list[Counter]
warn_samples = []
unconnected = []

for i in range(n):
    rep = work / "drc.json"
    if rep.exists():
        rep.unlink()
    r = subprocess.run(
        ["kicad-cli", "pcb", "drc", "--all-track-errors", "--format", "json",
         "--severity-all", "-o", "drc.json", "board.kicad_pcb"],
        cwd=work, capture_output=True, text=True,
    )
    if not rep.exists():
        print(f"run {i}: FAILED rc={r.returncode}\n{r.stderr[:2000]}", file=sys.stderr)
        sys.exit(1)
    d = json.loads(rep.read_text())
    ec, wc = Counter(), Counter()
    for v in d.get("violations", []):
        sev = v.get("severity")
        t = v.get("type")
        (ec if sev == "error" else wc)[t] += 1
    err_samples.append(ec)
    warn_samples.append(wc)
    unconnected.append(len(d.get("unconnected_items", [])))
    if i == 0:
        (outdir / "drc_run0.json").write_text(rep.read_text())
    if (i + 1) % 10 == 0:
        print(f"  {i+1}/{n} ...", flush=True)

def summarize(samples, label):
    keys = sorted({k for s in samples for k in s})
    print(f"\n=== {label} (N={len(samples)}) ===")
    print(f"{'category':<28} {'min':>6} {'max':>6} {'median':>8} {'mean':>9}")
    for k in keys:
        vals = [s.get(k, 0) for s in samples]
        print(f"{k:<28} {min(vals):>6} {max(vals):>6} "
              f"{statistics.median(vals):>8} {statistics.mean(vals):>9.2f}")
    tot = [sum(s.values()) for s in samples]
    print(f"{'TOTAL':<28} {min(tot):>6} {max(tot):>6} "
          f"{statistics.median(tot):>8} {statistics.mean(tot):>9.2f}")
    return {k: [s.get(k, 0) for s in samples] for k in keys}, tot

e, etot = summarize(err_samples, "ERRORS")
w, wtot = summarize(warn_samples, "WARNINGS")
print(f"\nunconnected_items: min={min(unconnected)} max={max(unconnected)} "
      f"median={statistics.median(unconnected)}")

json.dump(
    {"board": str(board), "n": n, "project_resolvable": have_pro,
     "errors": e, "warnings": w, "error_total": etot, "warning_total": wtot,
     "unconnected_items": unconnected},
    open(outdir / "campaign.json", "w"), indent=2)
print(f"\nwrote {outdir/'campaign.json'}")
