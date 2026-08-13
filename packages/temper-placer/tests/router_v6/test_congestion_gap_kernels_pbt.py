"""R1c/R1d property + metamorphic tests for the congestion-migration gap closure.

These run against the **shipped** `router_v6.congestion` module -- which
delegates `estimate_net_demand` to the accumulator kernel
(`congestion_estimate_net_demand_py`), `get_top_bottlenecks` to the
real-records kernel (`congestion_result_top_bottlenecks_py`), and resolves
pins through `pin_world_position_kernel_py` (mirror/rotate/translate) -- so a
green property is a claim about the Rust kernels AS WIRED, not about a frozen
oracle.  The oracle-side specification lives in `test_congestion_pbt.py`
(8 properties, 4 metamorphic); the existing differential
(`test_congestion_rust_differential.py`) pins the kernels bit-exactly against
the pinned pre-migration oracle, including the new accumulation and
real-record cases.

Gate G4 -- **6 non-vacuous properties** (P1-P6), each with a
``test_pN_fails_for_<mutant>`` mutation test that re-runs the property
against a degenerate kernel (monkeypatched onto the shared ``temper_geometry``
module the shipped wrappers call) and asserts it fails.  The mutations target
exactly the three gaps:

* P1/P2/P3 mutants replace the accumulator kernel with a fresh-zero-grid
  kernel -- the pre-migration shape that dropped every net's demand but the
  first (gap 1).
* P4/P5 mutants replace the real-records kernel with an ascending / uncapped
  sort -- the sort the synthetic-overflow kernel could not do with real
  fields (gap 2).
* P6's mutant drops the bottom-side X mirror from the pin kernel -- the exact
  omission gap 3's kernel fix (``congestion_analysis.rs``, #832) repaired.

Gate G5 -- **3 metamorphic relations** (M1-M3), honestly bounded.  M1/M2
claim bit-exactness and say why the transform preserves every f64 bit
(power-of-two cell sizes, integer cell offsets, dyadic coordinates).  M3
claims bit-exactness only for the default ``demand_per_cell = 1.0`` where the
accumulated sums are integers below ``2**53`` (float addition is then exact
and the equality genuinely cannot fail from arithmetic); the tie-stability
claim for ``get_top_bottlenecks`` is exact for any finite overflow values
because timsort is stable by construction.

Module-to-property map (G4 condition 1, cluster reading):

* ``estimate_net_demand`` / the accumulator kernel -- P1, P2, P3, M1, M2.
* ``CongestionResult.get_top_bottlenecks`` / the real-records kernel -- P4, P5, M3.
* ``analyze_congestion`` (pin geometry, bottom-side) -- P6.

Vacuity is measured, not assumed (G4 condition 2): every property's
``test_pN_fails_for_<mutant>`` passes a concrete witness through
``hypothesis.inner_test`` and the property asserts a strict witness of its
own (``>``/``!=``) wherever a constant kernel would satisfy the weak reading.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import temper_geometry as _TG
from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.router_v6 import congestion as _cong
from temper_placer.router_v6.congestion import (
    Bottleneck,
    CongestionGrid,
    CongestionResult,
    analyze_congestion,
)

_SETTINGS = settings(max_examples=100, deadline=None)

_BOARD = 16.0
_CELL = 1.0

# ---------------------------------------------------------------------------
# strategies
# ---------------------------------------------------------------------------

_on_board = st.floats(min_value=0.0, max_value=_BOARD - 1e-9, allow_nan=False, allow_infinity=False)


@st.composite
def _pin_pairs(draw, min_nets: int = 1, max_nets: int = 5):
    """A list of 2-pin nets, every pin strictly inside the board."""
    n = draw(st.integers(min_value=min_nets, max_value=max_nets))
    return [
        [(draw(_on_board), draw(_on_board)), (draw(_on_board), draw(_on_board))] for _ in range(n)
    ]


def _fresh_grid(layers: int = 1, supply: float = 10.0):
    return CongestionGrid.from_board(
        Board(width=_BOARD, height=_BOARD), cell_size_mm=_CELL, num_layers=layers, default_supply=supply
    )


def _accumulate(nets, demand_per_cell: float = 1.0, layers: int = 1):
    """Accumulate nets onto one fresh grid via the SHIPPED module."""
    grid = _fresh_grid(layers)
    for pins in nets:
        grid = _cong.estimate_net_demand(grid, pins, demand_per_cell=demand_per_cell)
    return grid


def _prepopulated(pins_so_far, extra_pins):
    """A grid with ``pins_so_far`` already accumulated, then ``extra_pins``."""
    grid = _accumulate(pins_so_far)
    out = _cong.estimate_net_demand(grid, extra_pins)
    return grid, out


def _netlist_pair(offsets, sides, pos1, pos2):
    """Two single-pin components joined by one net, with explicit per-component
    pin offsets and initial_sides (both rotation 0)."""
    def _comp(ref, pos, side, offset):
        return Component(
            ref=ref,
            footprint="F",
            bounds=(1.0, 1.0),
            pins=[Pin(name="1", number="1", position=offset, net="N1")],
            initial_position=pos,
            initial_rotation_quadrant=0,
            initial_side=side,
        )

    return Netlist(
        components=[_comp("U1", pos1, sides[0], offsets[0]), _comp("U2", pos2, sides[1], offsets[1])],
        nets=[Net(name="N1", pins=[("U1", "1"), ("U2", "1")])],
    )


# ===========================================================================
# P1 -- accumulation is ADDITIVE: the delta of a net is independent of the
#       grid it accumulates onto (for the default integer demand_per_cell).
# ===========================================================================


@given(_pin_pairs(), _pin_pairs(min_nets=1, max_nets=2))
@_SETTINGS
def test_p1_accumulation_delta_is_independent_of_pre_existing_demand(prep, nets):
    """The per-cell delta of accumulating a net is the same whether the grid
    is fresh or already carries demand.

    The production shape (``analyze_congestion``'s per-net loop) depends on
    this: every net's contribution must land on top of the previous nets'
    demand, not replace it.  All sums are integers below ``2**53`` (default
    ``demand_per_cell = 1.0``), so the subtraction is exact and the claim is
    bit-exact, not approximate.
    """
    base, out = _prepopulated(prep, nets[0])
    fresh_delta = _cong.estimate_net_demand(_fresh_grid(), nets[0]).demand
    assert np.array_equal(out.demand - base.demand, fresh_delta)
    # non-vacuity: the delta really is non-zero somewhere
    assert float(fresh_delta.sum()) > 0.0


# ===========================================================================
# P2 -- pre-existing demand is never reduced by accumulating a net.
# ===========================================================================


@given(_pin_pairs(), _pin_pairs(min_nets=1, max_nets=2))
@_SETTINGS
def test_p2_accumulation_is_monotone_in_pre_existing_demand(prep, nets):
    """Accumulating a net never lowers any cell, and raises at least one."""
    before, after = _prepopulated(prep, nets[0])
    assert np.all(after.demand >= before.demand)
    assert float(after.demand.sum()) > float(before.demand.sum())


# ===========================================================================
# P3 -- routing demand is monotone non-decreasing in net count, with a
#       strict-increase witness.
# ===========================================================================


@given(_pin_pairs())
@_SETTINGS
def test_p3_demand_is_monotone_in_net_count(nets):
    before = _accumulate(nets[:-1])
    after = _accumulate(nets)
    assert np.all(after.demand >= before.demand)
    assert float(after.demand.sum()) > float(before.demand.sum())


# ===========================================================================
# P4 -- get_top_bottlenecks is a length-capped, non-increasing selection of
#       the input that preserves every real record field.
# ===========================================================================


@st.composite
def _records(draw):
    """Real bottleneck records with arbitrary fields."""
    n = draw(st.integers(min_value=0, max_value=12))
    xs = st.integers(min_value=-5, max_value=5)
    ys = st.integers(min_value=-5, max_value=5)
    util = st.floats(min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False)
    ov = st.floats(min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False)
    layers = st.integers(min_value=0, max_value=3)
    return [(draw(xs), draw(ys), draw(util), draw(ov), draw(layers)) for _ in range(n)]


@given(_records(), st.integers(min_value=0, max_value=15))
@_SETTINGS
def test_p4_top_bottlenecks_is_a_sorted_capped_selection(records, n):
    bs = [Bottleneck(x=x, y=y, utilization=u, overflow=o, layer=l) for (x, y, u, o, l) in records]
    result = CongestionResult(grid=_fresh_grid(), bottlenecks=bs)
    top = result.get_top_bottlenecks(n)

    assert len(top) == min(n, len(records))
    assert [b.overflow for b in top] == sorted([b.overflow for b in top], reverse=True)
    assert all(b in bs for b in top)
    # the true fields must survive the round trip, not be discarded
    for b in top:
        assert (b.x, b.y, b.utilization, b.layer) == (
            records[bs.index(b)][0],
            records[bs.index(b)][1],
            records[bs.index(b)][2],
            records[bs.index(b)][4],
        )
    if top:
        rest = [b for b in bs if b not in top]
        assert all(b.overflow <= min(t.overflow for t in top) for b in rest)


# ===========================================================================
# P5 -- get_top_bottlenecks boundary behaviour on n.
# ===========================================================================


@given(_records())
@_SETTINGS
def test_p5_top_bottlenecks_caps_and_identity(records):
    bs = [Bottleneck(x=x, y=y, utilization=u, overflow=o, layer=l) for (x, y, u, o, l) in records]
    result = CongestionResult(grid=_fresh_grid(), bottlenecks=bs)

    assert result.get_top_bottlenecks(0) == []
    over = result.get_top_bottlenecks(len(records) + 5)
    assert [b.overflow for b in over] == sorted([b.overflow for b in over], reverse=True)
    assert len(over) == len(records)
    # a negative n is `[:-|n|]` -- the reference's slice semantics, NOT an
    # empty list and NOT a crash.
    negative = result.get_top_bottlenecks(-1)
    assert len(negative) == max(0, len(records) - 1)
    assert negative == over[:-1]


# ===========================================================================
# P6 -- the bottom-side X mirror: a bottom-side component (side 1) with pin
#       offset (px, py) is indistinguishable from a top-side component with
#       offset (-px, py).  This is the gap-3 concern made property: real
#       boards carry bottom-side components, and the demand they write must
#       be the mirrored one.
# ===========================================================================


@given(
    st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=1.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=1.0, max_value=10.0, allow_nan=False, allow_infinity=False),
)
@_SETTINGS
def test_p6_bottom_side_mirror_is_consistent(px, py, pos1, pos2):
    """``side=1`` + offset ``(px, py)`` == ``side=0`` + offset ``(-px, py)``.

    Mirror X is an involution, so analysing the same two components with every
    component's side AND offset-x flipped (the per-component transform
    ``(side, ox) -> (1 - side, -ox)``) must produce a byte-identical demand
    grid.  This is the property the pre-#832 kernel violated on every
    bottom-side component.
    """
    a = analyze_congestion(
        _netlist_pair([(px, py), (px, py)], [0, 1], (pos1, pos1), (pos2, pos2)),
        Board(width=_BOARD, height=_BOARD),
    )
    b = analyze_congestion(
        _netlist_pair([(-px, py), (-px, py)], [1, 0], (pos1, pos1), (pos2, pos2)),
        Board(width=_BOARD, height=_BOARD),
    )
    assert np.array_equal(a.grid.demand, b.grid.demand)


# ===========================================================================
# METAMORPHIC RELATIONS (gate G5)
# ===========================================================================


@given(_pin_pairs(), st.integers(min_value=-4, max_value=4), st.integers(min_value=-4, max_value=4))
@_SETTINGS
def test_m1_translation_by_whole_cells_is_bit_exact(nets, dcol, drow):
    """M1 -- translating pins AND the origin by a whole number of cells
    leaves the demand array **bit-identical**.

    Exactness claim: exact, every bit.  ``_CELL`` is ``1.0`` (a power of
    two) and the offsets are small integers, so ``pin + k*cell`` and
    ``origin + k*cell`` are both exact for the magnitudes drawn here.
    """
    dx = float(dcol) * _CELL
    dy = float(drow) * _CELL

    base = _accumulate(nets)
    grid = CongestionGrid.from_board(
        Board(width=_BOARD, height=_BOARD, origin=(dx, dy)), cell_size_mm=_CELL
    )
    for pins in nets:
        grid = _cong.estimate_net_demand(grid, [(x + dx, y + dy) for (x, y) in pins])
    assert np.array_equal(base.demand, grid.demand)
    assert base.demand.dtype == grid.demand.dtype


@given(_pin_pairs(), st.integers(min_value=-6, max_value=6))
@_SETTINGS
def test_m2_power_of_two_scaling_is_bit_exact(nets, exponent):
    """M2 -- scaling every coordinate and the cell size by the same power of
    two leaves the demand array **bit-identical**.

    Exactness claim: exact, every bit.  Multiplication by ``2**k`` only
    shifts the exponent field, so ``x * s / (cell * s)`` reproduces
    ``x / cell`` exactly and every ``int()`` truncation lands on the same
    cell.
    """
    scale = 2.0**exponent
    base = _accumulate(nets)

    scaled = CongestionGrid.from_board(
        Board(width=_BOARD * scale, height=_BOARD * scale), cell_size_mm=_CELL * scale
    )
    for pins in nets:
        scaled = _cong.estimate_net_demand(scaled, [(x * scale, y * scale) for (x, y) in pins])
    assert np.array_equal(base.demand, scaled.demand)


@given(_records())
@_SETTINGS
def test_m3_tie_stability_of_the_real_records_sort(records):
    """M3 -- records with EQUAL overflow keep their input order (bit-exact).

    ``sorted(..., reverse=True)`` is timsort, which is stable; a Rust mirror
    with an unstable sort would reorder equal-overflow records.  The order of
    the equal-overflow prefix is asserted directly.
    """
    if len(records) < 2:
        return
    bs = [Bottleneck(x=x, y=y, utilization=u, overflow=o, layer=l) for (x, y, u, o, l) in records]
    result = CongestionResult(grid=_fresh_grid(), bottlenecks=bs)
    top = result.get_top_bottlenecks(len(records))
    by_overflow = sorted(range(len(records)), key=lambda i: records[i][3], reverse=True)
    assert [b.overflow for b in top] == [records[i][3] for i in by_overflow]
    # the exact tie case: equal overflows appear in input order
    tie_sorted = sorted(records, key=lambda r: r[3], reverse=True)
    got = [(b.x, b.y, b.utilization, b.overflow, b.layer) for b in top]
    assert got == tie_sorted


# ===========================================================================
# Mutation tests (gate G4 vacuity guard).
#
# Each monkeypatches the shared `temper_geometry` module the shipped
# wrappers call, so the property runs against the DEGENERATE kernel through
# the real delegation path, then the fixture restores the real kernel.
# ===========================================================================


def test_p1_fails_for_a_fresh_grid_kernel(monkeypatch):
    """Gap 1's defect: a kernel that ignores the accumulator and rebuilds a
    fresh zero grid drops the pre-existing demand, so the delta depends on
    it and P1 fails."""

    def fresh_grid(width, height, cell, origin, pins, layer, per_cell, layers, demand=None):  # noqa: ARG001
        wc, hc = int(width / cell), int(height / cell)
        shape = (hc, wc) if layers == 1 else (layers, hc, wc)
        import numpy as _np
        return (_np.zeros(shape), False)

    monkeypatch.setattr(_TG, "congestion_estimate_net_demand_py", fresh_grid)
    with pytest.raises(AssertionError):
        test_p1_accumulation_delta_is_independent_of_pre_existing_demand.hypothesis.inner_test(
            [[(1.0, 1.0), (4.0, 4.0)]], [[(2.0, 2.0), (3.0, 3.0)]]
        )


def test_p2_fails_for_an_erasing_kernel(monkeypatch):
    """A kernel that returns the grid without adding demand satisfies 'never
    lowers' only vacuously; the strict-increase witness is the failure."""

    def noop(width, height, cell, origin, pins, layer, per_cell, layers, demand=None):  # noqa: ARG001
        return (demand, False)

    monkeypatch.setattr(_TG, "congestion_estimate_net_demand_py", noop)
    with pytest.raises(AssertionError):
        test_p2_accumulation_is_monotone_in_pre_existing_demand.hypothesis.inner_test(
            [[(1.0, 1.0), (4.0, 4.0)]], [[(2.0, 2.0), (3.0, 3.0)]]
        )


