"""Run the CP-SAT placer with the PER-PAIRING creepage barrier wired, and
extract the UNSAT core by ablation if it is infeasible.

Three solves plus an ablation sweep:

  A  netclass (DRU-resolved) + tank creepage, NO barrier      -- the baseline
  B  A + the per-pairing isolation barrier, all 8 isolators   -- the question
  C  ablation: one isolator enforced at a time, then the core relaxed
  D  B with T1 alone relaxed                                  -- "is T1 the
                                                                 only obstacle?"

WHY ABLATION AND NOT THE SOLVER'S OWN CORE. `SufficientAssumptionsForInfeasibility()`
comes back EMPTY here -- the infeasibility does not depend on the assumption
literals, because each isolator's rotation pin is a plain `Add`. So the core is
recovered by switching individual straddle constraints off with the module's own
`relax_isolator_straddle` exemption and watching the verdict flip. Same method as
`2026-08-19-barrier-unsat-core-ablation.py`, at the per-pairing figures.

NO REQUIREMENT IS LOWERED ANYWHERE IN THIS FILE. `per_pairing=True` derives every
setback from `elec/insulation_manifest.yaml`; the module refuses a caller-supplied
`corridor_width_mm` alongside it. Two of the four barrier-crossing figures are
PROVEN FLOORS, not requirements (47 kHz, above IEC 60664-1's 30 kHz ceiling;
IEC 60664-4 not obtained), so every verdict that depends on them is CONDITIONAL --
the harness prints that with each result rather than leaving it to the reader.

Read-only: `pcb/temper.kicad_pcb` is parsed, never written. A solved placement is
written to `--emit` only if asked, and never to the board.

Run from the repo root:

    python docs/evidence/2026-08-19-per-pairing-placer-solve.py
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

#: Every component whose own pads bridge an HV and a SELV net, per
#: elec/domain_manifest.yaml. Enumerated rather than discovered so the ablation
#: set is explicit and reviewable -- same list the 12.6mm ablation used.
ISOLATORS = ["C6", "K1", "K2", "K3", "PS1", "T1", "T2", "U6"]

SAT = ("optimal", "feasible")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout-ms", type=int, default=600_000)
    ap.add_argument("--ablation-timeout-ms", type=int, default=180_000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--emit", type=Path, default=None, help="write the solved placement here (JSON)")
    ap.add_argument("--skip-ablation", action="store_true")
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

    def run(label: str, *, barrier: bool, relaxed: list[str] | None = None,
            timeout_ms: int | None = None):
        kwargs: dict = {
            "netlist": netlist,
            "board": board,
            "timeout_ms": timeout_ms or args.timeout_ms,
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
        print(f"  {label:48s} -> {result.status:12s} ({wall:6.1f}s, "
              f"{len(result.positions)} placed)")
        return result

    print("A  netclass (DRU-resolved) + tank creepage, NO barrier")
    a = run("A: no barrier", barrier=False)

    print("\nB  + per-pairing isolation barrier, all 8 isolators enforced")
    b = run("B: per-pairing barrier, nothing relaxed", barrier=True)

    print("\nD  B with T1 alone relaxed")
    d = run("D: per-pairing barrier, T1 relaxed", barrier=True, relaxed=["T1"])

    core: list[str] = []
    necessity = None
    if b.status == "infeasible" and not args.skip_ablation:
        print("\nC  ablation -- only the named isolator enforced, all others relaxed:")
        singles = {}
        for ref in ISOLATORS:
            r = run(f"only {ref}", barrier=True,
                    relaxed=[x for x in ISOLATORS if x != ref],
                    timeout_ms=args.ablation_timeout_ms)
            singles[ref] = r.status
        # ONLY a proven `infeasible` is core membership. `unknown` is a
        # TIMEOUT -- no proof in either direction -- and counting it as
        # contradictory would manufacture core members out of a slow solve.
        # Reported separately and loudly rather than folded in.
        core = [ref for ref, s in singles.items() if s == "infeasible"]
        undecided = [ref for ref, s in singles.items() if s not in SAT and s != "infeasible"]
        print(f"\n  PROVEN individually contradictory: {core}")
        if undecided:
            print(f"  UNDECIDED (timed out, no proof either way): {undecided}")
            print("  -> the core below is a LOWER BOUND; re-run these with a longer "
                  "--ablation-timeout-ms before treating it as complete.")
        print("\n  necessity check -- relax exactly those, enforce every other isolator:")
        necessity = run(f"relax {'+'.join(core) or '(none)'}", barrier=True, relaxed=core)
        confirmed = necessity.status in SAT and not undecided
        print(f"\n  CORE {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}: "
              f"{core if core else 'empty'} (necessity solve: {necessity.status})")

    print("\n" + "=" * 78)
    print(f"A (no barrier)               {a.status}")
    print(f"B (barrier, nothing relaxed) {b.status}")
    print(f"D (barrier, T1 relaxed)      {d.status}")
    if core:
        print(f"UNSAT core                   {core}")
    print("=" * 78)
    if not setbacks.all_determinable:
        print("CONDITIONAL: the TANK and SWITCHING setbacks are PROVEN FLOORS, not")
        print("requirements. A SAT verdict above certifies the floor was cleared; it")
        print("does NOT certify compliance, which needs IEC 60664-4 (unobtained).")

    # Emit the STRICTEST solve that is actually SAT: nothing relaxed if that
    # worked, else T1 alone, else exactly the proven core. Recording which one
    # produced the placement is not optional -- a placement from a relaxed
    # solve is a measurement of what the board could do if those parts were
    # replaced, never a claim that it complies as built.
    candidates = [(b, []), (d, ["T1"]), (necessity, core)]
    winner, relaxed_for_winner = None, []
    for result, relaxed in candidates:
        if result is not None and result.status in SAT:
            winner, relaxed_for_winner = result, relaxed
            break
    if args.emit and winner is not None:
        print(f"\nemitting the solve with relaxed = {relaxed_for_winner or '(none)'}")
        payload = {
            "provenance": {
                "board_sha256_expected": (
                    "26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b"
                ),
                "status": winner.status,
                "relaxed_isolator_straddle": relaxed_for_winner,
                "seed": args.seed,
                "per_pairing_setbacks": setbacks.setback_mm,
                "all_determinable": setbacks.all_determinable,
            },
            "positions": {ref: list(xy) for ref, xy in winner.positions.items()},
            "rotations": dict(winner.rotations),
        }
        args.emit.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nplacement written to {args.emit} (scratch only -- the board is untouched)")


if __name__ == "__main__":
    main()
