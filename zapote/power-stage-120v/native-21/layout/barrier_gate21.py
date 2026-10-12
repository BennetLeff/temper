#!/usr/bin/env python3
"""Native-21 run of the repository's Rust plan-view barrier gate (tools/barrier_check.py).

    KICAD_PY tools/copper_dump.py <filled board> evidence.json
    python3 native-21/layout/barrier_gate21.py evidence.json [--floor 8.0]

tools/barrier_check.py classifies nets with the native-19 rule writer; native-21 has its
own net set, so this passes the same Rust checker the native-21 domains instead
(write_rules21.py via rules21: SELV, PE and every HOT potential group). Evidence format,
staleness checks and verdict are tools/barrier_check.py's.

Stage 18 (DECISIONS items 7, 18): the same Rust checker also runs once per OUTER layer at 12.6 mm with
HOT = RES_A only, on a subset of the verified evidence (that layer's RES_A / SELV / PE items, census
recounted), so every reported pair is same-layer surface copper. Output: the 8.0 mm report with
"res_a_outer" {layer: report} and "res_a_outer_violations" added.
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

    def run(p):
        result = subprocess.run(command, input=json.dumps(p, allow_nan=False), text=True,
                                capture_output=True, check=False)
        if result.returncode != 0:
            raise SystemExit(f"Rust barrier check rejected copper: {result.stderr.strip()}")
        return json.loads(result.stdout)

    report = run(payload)
    barrier = rules21.SELV | rules21.PE
    report["res_a_outer"] = {}
    for lay in rules21.OUTER:
        sub = [{**it, "layers": [lay]} for it in items if lay in it["layers"]
               and (it["net"] in rules21.RES_A_NETS or it["net"] in barrier)]
        kinds = {k: sum(it["kind"] == k for it in sub) for k in ("pad", "track", "via", "zone")}
        census = {**evidence["census"], "pads": kinds["pad"], "tracks": kinds["track"], "vias": kinds["via"],
                  "zones": kinds["zone"], "filled_zone_polygons": kinds["zone"], "items": len(sub)}
        ev = {**evidence, "copper_layers": [lay], "census": census, "items": sub}
        nets = {it["net"] for it in sub}
        dom = {"selv": sorted(rules21.SELV & nets), "hot": sorted(rules21.RES_A_NETS & nets), "pe": sorted(rules21.PE)}
        report["res_a_outer"][lay] = run({"evidence": ev, "floor_mm": rules21.RES_A_CREEPAGE, "domains": dom})
    report["res_a_outer_violations"] = sum(r["violations"] for r in report["res_a_outer"].values())
    print(json.dumps(report))


if __name__ == "__main__":
    main()
