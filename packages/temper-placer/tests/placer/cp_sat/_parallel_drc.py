"""Bounded-concurrency kicad-cli DRC runner shared by the trio of slow
DRC-measurement tests (plan 2026-08-03-001, U1).

The trio's DRC samples used to run in serial loops with silent
``pytest.skip`` on timeout or missing output. This helper replaces both
behaviors:

* Samples run under a concurrency bound — ``os.cpu_count()`` — instead
  of one-at-a-time.
* A failed DRC subprocess raises :class:`LoudDrcError` naming the label,
  the timeout, and the failure, instead of silently skipping green.

Timeout handling starts each subprocess in its own session
(``start_new_session=True``) so the whole process group can be killed on
timeout — ``subprocess.run(timeout=...)`` alone kills only the direct
child and leaves kicad-cli grandchildren orphaned.

Known, accepted deviation (plan KTD1): the bound is per-call-site. Under
the PR slow lane's ``-n auto`` xdist, two tests can each hold a pool of
``os.cpu_count()``, so up to 4 kicad-cli processes can run across the
runner's 2 cores during overlapping DRC phases. The measured per-call
latencies are far below the 600s/120s timeout ceilings, and loud
timeouts are the safety net — capping to ``cpu_count() // 2`` would
serialize the zone test's 3 samples per arm and defeat the purpose.
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import json
import os
import signal
import subprocess
import tempfile
from pathlib import Path


class LoudDrcError(Exception):
    """A DRC subprocess failed (timeout or missing output) loudly."""


def run_drc_loud(pcb_path: str | Path, *, timeout: int, label: str) -> dict:
    """Run one kicad-cli DRC and return the parsed JSON.

    Raises :class:`LoudDrcError` on timeout or missing output, naming
    ``label`` and ``timeout`` so the failure is attributable in the job
    log — never a silent skip that reports green.
    """
    drc_out_fd, drc_out_str = tempfile.mkstemp(suffix=".json")
    os.close(drc_out_fd)
    drc_out = Path(drc_out_str)
    try:
        proc = subprocess.Popen(
            [
                "kicad-cli",
                "pcb",
                "drc",
                "--format",
                "json",
                "-o",
                str(drc_out),
                str(pcb_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            raise LoudDrcError(
                f"{label}: kicad-cli pcb drc timed out after {timeout}s"
            ) from None
        proc_summary = (
            f"returncode={proc.returncode} "
            f"stdout={stdout.strip()[:300]!r} "
            f"stderr={stderr.strip()[:300]!r}"
        )

        if not drc_out.exists() or drc_out.stat().st_size == 0:
            raise LoudDrcError(
                f"{label}: kicad-cli DRC produced no output file: {proc_summary}"
            )
        try:
            with open(drc_out) as f:
                return json.load(f)
        except json.JSONDecodeError as exc:
            raise LoudDrcError(
                f"{label}: kicad-cli DRC produced invalid JSON: {proc_summary}"
            ) from exc
    finally:
        with contextlib.suppress(OSError):
            os.unlink(drc_out)


def run_drc_samples(
    pcb_path: str | Path, *, n: int, timeout: int, label: str
) -> list[dict]:
    """Run ``n`` DRC samples under concurrency bounded to the CPU count.

    Results preserve call order (one result per sample index). A failure
    in any sample raises :class:`LoudDrcError`; already-started samples
    are not cancelled (their subprocesses end with the CI container).
    """
    workers = min(os.cpu_count() or 1, n)
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    futures = [
        pool.submit(run_drc_loud, pcb_path, timeout=timeout, label=label)
        for _ in range(n)
    ]
    try:
        return [fut.result() for fut in futures]
    finally:
        for fut in futures:
            fut.cancel()
        pool.shutdown(wait=False, cancel_futures=True)
