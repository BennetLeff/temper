#!/usr/bin/env python3
"""Thin wrapper over Zapote's Rust fault-loop connectivity check.

The check itself lives in Rust — `zapote-erc::fault_loop`, exposed as the
`zapote-fault-loop` binary — per the project's convention that Rust owns
engineering rules and Python only transports. This file exists only to invoke
it; do not reintroduce the logic here.

The check is a **necessary connectivity check, and nothing more**: an element
can carry current in a declared loop only when at least two of its terminals lie
on that loop's nets. Two terminals on the loop's nets is *consistent with*
conduction. It does not prove a conductive path, a device state, a current
direction, or a current distribution, and peak current and energy distribution
stay unresolved wherever the model lacks defensible inputs.

Usage:
  check_fault_loop.py --netlist NETLIST.json --loop-nets A,B,C --assignments ASSIGNMENTS.json

Locate the binary with ZAPOTE_FAULT_LOOP_BIN, else on PATH, else at the shared
cargo target directory. Build it with:
  cd zapote && cargo build -p zapote-harness --bin zapote-fault-loop
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys


def binary_path() -> str | None:
    override = os.environ.get("ZAPOTE_FAULT_LOOP_BIN")
    if override:
        return override
    found = shutil.which("zapote-fault-loop")
    if found:
        return found
    # The build cache is shared across worktrees via CARGO_TARGET_DIR (the repo's
    # cargo wrapper derives it from the common git dir), so try that root first,
    # then a local target-shared.
    roots = []
    try:
        common = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, check=True,
            cwd=str(pathlib.Path(__file__).resolve().parents[1]),
        ).stdout.strip()
        if common:
            roots.append(pathlib.Path(common).parent)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    roots.append(pathlib.Path(__file__).resolve().parents[2])
    for root in roots:
        for profile in ("debug", "release"):
            candidate = root / "target-shared" / profile / "zapote-fault-loop"
            if candidate.exists():
                return str(candidate)
    return None


def main(argv: list[str]) -> int:
    binary = binary_path()
    if binary is None:
        print(
            "zapote-fault-loop not found; build it with:\n"
            "  cd zapote && cargo build -p zapote-harness --bin zapote-fault-loop\n"
            "or set ZAPOTE_FAULT_LOOP_BIN",
            file=sys.stderr,
        )
        return 2
    return subprocess.call([binary, *argv])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
