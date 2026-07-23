"""Area-sufficiency computation — reusable core logic for U4.

This module provides the courtyard-area vs. usable-board-area calculation.
Both the CLI script (scripts/analysis/area_sufficiency_check.py) and its
tests (tests/analysis/test_area_sufficiency_check.py) import from here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AreaSufficiencyResult:
    """Result of an area-sufficiency check.

    Attributes:
        total_courtyard_area_mm2: Sum of all component courtyard polygon areas.
        usable_area_mm2: (board_width - 2*margin) * (board_height - 2*margin).
        raw_ratio_pct: (total_courtyard / usable) * 100.
        board_width_mm: Parsed board width.
        board_height_mm: Parsed board height.
        component_count: Number of components with courtyards.
    """

    total_courtyard_area_mm2: float
    usable_area_mm2: float
    raw_ratio_pct: float
    board_width_mm: float
    board_height_mm: float
    component_count: int


def compute_area_sufficiency(pcb_path: Path, margin_mm: float = 5.0) -> AreaSufficiencyResult:
    """Compute courtyard-area vs. usable-area ratio for a board.

    Args:
        pcb_path: Path to .kicad_pcb file.
        margin_mm: Edge margin subtracted from each side (default 5.0mm,
            matching CourtyardCheckStage's own constant).

    Returns:
        AreaSufficiencyResult with the computed values.

    Raises:
        FileNotFoundError: If PCB file doesn't exist.
        ValueError: If board dimensions are invalid or usable area <= 0.
    """
    from temper_placer.io.kicad_metadata import extract_kicad_metadata

    meta = extract_kicad_metadata(pcb_path)

    used_w = meta.board_width - 2 * margin_mm
    used_h = meta.board_height - 2 * margin_mm
    usable = used_w * used_h
    if used_w <= 0 or used_h <= 0 or usable <= 0:
        raise ValueError(
            f"Usable board area is non-positive ({usable:.1f} mm^2) "
            f"with {margin_mm}mm margin on "
            f"{meta.board_width}x{meta.board_height}mm board "
            f"(usable region: {used_w:.1f}x{used_h:.1f} mm)."
        )

    total = sum(c._polygon.area for c in meta.courtyards.values())

    return AreaSufficiencyResult(
        total_courtyard_area_mm2=total,
        usable_area_mm2=usable,
        raw_ratio_pct=(total / usable) * 100.0,
        board_width_mm=meta.board_width,
        board_height_mm=meta.board_height,
        component_count=len(meta.courtyards),
    )


def compute_top_courtyards(pcb_path: Path, n: int = 8) -> list[tuple[str, float]]:
    """Return the N largest components by courtyard area.

    Args:
        pcb_path: Path to .kicad_pcb file.
        n: Number of top components to return.

    Returns:
        List of (ref, area_mm2) sorted by area descending.
    """
    from temper_placer.io.kicad_metadata import extract_kicad_metadata

    meta = extract_kicad_metadata(pcb_path)
    largest = sorted(
        meta.courtyards.items(),
        key=lambda kv: kv[1]._polygon.area,
        reverse=True,
    )[:n]
    return [(ref, c._polygon.area) for ref, c in largest]
