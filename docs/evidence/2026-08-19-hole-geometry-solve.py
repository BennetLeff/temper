"""Re-solve the per-pairing placement WITH the new hole-geometry constraints.

Rows, all at seed 42 against the committed board:

  E    per-pairing barrier, T1+T2 relaxed                 (the branch's row E)
  E+H  E + inter-component hole-to-hole
  E+G  E + hole-to-board-edge
  E+HG E + BOTH                                           (the row this emits)

Plus, when --ablate is passed and a barrier row is infeasible, the ablation
sweep that is the only route to an UNSAT core here (CP-SAT returns an empty
``SufficientAssumptionsForInfeasibility()`` on this model).

NO REQUIREMENT IS LOWERED HERE. ``per_pairing=True`` derives every barrier
setback from elec/insulation_manifest.yaml; ``hole_geometry={}`` passes NO
figure at all, so hole_geometry.py reads both from the tree
(scripts/generate_kicad_dru.py's generated DRU and pcb/temper.kicad_pro) and
would raise on any caller-supplied value that relaxed either. The two
relaxations are ``relax_isolator_straddle`` exemptions on T1 and T2 only --
the module's own documented ablation mechanism, exactly as row E of
docs/evidence/2026-08-19-per-pairing-placer-solve.md used it -- and both are
INTRA-PACKAGE shortfalls no placement can fix. Every downstream verdict is
CONDITIONAL on the SELV<->TANK and SELV<->SWITCHING figures being proven
floors, not requirements.

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
from temper_placer.placer.cp_sat.hole_geometry import resolve_hole_requirements
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
    ap.add_argument("--rows", default="E,EH,EG,EHG")
    ap.add_argument("--emit-row", default="EHG")
    ap.add_argument("--ablate", action="store_true")
    args = ap.parse_args()

    reqs = resolve_hole_requirements()
    print("Hole figures READ from the tree (none authored here):")
    print(f"  hole_to_hole  {reqs.hole_to_hole_mm:.3f} mm  <- {reqs.hole_to_hole_source}")
    print(f"  hole_to_edge  {reqs.hole_to_edge_mm:.3f} mm  <- {reqs.hole_to_edge_source}")
    print("  fabricator-sourced: "
          f"hole_to_hole={reqs.hole_to_hole_fab_sourced} "
          f"hole_to_edge={reqs.hole_to_edge_fab_sourced}  "
          "(NEITHER figure is traceable to a JLCPCB document in-tree)\n")

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

    def run(label, *, relaxed=("T1", "T2"), h2h=False, edge=False, barrier=True):
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
        if h2h or edge:
            kwargs["hole_geometry"] = {
                "enforce_hole_to_hole": h2h,
                "enforce_hole_to_edge": edge,
            }
        start = time.time()
        result = solve_placement(**kwargs)
        wall = time.time() - start
        rep = getattr(result, "hole_geometry_report", None)
        extra = f"  [{rep.summary()}]" if rep is not None else ""
        print(f"  {label:46s} -> {result.status:12s} ({wall:6.1f}s, "
              f"{len(result.positions)} placed){extra}")
        return result

    rows = {r.strip() for r in args.rows.split(",") if r.strip()}
    results: dict[str, object] = {}
    spec = {
        "E":   ("E    barrier only (branch row E)",           False, False),
        "EH":  ("E+H  + inter-component hole-to-hole",         True,  False),
        "EG":  ("E+G  + hole-to-board-edge",                   False, True),
        "EHG": ("E+HG + BOTH hole families",                   True,  True),
    }
    for key in ("E", "EH", "EG", "EHG"):
        if key not in rows:
            continue
        label, h2h, edge = spec[key]
        results[key] = run(label, h2h=h2h, edge=edge)

    print("\n" + "=" * 78)
    for key, res in results.items():
        print(f"{key:4s}  {res.status:12s}  {len(res.positions)} placed")
    print("=" * 78)

    emit = results.get(args.emit_row)
    if emit is None:
        raise SystemExit(f"--emit-row {args.emit_row} was not run")

    if emit.status not in SAT and args.ablate:
        print("\nINFEASIBLE -- ablating (SufficientAssumptionsForInfeasibility is "
              "empty on this model, so ablation is the only route to a core)")
        _, h2h, edge = spec[args.emit_row]
        print("  drop the barrier entirely:")
        run("    hole families alone, no barrier", h2h=h2h, edge=edge, barrier=False)
        print("  relax each additional isolator on top of T1+T2:")
        for extra_ref in ("T3", "T4", "U1", "U2", "K1", "K2", "K3", "C6", "U6"):
            run(f"    T1,T2,{extra_ref} relaxed",
                relaxed=("T1", "T2", extra_ref), h2h=h2h, edge=edge)

    if not setbacks.all_determinable:
        print("\nCONDITIONAL: the TANK and SWITCHING setbacks are PROVEN FLOORS, not")
        print("requirements. A SAT verdict certifies the floor was cleared; it does")
        print("NOT certify compliance, which needs IEC 60664-4 (unobtained).")

    if emit.status not in SAT:
        raise SystemExit(f"row {args.emit_row} did not solve: {emit.status}")

    rep = emit.hole_geometry_report
    payload = {
        "provenance": {
            "board_sha256_expected": (
                "26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b"
            ),
            "status": emit.status,
            "row": args.emit_row,
            "relaxed_isolator_straddle": ["T1", "T2"],
            "seed": args.seed,
            "per_pairing_setbacks": setbacks.setback_mm,
            "all_determinable": setbacks.all_determinable,
            "hole_to_hole_mm": rep.requirements.hole_to_hole_mm if rep else None,
            "hole_to_edge_mm": rep.requirements.hole_to_edge_mm if rep else None,
            "hole_to_hole_source": rep.requirements.hole_to_hole_source if rep else None,
            "hole_to_edge_source": rep.requirements.hole_to_edge_source if rep else None,
            "hole_pairs_constrained": rep.pairs_constrained if rep else 0,
            "hole_edge_refs": len(rep.edge_constrained_refs) if rep else 0,
        },
        "positions": {ref: list(xy) for ref, xy in emit.positions.items()},
        "rotations": dict(emit.rotations),
    }
    args.emit.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nrow-{args.emit_row} placement written to {args.emit} "
          "(scratch only -- board untouched)")


if __name__ == "__main__":
    main()
