#!/usr/bin/env python3
"""DRC gate measurement for the K3/tank3 solved-placement candidate (issue #523).

# provenance: commit=87df36a223472967624648372bde8a21c61ba02a dirty=false

Writes the solved placement (variant B summary JSON) to a /tmp COPY of
pcb/temper.kicad_pcb -- pcb/** stays untouched, read-only -- and measures
the handoff §1 DRC gates with the same tool the run-B doc used
(temper_placer.validation._drc_api.run_drc -> kicad-cli 10.0.4 with
--all-track-errors, the reproducible invocation per _drc_api.py's own
comment). Also runs the same DRC on the UNMODIFIED board for a same-tool
baseline, so candidate vs baseline are directly comparable.

Gates (handoff §1 / run-B doc):
  - REQ-SAFE-01      <= 3 violations / 1 pair (measured separately in
                       k3_resolve_gated_gates.py; reported here for the
                       written-candidate view is not possible without the
                       netlist -- REQ-SAFE-01 is validator-side, see gates
                       script).
  - courtyards_overlap <= 11 (baseline 11 on origin/main)
  - shorting_items    ~200 (baseline 199-200; ceiling 201)
  - solder_mask_bridge  (run-B doc also reported this: baseline 163)

N >= 5 samples for the nondeterministic categories (shorting_items,
hole_clearance, clearance) per the ceiling protocol's own convention
(120 samples for the ceiling; 5 here for a candidate gate-read, documented
as such -- the write-time re-measurement uses the full 120).

NO src/ changes. pcb/temper.kicad_pcb is read-only; the candidate board is
written to a tempfile under /tmp and deleted after measurement.

Usage:
    uv run --no-sync python docs/evidence/k3_resolve_gated_drc.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections import Counter
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
from temper_placer.validation._drc_api import run_drc  # noqa: E402

PCB = REPO / "pcb" / "temper.kicad_pcb"
SUMMARY = REPO / "docs" / "evidence" / "k3_resolve_gated_variantB_summary.json"
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

    print("=== BASELINE (unmodified board, same tool) ===")
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

    with tempfile.TemporaryDirectory(prefix="k3_gated_drc_") as tmp:
        candidate_pcb = Path(tmp) / "candidate.kicad_pcb"
        write_result = write_placements_to_pcb(
            template_pcb=PCB,
            output_pcb=candidate_pcb,
            placements=placements,
            preserve_unmatched=True,
            components=pcb.netlist.components,
        )
        print(f"\nwrite: {write_result.components_updated} components updated, "
              f"{len(write_result.warnings)} warnings")
        print("=== CANDIDATE (solved placement, /tmp copy) ===")
        measure(candidate_pcb, "candidate")
        # keep the file around only for the doc; tempdir cleanup deletes it


if __name__ == "__main__":
    main()
