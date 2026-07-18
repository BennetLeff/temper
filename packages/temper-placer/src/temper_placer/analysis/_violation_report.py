"""Courtyard/PTH violation-pair report generation — reusable core for U1.

Provides generate_violation_report() which runs kicad-cli DRC, filters
to courtyards_overlap and pth_inside_courtyard violations, computes
overlap magnitudes, and renders a Markdown decision-support report.

Both the CLI script (scripts/analysis/courtyard_violation_report.py)
and its tests (tests/analysis/test_courtyard_violation_report.py)
import from here.
"""

from __future__ import annotations

import logging
from pathlib import Path

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
    at their actual positions, or 0.0 if not computable."""
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
    """Build a list of report rows sorted by overlap area descending."""
    rows: list[dict] = []
    for err in errors:
        if getattr(err, "rule", None) not in _TARGET_RULES:
            continue
        refs = sorted(err.components) if len(err.components) >= 2 else list(err.components)
        row: dict = {
            "rule": err.rule,
            "components": err.components,
            "refs_sorted": refs,
            "location_x": err.location[0],
            "location_y": err.location[1],
            "message": err.message,
            "overlap_area_mm2": 0.0,
            "n_components": len(err.components),
        }
        if err.rule == "courtyards_overlap" and len(refs) == 2:
            row["overlap_area_mm2"] = _compute_overlap_area_mm2(
                refs[0], refs[1], meta, positions,
            )
        rows.append(row)
    rows.sort(key=lambda r: r["overlap_area_mm2"], reverse=True)
    return rows


def _render_report(rows: list[dict]) -> str:
    """Render the report as a Markdown string."""
    lines: list[str] = []
    lines.append("# Courtyard / PTH Violation-Pair Decision-Support Report")
    lines.append("")
    lines.append(
        "This report lists every `courtyards_overlap` and "
        "`pth_inside_courtyard` violation from `kicad-cli pcb drc`.  "
        "It does **not** judge which pairs are safe — that judgment "
        "requires a human PCB-layout reviewer (option C, deferred until "
        "a decision lands)."
    )
    lines.append("")
    lines.append("## Violation Pairs")
    lines.append("")

    by_rule: dict[str, list[dict]] = {}
    for r in rows:
        by_rule.setdefault(r["rule"], []).append(r)

    for rule, rule_rows in by_rule.items():
        lines.append(f"### {rule} ({len(rule_rows)} violations)")
        lines.append("")
        lines.append(
            "| # | Components | Location (x, y) | Overlap Area (mm^2) | kicad-cli Message |"
        )
        lines.append(
            "|---|-----------|----------------|--------------------|------------------|"
        )
        for idx, r in enumerate(rule_rows, 1):
            comps = ", ".join(r["refs_sorted"]) if r["refs_sorted"] else "(none)"
            loc = f"({r['location_x']:.1f}, {r['location_y']:.1f})"
            area = f"{r['overlap_area_mm2']:.2f}" if r["overlap_area_mm2"] > 0 else "\u2014"
            msg = r["message"].replace("|", "\\|")[:120]
            lines.append(f"| {idx} | {comps} | {loc} | {area} | {msg} |")
        lines.append("")

    courtyard_count = sum(1 for r in rows if r["rule"] == "courtyards_overlap")
    pth_count = sum(1 for r in rows if r["rule"] == "pth_inside_courtyard")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- `courtyards_overlap` violations: {courtyard_count}")
    lines.append(f"- `pth_inside_courtyard` violations: {pth_count}")
    lines.append(f"- Total: {len(rows)}")
    lines.append("")
    return "\n".join(lines)


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
