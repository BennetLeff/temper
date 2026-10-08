#!/usr/bin/env python3
"""Native-21 run of the repository's Rust plan-view barrier gate (tools/barrier_check.py).

    KICAD_PY tools/copper_dump.py <filled board> evidence.json
    python3 native-21/layout/barrier_gate21.py evidence.json [--floor 8.0]

tools/barrier_check.py classifies nets with the native-19 rule writer; native-21 has its
own net set, so this passes the same Rust checker the native-21 domains instead
(write_rules21.py via rules21: SELV, PE and every HOT potential group). Evidence format,
staleness checks and verdict are tools/barrier_check.py's.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(UNIT / "tools"))
import barrier_check  # noqa: E402
import rules21  # noqa: E402


def main() -> None:
    args = sys.argv[1:]
    floor = 8.0
    if "--floor" in args:
        floor = float(args[args.index("--floor") + 1])
    evidence = json.loads(Path(args[0]).read_text())
    board_path = Path(evidence["board_path"])
    if hashlib.sha256(board_path.read_bytes()).hexdigest() != evidence["board_sha256"]:
        raise SystemExit("copper evidence is stale or its board is missing")
    items = evidence["items"]
    digest = hashlib.sha256(json.dumps(items, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if digest != evidence["items_sha256"]:
        raise SystemExit("copper items differ from the evidence digest")
    payload = {"evidence": evidence, "floor_mm": floor,
               "domains": {"selv": sorted(rules21.SELV), "hot": sorted(rules21.GROUP), "pe": sorted(rules21.PE)}}
    binary = os.environ.get("ZAPOTE_POWER_BARRIER_BIN")
    command = [binary] if binary else ["cargo", "run", "--quiet", "--locked", "--manifest-path",
                                       str(barrier_check.ZAPOTE / "Cargo.toml"), "-p", "zapote-harness",
                                       "--bin", "zapote-power-barrier"]
    result = subprocess.run(command, input=json.dumps(payload, allow_nan=False), text=True,
                            capture_output=True, check=False)
    if result.returncode != 0:
        raise SystemExit(f"Rust barrier check rejected copper: {result.stderr.strip()}")
    print(result.stdout.strip())


if __name__ == "__main__":
    main()
