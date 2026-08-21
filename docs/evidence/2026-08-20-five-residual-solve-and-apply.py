# provenance: commit=30edd0a93cd4843b16bcc361c53fb02727511231 dirty=false
# provenance: board sha256 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b
# Read-only with respect to pcb/temper.kicad_pcb: the board is the writer's
# TEMPLATE and never its output; its sha256 is asserted before and after. No
# threshold, ceiling, ratchet, allowlist or oracle is read for modification or
# written.
"""Re-solve rows B, D and E of `2026-08-19-per-pairing-placer-solve.md` and
apply row E to a SCRATCH board through the production write contract.

Rows B and D are re-run so row E is *shown* to be the strictest satisfiable
model rather than assumed to be:

    B  per-pairing barrier, all 8 isolators enforced   expected `infeasible`
    D  B with T1 alone relaxed                         expected `infeasible`
    E  B with T1 and T2 relaxed                        expected `optimal`

A placement from a relaxed solve measures what the board could do **if those
parts were replaced**; it is never a claim that the board complies as built.
The script refuses to emit if a stricter row turns out to be satisfiable.

NO REQUIREMENT IS LOWERED HERE. `per_pairing=True` derives every setback from
`elec/insulation_manifest.yaml` and refuses a caller-supplied
`corridor_width_mm`. Two of the four barrier-crossing figures (SWITCHING 8.0,
TANK 20.0) are PROVEN FLOORS, not requirements -- 47 kHz is above IEC 60664-1
cl. 1.1.1's 30 kHz ceiling and cl. 2.3 routes dimensioning above it to the
unobtained IEC 60664-4 -- so every verdict that depends on them is
CONDITIONAL, and clearing a floor is not compliance.

Usage (from the repo root, in this worktree's own venv):

    python docs/evidence/2026-08-20-five-residual-solve-and-apply.py \
        --emit /tmp/rowE.json --out /tmp/model_e.kicad_pcb
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.kicad_writer import PlacementUpdate, write_placements_to_pcb
from temper_placer.placer.cp_sat.encoder import solve_placement
from temper_placer.placer.cp_sat.isolation_barrier import barrier_setbacks
from temper_placer.placer.cp_sat.tank_creepage import DEFAULT_TANK_CREEPAGE_MM
from temper_placer.validation.placement_roundtrip import check_placement_roundtrip

logging.basicConfig(level=logging.ERROR)

MANIFEST = Path("elec/domain_manifest.yaml")
BOARD = Path("pcb/temper.kicad_pcb")
EXPECTED = "26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b"
SAT = ("optimal", "feasible")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout-ms", type=int, default=600_000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--emit", type=Path, required=True, help="row-E placement JSON (scratch)")
    ap.add_argument("--out", type=Path, required=True, help="row-E .kicad_pcb (scratch)")
    args = ap.parse_args()

    if args.out.resolve() == BOARD.resolve():
        raise SystemExit("refusing to write the committed board")

    before = hashlib.sha256(BOARD.read_bytes()).hexdigest()
    print(f"board sha256 BEFORE: {before}")
    if before != EXPECTED:
        raise SystemExit("board is not the pinned revision")

    sb = barrier_setbacks()
    print("setbacks EXECUTED from elec/insulation_manifest.yaml, not quoted:")
    for g in sorted(sb.setback_mm):
        flag = "" if sb.determinable[g] else "  [PROVEN FLOOR ONLY]"
        print(f"  {g:11s} {sb.setback_mm[g]:6.2f} mm  ({sb.governing_pairing[g]}){flag}")
    print(f"  all_determinable = {sb.all_determinable}\n")

    parsed = parse_kicad_pcb(BOARD)
    netlist, board = parsed.netlist, parsed.board
    print(f"components = {len(netlist.components)}  board = {board.width} x {board.height} mm")
    print(f"board.origin = {board.origin}\n")

    def run(label: str, relaxed: list[str]):
        t0 = time.time()
        res = solve_placement(
            netlist=netlist,
            board=board,
            timeout_ms=args.timeout_ms,
            seed=args.seed,
            tank_creepage={"margin_mm": DEFAULT_TANK_CREEPAGE_MM},
            isolation_barrier={
                "manifest_path": MANIFEST,
                "orientation": "vertical",
                "per_pairing": True,
                "relax_isolator_straddle": set(relaxed),
            },
        )
        print(f"  {label:44s} -> {res.status:12s} ({time.time() - t0:6.1f}s, "
              f"{len(res.positions)} placed)")
        return res

    b = run("B: nothing relaxed", [])
    d = run("D: T1 alone relaxed", ["T1"])
    e = run("E: T1 and T2 relaxed", ["T1", "T2"])

    if b.status in SAT or d.status in SAT:
        raise SystemExit("a STRICTER model is satisfiable -- row E is not the right placement")
    if e.status not in SAT:
        raise SystemExit(f"row E did not solve: {e.status} -- refusing to report a placement")

    positions = {ref: (float(xy[0]), float(xy[1])) for ref, xy in e.positions.items()}
    rotations = {ref: int(r) for ref, r in e.rotations.items()}
    args.emit.write_text(
        json.dumps(
            {
                "provenance": {
                    "board_sha256_expected": EXPECTED,
                    "status": e.status,
                    "relaxed_isolator_straddle": ["T1", "T2"],
                    "seed": args.seed,
                    "per_pairing_setbacks": sb.setback_mm,
                    "all_determinable": sb.all_determinable,
                    "row_b_status": b.status,
                    "row_d_status": d.status,
                },
                "positions": {ref: list(xy) for ref, xy in positions.items()},
                "rotations": rotations,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nrow E written to {args.emit}")

    placements = {
        ref: PlacementUpdate(ref=ref, x=xy[0], y=xy[1], rotation=rotations.get(ref, 0) * 90.0)
        for ref, xy in positions.items()
    }
    res = write_placements_to_pcb(
        template_pcb=BOARD,
        output_pcb=args.out,
        placements=placements,
        preserve_unmatched=True,
        components=netlist.components,
        # parse_kicad_pcb defaulted to normalize=True, which subtracted
        # board.origin before the solve -- reverse it so the written anchors
        # land in the template's absolute frame.
        board_origin=board.origin,
    )
    skipped = len(placements) - res.components_updated
    print(f"write: {res.components_updated} updated / {skipped} skipped, "
          f"{len(res.warnings)} warning(s)")
    for w in res.warnings[:10]:
        print("  warning:", w)
    if res.components_updated != len(placements):
        raise SystemExit("not every solved component was written")

    # The round-trip oracle compares against the FILE frame, so the same
    # board_origin the writer added must be added here too.
    ox, oy = board.origin
    rt = check_placement_roundtrip(
        args.out,
        {ref: (x + ox, y + oy) for ref, (x, y) in positions.items()},
        {ref: rotations.get(ref, 0) * 90.0 for ref in positions},
        netlist.components,
    )
    print(f"round-trip oracle: {'PASS' if rt.passed else 'FAIL'} -- {rt.summary}")
    if not rt.passed:
        raise SystemExit("round-trip oracle FAILED")

    cont = subprocess.run(
        [sys.executable, "scripts/check_board_containment.py", "--board", str(args.out)],
        capture_output=True,
        text=True,
        check=False,
    )
    print(f"containment: rc={cont.returncode}\n{(cont.stdout or '').strip()[-2000:]}")
    if cont.returncode != 0:
        print((cont.stderr or "").strip()[-2000:])
        raise SystemExit("containment FAILED")

    after = hashlib.sha256(BOARD.read_bytes()).hexdigest()
    print(f"\nboard sha256 AFTER : {after}")
    if after != before:
        raise SystemExit("BOARD WAS MODIFIED -- aborting")
    print(f"scratch board {args.out} sha256 "
          f"{hashlib.sha256(args.out.read_bytes()).hexdigest()}")
    if not sb.all_determinable:
        print("\nCONDITIONAL: the TANK and SWITCHING setbacks are PROVEN FLOORS, not")
        print("requirements. A SAT verdict certifies the floor was cleared; it does")
        print("NOT certify compliance, which needs IEC 60664-4 (unobtained).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
