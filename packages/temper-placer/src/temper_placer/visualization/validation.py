"""
Coordinate validation utilities for PCB visualization.

This module provides tools to validate that visualization coordinates
match the original KiCad source data, enabling users to verify
rendering accuracy.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from .model import BoardView


@dataclass
class CoordinateDiscrepancy:
    """A discrepancy between expected and actual coordinates."""

    element_type: str  # 'component', 'trace', 'pad'
    ref: str  # Reference/identifier
    field: str  # Which field differs (e.g., 'x', 'y', 'rotation')
    expected: float
    actual: float
    difference: float

    def __str__(self) -> str:
        return (
            f"{self.element_type} {self.ref}: {self.field} "
            f"expected {self.expected:.4f}, got {self.actual:.4f} "
            f"(diff: {self.difference:.4f})"
        )


@dataclass
class ValidationResult:
    """Result of coordinate validation."""

    is_valid: bool
    discrepancies: list[CoordinateDiscrepancy]
    tolerance: float
    components_checked: int
    traces_checked: int
    pads_checked: int

    def __str__(self) -> str:
        if self.is_valid:
            return (
                f"Validation PASSED: {self.components_checked} components, "
                f"{self.traces_checked} traces, {self.pads_checked} pads "
                f"(tolerance: {self.tolerance}mm)"
            )
        return (
            f"Validation FAILED: {len(self.discrepancies)} discrepancies found\n"
            + "\n".join(f"  - {d}" for d in self.discrepancies[:10])
            + (
                f"\n  ... and {len(self.discrepancies) - 10} more"
                if len(self.discrepancies) > 10
                else ""
            )
        )


def validate_coordinates(
    board_view: BoardView,
    original_components: list[tuple[str, float, float, float]],  # (ref, x, y, rotation)
    original_traces: list[tuple[float, float, float, float]] | None = None,  # (x1, y1, x2, y2)
    original_pads: list[tuple[str, float, float]] | None = None,  # (ref, x, y)
    origin: tuple[float, float] = (0.0, 0.0),
    tolerance: float = 0.01,
) -> ValidationResult:
    """
    Validate that BoardView coordinates match original KiCad coordinates.

    Compares rendered positions (board-relative) against original absolute
    positions from KiCad, accounting for the board origin offset.

    Args:
        board_view: The BoardView to validate.
        original_components: List of (ref, x_abs, y_abs, rotation) from KiCad.
        original_traces: Optional list of trace endpoints (x1, y1, x2, y2).
        original_pads: Optional list of (component_ref-pad_num, x_abs, y_abs).
        origin: Board origin (x, y) for coordinate transformation.
        tolerance: Maximum allowed difference in mm (default 0.01mm = 10µm).

    Returns:
        ValidationResult with discrepancies exceeding tolerance.
    """
    discrepancies: list[CoordinateDiscrepancy] = []
    origin_x, origin_y = origin

    # Build lookup for board_view components
    view_components = {c.ref: c for c in board_view.components}

    # Validate components
    for ref, x_abs, y_abs, rotation in original_components:
        if ref not in view_components:
            discrepancies.append(
                CoordinateDiscrepancy(
                    element_type="component",
                    ref=ref,
                    field="missing",
                    expected=0,
                    actual=0,
                    difference=float("inf"),
                )
            )
            continue

        comp = view_components[ref]
        expected_x = x_abs - origin_x
        expected_y = y_abs - origin_y

        # Check X coordinate
        diff_x = abs(comp.position.x - expected_x)
        if diff_x > tolerance:
            discrepancies.append(
                CoordinateDiscrepancy(
                    element_type="component",
                    ref=ref,
                    field="x",
                    expected=expected_x,
                    actual=comp.position.x,
                    difference=diff_x,
                )
            )

        # Check Y coordinate
        diff_y = abs(comp.position.y - expected_y)
        if diff_y > tolerance:
            discrepancies.append(
                CoordinateDiscrepancy(
                    element_type="component",
                    ref=ref,
                    field="y",
                    expected=expected_y,
                    actual=comp.position.y,
                    difference=diff_y,
                )
            )

        # Check rotation (normalize to 0-360)
        expected_rot = rotation % 360
        actual_rot = comp.rotation % 360
        diff_rot = min(abs(expected_rot - actual_rot), 360 - abs(expected_rot - actual_rot))
        if diff_rot > tolerance:
            discrepancies.append(
                CoordinateDiscrepancy(
                    element_type="component",
                    ref=ref,
                    field="rotation",
                    expected=expected_rot,
                    actual=actual_rot,
                    difference=diff_rot,
                )
            )

    # Validate traces (if provided)
    traces_checked = 0
    if original_traces and board_view.traces:
        traces_checked = len(original_traces)
        view_traces = list(board_view.traces)

        for i, (x1, y1, x2, y2) in enumerate(original_traces):
            if i >= len(view_traces):
                break

            trace = view_traces[i]
            expected_start_x = x1 - origin_x
            expected_start_y = y1 - origin_y
            expected_end_x = x2 - origin_x
            expected_end_y = y2 - origin_y

            # Check start point
            diff_sx = abs(trace.start.x - expected_start_x)
            diff_sy = abs(trace.start.y - expected_start_y)
            if diff_sx > tolerance or diff_sy > tolerance:
                discrepancies.append(
                    CoordinateDiscrepancy(
                        element_type="trace",
                        ref=f"trace_{i}",
                        field="start",
                        expected=math.sqrt(expected_start_x**2 + expected_start_y**2),
                        actual=math.sqrt(trace.start.x**2 + trace.start.y**2),
                        difference=math.sqrt(diff_sx**2 + diff_sy**2),
                    )
                )

            # Check end point
            diff_ex = abs(trace.end.x - expected_end_x)
            diff_ey = abs(trace.end.y - expected_end_y)
            if diff_ex > tolerance or diff_ey > tolerance:
                discrepancies.append(
                    CoordinateDiscrepancy(
                        element_type="trace",
                        ref=f"trace_{i}",
                        field="end",
                        expected=math.sqrt(expected_end_x**2 + expected_end_y**2),
                        actual=math.sqrt(trace.end.x**2 + trace.end.y**2),
                        difference=math.sqrt(diff_ex**2 + diff_ey**2),
                    )
                )

    # Validate pads (if provided)
    pads_checked = 0
    if original_pads and board_view.pads:
        pads_checked = len(original_pads)
        # Build lookup for pads by component_ref-number
        view_pads = {f"{p.component_ref}-{p.number}": p for p in board_view.pads if p.component_ref}

        for ref, x_abs, y_abs in original_pads:
            if ref not in view_pads:
                continue

            pad = view_pads[ref]
            expected_x = x_abs - origin_x
            expected_y = y_abs - origin_y

            diff_x = abs(pad.position.x - expected_x)
            diff_y = abs(pad.position.y - expected_y)

            if diff_x > tolerance or diff_y > tolerance:
                discrepancies.append(
                    CoordinateDiscrepancy(
                        element_type="pad",
                        ref=ref,
                        field="position",
                        expected=math.sqrt(expected_x**2 + expected_y**2),
                        actual=math.sqrt(pad.position.x**2 + pad.position.y**2),
                        difference=math.sqrt(diff_x**2 + diff_y**2),
                    )
                )

    return ValidationResult(
        is_valid=len(discrepancies) == 0,
        discrepancies=discrepancies,
        tolerance=tolerance,
        components_checked=len(original_components),
        traces_checked=traces_checked,
        pads_checked=pads_checked,
    )


def export_coordinates_csv(
    board_view: BoardView,
    origin: tuple[float, float] = (0.0, 0.0),
    output_path: Path | None = None,
) -> str:
    """
    Export all coordinates to CSV for external comparison.

    Generates a CSV with component, trace, and pad coordinates in both
    board-relative and absolute (KiCad) coordinate systems.

    Args:
        board_view: The BoardView to export.
        origin: Board origin (x, y) for computing absolute coordinates.
        output_path: Optional path to write CSV file.

    Returns:
        CSV string content.

    Example output:
        type,ref,x_rel,y_rel,x_abs,y_abs,rotation,width,height,layer,net
        component,D1,4.5,3.5,82.0,74.5,0,3.36,1.9,,
        component,R1,10.9,3.5,88.4,74.5,180,3.36,1.9,,
        trace,trace_0,5.4,3.5,82.9,74.5,,0.25,,F.Cu,GND
        pad,D1-1,3.5,3.5,81.0,74.5,0,1.0,1.0,F.Cu,VCC
    """
    origin_x, origin_y = origin

    output = StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow(
        [
            "type",
            "ref",
            "x_rel",
            "y_rel",
            "x_abs",
            "y_abs",
            "rotation",
            "width",
            "height",
            "layer",
            "net",
        ]
    )

    # Components
    for comp in board_view.components:
        x_abs = comp.position.x + origin_x
        y_abs = comp.position.y + origin_y
        writer.writerow(
            [
                "component",
                comp.ref,
                f"{comp.position.x:.4f}",
                f"{comp.position.y:.4f}",
                f"{x_abs:.4f}",
                f"{y_abs:.4f}",
                f"{comp.rotation:.1f}",
                f"{comp.width:.4f}",
                f"{comp.height:.4f}",
                "",  # layer
                "",  # net
            ]
        )

    # Traces
    for i, trace in enumerate(board_view.traces):
        # Export start point
        x_abs_start = trace.start.x + origin_x
        y_abs_start = trace.start.y + origin_y
        writer.writerow(
            [
                "trace_start",
                f"trace_{i}",
                f"{trace.start.x:.4f}",
                f"{trace.start.y:.4f}",
                f"{x_abs_start:.4f}",
                f"{y_abs_start:.4f}",
                "",  # rotation
                f"{trace.width:.4f}",
                "",  # height
                trace.layer,
                trace.net or "",
            ]
        )
        # Export end point
        x_abs_end = trace.end.x + origin_x
        y_abs_end = trace.end.y + origin_y
        writer.writerow(
            [
                "trace_end",
                f"trace_{i}",
                f"{trace.end.x:.4f}",
                f"{trace.end.y:.4f}",
                f"{x_abs_end:.4f}",
                f"{y_abs_end:.4f}",
                "",  # rotation
                f"{trace.width:.4f}",
                "",  # height
                trace.layer,
                trace.net or "",
            ]
        )

    # Pads
    for pad in board_view.pads:
        x_abs = pad.position.x + origin_x
        y_abs = pad.position.y + origin_y
        ref = f"{pad.component_ref}-{pad.number}" if pad.component_ref else pad.number
        writer.writerow(
            [
                "pad",
                ref,
                f"{pad.position.x:.4f}",
                f"{pad.position.y:.4f}",
                f"{x_abs:.4f}",
                f"{y_abs:.4f}",
                f"{pad.rotation:.1f}",
                f"{pad.size[0]:.4f}",
                f"{pad.size[1]:.4f}",
                pad.layer,
                pad.net or "",
            ]
        )

    csv_content = output.getvalue()

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(csv_content)

    return csv_content


def check_components_in_bounds(board_view: BoardView) -> list[str]:
    """
    Check that all components are within board boundaries.

    Args:
        board_view: The BoardView to check.

    Returns:
        List of component refs that are outside bounds.
    """
    out_of_bounds = []

    for comp in board_view.components:
        # Get component corners considering rotation
        rect = comp.bounds
        corners = rect.corners

        for corner in corners:
            if (
                corner.x < 0
                or corner.x > board_view.width
                or corner.y < 0
                or corner.y > board_view.height
            ):
                out_of_bounds.append(comp.ref)
                break

    return out_of_bounds


def check_trace_connectivity(
    board_view: BoardView,
    tolerance: float = 0.5,
) -> list[tuple[str, str, float]]:
    """
    Check that trace endpoints are near pad positions.

    This helps verify that traces are correctly connected to component pads.

    Args:
        board_view: The BoardView to check.
        tolerance: Maximum distance from trace endpoint to nearest pad (mm).

    Returns:
        List of (trace_ref, endpoint, min_distance) for disconnected traces.
    """
    disconnected: list[tuple[str, tuple[float, float], float]] = []

    if not board_view.pads:
        return disconnected

    # Collect all pad positions
    pad_positions = [(p.position.x, p.position.y) for p in board_view.pads]

    for i, trace in enumerate(board_view.traces):
        trace_ref = f"trace_{i}"

        # Check start point
        min_dist_start = float("inf")
        for px, py in pad_positions:
            dist = math.sqrt((trace.start.x - px) ** 2 + (trace.start.y - py) ** 2)
            min_dist_start = min(min_dist_start, dist)

        if min_dist_start > tolerance:
            disconnected.append((trace_ref, "start", min_dist_start))

        # Check end point
        min_dist_end = float("inf")
        for px, py in pad_positions:
            dist = math.sqrt((trace.end.x - px) ** 2 + (trace.end.y - py) ** 2)
            min_dist_end = min(min_dist_end, dist)

        if min_dist_end > tolerance:
            disconnected.append((trace_ref, "end", min_dist_end))

    return disconnected


def compute_coordinate_statistics(board_view: BoardView) -> dict:
    """
    Compute statistics about coordinate ranges in the board view.

    Useful for debugging coordinate transformation issues.

    Args:
        board_view: The BoardView to analyze.

    Returns:
        Dictionary with min/max/mean for component, trace, and pad coordinates.
    """
    stats = {
        "board": {
            "width": board_view.width,
            "height": board_view.height,
        },
        "components": {},
        "traces": {},
        "pads": {},
    }

    # Component statistics
    if board_view.components:
        comp_x = [c.position.x for c in board_view.components]
        comp_y = [c.position.y for c in board_view.components]
        stats["components"] = {
            "count": len(board_view.components),
            "x_min": min(comp_x),
            "x_max": max(comp_x),
            "x_mean": sum(comp_x) / len(comp_x),
            "y_min": min(comp_y),
            "y_max": max(comp_y),
            "y_mean": sum(comp_y) / len(comp_y),
        }

    # Trace statistics
    if board_view.traces:
        trace_x = []
        trace_y = []
        for t in board_view.traces:
            trace_x.extend([t.start.x, t.end.x])
            trace_y.extend([t.start.y, t.end.y])
        stats["traces"] = {
            "count": len(board_view.traces),
            "x_min": min(trace_x),
            "x_max": max(trace_x),
            "y_min": min(trace_y),
            "y_max": max(trace_y),
        }

    # Pad statistics
    if board_view.pads:
        pad_x = [p.position.x for p in board_view.pads]
        pad_y = [p.position.y for p in board_view.pads]
        stats["pads"] = {
            "count": len(board_view.pads),
            "x_min": min(pad_x),
            "x_max": max(pad_x),
            "y_min": min(pad_y),
            "y_max": max(pad_y),
        }

    return stats
