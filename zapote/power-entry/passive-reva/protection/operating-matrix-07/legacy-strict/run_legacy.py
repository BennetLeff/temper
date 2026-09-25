#!/usr/bin/env python3
"""Bounded diagnostic run of the frozen strict checker pipeline.

This wrapper records every child status and kills the process group on timeout
or disk-floor breach.  A strict-check rejection is expected evidence here and
is never converted into an acceptance result.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "faults/settled-direct-capture-38/F2-CREST"
OUT = Path(__file__).resolve().parent / "run"
RAW = CASE / "raw.trace.raw.gz"
PREFIX_END = "6.49999987987940120e-1"
MIN_FREE = 10 * 1024**3
TIMEOUT_S = 900.0
TOOLS = {
    "pigz": Path("/opt/homebrew/bin/pigz"),
    "decoder": Path("/private/tmp/matrix07-fault-native-decoder-parent"),
    "selector": Path("/private/tmp/matrix07-prefault-selector-parent"),
    "normalizer": Path("/private/tmp/matrix07-normalize"),
    "checker": Path("/private/tmp/matrix07-checker"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def free_bytes(path: Path) -> int:
    return os.statvfs(path).f_bavail * os.statvfs(path).f_frsize


def shell_path(path: Path) -> str:
    return shlex.quote(str(path))


def main() -> int:
    if OUT.exists() and any(OUT.iterdir()):
        raise SystemExit(f"refusing non-empty output directory: {OUT}")
    OUT.mkdir(parents=True, exist_ok=True)
    if free_bytes(OUT) < MIN_FREE:
        raise SystemExit("disk floor is below 10 GiB before launch")

    raw_before = sha256(RAW)
    tool_hashes = {name: sha256(path) for name, path in TOOLS.items()}
    command = "\n".join(
        [
            "set -o pipefail",
            f"{shell_path(TOOLS['pigz'])} -dc {shell_path(RAW)} 2> {shell_path(OUT / 'pigz.stderr')} | "
            f"{shell_path(TOOLS['decoder'])} --schema fault42 --byte-order little 2> {shell_path(OUT / 'decoder.stderr')} | "
            f"{shell_path(TOOLS['selector'])} - - {shell_path(OUT / 'selector.json')} .65 1e-6 2> {shell_path(OUT / 'selector.stderr')} | "
            f"{shell_path(TOOLS['normalizer'])} 190 2> {shell_path(OUT / 'normalizer.stderr')} | "
            f"{shell_path(TOOLS['checker'])} --end-s {PREFIX_END} > {shell_path(OUT / 'checker.stdout')} 2> {shell_path(OUT / 'checker.stderr')}",
            'codes=("${PIPESTATUS[@]}")',
            f"printf '%s\\n' \"${{codes[*]}}\" > {shell_path(OUT / 'pipeline.exit')}",
            'for code in "${codes[@]}"; do test "$code" -eq 0 || exit 1; done',
        ]
    )
    (OUT / "command.sh").write_text(command + "\n", encoding="utf-8")
    started = time.monotonic()
    child = subprocess.Popen(
        ["/bin/bash", "-c", command],
        cwd=OUT,
        start_new_session=True,
    )
    resource_stop: str | None = None
    timed_out = False
    while child.poll() is None:
        if free_bytes(OUT) < MIN_FREE:
            resource_stop = "disk_floor_breached"
            os.killpg(child.pid, signal.SIGTERM)
            break
        if time.monotonic() - started > TIMEOUT_S:
            timed_out = True
            os.killpg(child.pid, signal.SIGTERM)
            break
        time.sleep(1.0)
    try:
        returncode = child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        returncode = child.wait(timeout=10)
    raw_after = sha256(RAW)
    if raw_before != raw_after:
        raise SystemExit("raw capture changed during strict check")
    exit_text = (OUT / "pipeline.exit").read_text(encoding="utf-8").strip() if (OUT / "pipeline.exit").exists() else ""
    statuses = [int(value) for value in exit_text.split()] if exit_text else []
    checker_rejected = "time not strictly increasing" in (OUT / "checker.stderr").read_text(encoding="utf-8", errors="replace")
    receipt = {
        "status": "EXPECTED_STRICT_REJECTION" if checker_rejected else "DIAGNOSTIC_PIPELINE_COMPLETE",
        "accepted": False,
        "raw_before_sha256": raw_before,
        "raw_after_sha256": raw_after,
        "tool_sha256": tool_hashes,
        "pipeline_status_order": ["pigz", "decoder", "selector", "normalizer", "checker"],
        "pipeline_statuses": statuses,
        "wrapper_returncode": returncode,
        "checker_rejected_duplicate_time": checker_rejected,
        "timed_out": timed_out,
        "resource_stop": resource_stop,
        "max_seconds": TIMEOUT_S,
        "minimum_free_bytes": MIN_FREE,
        "prefix_end_s": PREFIX_END,
    }
    (OUT / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
