"""Differential tests: ``placer/adjustment.py`` compute vs the pinned oracle.

Wave 4 Phase 4: the per-(bottleneck, component) push loop of
``adjust_for_congestion`` moved to ``temper-io-types/placer_core``
(exposed as ``temper_io_types.placer_adjust_for_congestion``). The oracle
is the verbatim pre-migration module in
``tests/placer/_placer_adjustment_py_oracle.py``.

The bottleneck iteration (``bottleneck.overflow <= 0`` skip and
``bottleneck.to_coordinates(...)``) is Python object navigation and stays
in the shim; the kernel receives precomputed bottleneck coordinates. The
kernel is dtype-aware (``is_f32``): numpy 2.x NEP-50 keeps a float32 input
array's whole normalized-push chain in float32 (dx = px - bx computed in
f32, force in f32, in-place add in f32), while the exact-spot random-push
branch adds the f64 random-delta to the widened f32 element and rounds on
store -- both paths transcribed op-for-op.

Python seams called back from the kernel (so the oracle's own bits are
preserved by construction):
- ``dist`` = ``np.sqrt(dx**2 + dy**2)`` -- numpy's ``**2`` is libm pow,
  NOT ``x*x`` (measured 1302/500k float64 and 1932/300k float32
  mismatches 2026-08-05), and ``np.float32.sqrt`` is a correctly-rounded
  float32 sqrt, not an f64 sqrt cast.
- ``np.random.uniform(0, 2*pi)`` -- the global numpy RNG, called in the
  kernel in the oracle's exact iteration order (bottleneck-major,
  component-minor), so seeding reproduces the oracle's angle sequence.
- ``np.cos``/``np.sin`` of the random angle (float64).

Each arm re-seeds ``np.random`` so the two arms draw identical angles.

RED state: this file fails to collect with ``AttributeError: module
'temper_io_types' has no attribute 'placer_adjust_for_congestion'`` until
the Rust kernel lands (the TDD-RED evidence).
"""

from __future__ import annotations

import numpy as np
import pytest
import temper_io_types as _t

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist
from temper_placer.placer.adjustment import adjust_for_congestion
from temper_placer.router_v6.congestion import Bottleneck, CongestionGrid, CongestionResult
from tests.placer import _placer_adjustment_py_oracle as oracle
from tests.placer._placer_diff import assert_array_identical

# The Rust surface this differential pins. Imported at module level so the
# RED state is a collection failure (AttributeError) before the kernel
# lands, per the TDD convention.
placer_adjust_for_congestion = _t.placer_adjust_for_congestion


def _numpy_dist_f64(dx, dy):
    return float(np.sqrt(np.float64(dx) ** 2 + np.float64(dy) ** 2))


def _numpy_dist_f32(dx, dy):
    return float(np.sqrt(np.float32(dx) ** 2 + np.float32(dy) ** 2))


def _uniform():
    return float(np.random.uniform(0, 2 * np.pi))


def _cos_sin(angle):
    return (float(np.cos(angle)), float(np.sin(angle)))

SEEDS = [0, 1, 42, 7, 1234]


def _netlist(positions_n: int = 1, fixed: set[int] | None = None) -> Netlist:
    fixed = fixed or set()
    comps = [
        Component(f"U{i}", "Pkg", (10 * (i + 1), 10)) if i not in fixed else Component(
            f"U{i}", "Pkg", (10 * (i + 1), 10), fixed=True
        )
        for i in range(positions_n)
    ]
    return Netlist(comps, [])


def _congestion(bottlenecks: list[Bottleneck]) -> CongestionResult:
    grid = CongestionGrid.from_board(Board(width=100, height=100))
    return CongestionResult(grid=grid, bottlenecks=bottlenecks)


def _run_both(positions, netlist, congestion, push_strength=2.0, seed=0):
    np.random.seed(seed)
    ref = oracle.adjust_for_congestion(positions, netlist, None, congestion, push_strength)
    np.random.seed(seed)
    prod = adjust_for_congestion(positions, netlist, None, congestion, push_strength)
    return prod, ref


