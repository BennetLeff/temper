#!/usr/bin/env python3
"""Snapshot native-21's frozen netlist/BOM/resolved export as a read-only input.

native-21's authoritative source is on branch ``claude/native21-s55-unified`` (stage 56)
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
DEFAULT_COMMIT = "f0c669a86b70ac270d36fa416fd75870c078974a"  # claude/native21-s55-unified: stage 56, the board of record (C51)
FILES = (
    "zapote/power-stage-120v/native-21/frozen/default.net",
    "zapote/power-stage-120v/native-21/frozen/default.csv",
    "zapote/power-stage-120v/native-21/frozen/resolved-components.json",
)


def git_bytes(commit: str, path: str) -> bytes:
    return subprocess.run(["git", "show", f"{commit}:{path}"], cwd=REPO, check=True,
                          capture_output=True).stdout


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--commit", default=DEFAULT_COMMIT)
    args = ap.parse_args()
    args.commit = subprocess.run(["git", "rev-parse", f"{args.commit}^{{commit}}"], cwd=REPO, check=True,
                                 capture_output=True, text=True).stdout.strip()
    OUT.mkdir(parents=True, exist_ok=True)
    record = {"schema": "temper.controller.native21-snapshot.v1",
              "branch": "claude/native21-s55-unified", "commit": args.commit, "files": {}}
    for path in FILES:
        data = git_bytes(args.commit, path)
        (OUT / Path(path).name).write_bytes(data)
        record["files"][Path(path).name] = {"source": path, "sha256": hashlib.sha256(data).hexdigest()}
    (OUT / "provenance.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
