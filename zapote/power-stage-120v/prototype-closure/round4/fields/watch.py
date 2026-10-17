#!/usr/bin/env python3
"""Bound one local solver process group by observed RSS, elapsed time and swap.

macOS rejects RLIMIT_AS on this host; do not pretend ulimit imposed a ceiling.
Requires read-only ps/sysctl access. No process command strings are recorded.
"""

import argparse
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path


def swap_bytes() -> int:
    result = subprocess.run(
        ["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True, check=True
    )
    match = re.search(r"used = ([0-9.]+)([MG])", result.stdout)
    if not match:
        raise RuntimeError("cannot read swap usage")
    return int(float(match[1]) * (1024**2 if match[2] == "M" else 1024**3))


def swapout_bytes() -> int:
    """Cumulative pages written to swap; net used swap can hide paging churn."""
    result = subprocess.run(["vm_stat"], capture_output=True, text=True, check=True)
    size = re.search(r"page size of (\d+) bytes", result.stdout)
    pages = re.search(r"^Swapouts:\s+(\d+)\.", result.stdout, re.MULTILINE)
    if not size or not pages:
        raise RuntimeError("cannot read cumulative swap-out counter")
    return int(size[1]) * int(pages[1])


def tree_rss(pid: int) -> int:
    result = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,rss="], capture_output=True, text=True, check=True
    )
    rows = [tuple(map(int, line.split())) for line in result.stdout.splitlines()]
    owned = {pid}
    while True:
        next_owned = owned | {child for child, parent, _ in rows if parent in owned}
        if next_owned == owned:
            break
        owned = next_owned
    return 1024 * sum(rss for child, _, rss in rows if child in owned)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--rss-gib", type=float, default=8)
    parser.add_argument("--seconds", type=float, default=1800)
    parser.add_argument("--solver-result", type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or args.rss_gib <= 0 or args.seconds <= 0:
        raise ValueError("positive limits and a command are required")
    baseline = swap_bytes()
    initial_swapout = swapout_bytes()
    tree_rss(os.getpid())  # Fail before launch if ps is unavailable.
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    record = {"status": "RUNNING", "rss_limit_gib": args.rss_gib, "time_limit_s": args.seconds,
              "initial_used_swap_bytes": baseline, "initial_swapout_bytes": initial_swapout}
    args.receipt.write_text(json.dumps(record, indent=2) + "\n")
    start = time.monotonic()
    proc = subprocess.Popen(command, start_new_session=True)
    peak = 0
    peak_swap_growth = 0
    new_swapout = 0
    last_report = 0
    reason = None
    try:
        while proc.poll() is None:
            elapsed = time.monotonic() - start
            rss = tree_rss(proc.pid)
            peak = max(peak, rss)
            peak_swap_growth = max(peak_swap_growth, swap_bytes() - baseline)
            new_swapout = max(new_swapout, swapout_bytes() - initial_swapout)
            if rss > args.rss_gib * 1024**3:
                reason = "RSS_LIMIT"
            elif elapsed > args.seconds:
                reason = "TIME_LIMIT"
            elif peak_swap_growth > 256 * 1024**2:
                reason = "SYSTEM_SWAP_GROWTH_GT_256MiB"
            elif new_swapout > 256 * 1024**2:
                reason = "SYSTEM_SWAPOUT_GT_256MiB"
            if reason:
                break
            if elapsed - last_report >= 30:
                record.update(elapsed_s=elapsed, peak_tree_rss_gib=peak / 1024**3,
                              peak_used_swap_growth_bytes=peak_swap_growth, new_swapout_bytes=new_swapout)
                args.receipt.write_text(json.dumps(record, indent=2) + "\n")
                print(
                    json.dumps(
                        {"elapsed_s": round(elapsed), "tree_rss_gib": round(rss / 1024**3, 3)}
                    ),
                    flush=True,
                )
                last_report = elapsed
            time.sleep(2)
    except BaseException:
        reason = "MONITOR_ERROR"
        raise
    finally:
        if reason and proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
        record.update(
            status=reason or "COMPLETED",
            exit_code=proc.returncode,
            peak_tree_rss_gib=peak / 1024**3,
            elapsed_s=time.monotonic() - start,
            peak_used_swap_growth_bytes=peak_swap_growth,
            new_swapout_bytes=new_swapout,
        )
        args.receipt.write_text(json.dumps(record, indent=2) + "\n")
    if reason or proc.returncode:
        raise SystemExit(1)
    if args.solver_result:
        solved = json.loads(args.solver_result.read_text())
        if not solved.get("converged") or solved.get("exit_code") != 0:
            record.update(status="SOLVER_REJECTED", solver_converged=False)
            args.receipt.write_text(json.dumps(record, indent=2) + "\n")
            raise SystemExit("solver did not converge; a runner exit 0 is insufficient")
        record["solver_converged"] = True
        args.receipt.write_text(json.dumps(record, indent=2) + "\n")


if __name__ == "__main__":
    main()
