"""
Commutation-loop area computation from routed PCB traces.

Compute the area (mm²) of the closed polygon formed by the commutation
loop traces: DC_BUS+ → Q1 collector → Q1 emitter → SW_NODE →
Q2 emitter → Q2 collector → DC_BUS−.

The primary entry point is :func:`commutation_loop_area`, which accepts
a path to a routed ``.kicad_pcb`` file.  Internally it uses
:func:`auto_extract_loops` for topology and the convex-hull area
(``temper_geometry.convex_hull_area_py``, Rust QuickHull) as the sole
area computation.

.. note::

   The convex-hull area is a documented conservative over-estimate for
   non-convex loops (Spike S5,
   ``docs/evidence/2026-08-11-loop-area-cycle-basis-order-spike.md``).
   The prior shoelace-on-cycle path (``nx.cycle_basis`` + longest-in-basis
   heuristic) was deleted: it was order-unstable (62-64/64 seeds), could
   underestimate true area up to 4×, and was unreachable on the production
   board.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import numpy as np


class MeasurementError(Exception):
    """Raised when area measurement cannot be performed."""


class _TraceLike(Protocol):
    """Minimal trace interface accepted by the area helpers."""

    start: tuple[float, float]
    end: tuple[float, float]
    net: str | None


def commutation_loop_area(routed_pcb_path: Path) -> float | None:
    """Compute the area (mm²) of the closed polygon formed by the
    commutation loop traces: DC_BUS+ → Q1 collector → Q1 emitter →
    SW_NODE → Q2 emitter → Q2 collector → DC_BUS−.

    Returns None if trace extraction fails (gate returns UNMEASURED).
    """
    try:
        from temper_placer.core.loop import LoopType
        from temper_placer.core.loop_extractor import auto_extract_loops
        from temper_placer.io.kicad_parser import parse_kicad_pcb
    except ImportError:
        return None

    try:
        result = parse_kicad_pcb(routed_pcb_path)
    except Exception:
        return None

    netlist = result.netlist
    trace_data: list[_TraceLike] = list(result.traces)

    try:
        loops = auto_extract_loops(netlist)
    except Exception:
        return None

    comm_loops = loops.get_loops_by_type(LoopType.COMMUTATION)
    if not comm_loops:
        return None

    loop = comm_loops[0]
    net_names: set[str] = set(loop.nets)

    loop_traces = [t for t in trace_data if t.net in net_names]
    return _compute_area_from_traces(loop_traces)


def _compute_area_from_traces(traces: Sequence[_TraceLike]) -> float | None:
    """Compute enclosed area from a collection of routed trace segments.

    Collects trace endpoints, rounds to 1 µm, and computes the convex-hull
    area.  This is the sole computation path (Spike S5,
    ``docs/evidence/2026-08-11-loop-area-cycle-basis-order-spike.md``):
    the prior ``nx.cycle_basis`` / shoelace branch was deleted because it
    was order-unstable, could underestimate true area up to 4×, and was
    unreachable on the production board.

    Returns:
        Area in mm², or None when fewer than 3 unique points exist.
    """
    if not traces:
        return None

    points_set: set[tuple[float, float]] = set()
    for t in traces:
        points_set.add((round(t.start[0], 3), round(t.start[1], 3)))
        points_set.add((round(t.end[0], 3), round(t.end[1], 3)))

    if len(points_set) < 3:
        return None

    return _convex_hull_area(list(points_set))


def _shoelace_area(vertices: np.ndarray) -> float:
    """Compute the signed polygon area via the shoelace formula.

    Args:
        vertices: (N, 2) array of (x, y) coordinates.

    Returns:
        Absolute area in mm².
    """
    x = vertices[:, 0]
    y = vertices[:, 1]
    area = 0.5 * abs(float(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))))
    return area


def _convex_hull_area(points: list[tuple[float, float]]) -> float:
    """Compute convex-hull area as a conservative upper-bound proxy.

    Used as the fallback when the true routed polygon cannot be formed
    (e.g. trace graph contains spurs that prevent cycle detection).

    Rust kernel (``temper_geometry.convex_hull_area_py``, ``geo``'s
    QuickHull), replacing ``scipy.spatial.ConvexHull``: this call site only
    ever read the scalar ``hull.volume`` (2-D "volume" == area), never
    vertex ordering, so the port carries no ordering/tie-break risk — see
    docs/evidence/2026-08-07-scipy-keeps-re-triage.md Sec 2. Degenerate
    inputs (< 3 points, collinear, all-duplicate) return ``0.0`` directly
    from the kernel rather than raising, matching this function's
    pre-migration ``except Exception: return 0.0`` fallback exactly.
    """
    import temper_geometry

    flat: list[float] = [c for p in points for c in (float(p[0]), float(p[1]))]
    try:
        return float(temper_geometry.convex_hull_area_py(flat))
    except Exception:
        return 0.0
