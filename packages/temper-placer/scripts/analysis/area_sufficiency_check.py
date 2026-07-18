#!/usr/bin/env python3
"""Area-sufficiency check: courtyard area vs. usable board area.

Usage:
    uv run python packages/temper-placer/scripts/analysis/area_sufficiency_check.py \
        --pcb pcb/temper.kicad_pcb [--margin-mm 5.0] [--packing-efficiency 0.7]

Reports total courtyard area, usable board area (after edge margin), and the
ratio of courtyard-area to usable-area.  Exit code 0 means the raw ratio
is <= 100% (sufficient); exit code 2 means area-constrained (> 100%).

Per U4 (R4):
    Package the courtyard-area-vs-usable-area calculation as a standalone,
    board-path-parameterized script and test, so "did the shortfall actually
    close" is a fast, objective, re-runnable check against whichever board/BOM
    state exists after a decision lands.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from temper_placer.analysis._area_sufficiency import (
    compute_area_sufficiency,
    compute_top_courtyards,
)


def _parse_args(argv: Sequence[str] | None = None) -> tuple[Path, float, list[float]]:
    import argparse

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--pcb", required=True, type=Path, help="Path to .kicad_pcb file")
    p.add_argument(
        "--margin-mm",
        type=float,
        default=5.0,
        help="Edge margin in mm (default: 5.0, matching CourtyardCheckStage constant)",
    )
    p.add_argument(
        "--packing-efficiency",
        type=float,
        nargs="*",
        default=[0.5, 0.6, 0.7, 0.8],
        help="Packing-efficiency assumptions for safety-factored ratios",
    )
    args = p.parse_args(argv)
    return args.pcb, args.margin_mm, args.packing_efficiency


def _print_report(result, packing_efficiencies: Sequence[float]) -> None:
    print("=== Area-Sufficiency Check ===")
    print(f"Board:  {result.board_width_mm:.1f} x {result.board_height_mm:.1f} mm")
    print(f"Components:  {result.component_count}")
    print(f"Total courtyard area:  {result.total_courtyard_area_mm2:.1f} mm^2")
    print(f"Usable board area (after margin):  {result.usable_area_mm2:.1f} mm^2")
    print(f"Raw ratio:  {result.raw_ratio_pct:.1f}%")
    print()
    for pe in packing_efficiencies:
        effective = result.raw_ratio_pct / pe
        print(f"  At {pe:.0%} packing efficiency: effective ratio = {effective:.1f}%")
    print()
    if result.raw_ratio_pct <= 100.0:
        print("VERDICT: Raw area sufficient (<= 100%).")
    else:
        print(f"VERDICT: Raw area INSUFFICIENT ({result.raw_ratio_pct:.1f}% > 100%).")


def main(argv: Sequence[str] | None = None) -> int:
    pcb_path, margin_mm, packing_efficiencies = _parse_args(argv)
    result = compute_area_sufficiency(pcb_path, margin_mm)
    _print_report(result, packing_efficiencies)

    top_n = 8
    largest = compute_top_courtyards(pcb_path, top_n)
    print(f"\nTop {top_n} by courtyard area:")
    for ref, area in largest:
        print(f"  {ref}: {area:.1f} mm^2")

    return 0 if result.raw_ratio_pct <= 100.0 else 2


if __name__ == "__main__":
    sys.exit(main())