def test_p3_fails_for_an_identity_kernel(monkeypatch):
    """A kernel that never adds demand satisfies 'never decreases' and fails
    the strict-increase witness -- which is why the witness is there."""

    def identity(grid, pins, layer=0, demand_per_cell=1.0):  # noqa: ARG001
        return grid

    monkeypatch.setattr(_cong, "estimate_net_demand", identity)
    with pytest.raises(AssertionError):
        test_p3_demand_is_monotone_in_net_count.hypothesis.inner_test(
            [[(1.0, 1.0), (4.0, 4.0)], [(6.0, 6.0), (9.0, 9.0)]]
        )


def test_p4_fails_for_an_ascending_sort(monkeypatch):
    """Sorting the wrong way round keeps every item and the right length, so
    only the ordering assertion catches it."""

    def ascending(records, n):
        return sorted(records, key=lambda r: r[3])[:n]

    monkeypatch.setattr(_TG, "congestion_result_top_bottlenecks_py", ascending)
    with pytest.raises(AssertionError):
        test_p4_top_bottlenecks_is_a_sorted_capped_selection.hypothesis.inner_test(
            [(1, 1, 0.0, 1.0, 0), (2, 2, 0.0, 5.0, 1), (3, 3, 0.0, 3.0, 0)], 3
        )