def test_no_bottlenecks_returns_identical_copy():
    for dtype in (np.float64, np.float32):
        positions = np.array([[50.0, 50.0]], dtype=dtype)
        netlist = _netlist(1)
        congestion = _congestion([])
        prod, ref = _run_both(positions, netlist, congestion)
        assert_array_identical(prod, ref)
        assert_array_identical(prod, positions)
        assert prod is not positions  # .copy() semantics


def test_overflow_zero_or_negative_skipped():
    positions = np.array([[50.0, 50.0]])
    netlist = _netlist(1)
    congestion = _congestion([Bottleneck(x=50, y=50, utilization=0.5, overflow=0.0)])
    prod, ref = _run_both(positions, netlist, congestion)
    assert_array_identical(prod, ref)
    assert_array_identical(prod, positions)


def test_normalized_push_within_radius():
    # Component at (50,50), bottleneck cell (50,50) -> center (50.5, 50.5),
    # dist ~0.707 < 10 -> normalized push away from the hotspot.
    for dtype in (np.float64, np.float32):
        positions = np.array([[50.0, 50.0]], dtype=dtype)
        netlist = _netlist(1)
        congestion = _congestion([Bottleneck(x=50, y=50, utilization=2.0, overflow=1.0)])
        prod, ref = _run_both(positions, netlist, congestion)
        assert_array_identical(prod, ref)
        assert not np.allclose(prod[0], [50.0, 50.0])


def test_fixed_component_not_pushed():
    for dtype in (np.float64, np.float32):
        positions = np.array([[50.0, 50.0]], dtype=dtype)
        netlist = _netlist(1, fixed={0})
        congestion = _congestion([Bottleneck(x=50, y=50, utilization=2.0, overflow=1.0)])
        prod, ref = _run_both(positions, netlist, congestion)
        assert_array_identical(prod, ref)
        assert_array_identical(prod, positions)


def test_at_exact_bottleneck_spot_random_push():
    # Component exactly at the bottleneck cell center -> dist < 1e-3 ->
    # random push. Seeded so both arms draw the same angle.
    for dtype in (np.float64, np.float32):
        positions = np.array([[50.5, 50.5]], dtype=dtype)
        netlist = _netlist(1)
        congestion = _congestion([Bottleneck(x=50, y=50, utilization=2.0, overflow=1.0)])
        prod, ref = _run_both(positions, netlist, congestion, seed=SEEDS[0])
        assert_array_identical(prod, ref)
        assert not np.allclose(prod[0], [50.5, 50.5])


@pytest.mark.parametrize("seed", SEEDS)
def test_random_push_seed_sequence(seed):
    positions = np.array([[50.5, 50.5]])
    netlist = _netlist(1)
    congestion = _congestion([Bottleneck(x=50, y=50, utilization=2.0, overflow=1.0)])
    prod, ref = _run_both(positions, netlist, congestion, seed=seed)
    assert_array_identical(prod, ref)


def test_distance_exactly_influence_radius_not_pushed():
    # dist == 10.0 exactly -> `dist < influence_radius` is False -> no push.
    # Cell (44, 50) center is (44.5, 50.5); a component at (54.5, 50.5) is
    # exactly 10.0 mm away (x-distance 10.0, y-distance 0.0).
    positions = np.array([[54.5, 50.5]])
    netlist = _netlist(1)
    congestion = _congestion([Bottleneck(x=44, y=50, utilization=2.0, overflow=1.0)])
    prod, ref = _run_both(positions, netlist, congestion)
    assert_array_identical(prod, ref)
    assert_array_identical(prod, positions)


def test_distance_just_inside_radius_pushed():
    positions = np.array([[54.49, 50.5]])
    netlist = _netlist(1)
    congestion = _congestion([Bottleneck(x=44, y=50, utilization=2.0, overflow=1.0)])
    prod, ref = _run_both(positions, netlist, congestion)
    assert_array_identical(prod, ref)
    assert not np.allclose(prod[0], [54.49, 50.5])


def test_multiple_bottlenecks_accumulate():
    positions = np.array([[50.5, 50.5], [60.0, 60.0], [5.0, 5.0]])
    netlist = _netlist(3)
    congestion = _congestion(
        [
            Bottleneck(x=50, y=50, utilization=2.0, overflow=1.0),
            Bottleneck(x=60, y=60, utilization=3.0, overflow=2.0),
            Bottleneck(x=0, y=0, utilization=1.5, overflow=0.5),
        ]
    )
    prod, ref = _run_both(positions, netlist, congestion, seed=3)
    assert_array_identical(prod, ref)


