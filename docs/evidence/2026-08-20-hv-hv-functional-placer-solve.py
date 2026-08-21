"""Does pricing HV<->HV functional creepage change the placer's feasibility?

THE QUESTION. ``docs/evidence/2026-08-19-per-pairing-placer-solve.md`` computed
the UNSAT core ``{T1, T2}`` with HV<->HV charged **0.0 mm** -- the barrier
family separates HV from SELV and says nothing about what happens inside the HV
pocket. Adding a real cost there may change the core, and the honest way to find
out is to re-solve, not to reason about it.

THE LADDER, each row a proven verdict or an explicit timeout:

  A   netclass (DRU-resolved) + tank creepage, no barrier          [the 2026-08-19 baseline]
  A+  A + HV<->HV functional                                       [does HV<->HV alone bind?]
  B   A + per-pairing isolation barrier, all 8 isolators           [reproduces `infeasible`]
  B+  B + HV<->HV functional
  E   B with {T1, T2} relaxed                                      [reproduces `optimal`, model E]
  E+  E + HV<->HV functional                                       [THE QUESTION]
  ablation (only when E+ is infeasible): drop one HV<->HV pairing family at a
      time to name which pairing carries the new infeasibility.

NO FIGURE IS LOWERED ANYWHERE IN THIS FILE. Every HV<->HV separation is derived
by ``hv_functional_creepage.hv_functional_separations()`` from
``elec/insulation_manifest.yaml`` through ``insulation.rs``; the module takes no
margin argument, so there is nothing here a solve could be made feasible by
turning down. The ablation rows below DROP a whole derived pairing family to
attribute an infeasibility -- they never shrink one.

SEVEN OF THE TEN HV<->HV PAIRINGS ARE PROVEN FLOORS, NOT REQUIREMENTS (47 kHz,
above IEC 60664-1 cl. 1.1.1's 30 kHz ceiling; IEC 60664-4 unobtained), as are
two of the four barrier crossings. So every SAT verdict below certifies that
the floors were cleared and **nothing more**; the harness prints that with the
result rather than leaving it to the reader.

Read-only: ``pcb/temper.kicad_pcb`` is parsed, never written.

    python docs/evidence/2026-08-20-hv-hv-functional-placer-solve.py
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
    hv_functional_separations,
)
from temper_placer.placer.cp_sat.isolation_barrier import barrier_setbacks
from temper_placer.placer.cp_sat.tank_creepage import DEFAULT_TANK_CREEPAGE_MM

logging.basicConfig(level=logging.ERROR)

MANIFEST = Path("elec/domain_manifest.yaml")
BOARD = Path("pcb/temper.kicad_pcb")
SAT = ("optimal", "feasible")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout-ms", type=int, default=600_000)
    ap.add_argument("--ablation-timeout-ms", type=int, default=240_000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--emit", type=Path, default=None)
    ap.add_argument("--skip-ablation", action="store_true")
    args = ap.parse_args()

    seps = hv_functional_separations()
    print("HV<->HV FUNCTIONAL figures encoded below -- derived, not written:")
    hdr = f"  {'pairing':24} {'Vrms':>7} {'table':>9} {'row':>10} {'floor':>7}  status"
    print(hdr)
    for key in sorted(seps):
        s = seps[key]
        status = "" if s.determinable else "PROVEN FLOOR ONLY (47 kHz, IEC 60664-4 unobtained)"
        print(f"  {key:24} {s.working_voltage_vrms:7.1f} {s.table:>9} "
              f"{s.voltage_range:>10} {s.floor_mm:7.2f}  {status}")
    print(f"  all_determinable = {all(s.determinable for s in seps.values())}\n")

    setbacks = barrier_setbacks()
    print("Per-HV-group barrier setbacks (unchanged from 2026-08-19):")
    for group in sorted(setbacks.setback_mm):
        flag = "" if setbacks.determinable[group] else "  [PROVEN FLOOR ONLY]"
        print(f"  {group:11s} {setbacks.setback_mm[group]:6.2f} mm  "
              f"({setbacks.governing_pairing[group]}){flag}")
    print()

    parsed = parse_kicad_pcb(BOARD)
    netlist, board = parsed.netlist, parsed.board
    hv_cons, report = generate_hv_functional_constraints(netlist)
    print(f"components = {len(netlist.components)}  board = {board.width} x {board.height} mm")
    print(f"HV<->HV component-pair constraints = {len(hv_cons)} over "
          f"{len({c.a for c in hv_cons} | {c.b for c in hv_cons})} HV components")
    print(f"HV<->HV INTRA-PACKAGE shortfalls (not encodable, placement-invariant) = "
          f"{len(report.intra_package)}")
    print(f"HighVoltage-family nets with NO declared figure = {len(report.undeclared)}\n")

    def run(label, *, barrier, hv_functional, relaxed=None, timeout_ms=None,
            drop_pairing=None):
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
        if hv_functional:
            # `drop_pairing` removes a WHOLE derived pairing family for
            # attribution. It never lowers a figure -- there is no figure
            # here a caller can lower. Membership is tested against the
            # constraint's own `governing_pairing` field, never by substring
            # search over prose: "MAINS<->MAINS" and "DC_BUS<->MAINS" share
            # a token, and this repo has already shipped one net-classifier
            # bug of exactly that shape (`1a7d1dde0`).
            keep = [
                c
                for c, req in zip(hv_cons, report.pair_requirements, strict=True)
                if drop_pairing is None or req.governing_pairing != drop_pairing
            ]
            kwargs["extra_constraints"] = keep
        start = time.time()
        result = solve_placement(**kwargs)
        wall = time.time() - start
        print(f"  {label:52s} -> {result.status:12s} ({wall:6.1f}s, "
              f"{len(result.positions)} placed)")
        return result

    print("A   netclass + tank creepage, no barrier, HV<->HV FREE (the 2026-08-19 baseline)")
    a = run("A", barrier=False, hv_functional=False)

    print("\nA+  the same, with HV<->HV functional priced")
    a_plus = run("A+", barrier=False, hv_functional=True)

    print("\nB   A + per-pairing barrier, all 8 isolators, HV<->HV FREE")
    b = run("B", barrier=True, hv_functional=False)

    print("\nB+  the same, with HV<->HV functional priced")
    b_plus = run("B+", barrier=True, hv_functional=True)

    print("\nE   B with {T1, T2} relaxed, HV<->HV FREE (model E)")
    e = run("E", barrier=True, hv_functional=False, relaxed=["T1", "T2"])

    print("\nE+  the same, with HV<->HV functional priced -- THE QUESTION")
    e_plus = run("E+", barrier=True, hv_functional=True, relaxed=["T1", "T2"])

    attribution: dict[str, str] = {}
    if a_plus.status == "infeasible" and not args.skip_ablation:
        print("\nATTRIBUTION -- drop ONE derived HV<->HV pairing family, keep every other")
        print("(a dropped family is REMOVED, never shrunk; this names the binding pairing)")
        for key in sorted(seps):
            r = run(f"A+ minus {key}", barrier=False, hv_functional=True,
                    drop_pairing=key, timeout_ms=args.ablation_timeout_ms)
            attribution[key] = r.status

    print("\n" + "=" * 78)
    print(f"A   no barrier,  HV<->HV free    {a.status}")
    print(f"A+  no barrier,  HV<->HV priced  {a_plus.status}")
    print(f"B   barrier,     HV<->HV free    {b.status}")
    print(f"B+  barrier,     HV<->HV priced  {b_plus.status}")
    print(f"E   barrier-T1T2,HV<->HV free    {e.status}")
    print(f"E+  barrier-T1T2,HV<->HV priced  {e_plus.status}")
    if attribution:
        print("\nsingle-family drops from A+:")
        for key, status in attribution.items():
            print(f"  A+ minus {key:24} {status}")
    print("=" * 78)
    print("CONDITIONAL: SEVEN of the ten HV<->HV pairings and two of the four barrier")
    print("crossings are PROVEN FLOORS, not requirements. A SAT verdict above certifies")
    print("the floors were cleared; it does NOT certify compliance, which needs")
    print("IEC 60664-4 (paywalled, unobtained).")

    winner = e_plus if e_plus.status in SAT else None
    if args.emit and winner is not None:
        payload = {
            "provenance": {
                "board_sha256_expected": (
                    "26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b"
                ),
                "status": winner.status,
                "relaxed_isolator_straddle": ["T1", "T2"],
                "seed": args.seed,
                "model": "E+",
                "hv_functional": {k: seps[k].floor_mm for k in sorted(seps)},
                "hv_functional_all_determinable": report.determinable,
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