def test_p5_fails_for_an_uncapped_selection(monkeypatch):
    """Ignoring ``n`` returns too many items."""

    def uncapped(records, n):  # noqa: ARG001
        return sorted(records, key=lambda r: r[3], reverse=True)

    monkeypatch.setattr(_TG, "congestion_result_top_bottlenecks_py", uncapped)
    with pytest.raises(AssertionError):
        test_p5_top_bottlenecks_caps_and_identity.hypothesis.inner_test(
            [(1, 1, 0.0, 1.0, 0), (2, 2, 0.0, 5.0, 1)]
        )


def test_p6_fails_for_a_kernel_without_the_bottom_side_mirror(monkeypatch):
    """Gap 3's defect: without the `side == 1 -> px = -px` mirror, a
    bottom-side component's pin lands on the wrong side of its origin, so the
    side-flip involution breaks."""

    import temper_placer.core.pin_geometry as pin_geometry_mod

    def no_mirror(px, py, side, rotation_rad, cx, cy):  # noqa: ARG001
        # The pre-#832 behaviour: no `side == 1 -> px = -px` mirror, then the
        # same R(-theta) rotation and translation.  The two sides then place
        # their pins on OPPOSITE x-sides of the component origin, so the
        # side-flip involution P6 asserts breaks.
        c = math.cos(rotation_rad)
        s = math.sin(rotation_rad)
        rx = px * c + py * s
        ry = -px * s + py * c
        return (cx + rx, cy + ry)

    monkeypatch.setattr(pin_geometry_mod._tg, "pin_world_position_kernel_py", no_mirror)
    with pytest.raises(AssertionError):
        test_p6_bottom_side_mirror_is_consistent.hypothesis.inner_test(2.0, 1.0, 5.0, 9.0)


