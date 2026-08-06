"""Courtyard/PTH violation-pair report generation — reusable core for U1.

Provides generate_violation_report() which runs kicad-cli DRC, filters
to courtyards_overlap and pth_inside_courtyard violations, computes
overlap magnitudes, and renders a Markdown decision-support report.

Both the CLI script (scripts/analysis/courtyard_violation_report.py)
and its tests (tests/analysis/test_courtyard_violation_report.py)
import from here.

Wave 4, Phase 4 migration (plan
``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``):
the report-building/shape logic lives in the ``temper-drc-rs`` crate,
exposed as ``temper_drc_rs.build_report_rows`` and
``temper_drc_rs.render_report``.  This module is a delegation shim: the
pre-migration implementation is pinned verbatim as the differential
oracle (``tests/analysis/_violation_report_py_oracle.py``), and
bit-exact parity is asserted by
``tests/analysis/test_violation_report_rust_differential.py``.

Boundary (argued in-source per the R1 rulings — the six remaining
runtime-kiutils importers resolve as their surfaces migrate; #718's
write-engine migration removed one of them):
- ``KiBoard.from_file`` and ``_extract_component_positions`` stay
  Python-side: kiutils object construction and footprint-property
  reading are kiutils library semantics.
- ``_compute_overlap_area_mm2`` stays Python-side: shapely/GEOS
  ``get_global_polygon``/``intersection`` are library semantics that
  cannot be crossed bit-exactly.  It is invoked from Rust as a callback
  (``overlap_fn``) at the exact dispatch points the oracle used.
- ``run_drc`` (kicad-cli subprocess) stays Python-side (I/O boundary).
- Everything downstream — target-rule filtering, ref shaping, row
  construction, the stable overlap-descending sort, and the Markdown
  renderer (CPython fixed-format floats, 120-char pipe-escaped message
  truncation) — is Rust.
"""

from __future__ import annotations

import logging
from pathlib import Path

import temper_drc_rs as _drc
from kiutils.board import Board as KiBoard

from temper_placer.io.kicad_metadata import extract_kicad_metadata
from temper_placer.validation._drc_api import run_drc

_TARGET_RULES = {"courtyards_overlap", "pth_inside_courtyard"}

_logger = logging.getLogger(__name__)


def _extract_component_positions(
    raw_board: KiBoard,
) -> dict[str, tuple[float, float, int]]:
    """Build a map from component ref to (x, y, rotation_idx).

    rotation_idx: 0=0deg, 1=90deg, 2=180deg, 3=270deg CCW.

    Kept Python-side: reads kiutils footprint objects (kiutils library
    semantics — see the module docstring's boundary note).
    """
    positions: dict[str, tuple[float, float, int]] = {}
    if not raw_board.footprints:
        return positions
    for fp in raw_board.footprints:
        ref = fp.properties.get("Reference", "")
        if not ref:
            continue
        x = fp.position.X
        y = fp.position.Y
        angle_raw = getattr(fp.position, "angle", 0.0) or 0.0
        angle_norm = round(angle_raw) % 360
        rotation_idx = angle_norm // 90
        positions[ref] = (x, y, rotation_idx)
    return positions


def _compute_overlap_area_mm2(
    ref_a: str,
    ref_b: str,
    meta,
    positions: dict,
) -> float:
    """Compute the shapely intersection area of two components' courtyards
    at their actual positions, or 0.0 if not computable.

    Kept Python-side: shapely/GEOS intersection area is a library semantic
    that cannot be crossed bit-exactly (see the module docstring's boundary
    note).  Rust invokes this as the ``overlap_fn`` callback.
    """
    try:
        c_a = meta.courtyards.get(ref_a)
        c_b = meta.courtyards.get(ref_b)
        if c_a is None or c_b is None:
            return 0.0
        if ref_a not in positions or ref_b not in positions:
            return 0.0
        xa, ya, ra = positions[ref_a]
        xb, yb, rb = positions[ref_b]
        poly_a = c_a.get_global_polygon(xa, ya, ra)
        poly_b = c_b.get_global_polygon(xb, yb, rb)
        intersection = poly_a.intersection(poly_b)
        if intersection.is_empty:
            return 0.0
        return float(intersection.area)
    except Exception:
        _logger.warning(
            "overlap-area computation failed for pair (%s, %s); "
            "reporting 0.0 — magnitude for this row is unreliable",
            ref_a,
            ref_b,
            exc_info=True,
        )
        return 0.0


def _generate_report_rows(
    errors: list,
    meta,
    positions: dict,
) -> list[dict]:
    """Build a list of report rows sorted by overlap area descending.

    Delegation shim: the row shaping/sorting is
    ``temper_drc_rs.build_report_rows``; the overlap callback keeps the
    shapely/GEOS kernel Python-side.
    """
    extracted = [
        (
            getattr(e, "rule", None),
            tuple(e.components),
            (e.location[0], e.location[1]),
            e.message,
        )
        for e in errors
    ]

    def _overlap(ref_a: str, ref_b: str) -> float:
        return _compute_overlap_area_mm2(ref_a, ref_b, meta, positions)

    return _drc.build_report_rows(extracted, _overlap)


def _render_report(rows: list[dict]) -> str:
    """Render the report as a Markdown string.

    Delegation shim: the Markdown renderer is
    ``temper_drc_rs.render_report``.
    """
    return _drc.render_report(rows)


def generate_violation_report(pcb_path: Path) -> tuple[str, dict]:
    """Generate the full violation-pair report as a Markdown string.

    Args:
        pcb_path: Path to .kicad_pcb file.

    Returns:
        (report_markdown, counts_dict) where counts_dict has keys:
            "courtyards_overlap", "pth_inside_courtyard", "total".

    Raises:
        FileNotFoundError: If PCB file doesn't exist.
        DrcRunnerError: If kicad-cli is not available or DRC fails.
    """
    drc_result = run_drc(pcb_path)
    filtered = [e for e in drc_result.errors if e.rule in _TARGET_RULES]
    filtered_w = [w for w in drc_result.warnings if w.rule in _TARGET_RULES]
    all_items = list(filtered) + list(filtered_w)
    raw_board = KiBoard.from_file(str(pcb_path))
    meta = extract_kicad_metadata(pcb_path)
    positions = _extract_component_positions(raw_board)
    rows = _generate_report_rows(all_items, meta, positions)
    report = _render_report(rows)
    counts = {
        "courtyards_overlap": sum(1 for r in rows if r["rule"] == "courtyards_overlap"),
        "pth_inside_courtyard": sum(1 for r in rows if r["rule"] == "pth_inside_courtyard"),
        "total": len(rows),
    }
    return report, counts
