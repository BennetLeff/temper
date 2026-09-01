#!/usr/bin/env python3
"""DRC measurement for the domain-first re-solve (#518).

# provenance: commit=ab11daaba37f1fca17d057fd087110a663e01deb dirty=false

Writes the solved placement (2026-08-04_domain_first_resolve_solve_summary.json)
to a /tmp COPY of pcb/temper.kicad_pcb -- pcb/** stays untouched -- and
measures the DRC class with temper_placer.validation._drc_api.run_drc
(kicad-cli --all-track-errors), the same tool the ceiling protocol uses.

The candidate is measured under the board's CANONICAL FILENAME with the
regenerated temper.kicad_dru and a copy of temper.kicad_pro beside it
(the wave-2 Sec 4 convention), so kicad-cli resolves the project DRU rules
-- the apples-to-apples figure the ceiling protocol records.

Reported class expectation: the hoisted-caller solve measured 1281-1282
(docs/evidence/2026-08-03-fixed-copper-repair-caller.md §4) for its
placement; the committed board (ceiling) is 1261-1263 / 1267. This run
reports what THIS solve's placement measures.

Usage:
    export PYTHONPATH="$(pwd)/packages/temper-placer/src:$(pwd)/scripts"
    python3 docs/evidence/scripts/2026-08-04_domain_first_resolve_drc.py
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
SUMMARY = REPO / "docs" / "evidence" / "2026-08-04_domain_first_resolve_solve_summary.json"
N_SAMPLES = 5

ALL_RULES = (
    "shorting_items",
    "courtyards_overlap",
    "solder_mask_bridge",
    "hole_clearance",
    "clearance",
    "creepage",
    "track_width",
    "unconnected_items",
)


def measure(pcb_path: Path, label: str) -> dict[str, list[int]]:
    counts: dict[str, list[int]] = {r: [] for r in ALL_RULES}
    totals: list[int] = []
    for _i in range(N_SAMPLES):
        res = run_drc(pcb_path)
        c = Counter(e.rule for e in res.errors)
        for r in ALL_RULES:
            counts[r].append(c.get(r, 0))
        totals.append(res.error_count)
    print(f"[{label}] over {N_SAMPLES} samples (rule: min..max / last):")
    for r in ALL_RULES:
        vals = counts[r]
        print(f"    {r:22s} min={min(vals)} max={max(vals)} last={vals[-1]}")
    print(f"    {'total_errors':22s} min={min(totals)} max={max(totals)} last={totals[-1]}")
    return counts


def main() -> None:
    summary = json.loads(SUMMARY.read_text())
    solved = summary["placement"]  # {ref: {position, rotation_idx}} local frame
    pcb = parse_kicad_pcb(PCB)
    board_origin = getattr(pcb.board, "origin", (0.0, 0.0))

    dru_content = generate_kicad_dru.generate_dru()
    print("=== BASELINE (unmodified board, canonical path, project DRU) ===")
    measure(PCB, "baseline")

    placements: dict[str, PlacementUpdate] = {}
    for ref, d in solved.items():
        placements[ref] = PlacementUpdate(
            ref=ref,
            x=d["position"][0] + board_origin[0],
            y=d["position"][1] + board_origin[1],
            rotation=d["rotation_idx"] * 90.0,
        )

    with tempfile.TemporaryDirectory(prefix="df_resolve_drc_") as tmp:
        tmpdir = Path(tmp)
        candidate_pcb = tmpdir / "temper.kicad_pcb"
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
        print("=== CANDIDATE (domain-first solved placement, canonical /tmp copy) ===")
        measure(candidate_pcb, "candidate")


if __name__ == "__main__":
    main()
