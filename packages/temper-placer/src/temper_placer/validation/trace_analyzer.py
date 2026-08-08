"""
Validation of actual routed traces.

This module provides functions to analyze physical traces on the PCB
to validate compliance with EMI, Signal Integrity, and Thermal specs.

Wave 4 Phase 4: the two pure numeric kernels (total net length and the
HV-LV minimum endpoint distance) delegate to ``temper_drc_rs``
(``trace_length`` / ``min_hv_lv_trace_clearance`` in
packages/temper-drc-rs/src/validation.rs). ``calculate_actual_loop_area``'s
convex-hull core also delegates to Rust now (``temper_geometry.
convex_hull_area_py``, ``geo``'s QuickHull replacing
``scipy.spatial.ConvexHull``): this call site only ever reads the scalar
``hull.volume`` (2-D "volume" == area), never vertex ordering, so the
"not bit-reproducible outside scipy" concern that blocked this port for a
while does not apply — that was a blanket claim never actually checked
against this call site's contract, corrected in
docs/evidence/2026-08-07-scipy-keeps-re-triage.md Sec 2. The two remaining
validators are orchestration/printing over these kernels and stay Python.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from temper_placer.core.board import Board


def calculate_actual_trace_length(board: Board, net_name: str) -> float:
    """Calculate total routed length of a specific net (Rust kernel)."""
    # Marshalling: (net, x1, y1, x2, y2) per trace — the arithmetic
    # (dx = end - start, dx**2 via the dlsym'd host libm pow, exactly what
    # CPython's `**2` calls, sqrt(dx**2 + dy**2)) is bit-identical
    # Rust-side.
    # `net` is `str | None` per the Trace contract; None-net traces marshal
    # as None and are skipped by the kernel (None never equals a str
    # net_name), matching the oracle's `if trace.net == net_name` skip.
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
    # For validation, we'll use convex hull area as a conservative upper
    # bound (Rust kernel -- see module docstring). Degenerate inputs
    # (< 3 points, collinear, all-duplicate) return 0.0 directly from the
    # kernel rather than raising, matching the pre-migration
    # `except Exception: return 0.0` fallback exactly.
    import temper_geometry

    flat: list[float] = [c for p in points for c in (float(p[0]), float(p[1]))]
    try:
        return float(temper_geometry.convex_hull_area_py(flat))  # area of 2D hull
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