# ---------------------------------------------------------------------------
# Sanity: the input classes are genuinely discriminating.
# ---------------------------------------------------------------------------


def test_strategies_are_discriminating():
    """Guards against a strategy collapsing to a single trivial value."""
    acc = _accumulate([[(1.0, 1.0), (4.0, 4.0)], [(6.0, 6.0), (9.0, 9.0)]])
    assert float(acc.demand.sum()) > 0.0
    assert len(np.unique(acc.demand)) > 1, "the accumulated grid is uniform"

    base, out = _prepopulated([[(1.0, 1.0), (4.0, 4.0)]], [(6.0, 6.0), (9.0, 9.0)])
    assert float(out.demand.sum()) > float(base.demand.sum())

    mirror = analyze_congestion(
        _netlist_pair([(2.0, 1.0), (2.0, 1.0)], [0, 1], (5.0, 5.0), (9.0, 9.0)),
        Board(width=_BOARD, height=_BOARD),
    )
    assert float(mirror.grid.demand.sum()) > 0.0

    recs = [(1, 1, 0.0, 1.0, 0), (2, 2, 0.0, 5.0, 1)]
    top = CongestionResult(grid=_fresh_grid(), bottlenecks=[Bottleneck(*r) for r in recs]).get_top_bottlenecks(1)
    assert len(top) == 1 and top[0].overflow == 5.0
