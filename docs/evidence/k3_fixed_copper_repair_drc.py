#!/usr/bin/env python3
"""DRC proxy for the issue #617 hoisted-caller solved placement.

# provenance: commit=a7dc2c5636121d5c0b18ef51c7eaadf4f8fe17b7 dirty=false (re-pointed from the pre-merge branch SHA, orphaned by squash-merge, to PR #653's merge commit -- issue #617)

Writes the solved placement (k3_fixed_copper_repair_solve_summary.json,
the run-B recipe through the hoisted run_clearance_repair_solve) to a
/tmp COPY of pcb/temper.kicad_pcb -- pcb/** stays untouched -- and
measures the same DRC gates the run-B doc used
(temper_placer.validation._drc_api.run_drc -> kicad-cli 10.0.4 with
--all-track-errors, N=5 samples for the nondeterministic categories).

The candidate is written under the board's CANONICAL FILENAME
(temper.kicad_pcb) with the regenerated temper.kicad_dru and a copy of
temper.kicad_pro beside it, so kicad-cli resolves the project DRU rules.
This is the apples-to-apples convention the wave-2 write doc established
(docs/evidence/2026-08-02-k3-swap-and-board-write.md Sec 4): a candidate
named "candidate.kicad_pcb" in /tmp has no DRU beside it and silently
drops the custom creepage/track_width categories, understating the total
by ~300. The baseline is measured at the committed board's canonical path
(same DRU resolution), so candidate vs baseline are directly comparable.

The gate this run serves: the hoisted caller must produce the Run-B-class
result -- error total well under the 1267 ceiling (the written board
itself measures ~1256-1263), never the Run-A-style 1428-1437 regression
(which was the pre-hoist caller moving 166 refs without fixed_copper).

NO src/ changes. pcb/temper.kicad_pcb is read-only.

Usage:
    export PYTHONPATH="$(pwd)/packages/temper-placer/src:$(pwd)/scripts"
    python3 docs/evidence/k3_fixed_copper_repair_drc.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "packages" / "temper-placer" / "src"))

import generate_kicad_dru  # noqa: E402

from temper_placer.io._write_board import (  # noqa: E402
    PlacementUpdate,
    write_placements_to_pcb,
)
from temper_placer.io.kicad_parser import parse_kicad_pcb  # noqa: E402
from temper_placer.validation._drc_api import run_drc  # noqa: E402

PCB = REPO / "pcb" / "temper.kicad_pcb"
SUMMARY = REPO / "docs" / "evidence" / "k3_fixed_copper_repair_solve_summary.json"
N_SAMPLES = 5

TARGET_RULES = (
    "shorting_items",
    "courtyards_overlap",
    "solder_mask_bridge",
    "hole_clearance",
    "clearance",
)


def measure(pcb_path: Path, label: str) -> dict[str, list[int]]:
    counts: dict[str, list[int]] = {r: [] for r in TARGET_RULES}
    totals: list[int] = []
    for _i in range(N_SAMPLES):
        res = run_drc(pcb_path)
        c = Counter(e.rule for e in res.errors)
        for r in TARGET_RULES:
            counts[r].append(c.get(r, 0))
        totals.append(res.error_count)
    print(f"[{label}] over {N_SAMPLES} samples (rule: min..max / last):")
    for r in TARGET_RULES:
        vals = counts[r]
        print(f"    {r:22s} min={min(vals)} max={max(vals)} last={vals[-1]}")
    print(f"    {'total_errors':22s} min={min(totals)} max={max(totals)} last={totals[-1]}")
    return counts


def main() -> None:
    summary = json.loads(SUMMARY.read_text())
    solved = summary["placement"]  # {ref: {position, rotation_idx}} local frame
    pcb = parse_kicad_pcb(PCB)

    # The candidate must be measured under the canonical stem with the
    # project DRU + .kicad_pro beside it (wave-2 Sec 4 convention) so
    # kicad-cli resolves the custom creepage/track_width rules.
    dru_content = generate_kicad_dru.generate_dru()
    print("=== BASELINE (unmodified board, canonical path, project DRU) ===")
    measure(PCB, "baseline")

    placements: dict[str, PlacementUpdate] = {}
    board_origin = getattr(pcb.board, "origin", (0.0, 0.0))
    for ref, d in solved.items():
        placements[ref] = PlacementUpdate(
            ref=ref,
            # CP-SAT local frame -> absolute: add board origin (the pd2
            # resolve doc's write convention, verified by its re-parse
            # round trip; without it the written board is shifted by
            # -origin and every DRC figure is measured on the wrong board).
            x=d["position"][0] + board_origin[0],
            y=d["position"][1] + board_origin[1],
            rotation=d["rotation_idx"] * 90.0,
        )

    with tempfile.TemporaryDirectory(prefix="k3_fc_repair_drc_") as tmp:
        tmpdir = Path(tmp)
        candidate_pcb = tmpdir / "temper.kicad_pcb"
        # Project DRU (regenerated -- CI gate's exact invocation) + project
        # settings beside the candidate so kicad-cli resolves them.
        (tmpdir / "temper.kicad_dru").write_text(dru_content, encoding="utf-8")
        shutil.copy(REPO / "pcb" / "temper.kicad_pro", tmpdir / "temper.kicad_pro")
        write_result = write_placements_to_pcb(
            template_pcb=PCB,
            output_pcb=candidate_pcb,
            placements=placements,
            preserve_unmatched=True,
            components=pcb.netlist.components,
        )
        print(f"\nwrite: {write_result.components_updated} components updated, "
              f"{len(write_result.warnings)} warnings")
        print("=== CANDIDATE (hoisted-caller solved placement, canonical /tmp copy) ===")
        measure(candidate_pcb, "candidate")


if __name__ == "__main__":
    main()
