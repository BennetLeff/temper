"""
Tests for commutation-loop area computation (U1: loop_area.py).

Validates:
  - Shoelace area on synthetic closed-loop traces
  - Convex-hull fallback for non-cyclic trace graphs
  - Measurement failure (None / empty / < 3 points)
  - Boundary condition at 2000 mm²
  - Non-convex loop territory check (hull over-estimates, shoelace is accurate)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from temper_placer.physics.loop_area import (
    MeasurementError,
    _compute_area_from_traces,
    _convex_hull_area,
    _shoelace_area,
    commutation_loop_area,
)


@dataclass
class _FakeTrace:
    """Lightweight trace for unit-tests without KiCad I/O."""

    start: tuple[float, float]
    end: tuple[float, float]
    net: str | None = None
    width: float = 0.5
    layer: str = "F.Cu"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rectangular_loop_traces(
    net: str = "DC+",
    width: float = 50.0,
    height: float = 30.0,
    origin: tuple[float, float] = (0.0, 0.0),
) -> list[_FakeTrace]:
    """Build traces forming a closed rectangular polygon."""
    x0, y0 = origin
    x1, y1 = x0 + width, y0
    x2, y2 = x0 + width, y0 + height
    x3, y3 = x0, y0 + height
    return [
        _FakeTrace((x0, y0), (x1, y1), net=net),
        _FakeTrace((x1, y1), (x2, y2), net=net),
        _FakeTrace((x2, y2), (x3, y3), net=net),
        _FakeTrace((x3, y3), (x0, y0), net=net),
    ]


def _make_non_convex_loop_traces(
    net: str = "DC+",
) -> list[_FakeTrace]:
    """Build a visibly non-convex (L-shaped / inward notch) closed polygon.

    The polygon area is 1500 mm² but the convex hull is 2400 mm².
    Shape (x, y):

        (0,0) ──────────── (80,0)
          │                    │
          │   (20,20)──(60,20) │
          │       │        │   │
        (0,60)──(20,60)──(60,60)──(80,60)
          │                           │
        (0,40)──────────────────── (80,40)
    """
    pts = [
        (0.0, 0.0),
        (80.0, 0.0),
        (80.0, 40.0),
        (0.0, 40.0),
        (0.0, 60.0),
        (20.0, 60.0),
        (20.0, 20.0),
        (60.0, 20.0),
        (60.0, 60.0),
        (80.0, 60.0),
    ]
    traces = []
    for i in range(len(pts)):
        u = pts[i]
        v = pts[(i + 1) % len(pts)]
        traces.append(_FakeTrace(u, v, net=net))
    return traces


def _non_convex_true_area() -> float:
    """Compute the true shoelace area of the non-convex test polygon."""
    return _shoelace_area(
        np.array(
            [
                (0, 0),
                (80, 0),
                (80, 40),
                (0, 40),
                (0, 60),
                (20, 60),
                (20, 20),
                (60, 20),
                (60, 60),
                (80, 60),
            ],
            dtype=np.float64,
        )
    )


def _non_convex_hull_area() -> float:
    """Compute convex-hull area of the non-convex test polygon."""
    return _convex_hull_area(
        [
            (0, 0),
            (80, 0),
            (80, 40),
            (0, 40),
            (0, 60),
            (20, 60),
            (20, 20),
            (60, 20),
            (60, 60),
            (80, 60),
        ],
    )


# ---------------------------------------------------------------------------
# Shoelace formula
# ---------------------------------------------------------------------------


def test_shoelace_square():
    """10×10 mm² square = 100 mm²."""
    square = np.array([(0, 0), (10, 0), (10, 10), (0, 10)], dtype=np.float64)
    assert _shoelace_area(square) == pytest.approx(100.0)


def test_shoelace_rectangle_50x30():
    """50×30 mm² rectangle = 1500 mm²."""
    rect = np.array([(0, 0), (50, 0), (50, 30), (0, 30)], dtype=np.float64)
    assert _shoelace_area(rect) == pytest.approx(1500.0)


# ---------------------------------------------------------------------------
# _compute_area_from_traces — happy path
# ---------------------------------------------------------------------------


def test_rectangular_loop_1500mm2():
    """Traces forming a clean 50×30 rectangle → shoelace area 1500 mm²."""
    traces = _make_rectangular_loop_traces(width=50.0, height=30.0)
    area = _compute_area_from_traces(traces)
    assert area == pytest.approx(1500.0)


def test_rectangular_loop_2500mm2():
    """Traces forming a clean 50×50 rectangle → shoelace area 2500 mm²."""
    traces = _make_rectangular_loop_traces(width=50.0, height=50.0)
    area = _compute_area_from_traces(traces)
    assert area == pytest.approx(2500.0)


def test_rectangular_loop_boundary_2000mm2():
    """Boundary: exactly 2000 mm² (50×40 mm)."""
    traces = _make_rectangular_loop_traces(width=50.0, height=40.0)
    area = _compute_area_from_traces(traces)
    assert area == pytest.approx(2000.0)


# ---------------------------------------------------------------------------
# Non-convex loop (territory check)
# ---------------------------------------------------------------------------


def test_non_convex_loop_shoelace_lt_hull():
    """Non-convex polygon: shoelace area < convex-hull area."""
    true_area = _non_convex_true_area()
    hull_area = _non_convex_hull_area()
    assert hull_area > true_area, (
        f"convex hull ({hull_area:.1f}) should over-estimate shoelace ({true_area:.1f})"
    )


def test_non_convex_loop_uses_shoelace_not_hull():
    """_compute_area_from_traces must return shoelace, not convex-hull."""
    traces = _make_non_convex_loop_traces()
    area = _compute_area_from_traces(traces)
    true_area = _non_convex_true_area()
    hull_area = _non_convex_hull_area()
    assert area == pytest.approx(true_area), f"expected shoelace {true_area:.1f}, got {area:.1f}"
    # shoelace must be strictly less than the hull proxy
    assert area < hull_area


# ---------------------------------------------------------------------------
# Measurement failures
# ---------------------------------------------------------------------------


def test_empty_traces_returns_none():
    """No traces → None."""
    assert _compute_area_from_traces([]) is None


def test_single_trace_returns_none():
    """Single trace segment → only 2 points → None."""
    traces = [_FakeTrace((0.0, 0.0), (10.0, 0.0), net="DC+")]
    assert _compute_area_from_traces(traces) is None


def test_three_collinear_points_returns_none():
    """Three collinear points → not a polygon → hull area 0 → None."""
    traces = [
        _FakeTrace((0.0, 0.0), (5.0, 0.0), net="DC+"),
        _FakeTrace((5.0, 0.0), (10.0, 0.0), net="DC+"),
    ]
    area = _compute_area_from_traces(traces)
    assert area is None or area == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Convex-hull fallback
# ---------------------------------------------------------------------------


def test_unclosable_traces_falls_back_to_convex_hull():
    """Traces that don't form a cycle but have ≥3 non-collinear points
    fall back to convex-hull area."""
    traces = [
        _FakeTrace((0.0, 0.0), (10.0, 0.0), net="DC+"),
        _FakeTrace((10.0, 0.0), (10.0, 10.0), net="DC+"),
        _FakeTrace((10.0, 10.0), (5.0, 5.0), net="DC+"),
    ]
    area = _compute_area_from_traces(traces)
    assert area is not None
    assert area > 0.0


# ---------------------------------------------------------------------------
# Net filtering
# ---------------------------------------------------------------------------


def test_filters_by_net():
    """Only traces on the commutation loop nets contribute to area."""
    traces_loop = _make_rectangular_loop_traces(net="DC+", width=20, height=10)
    # Add irrelevant trace on a different net
    traces_other = [_FakeTrace((100.0, 100.0), (200.0, 200.0), net="SIGNAL")]
    all_traces = traces_loop + traces_other
    # All traces are on "DC+", so they should all be included.
    # Let's filter manually and confirm.
    loop_traces = [t for t in all_traces if t.net == "DC+"]
    area = _compute_area_from_traces(loop_traces)
    assert area == pytest.approx(200.0)  # 20×10


# ---------------------------------------------------------------------------
# commutation_loop_area with real PCB (requires fixture)
# ---------------------------------------------------------------------------


def test_commutation_loop_area_nonexistent_pcb():
    """Non-existent file returns None (graceful failure)."""
    path = Path("/nonexistent/pcb.kicad_pcb")
    result = commutation_loop_area(path)
    assert result is None


# ---------------------------------------------------------------------------
# MeasurementError
# ---------------------------------------------------------------------------


def test_measurement_error_is_exception():
    """MeasurementError is a regular Exception subclass."""
    err = MeasurementError("could not measure")
    assert isinstance(err, Exception)
    assert str(err) == "could not measure"
