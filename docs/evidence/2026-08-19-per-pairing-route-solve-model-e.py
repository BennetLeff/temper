# provenance: commit=de3e5dabe65f2ac01680b59dfb0ece2a130b4770 dirty=false
# Measurements taken at this commit (barrier 20.0mm configuration) and at
# fd4e73644fec24b26a0c0c4ec51f5c7573c151e4 (barrier 12.6mm configuration),
# working tree clean in both. See
# docs/evidence/2026-08-19-per-pairing-placement-routed.md
"""Reproduce rows A/B/D/E of docs/evidence/2026-08-19-per-pairing-placer-solve.md
and emit the row-E placement.

This is the committed harness's own call path, restricted to the four headline
rows (no ablation sweep) and with the emit forced to row E so the routed board
below is unambiguously the `optimal` T1+T2-relaxed solve.

NO REQUIREMENT IS LOWERED HERE. `per_pairing=True` derives every setback from
elec/insulation_manifest.yaml. The two relaxations are `relax_isolator_straddle`
exemptions on T1 and T2 only -- the module's own documented ablation mechanism,
exactly as row E of the evidence table used it -- and both are INTRA-PACKAGE
shortfalls no placement can fix. Every downstream verdict is CONDITIONAL on the
SELV<->TANK and SELV<->SWITCHING figures being proven floors, not requirements.

Read-only with respect to pcb/temper.kicad_pcb.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.placer.cp_sat.encoder import solve_placement
from temper_placer.placer.cp_sat.isolation_barrier import barrier_setbacks
from temper_placer.placer.cp_sat.tank_creepage import DEFAULT_TANK_CREEPAGE_MM

logging.basicConfig(level=logging.ERROR)

MANIFEST = Path("elec/domain_manifest.yaml")
BOARD = Path("pcb/temper.kicad_pcb")
SAT = ("optimal", "feasible")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout-ms", type=int, default=600_000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--emit", type=Path, required=True)
    ap.add_argument("--rows", default="ABDE")
    args = ap.parse_args()

    setbacks = barrier_setbacks()
    print("Per-HV-group setbacks encoded by every barrier solve below:")
    for group in sorted(setbacks.setback_mm):
        flag = "" if setbacks.determinable[group] else "  [PROVEN FLOOR ONLY]"
        print(f"  {group:11s} {setbacks.setback_mm[group]:6.2f} mm  "
              f"({setbacks.governing_pairing[group]}){flag}")
    print(f"  all_determinable = {setbacks.all_determinable}\n")

    parse_result = parse_kicad_pcb(BOARD)
    netlist, board = parse_result.netlist, parse_result.board
    print(f"components = {len(netlist.components)}  "
          f"board = {board.width} x {board.height} mm\n")

    def run(label, *, barrier, relaxed=None):
        kwargs: dict = {
            "netlist": netlist,
            "board": board,
            "timeout_ms": args.timeout_ms,
            "seed": args.seed,
            "tank_creepage": {"margin_mm": DEFAULT_TANK_CREEPAGE_MM},
        }
        if barrier:
            kwargs["isolation_barrier"] = {
                "manifest_path": MANIFEST,
                "orientation": "vertical",
                "per_pairing": True,
                "relax_isolator_straddle": set(relaxed or ()),
            }
        start = time.time()
        result = solve_placement(**kwargs)
        wall = time.time() - start
        print(f"  {label:52s} -> {result.status:12s} ({wall:6.1f}s, "
              f"{len(result.positions)} placed)")
        return result

    results = {}
    if "A" in args.rows:
        print("A  netclass (DRU-resolved) + tank creepage, NO barrier")
        results["A"] = run("A: no barrier", barrier=False)
    if "B" in args.rows:
        print("\nB  + per-pairing isolation barrier, all 8 isolators enforced")
        results["B"] = run("B: per-pairing barrier, nothing relaxed", barrier=True)
    if "D" in args.rows:
        print("\nD  B with T1 alone relaxed")
        results["D"] = run("D: per-pairing barrier, T1 relaxed", barrier=True, relaxed=["T1"])
    print("\nE  B with T1 AND T2 relaxed  (the row this session routes)")
    results["E"] = run("E: per-pairing barrier, T1+T2 relaxed", barrier=True,
                       relaxed=["T1", "T2"])

    e = results["E"]
    print("\n" + "=" * 78)
    for row in "ABDE":
        if row in results:
            print(f"{row}  {results[row].status:12s}  {len(results[row].positions)} placed")
    print("=" * 78)
    if not setbacks.all_determinable:
        print("CONDITIONAL: the TANK and SWITCHING setbacks are PROVEN FLOORS, not")
        print("requirements. A SAT verdict certifies the floor was cleared; it does")
        print("NOT certify compliance, which needs IEC 60664-4 (unobtained).")

    if e.status not in SAT:
        raise SystemExit(f"row E did not solve: {e.status} -- NOT reproduced")

    payload = {
        "provenance": {
            "board_sha256_expected": (
                "26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b"
            ),
            "status": e.status,
            "relaxed_isolator_straddle": ["T1", "T2"],
            "seed": args.seed,
            "per_pairing_setbacks": setbacks.setback_mm,
            "all_determinable": setbacks.all_determinable,
        },
        "positions": {ref: list(xy) for ref, xy in e.positions.items()},
        "rotations": dict(e.rotations),
    }
    args.emit.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nrow-E placement written to {args.emit} (scratch only -- board untouched)")


if __name__ == "__main__":
    main()
