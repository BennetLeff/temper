#!/usr/bin/env python3
"""External PID RSS sampler for the 2026-08-15 Stage 3 memory-blowup run.

Usage:
    python3 docs/evidence/scripts/2026-08-15-stage3-rss-watchdog.py \
        --interval 0.5 --out /tmp/opencode/stage3-rss.log \
        -- .venv/bin/python scripts/route_board.py --output /tmp/opencode/route-out.kicad_pcb

Spawns the command, samples /proc/<pid>/status VmRSS every `interval`
seconds (also VmHWM once per sample for free), prints one line per sample
to stdout AND appends to --out, and reports the peak on exit. The child's
stderr/stdout pass through to this process's stderr/stdout so the
[mem-trace] lines interleave naturally with the RSS samples.

Pure /proc reads -- no psutil dependency, no root, no coverage. The route
runs as a single process (monolithic Stage 3), so one PID suffices; the
net-batching subprocess path is out of scope for this investigation's run.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


def rss_kb(pid: int) -> tuple[int, int]:
    """Return (VmRSS, VmHWM) in KiB for pid, or (-1, -1)."""
    try:
        with open(f"/proc/{pid}/status", encoding="utf-8") as f:
            rss = hwm = -1
            for line in f:
                if line.startswith("VmRSS:"):
                    rss = int(line.split()[1])
                elif line.startswith("VmHWM:"):
                    hwm = int(line.split()[1])
            return rss, hwm
    except Exception:
        return -1, -1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=0.5)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    args = ap.parse_args()
    if not args.cmd:
        ap.error("command required after --")
    # strip the leading "--" argparse leaves in REMAINDER
    if args.cmd[0] == "--":
        args.cmd = args.cmd[1:]

    out_fh = open(args.out, "a", encoding="utf-8") if args.out else None

    def emit(line: str) -> None:
        print(line, flush=True)
        if out_fh:
            out_fh.write(line + "\n")
            out_fh.flush()

    t0 = time.monotonic()
    emit(f"[watchdog] spawning: {' '.join(args.cmd)}")
    proc = subprocess.Popen(args.cmd)
    pid = proc.pid
    emit(f"[watchdog] pid={pid}")

    peak_rss = 0
    peak_hwm = 0
    try:
        while proc.poll() is None:
            rss, hwm = rss_kb(pid)
            if rss > 0:
                peak_rss = max(peak_rss, rss)
            if hwm > 0:
                peak_hwm = max(peak_hwm, hwm)
            emit(
                f"[watchdog] t={time.monotonic() - t0:7.1f}s "
                f"rss_kb={rss:>10,d} hwm_kb={hwm:>10,d}"
            )
            time.sleep(args.interval)
    finally:
        rc = proc.wait()
        rss, hwm = rss_kb(pid)
        emit(
            f"[watchdog] exit rc={rc} final_rss_kb={rss} peak_rss_kb={peak_rss} "
            f"peak_hwm_kb={peak_hwm} wall={time.monotonic() - t0:.1f}s"
        )
        if out_fh:
            out_fh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
