"""
Validation of actual routed traces.

This module provides functions to analyze physical traces on the PCB
to validate compliance with EMI, Signal Integrity, and Thermal specs.

Wave 4 Phase 4: the two pure numeric kernels (total net length and the
HV-LV minimum endpoint distance) delegate to ``temper_drc_rs``
(``trace_length`` / ``min_hv_lv_trace_clearance`` in
packages/temper-drc-rs/src/validation.rs). ``calculate_actual_loop_area``
stays here: its core is ``scipy.spatial.ConvexHull`` (Qhull), which is not
bit-reproducible outside scipy — the GEOS-style "library semantics are not
reimplementable" boundary (see docs/MIGRATION_PHASE_GUIDE.md). The two
remaining validators are orchestration/printing over those kernels and stay
Python.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from temper_placer.core.board import Board


def calculate_actual_trace_length(board: Board, net_name: str) -> float:
    """Calculate total routed length of a specific net (Rust kernel)."""
    # Marshalling: (net, x1, y1, x2, y2) per trace — the arithmetic
    # (dx = end - start, sqrt(dx*dx + dy*dy)) is bit-identical Rust-side.
    import temper_drc_rs  # type: ignore[import-untyped]

    traces = [
        (t.net, t.start[0], t.start[1], t.end[0], t.end[1])
        for t in board.traces  # type: ignore[attr-defined]
    ]
    return float(temper_drc_rs.trace_length(traces, net_name))


def calculate_actual_loop_area(board: Board, net_names: list[str]) -> float:
    """
    Calculate polygon area formed by traces of multiple nets.

    Used for differential pairs or switching loops (e.g. SW and GND).
    """
    # 1. Collect all trace endpoints
    points = []
    for trace in board.traces:  # type: ignore[attr-defined]
        if trace.net in net_names:
            points.append(trace.start)
            points.append(trace.end)

    if len(points) < 3:
        return 0.0

    # 2. Convert to convex hull or ordered path?
    # For a simple area estimate, we can use the bounding box or convex hull
    # or try to trace the path if it's a simple loop.
    # Simple bounding box area as proxy if not enough points.

    # Better: use actual points and shoelace if they form a closed loop.
    # For validation, we'll use convex hull area as a conservative upper bound.
    from scipy.spatial import ConvexHull

    try:
        hull = ConvexHull(np.array(points))
        return float(hull.volume)  # volume of 2D hull is area
    except Exception:
        return 0.0


def calculate_min_hv_lv_clearance(board: Board, net_classes: dict[str, str]) -> float:
    """
    Calculate minimum physical distance between any HV trace and any LV trace.

    The split (net_classes lookup) stays here; the endpoint-pair distance
    minimization runs in the Rust kernel (``min_hv_lv_trace_clearance``).
    Empty HV or LV arm returns ``+inf``, exactly as before.
    """
    import temper_drc_rs  # type: ignore[import-untyped]

    hv_traces = [t for t in board.traces if net_classes.get(t.net) == "HighVoltage"]  # type: ignore[attr-defined]
    lv_traces = [t for t in board.traces if net_classes.get(t.net) != "HighVoltage"]  # type: ignore[attr-defined]

    hv = [(t.start[0], t.start[1], t.end[0], t.end[1]) for t in hv_traces]
    lv = [(t.start[0], t.start[1], t.end[0], t.end[1]) for t in lv_traces]
    return float(temper_drc_rs.min_hv_lv_trace_clearance(hv, lv))


def validate_signal_integrity(board: Board, spec: Any) -> dict[str, float]:
    """Validate trace lengths against Signal Integrity spec."""
    results = {}
    for net_name, max_len in spec.max_length_mm.items():
        actual_len = calculate_actual_trace_length(board, net_name)
        results[f"{net_name}_length"] = actual_len
        if actual_len > max_len:
            print(f"Warning: Net {net_name} exceeds max length ({actual_len:.1f} > {max_len}mm)")

    return results


def validate_emi_traces(_board: Board, _spec: Any) -> dict[str, float]:
    """Validate loop areas from actual traces."""
    # This is complex because we need to know which nets form the loop
    # TODO: Implement proper loop net identification
    return {}
