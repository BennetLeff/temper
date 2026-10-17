#!/usr/bin/env python3
"""Snapshot native-21's frozen netlist/BOM/resolved export as a read-only input.

native-21's authoritative source is on branch ``codex/power-stage-integration``
(not on this unit's base). This copies its ``frozen/`` outputs byte for byte
out of a pinned commit with ``git show`` and records the commit and hashes in
``inputs/native-21/provenance.json``. Nothing in zapote/power-stage-120v is
touched. ``verify_controller.py --provenance`` re-derives the bytes from git.

Usage: python3 tools/snapshot_native21.py [--commit SHA]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

UNIT = Path(__file__).resolve().parents[1]
REPO = UNIT.parents[1]
OUT = UNIT / "inputs" / "native-21"
DEFAULT_COMMIT = "7c55c9ab81260b396be266861a0f0e8a42f96a5f"  # codex/power-stage-integration head, 2026-10-08
FILES = (
    "zapote/power-stage-120v/frozen/default.net",
    "zapote/power-stage-120v/frozen/default.csv",
    "zapote/power-stage-120v/frozen/resolved-components.json",
)


def git_bytes(commit: str, path: str) -> bytes:
    return subprocess.run(["git", "show", f"{commit}:{path}"], cwd=REPO, check=True,
                          capture_output=True).stdout


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--commit", default=DEFAULT_COMMIT)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    record = {"schema": "temper.controller.native21-snapshot.v1",
              "branch": "codex/power-stage-integration", "commit": args.commit, "files": {}}
    for path in FILES:
        data = git_bytes(args.commit, path)
        (OUT / Path(path).name).write_bytes(data)
        record["files"][Path(path).name] = {"source": path, "sha256": hashlib.sha256(data).hexdigest()}
    (OUT / "provenance.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