def test_push_strength_variants():
    for strength in (2.0, 0.5, 1.0):
        positions = np.array([[52.0, 52.0]])
        netlist = _netlist(1)
        congestion = _congestion([Bottleneck(x=50, y=50, utilization=2.0, overflow=1.0)])
        prod, ref = _run_both(positions, netlist, congestion, push_strength=strength)
        assert_array_identical(prod, ref)


def test_multiple_components_mixed_fixed():
    # 5 components, some fixed, some inside/outside the radius, in one arm
    # with an exact-spot hit too.
    positions = np.array(
        [[50.5, 50.5], [52.0, 52.0], [70.0, 70.0], [53.0, 50.5], [50.5, 60.0]]
    )
    netlist = _netlist(5, fixed={2})
    congestion = _congestion(
        [
            Bottleneck(x=50, y=50, utilization=2.0, overflow=1.0),
            Bottleneck(x=49, y=50, utilization=2.5, overflow=1.5),
        ]
    )
    prod, ref = _run_both(positions, netlist, congestion, seed=42)
    assert_array_identical(prod, ref)


def test_empty_positions():
    positions = np.zeros((0, 2))
    netlist = _netlist(0)
    congestion = _congestion([Bottleneck(x=50, y=50, utilization=2.0, overflow=1.0)])
    prod, ref = _run_both(positions, netlist, congestion)
    assert_array_identical(prod, ref)


def test_float32_exact_spot_store_semantics():
    # The exact-spot branch on a float32 array: numpy does an f64 add on the
    # widened f32 element and rounds on store. The kernel must NOT f32-round
    # before the store for this branch (the normalized branch rounds at every
    # step). Seed pinned; both arms must agree bit-for-bit.
    positions = np.array([[50.5, 50.5], [51.0, 51.0]], dtype=np.float32)
    netlist = _netlist(2)
    congestion = _congestion(
        [
            Bottleneck(x=50, y=50, utilization=2.0, overflow=1.0),
            Bottleneck(x=49, y=49, utilization=3.0, overflow=2.0),
        ]
    )
    prod, ref = _run_both(positions, netlist, congestion, seed=7)
    assert_array_identical(prod, ref)


def test_float32_normalized_chain():
    # Exercise the float32 normalized-push chain (f32 fma-free op-for-op) on
    # values whose f32 vs f64 intermediates genuinely diverge (repeating
    # decimals).
    positions = np.array([[0.1, 0.2], [49.3, 51.7]], dtype=np.float32)
    netlist = _netlist(2)
    congestion = _congestion([Bottleneck(x=1, y=2, utilization=2.0, overflow=1.0)])
    prod, ref = _run_both(positions, netlist, congestion)
    assert_array_identical(prod, ref)


def test_kernel_matches_oracle_direct():
    # Direct kernel-vs-oracle pin (bypassing the shim): drive the raw kernel
    # with the same marshalled inputs the shim builds, and compare its flat
    # output to the oracle's public result.
    positions = np.array([[50.5, 50.5], [52.0, 52.0], [70.0, 70.0]], dtype=np.float64)
    netlist = _netlist(3, fixed={2})
    congestion = _congestion(
        [
            Bottleneck(x=50, y=50, utilization=2.0, overflow=1.0),
            Bottleneck(x=49, y=50, utilization=2.5, overflow=1.5),
        ]
    )
    grid = congestion.grid
    coords = [
        b.to_coordinates(grid.cell_size_mm, grid.origin)
        for b in congestion.bottlenecks
        if b.overflow > 0
    ]
    np.random.seed(11)
    ref = oracle.adjust_for_congestion(positions, netlist, None, congestion, 2.0)
    np.random.seed(11)
    out = placer_adjust_for_congestion(
        positions.reshape(-1).tolist(),
        False,
        [c.fixed for c in netlist.components],
        coords,
        2.0,
        10.0,
        _numpy_dist_f64,
        _uniform,
        _cos_sin,
    )
    assert_array_identical(
        np.asarray(out).reshape(positions.shape), np.asarray(ref, dtype=np.float64)
    )
