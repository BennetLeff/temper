#!/usr/bin/env python3
"""K3 swap + board write — apply the Run-B (evidence-validated) candidate (wave-2, #523).

# provenance: commit=<filled-at-write-time> dirty=<bool>

Writes the solved placement from k3_swap_board_write_variantB_summary.json to
pcb/temper.kicad_pcb using the SAME application mechanism the re-solve
evidence doc used (k3_resolve_gated_drc.py): ``write_placements_to_pcb``
with the CP-SAT local frame -> absolute conversion (add board origin) and
the components list so bbox-center -> footprint-origin is handled by the
writer (rotation-aware center-offset subtraction).

WHY VARIANT B (not the production-caller Run A): ``run_clearance_repair_solve``
cannot express ``fixed_copper``, so its solve moved 166 refs and the written
board REGRESSED on DRC (measured total 1428-1437 vs ceiling 1356; clearance
458, creepage 211, solder_mask_bridge 206, silk_over_copper 199). The
evidence-validated candidate (docs/evidence/2026-08-01-k3-resolve-validator-
gated.md §4/§5, the wall-spike variant B: direct solve_placement with
``fixed_copper free_refs={K3,C27}``, margin 0.05, nothing else pinned) moves
K3/C27 while keeping every other ref as a fixed-copper obstacle, and the
written board measures 1262-1263 total errors vs the 1331 swap-only baseline
(--all-track-errors, DRU regenerated, canonical filename so kicad-cli
resolves the rules) -- a real improvement in every category. This is the
candidate the evidence doc said to write on GO.

Position-frame traps handled (handoff §6):
- the parser reports initial_position in the CP-SAT local frame (board
  origin subtracted, pad-centroid-shifted); the board file stores the
  footprint anchor in the absolute board frame, so solved positions get
  ``+ board.origin`` before writing (the pd2-resolve write convention,
  verified by its re-parse round trip).
- ``write_placements_to_pcb(components=...)`` subtracts the ROTATED center
  offset, converting bbox-center back to footprint-origin; this must match
  the parser's inverse (io/_parse_modules.py) or every off-centroid
  component lands shifted.

Verification after write (same script):
- re-parse the written board and confirm K3/C27 land at the solved
  positions (+ origin, minus center offset -> footprint anchor) within the
  model grid tolerance;
- re-run verify_iec60335_compliance on the real-board fixture against the
  WRITTEN board -> expect 0 violations, REQ-SAFE-01 0/0.

Usage:
    uv run --no-sync python docs/evidence/k3_swap_board_write_apply.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve()
while not (REPO / "pyproject.toml").exists():
    REPO = REPO.parent

_PLACER_DIR = REPO / "packages" / "temper-placer"
os.chdir(_PLACER_DIR)
sys.path.insert(0, str(_PLACER_DIR))

from temper_placer.io._write_board import (  # noqa: E402
    PlacementUpdate,
    write_placements_to_pcb,
)
from temper_placer.io.kicad_parser import parse_kicad_pcb  # noqa: E402

PCB = REPO / "pcb" / "temper.kicad_pcb"
SUMMARY = REPO / "docs" / "evidence" / "k3_swap_board_write_variantB_summary.json"
BACKUP = REPO / "pcb" / "temper.kicad_pcb.pre-write"


def main() -> None:
    summary = json.loads(SUMMARY.read_text())
    solved = summary["placement"]  # {ref: {position, rotation_idx}} local frame

    pcb = parse_kicad_pcb(PCB)
    board_origin = getattr(pcb.board, "origin", (0.0, 0.0))

    placements: dict[str, PlacementUpdate] = {}
    for ref, d in solved.items():
        placements[ref] = PlacementUpdate(
            ref=ref,
            # CP-SAT local frame -> absolute: add board origin (the pd2
            # resolve doc's write convention, verified by its re-parse
            # round trip).
            x=d["position"][0] + board_origin[0],
            y=d["position"][1] + board_origin[1],
            rotation=d["rotation_idx"] * 90.0,
        )

    # Backup the pre-write board for a byte-comparable "before" (never git
    # stash -- this is a plain file copy for the evidence doc).
    BACKUP.write_bytes(PCB.read_bytes())
    print(f"backed up pre-write board to {BACKUP.relative_to(REPO)}")

    write_result = write_placements_to_pcb(
        template_pcb=PCB,
        output_pcb=PCB,
        placements=placements,
        preserve_unmatched=True,
        components=pcb.netlist.components,
    )
    print(
        f"write: {write_result.components_updated} components updated, "
        f"{len(write_result.warnings)} warnings"
    )
    for w in write_result.warnings[:10]:
        print(f"  warning: {w}")

    # --- Round-trip verify: re-parse the written board.
    pcb2 = parse_kicad_pcb(PCB)
    cur = {c.ref: c.initial_position for c in pcb2.netlist.components}
    rot = {c.ref: c.initial_rotation for c in pcb2.netlist.components}
    print("\n=== ROUND-TRIP (written board re-parse) ===")
    for ref in ("K3", "C27"):
        solved_pos = solved[ref]["position"]
        parsed = cur.get(ref)
        if parsed is None:
            print(f"  {ref}: MISSING from written board!")
            continue
        dx = abs(parsed[0] - solved_pos[0])
        dy = abs(parsed[1] - solved_pos[1])
        ok = dx <= 0.02 and dy <= 0.02
        print(
            f"  {ref}: solved_local={solved_pos} rot={solved[ref]['rotation_idx']} "
            f"parsed={parsed} rot={rot.get(ref)} d=({dx:.3f},{dy:.3f}) {'OK' if ok else 'MISMATCH'}"
        )

    # All refs should round-trip within the 0.01mm model grid.
    bad = 0
    for ref, d in solved.items():
        parsed = cur.get(ref)
        if parsed is None:
            bad += 1
            print(f"  MISSING ref: {ref}")
            continue
        if abs(parsed[0] - d["position"][0]) > 0.02 or abs(parsed[1] - d["position"][1]) > 0.02:
            bad += 1
            print(
                f"  ROUND-TRIP FAIL {ref}: solved={d['position']} parsed={parsed} "
                f"d=({abs(parsed[0]-d['position'][0]):.3f},{abs(parsed[1]-d['position'][1]):.3f})"
            )
    print(f"round-trip: {len(solved)} refs checked, {bad} mismatches")

    # --- REQ-SAFE-01 on the WRITTEN board.
    from tests.requirements.safety._real_board_fixture import load_real_board_placement

    from temper_placer.requirements.validators.clearance import verify_iec60335_compliance

    placement, voltage_domains, stats = load_real_board_placement()
    result = verify_iec60335_compliance(placement, voltage_domains)
    print("\n=== REQ-SAFE-01 on WRITTEN board ===")
    print(f"  violations={result.error_count} pairs={len(result.violations)}")
    for v in result.violations[:10]:
        print(
            f"  {v.ref_a}<->{v.ref_b} {v.metric} {v.measured_mm if v.measured_mm else '?'} "
            f"< {v.required_mm} ({v.pair_kind})"
        )
    inter = [v for v in result.violations if v.pair_kind == "inter"]
    intra = [v for v in result.violations if v.pair_kind == "intra"]
    print(f"  inter={len(inter)} intra={len(intra)}")
    print(f"  REQ-SAFE-01 = {len(inter)}/{len(intra)}")


if __name__ == "__main__":
    main()
