#!/usr/bin/env python3
"""Transport board-bound copper evidence to the Rust plan-view barrier gate.

    python3 tools/barrier_check.py copper.json [--floor 8.0]

The provisional 8 mm HOT-to-SELV/PE screen includes every copper layer.
The Rust checker owns copper geometry, net classification, and the verdict.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import write_rules  # noqa: E402

SCHEMA = "temper.power-stage-120v.copper-evidence.v1"
UNIT = Path(__file__).resolve().parents[1]
ZAPOTE = UNIT.parent


def check(evidence: dict, floor: float) -> dict:
    board_path = Path(evidence["board_path"])
    if not board_path.is_file() or hashlib.sha256(board_path.read_bytes()).hexdigest() != evidence["board_sha256"]:
        raise ValueError("copper evidence is stale or its board is missing")
    items = evidence["items"]
    digest = hashlib.sha256(json.dumps(items, sort_keys=True, separators=(",", ":"),
                                       allow_nan=False).encode()).hexdigest()
    if digest != evidence["items_sha256"]:
        raise ValueError("copper items differ from the evidence digest")
    selv = write_rules.audit_selv_nets(UNIT / "audit.rs") | write_rules.SELV_NC
    hot = set().union(*write_rules.HOT_GROUPS.values())
    payload = {"evidence": evidence, "floor_mm": floor,
               "domains": {"selv": sorted(selv), "hot": sorted(hot),
                           "pe": sorted(write_rules.PE)}}
    binary = os.environ.get("ZAPOTE_POWER_BARRIER_BIN")
    command = ([binary] if binary else [
        "cargo", "run", "--quiet", "--locked", "--manifest-path", str(ZAPOTE / "Cargo.toml"),
        "-p", "zapote-harness", "--bin", "zapote-power-barrier",
    ])
    result = subprocess.run(command, input=json.dumps(payload, allow_nan=False),
                            text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise ValueError(f"Rust barrier check rejected copper: {result.stderr.strip()}")
    if hashlib.sha256(board_path.read_bytes()).hexdigest() != evidence["board_sha256"]:
        raise ValueError("copper evidence became stale during Rust barrier check")
    return json.loads(result.stdout)


def main() -> None:
    if len(sys.argv) not in (2, 4) or (len(sys.argv) == 4 and sys.argv[2] != "--floor"):
        raise SystemExit("usage: barrier_check.py copper.json [--floor millimetres]")
    floor = float(sys.argv[3]) if len(sys.argv) == 4 else 8.0
    result = check(json.loads(Path(sys.argv[1]).read_text()), floor)
    print(json.dumps(result, indent=1))
    raise SystemExit(1 if result["violations"] else 0)


if __name__ == "__main__":
    main()
