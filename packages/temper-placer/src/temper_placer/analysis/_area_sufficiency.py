"""Area-sufficiency computation — reusable core logic for U4.

This module provides the courtyard-area vs. usable-board-area calculation.
Both the CLI script (scripts/analysis/area_sufficiency_check.py) and its
tests (tests/analysis/test_area_sufficiency_check.py) import from here.

Wave 4, Phase 4 migration (plan
``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``):
the aggregation compute lives in the ``temper-geometry`` crate, exposed
as ``temper_geometry.area_sufficiency_compute`` /
``temper_geometry.top_courtyards`` (and the ``temper_geometry.py_sum``
kernel, which reproduces CPython 3.12's Neumaier-compensated builtin
``sum()``).  This module is a delegation shim: the pre-migration
implementation is pinned verbatim as the differential oracle
(``tests/analysis/_area_sufficiency_py_oracle.py``), and bit-exact parity
is asserted by ``tests/analysis/test_area_sufficiency_rust_differential.py``.

Boundary (argued in-source per the R1 rulings): the per-courtyard areas
(``c._polygon.area``) stay Python-side — shapely/GEOS polygon area is a
library semantic that cannot be crossed bit-exactly (the guide's
"library semantics are not reimplementable" precedent).  The board
dimensions also stay Python-side as their original int-or-float objects
so an int board width remains an int in the result; the Rust function
receives them as opaque values and passes them through unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import temper_geometry as _tg


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
    areas = [c._polygon.area for c in meta.courtyards.values()]
    total, usable, ratio, bw, bh, n = _tg.area_sufficiency_compute(
        meta.board_width,
        meta.board_height,
        margin_mm,
        areas,
    )
    return AreaSufficiencyResult(total, usable, ratio, bw, bh, n)


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
    pairs = [(ref, c._polygon.area) for ref, c in meta.courtyards.items()]
    return _tg.top_courtyards(pairs, n)
