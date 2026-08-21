# provenance: commit=6bffbf4a72f03ae89cc48e85b1555d5fa1fd562d dirty=false
"""Resolve row E+ -- the one row the first ladder left ``unknown``.

``2026-08-20-hv-hv-functional-placer-solve.py`` proved five of its six rows and
timed out on the sixth: **E+**, the per-pairing barrier with ``{T1, T2}``
relaxed *plus* HV<->HV functional pricing, came back ``unknown`` at 600 s. An
``unknown`` is a TIMEOUT -- no proof in either direction -- and reporting it as
"the core grew" would be manufacturing a result out of a slow solve. This
harness gives that row a real budget and a warm start, and then, if it is SAT,
re-runs the isolator ablation *under the priced model* so the UNSAT core is
recomputed rather than inherited.

WHY A WARM START IS SOUND HERE. ``hint_positions`` feeds ``CpModel.AddHint()``.
A hint changes the ORDER CP-SAT searches in; it does not add, remove or weaken
a single constraint, so it cannot turn an infeasible model feasible. The hint
used is row **A+**'s placement -- the ``optimal`` solve of "netclass + tank
creepage + HV<->HV functional, no barrier" -- i.e. a placement already
satisfying every HV<->HV figure, which leaves the barrier as the only thing the
search must additionally satisfy. Both a hinted and an unhinted attempt are
run and both verdicts are printed; if they disagree in anything other than
wall time, that is itself the finding.

NO FIGURE IS LOWERED. Every HV<->HV separation and every barrier setback is
derived from ``elec/insulation_manifest.yaml``. The ablation relaxes an
ISOLATOR STRADDLE (the module's own ``relax_isolator_straddle`` exemption, the
same instrument ``2026-08-19-per-pairing-placer-solve.py`` used) -- it never
shrinks a millimetre.

    python docs/evidence/2026-08-20-hv-hv-functional-core-resolve.py \\
        --timeout-ms 3600000
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.placer.cp_sat.encoder import solve_placement
from temper_placer.placer.cp_sat.hv_functional_creepage import (
    generate_hv_functional_constraints,
)
from temper_placer.placer.cp_sat.isolation_barrier import barrier_setbacks
from temper_placer.placer.cp_sat.tank_creepage import DEFAULT_TANK_CREEPAGE_MM

logging.basicConfig(level=logging.ERROR)

MANIFEST = Path("elec/domain_manifest.yaml")
BOARD = Path("pcb/temper.kicad_pcb")
ISOLATORS = ["C6", "K1", "K2", "K3", "PS1", "T1", "T2", "U6"]
SAT = ("optimal", "feasible")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout-ms", type=int, default=3_600_000)
    ap.add_argument("--ablation-timeout-ms", type=int, default=900_000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--emit", type=Path, default=None)
    ap.add_argument("--skip-ablation", action="store_true")
    args = ap.parse_args()

    parsed = parse_kicad_pcb(BOARD)
    netlist, board = parsed.netlist, parsed.board
    hv_cons, report = generate_hv_functional_constraints(netlist)
    setbacks = barrier_setbacks()
    print(f"HV<->HV constraints = {len(hv_cons)}   "
          f"all_determinable = {report.determinable}")
    print(f"barrier setbacks    = "
          f"{ {k: round(v, 2) for k, v in sorted(setbacks.setback_mm.items())} }   "
          f"all_determinable = {setbacks.all_determinable}\n")

    def run(label, *, barrier, hv, relaxed=None, hint=None, timeout_ms=None):
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
        if hv:
            kwargs["extra_constraints"] = hv_cons
        if hint:
            kwargs["hint_positions"] = hint
        start = time.time()
        result = solve_placement(**kwargs)
        wall = time.time() - start
        print(f"  {label:46s} -> {result.status:12s} "
              f"({wall:7.1f}s, {len(result.positions)} placed)", flush=True)
        return result

    print("A+  no barrier, HV<->HV priced -- the warm-start source")
    a_plus = run("A+", barrier=False, hv=True)
    hint = None
    if a_plus.status in SAT:
        hint = {
            ref: (xy[0], xy[1], int(a_plus.rotations.get(ref, 0)))
            for ref, xy in a_plus.positions.items()
        }

    print("\nE+  barrier with {T1,T2} relaxed, HV<->HV priced -- WARM START from A+")
    e_plus_hinted = run("E+ (hinted)", barrier=True, hv=True,
                        relaxed=["T1", "T2"], hint=hint)

    print("\nE+  the same, COLD -- a hint must not change the verdict, only the time")
    e_plus_cold = run("E+ (cold)", barrier=True, hv=True, relaxed=["T1", "T2"])

    verdicts = {e_plus_hinted.status, e_plus_cold.status}
    decided = [s for s in verdicts if s in SAT or s == "infeasible"]
    e_plus_status = decided[0] if decided else "unknown"
    if len(set(decided)) > 1:
        print("\n!! HINTED AND COLD DISAGREE -- that is itself the finding, report both")

    core: list[str] = []
    undecided: list[str] = []
    necessity = None
    if e_plus_status in SAT and not args.skip_ablation:
        print("\nABLATION under the PRICED model -- only the named isolator enforced")
        print("(the UNSAT core is RECOMPUTED here, never inherited from the free model)")
        singles: dict[str, str] = {}
        for ref in ISOLATORS:
            r = run(f"only {ref}", barrier=True, hv=True,
                    relaxed=[x for x in ISOLATORS if x != ref],
                    hint=hint, timeout_ms=args.ablation_timeout_ms)
            singles[ref] = r.status
        # ONLY a proven `infeasible` is core membership. `unknown` is a
        # TIMEOUT, and counting it would manufacture core members out of a
        # slow solve.
        core = [ref for ref, s in singles.items() if s == "infeasible"]
        undecided = [ref for ref, s in singles.items() if s not in SAT and s != "infeasible"]
        print(f"\n  PROVEN individually contradictory: {core}")
        if undecided:
            print(f"  UNDECIDED (timed out, no proof either way): {undecided}")
            print("  -> the core below is a LOWER BOUND, not a complete core.")
        print("\n  necessity -- relax exactly those, enforce every other isolator:")
        necessity = run(f"relax {'+'.join(core) or '(none)'}", barrier=True, hv=True,
                        relaxed=core, hint=hint)

    print("\n" + "=" * 78)
    print(f"A+            {a_plus.status}")
    print(f"E+ hinted     {e_plus_hinted.status}")
    print(f"E+ cold       {e_plus_cold.status}")
    print(f"E+ VERDICT    {e_plus_status}")
    if core or necessity is not None:
        confirmed = (
            necessity is not None and necessity.status in SAT and not undecided
        )
        print(f"UNSAT core under the PRICED model: {core or 'empty'}   "
              f"({'CONFIRMED' if confirmed else 'NOT CONFIRMED'}; "
              f"necessity = {necessity.status if necessity else 'n/a'})")
    print("=" * 78)
    print("CONDITIONAL: SEVEN of ten HV<->HV pairings and two of four barrier crossings")
    print("are PROVEN FLOORS. A SAT verdict certifies the floors were cleared, never")
    print("compliance -- that needs IEC 60664-4 (paywalled, unobtained).")

    winner = e_plus_hinted if e_plus_hinted.status in SAT else (
        e_plus_cold if e_plus_cold.status in SAT else None
    )
    if args.emit and winner is not None:
        args.emit.write_text(
            json.dumps(
                {
                    "provenance": {
                        "board_sha256_expected": (
                            "26981fea2dbc425f456010d4d4e755"
                            "cdebdefee2b5355ad915086352b90c110b"
                        ),
                        "status": winner.status,
                        "model": "E+",
                        "relaxed_isolator_straddle": ["T1", "T2"],
                        "seed": args.seed,
                        "hv_functional_all_determinable": report.determinable,
                        "all_determinable": setbacks.all_determinable,
                    },
                    "positions": {r: list(v) for r, v in winner.positions.items()},
                    "rotations": dict(winner.rotations),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nplacement written to {args.emit} (scratch only -- board untouched)")


if __name__ == "__main__":
    main()
