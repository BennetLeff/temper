"""Property-based tests for EDT channel width computation.

Proves that the Euclidean Distance Transform (EDT) approach produces
widths within grid-resolution tolerance of the exact Shapely-based
computation.

Proof structure:
  1. BASE CASE: A point exactly on the boundary yields width 0 (both methods)
  2. INDUCTION: For any point inside the routing area, the EDT width
     differs from the exact Shapely width by at most cell_size * sqrt(2)
  3. MONOTONICITY: Width decreases as you approach a boundary
  4. IDEMPOTENCY: Repeated queries at the same point yield the same result
"""

from __future__ import annotations

import math
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from shapely.geometry import MultiPolygon, Point, Polygon, box

from temper_placer.router_v6.channel_widths import (
    _build_edt,
    _compute_width_at_point,
    _edt_width_lookup,
    _rasterize_boundary_mask,
)


def make_available_area(polygons: list[Polygon]) -> MultiPolygon | Polygon:
    if len(polygons) == 1:
        return polygons[0]
    return MultiPolygon(polygons)


class FakeRoutingSpace:
    def __init__(self, polygon):
        self.available_area = polygon
        self.layer_name = "F.Cu"


# --- BASE CASE: Boundary points yield zero ---


def test_base_case_boundary_zero():
    """A point on the polygon boundary must yield width 0 from both EDT and Shapely."""
    board = box(0, 0, 100, 100)
    bounds = board.bounds
    cell_size = 1.0

    edt, mask, _ = _build_edt(FakeRoutingSpace(board), cell_size, use_cache=False)

    # Test corners (exactly on boundary)
    for pt in [(0, 0), (100, 0), (0, 100), (100, 100)]:
        edt_w = _edt_width_lookup(*pt, edt, mask, bounds, cell_size)
        shapely_w = _compute_width_at_point(pt, board)
        assert pytest.approx(edt_w, abs=cell_size) == 0.0, f"corner {pt}: EDT={edt_w}"
        assert shapely_w == 0.0, f"corner {pt}: Shapely={shapely_w}"


def test_base_case_interior_nonzero():
    """A point at the center of the board must yield non-zero width."""
    board = box(0, 0, 100, 100)
    bounds = board.bounds
    cell_size = 1.0

    edt, mask, _ = _build_edt(FakeRoutingSpace(board), cell_size, use_cache=False)
    w = _edt_width_lookup(50, 50, edt, mask, bounds, cell_size)
    assert w > 0, f"Center point should have non-zero width, got {w}"


# --- INDUCTION: Error bound ---


@given(
    width=st.integers(20, 100),
    height=st.integers(20, 100),
    nx=st.integers(5, 30),
    ny=st.integers(5, 30),
)
@settings(max_examples=200)
def test_induction_error_bound(width, height, nx, ny):
    """EDT width at any point differs from Shapely width by at most sqrt(2)*cell_size.

    The proof: the EDT discretization introduces at most one cell of error
    in each axis.  The worst-case error is the diagonal of one cell:
    cell_size * sqrt(2).
    """
    board = box(0, 0, float(width), float(height))
    routing = FakeRoutingSpace(board)
    cell_size = 0.5
    edt, mask, bounds = _build_edt(routing, cell_size, use_cache=False)
    max_error = cell_size * math.sqrt(2)

    xs = np.linspace(0.5, width - 0.5, nx)
    ys = np.linspace(0.5, height - 0.5, ny)

    for x in xs:
        for y in ys:
            edt_w = _edt_width_lookup(float(x), float(y), edt, mask, bounds, cell_size)
            shapely_w = _compute_width_at_point((float(x), float(y)), board)
            error = abs(edt_w - shapely_w)
            assert error <= max_error + 0.01, (
                f"({x:.1f},{y:.1f}): EDT={edt_w:.3f}, Shapely={shapely_w:.3f}, "
                f"error={error:.3f}, max_allowed={max_error:.3f}"
            )


# --- MONOTONICITY: Width decreases toward boundary ---


@given(
    cell_size=st.sampled_from([0.5, 1.0, 2.0]),
)
@settings(max_examples=10)
def test_monotonicity_toward_boundary(cell_size):
    """Width must decrease or stay the same as you move toward a boundary."""
    board = box(0, 0, 100, 100)
    routing = FakeRoutingSpace(board)
    edt, mask, bounds = _build_edt(routing, cell_size, use_cache=False)

    # Move from center (50,50) toward left edge (0,50)
    prev = float("inf")
    for x in range(50, 0, -2):
        w = _edt_width_lookup(float(x), 50.0, edt, mask, bounds, cell_size)
        assert w <= prev + 0.01, f"({x},50): w={w:.2f} > prev={prev:.2f} (should decrease)"
        prev = w


# --- IDEMPOTENCY ---


def test_idempotency():
    """Repeated queries at the same point always return the same value."""
    board = box(0, 0, 100, 100)
    routing = FakeRoutingSpace(board)
    edt, mask, bounds = _build_edt(routing, 0.5, use_cache=False)

    for _ in range(100):
        w1 = _edt_width_lookup(42.3, 57.8, edt, mask, bounds, 0.5)
        w2 = _edt_width_lookup(42.3, 57.8, edt, mask, bounds, 0.5)
        assert w1 == w2


# --- REGRESSION: EDT matches Shapely on temper board ---


@pytest.mark.slow
def test_edt_matches_shapely_on_temper():
    """Smoke test: EDT produces reasonable widths on the actual temper PCB."""
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.router_v6.pipeline import RouterV6Pipeline

    pcb_path = Path(__file__).parents[5] / "pcb" / "temper.kicad_pcb"
    if not pcb_path.exists():
        pytest.skip("temper.kicad_pcb not found")

    parsed = parse_kicad_pcb_v6(str(pcb_path))
    pipeline = RouterV6Pipeline(verbose=False)
    stage2 = pipeline._run_stage2(parsed, [])

    for layer_name, routing_space in stage2.routing_spaces.items():
        cell_size = 0.1
        edt, mask, bounds = _build_edt(routing_space, cell_size, use_cache=False)

        # Sample a grid of points
        min_x, min_y, max_x, max_y = bounds
        xs = np.linspace(min_x + 0.5, max_x - 0.5, 10)
        ys = np.linspace(min_y + 0.5, max_y - 0.5, 10)

        max_err = cell_size * math.sqrt(2) + 0.1  # extra tolerance for rasterization
        for x in xs:
            for y in ys:
                edt_w = _edt_width_lookup(float(x), float(y), edt, mask, bounds, cell_size)
                shapely_w = _compute_width_at_point((float(x), float(y)), routing_space.available_area)
                err = abs(edt_w - shapely_w)
                assert err <= max_err, (
                    f"{layer_name} ({x:.1f},{y:.1f}): EDT={edt_w:.3f} Shapely={shapely_w:.3f} err={err:.3f}"
                )
