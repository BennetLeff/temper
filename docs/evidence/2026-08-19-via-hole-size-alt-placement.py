#!/usr/bin/env python3
"""Solve a SECOND, materially-different placement at THIS branch's HEAD.

Why not the referenced `model-E`: that placement is produced by
`isolation_barrier.barrier_setbacks()` + `per_pairing=True`, which do not
exist on origin/main (they live on analysis/per-pairing-placer-solve) and
whose tank-creepage configuration is 20.0mm rather than HEAD's 10.0mm.
Reproducing it here would require merging that branch, which this task's
brief forbids. This harness therefore solves the closest HEAD-native
equivalent -- the same CP-SAT entry point, the same seed, the isolation
barrier enabled with T1/T2's isolator-straddle exemption -- so the second
board is a genuinely different, optimizer-produced placement rather than a
perturbation of the committed one.

Read-only with respect to pcb/temper.kicad_pcb.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import time
from pathlib import Path

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.placer.cp_sat.encoder import solve_placement
from temper_placer.placer.cp_sat.tank_creepage import DEFAULT_TANK_CREEPAGE_MM

logging.basicConfig(level=logging.ERROR)

BOARD = Path("pcb/temper.kicad_pcb")
MANIFEST = Path("elec/domain_manifest.yaml")
SAT = ("optimal", "feasible")

ap = argparse.ArgumentParser()
ap.add_argument("--timeout-ms", type=int, default=600_000)
ap.add_argument("--seed", type=int, default=42)
ap.add_argument("--emit", type=Path, required=True)
ap.add_argument("--barrier", action="store_true")
args = ap.parse_args()

before = hashlib.sha256(BOARD.read_bytes()).hexdigest()
print(f"board sha256 BEFORE {before}")

pr = parse_kicad_pcb(BOARD)
netlist, board = pr.netlist, pr.board
print(f"components={len(netlist.components)} board={board.width}x{board.height}mm")
print(f"tank creepage margin = {DEFAULT_TANK_CREEPAGE_MM}mm (HEAD default)")

kwargs: dict = {
    "netlist": netlist,
    "board": board,
    "timeout_ms": args.timeout_ms,
    "seed": args.seed,
    "tank_creepage": {"margin_mm": DEFAULT_TANK_CREEPAGE_MM},
}
if args.barrier:
    kwargs["isolation_barrier"] = {
        "manifest_path": MANIFEST,
        "orientation": "vertical",
        "relax_isolator_straddle": {"T1", "T2"},
    }
t0 = time.time()
res = solve_placement(**kwargs)
wall = time.time() - t0
print(f"status={res.status} wall={wall:.1f}s placed={len(res.positions)}")
if res.status not in SAT:
    raise SystemExit(f"solve did not succeed: {res.status}")

args.emit.write_text(
    json.dumps(
        {
            "provenance": {
                "board_sha256": before,
                "status": res.status,
                "seed": args.seed,
                "isolation_barrier": bool(args.barrier),
                "relaxed_isolator_straddle": ["T1", "T2"] if args.barrier else [],
                "tank_creepage_margin_mm": DEFAULT_TANK_CREEPAGE_MM,
            },
            "positions": {r: list(xy) for r, xy in res.positions.items()},
            "rotations": dict(res.rotations),
        },
        indent=2,
    ),
    encoding="utf-8",
)
after = hashlib.sha256(BOARD.read_bytes()).hexdigest()
print(f"board sha256 AFTER  {after}  ({'UNCHANGED' if after == before else 'MODIFIED!'})")
print(f"wrote {args.emit}")
