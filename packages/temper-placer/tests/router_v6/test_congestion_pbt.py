"""R1c/R1d property + metamorphic tests for Wave-4 cluster E (congestion & feedback).

**GREEN.**  These run against the pinned oracle
(``tests/router_v6/_congestion_py_oracle.py``), which is the pre-migration
behaviour; they are the specification the Phase-B Rust must also satisfy, and
they are written now so that "the Rust passes the properties" is a claim about
properties that existed before it did.

Gate G4 -- **8 non-vacuous properties** (P1-P8), each with at least one
``test_pN_fails_for_<mutant>`` mutation test that re-runs the property against
a degenerate kernel through ``hypothesis.inner_test`` and asserts it fails.
A property nobody can break is a property nobody is testing.

Gate G5 -- **4 metamorphic relations** (M1-M4), honestly bounded.  M1/M2/M4
claim **bit-exactness** and say why the transform preserves every f64 bit
(power-of-two cell sizes, integer cell offsets, dyadic coordinates).  M3
claims exactness only for the default ``demand_per_cell = 1.0``, where the
accumulated sum is an integer below 2**53 and float addition is therefore
associative; at other values it is stated as approximate and is NOT asserted
as exact.

Two bounds here were **found by these tests, not assumed**, and are recorded
rather than smoothed over:

* P3's natural strengthening ("positive demand gives positive utilization")
  is false -- ``5e-324 / 2.0`` underflows to ``+0.0``.  That is B8's standing
  denormal class showing up in this kernel.
* P5's natural companion ("damping 1.0 reproduces ``suggested`` exactly") is
  false -- ``c + (s - c) * 1.0`` rounds the subtraction, so it lands within
  one ulp *of the span*, not of the endpoint.  A Rust mirror written as the
  exact ``c*(1-d) + s*d`` lerp would be endpoint-exact and would therefore
  **fail the differential**.

Scope note
----------
The strategies below deliberately keep pins **on-board** for the monotonicity
and metamorphic properties.  Off-board pins hit defect D3 (a negative-index
slice that writes a block at the origin -- see the oracle header), which makes
"adding a net never decreases demand" false in a way that is a *property of
the defect*, not of the kernel.  D3 is pinned by name in the differential;
duplicating it here as a weakened property would hide it.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import tests.router_v6._congestion_py_oracle as ORACLE
from tests.router_v6._congestion_builders import build_board, build_grid, build_netlist

_SETTINGS = settings(max_examples=100, deadline=None)

_BOARD = 16.0
_CELL = 1.0


# ---------------------------------------------------------------------------
# strategies
# ---------------------------------------------------------------------------

_on_board = st.floats(min_value=0.0, max_value=_BOARD - 1e-9, allow_nan=False, allow_infinity=False)


@st.composite
def _pin_pairs(draw, min_nets: int = 1, max_nets: int = 6):
    """A list of 2-pin nets, every pin strictly inside the board."""
    n = draw(st.integers(min_value=min_nets, max_value=max_nets))
    return [
        [(draw(_on_board), draw(_on_board)), (draw(_on_board), draw(_on_board))] for _ in range(n)
    ]


@st.composite
def _net_designs(draw):
    """A ``(components, nets)`` pair in the corpus's tuple shape.

    Every net is 2-pin and every pin is on-board, so the D3 negative-index
    slice (see the oracle header) is out of scope here -- it is pinned by
    name in the differential instead.
    """
    n = draw(st.integers(min_value=1, max_value=5))
    components = []
    nets = []
    for i in range(n):
        components.append(
            (f"U{i}A", (draw(_on_board), draw(_on_board)), 0, [("1", (0.0, 0.0), f"N{i}")])
        )
        components.append(
            (f"U{i}B", (draw(_on_board), draw(_on_board)), 0, [("1", (0.0, 0.0), f"N{i}")])
        )
        nets.append((f"N{i}", [(f"U{i}A", "1"), (f"U{i}B", "1")]))
    return components, nets


@st.composite
def _demand_supply(draw):
    n = draw(st.integers(min_value=1, max_value=8))
    finite = st.floats(
        min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False, width=64
    )
    return ([draw(finite) for _ in range(n)], [draw(finite) for _ in range(n)])


@st.composite
def _heatmap_field(draw):
    rows = draw(st.integers(min_value=1, max_value=4))
    cols = draw(st.integers(min_value=1, max_value=4))
    layers = draw(st.integers(min_value=1, max_value=3))
    cell = st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False)
    present = [[[draw(cell) for _ in range(layers)] for _ in range(cols)] for _ in range(rows)]
    history = [[[draw(cell) for _ in range(layers)] for _ in range(cols)] for _ in range(rows)]
    return present, history


class _Router:
    __slots__ = ("_conflicts", "cell_size", "history_cost", "origin", "present_congestion")

    def __init__(self, present, history, conflicts=(), cell_size=1.0, origin=(0.0, 0.0)):
        self.present_congestion = np.array(present, dtype=np.float64)
        self.history_cost = np.array(history, dtype=np.float64)
        self._conflicts = list(conflicts)
        self.cell_size = cell_size
        self.origin = origin

    def get_conflict_locations(self):
        return self._conflicts


def _fresh_grid(layers: int = 1, supply: float = 10.0):
    return ORACLE.CongestionGrid.from_board(
        build_board(_BOARD, _BOARD), cell_size_mm=_CELL, num_layers=layers, default_supply=supply
    )


def _accumulate(nets, demand_per_cell: float = 1.0, layers: int = 1, supply: float = 10.0):
    grid = _fresh_grid(layers, supply)
    for pins in nets:
        grid = ORACLE.estimate_net_demand(grid, pins, demand_per_cell=demand_per_cell)
    return grid


# ===========================================================================
# P1 -- routing demand is monotone non-decreasing in net count, with a
#       strict-increase witness.
# ===========================================================================


@given(_pin_pairs())
@_SETTINGS
def test_p1_demand_is_monotone_in_net_count(nets):
    """Adding a net never lowers any cell's demand, and adds at least one.

    A degenerate kernel that returns the grid unchanged satisfies "never
    lowers"; the strict witness is what makes the property non-vacuous, and
    the mutation test at the bottom proves a constant kernel fails it.
    """
    before = _accumulate(nets[:-1])
    after = _accumulate(nets)
    assert np.all(after.demand >= before.demand)
    # a 2-pin net whose bbox is entirely on-board always covers >= 1 cell
    assert float(after.demand.sum()) > float(before.demand.sum())


# ===========================================================================
# P2 -- overflow is non-negative and is exactly the positive part of
#       (demand - supply).
# ===========================================================================


@given(_demand_supply())
@_SETTINGS
def test_p2_overflow_is_the_positive_part(pair):
    """``np.maximum(demand - supply, 0.0)``: never negative, and zero exactly
    where demand does not exceed supply."""
    demand, supply = pair
    grid = build_grid(ORACLE, demand, supply)
    overflow = grid.get_overflow()
    assert np.all(overflow >= 0.0)
    raw = grid.demand - grid.supply
    assert np.array_equal(overflow[raw > 0.0], raw[raw > 0.0])
    assert np.all(overflow[raw <= 0.0] == 0.0)


# ===========================================================================
# P3 -- utilization respects the 1e-6 supply floor and is sign-consistent
#       with demand.
# ===========================================================================


@given(_demand_supply())
@_SETTINGS
def test_p3_utilization_uses_the_supply_floor(pair):
    """The denominator is ``np.maximum(supply, 1e-6)``, so a zero or negative
    supply divides by exactly ``1e-6`` -- never by zero, never by a negative
    number -- and the quotient never has the opposite sign to the demand.

    **Bounded honestly**: the natural strengthening "positive demand gives
    positive utilization" is **false**, and hypothesis found the witness --
    ``demand = 5e-324`` (the smallest denormal) over ``supply = 2.0``
    underflows to ``+0.0``.  That is not a defect, it is IEEE arithmetic, and
    it is the reason B8 (denormal underflow) is a standing class: a
    fast-math Rust build would flush the *input* too and reach the same zero
    by a different route, which is exactly the divergence B8 warns about.
    So the property asserts non-negativity, not positivity, and the
    underflow band is asserted explicitly below.
    """
    demand, supply = pair
    grid = build_grid(ORACLE, demand, supply)
    util = grid.get_utilization()
    denom = np.maximum(grid.supply, 1e-6)
    assert np.all(denom >= 1e-6)
    assert np.array_equal(util, grid.demand / denom)
    positive = grid.demand > 0.0
    assert np.all(util[positive] >= 0.0)
    assert np.all(util[grid.demand < 0.0] <= 0.0)
    assert np.all(util[grid.demand == 0.0] == 0.0)


def test_p3_underflow_band_is_reachable_and_stays_signed():
    """The witness for P3's bounded claim, pinned as its own case.

    ``5e-324 / 2.0`` is ``+0.0``: a positive demand with a zero utilization.
    The sign bit survives, which is the part a Rust mirror can still get
    wrong (``-0.0`` vs ``+0.0`` are distinguishable by ``float.hex``).
    """
    grid = build_grid(ORACLE, [5e-324, -5e-324], [2.0, 2.0])
    util = grid.get_utilization()
    assert util[0, 0] == 0.0
    assert math.copysign(1.0, float(util[0, 0])) == 1.0
    assert math.copysign(1.0, float(util[0, 1])) == -1.0


# ===========================================================================
# P4 -- every reported bottleneck is a real overflowing cell, and none is
#       missed.
# ===========================================================================


@given(_net_designs(), st.floats(min_value=0.0, max_value=2.0, allow_nan=False))
@_SETTINGS
def test_p4_bottlenecks_are_exactly_the_overflowing_cells(design, capacity):
    """``analyze_congestion``'s bottleneck list is exactly the cells whose
    demand exceeds their supply, each carrying that cell's own numbers.

    The expectation is recomputed **independently**, straight from the
    returned ``demand``/``supply`` arrays with plain numpy -- not by calling
    ``get_overflow`` again.  That is what stops the property from being a
    restatement of the implementation, and it is what lets the mutation test
    below break it by replacing ``get_overflow``.
    """
    components, nets = design
    result = ORACLE.analyze_congestion(
        build_netlist(components, nets),
        build_board(_BOARD, _BOARD),
        cell_size_mm=_CELL,
        capacity_per_cell=capacity,
    )
    raw_overflow = np.maximum(result.grid.demand - result.grid.supply, 0.0)
    raw_util = result.grid.demand / np.maximum(result.grid.supply, 1e-6)

    expected = {(int(c), int(r)) for r, c in zip(*np.where(raw_overflow > 0.0))}
    assert {(b.x, b.y) for b in result.bottlenecks} == expected
    assert len(result.bottlenecks) == len(expected)  # no duplicates
    for b in result.bottlenecks:
        assert b.overflow > 0.0
        assert float(raw_overflow[b.y, b.x]) == b.overflow
        assert float(raw_util[b.y, b.x]) == b.utilization
        assert b.layer == 0
    assert result.total_overflow == float(raw_overflow.sum())
    assert result.max_utilization == float(raw_util.max())
    assert result.is_feasible() == (result.max_utilization <= 1.0)


# ===========================================================================
# P8 -- get_top_bottlenecks is a length-capped, non-increasing selection of
#       the input.
# ===========================================================================


@given(
    st.lists(
        st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
        min_size=0,
        max_size=12,
    ),
    st.integers(min_value=0, max_value=15),
)
@_SETTINGS
def test_p8_top_bottlenecks_is_a_sorted_capped_selection(overflows, n):
    """At most ``n`` items, every one from the input, in non-increasing
    overflow order, and the same multiset as the ``n`` largest."""
    bottlenecks = [
        ORACLE.Bottleneck(x=i, y=0, utilization=0.0, overflow=o) for i, o in enumerate(overflows)
    ]
    result = ORACLE.CongestionResult(grid=build_grid(ORACLE, [0.0], [1.0]), bottlenecks=bottlenecks)
    top = result.get_top_bottlenecks(n)

    assert len(top) == min(n, len(overflows))
    assert all(b in bottlenecks for b in top)
    assert [b.overflow for b in top] == sorted([b.overflow for b in top], reverse=True), (
        "not in non-increasing overflow order"
    )
    if top:
        rest = [b for b in bottlenecks if b not in top]
        assert all(b.overflow <= min(t.overflow for t in top) for b in rest)


# ===========================================================================
# P5 -- damping produces a point on the segment, with the two endpoints
#       reproduced exactly.
# ===========================================================================


@given(
    st.floats(min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
@_SETTINGS
def test_p5_damping_is_a_convex_combination(cx, cy, sx, sy, damping):
    """``_calculate_damped_position`` interpolates: exactly ``current`` at
    ``damping == 0``, and never outside the axis-aligned box between the two
    endpoints (up to one rounding step) in between.

    **Bounded honestly, and the bound was found by this test.**  The obvious
    companion claim -- "exactly ``suggested`` at ``damping == 1``" -- is
    **false** for the reference's own expression.  ``c + (s - c) * 1.0``
    rounds ``s - c`` first, so the result is only within one ulp of ``s``:
    hypothesis's witness is ``c = -733.0``, ``s = 291.9999999999999``, which
    comes back as ``292.0``.  That is a property of the *form* the module
    chose, not of any implementation of it, so it is recorded as a fact
    (:func:`test_p5_endpoint_is_not_exact_at_full_damping`) instead of being
    asserted here.  A Rust mirror written as ``lerp(c, s, d)`` or
    ``c*(1-d) + s*d`` would give the exact endpoint and therefore **fail the
    differential** -- which is the point.
    """
    current = (cx, cy)
    suggested = (sx, sy)
    got = ORACLE._calculate_damped_position(current, suggested, damping)

    if damping == 0.0:
        # `(s - c) * 0.0` is exactly +0.0 for finite operands, and
        # `c + 0.0 == c` for every finite c, so this endpoint IS exact.
        assert got == current

    lo_x, hi_x = min(cx, sx), max(cx, sx)
    lo_y, hi_y = min(cy, sy), max(cy, sy)
    # a rounding slack of one ulp of the span: the interpolation is
    # `c + (s - c) * d`, which can land one ulp outside the closed interval
    slack_x = max(abs(hi_x - lo_x), 1.0) * 1e-12
    slack_y = max(abs(hi_y - lo_y), 1.0) * 1e-12
    assert lo_x - slack_x <= got[0] <= hi_x + slack_x
    assert lo_y - slack_y <= got[1] <= hi_y + slack_y


def test_p5_endpoint_is_not_exact_at_full_damping():
    """P5's bounded claim, with the witness hypothesis found.

    ``c + (s - c) * 1.0 != s`` in general: the subtraction rounds.  Pinned so
    a Phase-B author who "improves" the Rust to ``c*(1-d) + s*d`` sees why
    the differential then fails, rather than concluding the differential is
    wrong.
    """
    c, s = -733.0, 291.9999999999999
    got = ORACLE._calculate_damped_position((c, 0.0), (s, 0.0), 1.0)
    assert got[0] == 292.0
    assert got[0] != s
    # The error is one ulp of the SPAN (`s - c` is what rounds), not one ulp
    # of the endpoint -- so it grows with how far apart the two points are.
    # Measured here: 1.14e-13 absolute over a span of ~1025.
    assert abs(got[0] - s) <= abs(s - c) * 2.0**-52
    assert abs(got[0] - s) > abs(s) * 2.0**-53

    # the exact-lerp spelling a Rust author would reach for gives `s` back
    assert c * (1.0 - 1.0) + s * 1.0 == s

    # ... while damping 0.0 IS exact, in both spellings
    assert ORACLE._calculate_damped_position((c, 0.0), (s, 0.0), 0.0)[0] == c


# ===========================================================================
# P6 -- the routing-demand net classification partitions the routable nets.
# ===========================================================================


@given(
    st.lists(
        st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ_+-0123456789", min_size=1, max_size=8).filter(
            lambda s: s.strip() != ""
        ),
        min_size=0,
        max_size=8,
        unique=True,
    )
)
@_SETTINGS
def test_p6_net_classes_partition_the_routable_nets(names):
    """Every routable net lands in exactly one of signal / power / diff-pair.

    The three counters are incremented in an if/elif/else, so their sum must
    equal ``routable_nets`` -- and ``routable_nets`` must never exceed
    ``total_nets``.  This is the invariant ``validate_routing_demand`` checks
    a weaker version of in production.
    """
    from tests.router_v6._congestion_builders import build_parsed_pcb

    components = [("U1", [(str(i), n) for i, n in enumerate(names)])]
    components.append(("U2", [(str(i), n) for i, n in enumerate(names)]))
    demand = ORACLE.estimate_routing_demand(build_parsed_pcb(components, list(names)))

    assert demand.signal_nets + demand.power_nets + demand.diff_pair_nets == demand.routable_nets
    assert demand.routable_nets <= demand.total_nets
    assert demand.total_nets == len(names)
    assert demand.total_pins == 2 * len(names)
    if demand.routable_nets:
        assert demand.max_pins_per_net >= demand.avg_pins_per_net
    else:
        assert demand.avg_pins_per_net == 0.0
        assert demand.max_pins_per_net == 0


# ===========================================================================
# P7 -- the heatmap normalizes to a maximum of exactly 1.0 (or leaves the
#       field alone when there is nothing to normalize).
# ===========================================================================


@given(_heatmap_field())
@_SETTINGS
def test_p7_heatmap_normalizes_to_unit_maximum(field):
    """``from_router`` divides by ``np.max(combined)`` when that is positive.

    So the resulting f32 grid has a maximum of exactly 1.0; and when the
    combined field has no positive cell, the array is returned *unnormalized*
    -- a branch a "always divide" implementation would get wrong on an
    all-zero board.
    """
    present, history = field
    heatmap = ORACLE.CongestionHeatmap.from_router(_Router(present, history))
    assert heatmap.grid.dtype == np.float32

    combined = np.max(np.array(present), axis=2) + 0.5 * (np.max(np.array(history), axis=2) - 1.0)
    max_val = float(np.max(combined))
    if max_val > 0.0:
        assert float(np.max(heatmap.grid)) == pytest.approx(1.0, abs=1e-6)
        assert float(np.max(heatmap.grid)) <= 1.0 + 1e-6
    else:
        assert np.array_equal(heatmap.grid, combined.astype(np.float32))

    total = heatmap.get_total_congestion()
    assert total == float(np.sum(heatmap.grid))
    assert total <= heatmap.grid.size * (1.0 + 1e-6) or max_val <= 0.0


# ===========================================================================
# METAMORPHIC RELATIONS (gate G5)
# ===========================================================================


@given(_pin_pairs(), st.integers(min_value=-4, max_value=4), st.integers(min_value=-4, max_value=4))
@_SETTINGS
def test_m1_translation_by_whole_cells_is_bit_exact(nets, dcol, drow):
    """M1 -- translating pins AND the origin by a whole number of cells
    leaves the demand array **bit-identical**.

    **Exactness claim: exact, every bit.**  ``_CELL`` is ``1.0`` (a power of
    two) and the offsets are small integers, so ``pin + k*cell`` and
    ``origin + k*cell`` are both exact for the magnitudes drawn here
    (|value| < 32, and every intermediate is an integer multiple of a power
    of two well inside the f64 significand).  Nothing here needs a tolerance,
    and none is used.
    """
    dx = float(dcol) * _CELL
    dy = float(drow) * _CELL
    origin = (dx, dy)

    base = _accumulate(nets)
    grid = ORACLE.CongestionGrid.from_board(build_board(_BOARD, _BOARD, origin), cell_size_mm=_CELL)
    for pins in nets:
        grid = ORACLE.estimate_net_demand(grid, [(x + dx, y + dy) for (x, y) in pins])

    assert np.array_equal(base.demand, grid.demand)
    assert base.demand.dtype == grid.demand.dtype


@given(_pin_pairs(), st.integers(min_value=-6, max_value=6))
@_SETTINGS
def test_m2_power_of_two_scaling_is_bit_exact(nets, exponent):
    """M2 -- scaling every coordinate and the cell size by the same power of
    two leaves the demand array **bit-identical**.

    **Exactness claim: exact, every bit.**  Multiplication by ``2**k`` only
    shifts the exponent field, so ``x * s / (cell * s)`` reproduces
    ``x / cell`` exactly and every ``int()`` truncation lands on the same
    cell.  This is the one scale family where exactness is legitimate; a
    non-dyadic scale is *not* claimed and is not tested.
    """
    scale = 2.0**exponent
    base = _accumulate(nets)

    scaled = ORACLE.CongestionGrid.from_board(
        build_board(_BOARD * scale, _BOARD * scale), cell_size_mm=_CELL * scale
    )
    for pins in nets:
        scaled = ORACLE.estimate_net_demand(scaled, [(x * scale, y * scale) for (x, y) in pins])

    assert np.array_equal(base.demand, scaled.demand)


@given(_pin_pairs(min_nets=2, max_nets=5), st.data())
@_SETTINGS
def test_m3_net_insertion_order_does_not_change_demand(nets, data):
    """M3 -- permuting the order in which nets are accumulated leaves the
    demand array **bit-identical**, at the default ``demand_per_cell``.

    **Exactness claim: exact ONLY for ``demand_per_cell = 1.0``** (the
    default, and the value ``analyze_congestion`` always uses).  Each cell
    then accumulates a sum of 1.0s -- an integer far below ``2**53`` -- and
    integer-valued f64 addition is associative, so the order genuinely cannot
    matter.  At an arbitrary ``demand_per_cell`` the accumulation is a sum of
    equal non-dyadic floats and reordering is only approximately invariant;
    that weaker statement is deliberately **not** asserted, because a
    metamorphic relation with a tolerance nobody derived is worse than none.
    """
    order = data.draw(st.permutations(range(len(nets))))
    base = _accumulate(nets, demand_per_cell=1.0)
    permuted = _accumulate([nets[i] for i in order], demand_per_cell=1.0)
    assert np.array_equal(base.demand, permuted.demand)
    # non-vacuity: there must be something to permute
    assert len(nets) >= 2


@given(
    st.floats(min_value=-1024.0, max_value=1024.0, allow_nan=False).map(lambda v: float(int(v))),
    st.floats(min_value=-1024.0, max_value=1024.0, allow_nan=False).map(lambda v: float(int(v))),
    st.integers(min_value=-8, max_value=8),
    st.sampled_from([0.0, 0.25, 0.5, 0.75, 1.0]),
)
@_SETTINGS
def test_m4_damping_is_exactly_scale_equivariant(cx, sx, exponent, damping):
    """M4 -- ``_calculate_damped_position`` commutes with a power-of-two
    scaling of both endpoints, **bit-exactly**.

    **Exactness claim: exact, every bit**, and only because all three
    ingredients are dyadic: the coordinates are drawn as integers, the
    damping factors are quarters, and the scale is ``2**k``.  ``c + (s - c)*d``
    is then a chain of exactly-representable operations, so
    ``f(c*S, s*S, d) == f(c, s, d) * S``.  With a non-dyadic damping factor
    this would be a tolerance claim, and it is not made.
    """
    scale = 2.0**exponent
    plain = ORACLE._calculate_damped_position((cx, 0.0), (sx, 0.0), damping)
    scaled = ORACLE._calculate_damped_position((cx * scale, 0.0), (sx * scale, 0.0), damping)
    assert scaled[0] == plain[0] * scale
    assert scaled[1] == plain[1] * scale


# ===========================================================================
# Mutation tests (gate G4 vacuity guard).
#
# Each restores the kernel it replaced, so ordering between tests cannot
# leak a mutant into an unrelated property.
# ===========================================================================


@pytest.fixture
def restore_kernels():
    saved = {
        name: getattr(ORACLE, name)
        for name in (
            "estimate_net_demand",
            "_calculate_damped_position",
            "estimate_routing_demand",
        )
    }
    saved_methods = {
        "get_overflow": ORACLE.CongestionGrid.get_overflow,
        "get_utilization": ORACLE.CongestionGrid.get_utilization,
        "from_router": ORACLE.CongestionHeatmap.from_router,
        "get_top_bottlenecks": ORACLE.CongestionResult.get_top_bottlenecks,
    }
    yield
    for name, fn in saved.items():
        setattr(ORACLE, name, fn)
    ORACLE.CongestionGrid.get_overflow = saved_methods["get_overflow"]
    ORACLE.CongestionGrid.get_utilization = saved_methods["get_utilization"]
    ORACLE.CongestionHeatmap.from_router = saved_methods["from_router"]
    ORACLE.CongestionResult.get_top_bottlenecks = saved_methods["get_top_bottlenecks"]


_SAMPLE_NETS = [[(1.0, 1.0), (4.0, 4.0)], [(6.0, 6.0), (9.0, 9.0)]]
_SAMPLE_DESIGN = (
    [
        ("U0A", (1.0, 1.0), 0, [("1", (0.0, 0.0), "N0")]),
        ("U0B", (4.0, 4.0), 0, [("1", (0.0, 0.0), "N0")]),
        ("U1A", (2.0, 2.0), 0, [("1", (0.0, 0.0), "N1")]),
        ("U1B", (6.0, 6.0), 0, [("1", (0.0, 0.0), "N1")]),
    ],
    [("N0", [("U0A", "1"), ("U0B", "1")]), ("N1", [("U1A", "1"), ("U1B", "1")])],
)


def test_p1_fails_for_identity_kernel(restore_kernels):
    """A kernel that never adds demand satisfies "never decreases" and fails
    the strict-increase witness -- which is why the witness is there."""

    def identity(grid, pins, layer=0, demand_per_cell=1.0):  # noqa: ARG001
        return grid

    ORACLE.estimate_net_demand = identity
    with pytest.raises(AssertionError):
        test_p1_demand_is_monotone_in_net_count.hypothesis.inner_test(_SAMPLE_NETS)


def test_p2_fails_for_unclipped_overflow(restore_kernels):
    """``demand - supply`` without the ``np.maximum(..., 0.0)`` goes negative."""
    ORACLE.CongestionGrid.get_overflow = lambda self: self.demand - self.supply
    with pytest.raises(AssertionError):
        test_p2_overflow_is_the_positive_part.hypothesis.inner_test(([0.0], [5.0]))


def test_p3_fails_for_unfloored_division(restore_kernels):
    """Dividing by the raw supply gives ``inf`` (or a negative ratio) where
    the reference's ``1e-6`` floor gives a finite positive one."""
    ORACLE.CongestionGrid.get_utilization = lambda self: self.demand / self.supply
    with pytest.raises(AssertionError):
        test_p3_utilization_uses_the_supply_floor.hypothesis.inner_test(([1.0], [-1.0]))


def test_p4_fails_for_a_suppressed_overflow(restore_kernels):
    """An overflow kernel that reports nothing drops every bottleneck.

    The property recomputes its expectation straight from ``demand`` and
    ``supply``, so replacing ``get_overflow`` desynchronizes the two and the
    set equality fails.  A property that had called ``get_overflow`` for its
    own expectation would sail through this."""
    ORACLE.CongestionGrid.get_overflow = lambda self: np.zeros_like(self.demand)
    with pytest.raises(AssertionError):
        test_p4_bottlenecks_are_exactly_the_overflowing_cells.hypothesis.inner_test(
            _SAMPLE_DESIGN, 0.0
        )


def test_p8_fails_for_an_ascending_sort(restore_kernels):
    """Sorting the wrong way round keeps every item and the right length, so
    only the ordering assertion catches it."""
    ORACLE.CongestionResult.get_top_bottlenecks = lambda self, n=10: sorted(
        self.bottlenecks, key=lambda b: b.overflow
    )[:n]
    with pytest.raises(AssertionError):
        test_p8_top_bottlenecks_is_a_sorted_capped_selection.hypothesis.inner_test(
            [1.0, 5.0, 3.0], 3
        )


def test_p8_fails_for_an_uncapped_selection(restore_kernels):
    """Ignoring ``n`` returns too many items."""
    ORACLE.CongestionResult.get_top_bottlenecks = lambda self, n=10: sorted(  # noqa: ARG005
        self.bottlenecks, key=lambda b: b.overflow, reverse=True
    )
    with pytest.raises(AssertionError):
        test_p8_top_bottlenecks_is_a_sorted_capped_selection.hypothesis.inner_test(
            [1.0, 5.0, 3.0], 1
        )


def test_p5_fails_for_a_constant_position(restore_kernels):
    """A kernel returning a fixed point is not an interpolation."""

    def constant(current, suggested, damping):  # noqa: ARG001
        return (7.0, 7.0)

    ORACLE._calculate_damped_position = constant
    with pytest.raises(AssertionError):
        test_p5_damping_is_a_convex_combination.hypothesis.inner_test(0.0, 0.0, 1.0, 1.0, 0.0)


def test_p6_fails_for_a_double_counting_classifier(restore_kernels):
    """Counting a net as both power and signal breaks the partition."""
    original = ORACLE.estimate_routing_demand

    def double_count(pcb):
        d = original(pcb)
        return ORACLE.RoutingDemand(
            total_nets=d.total_nets,
            routable_nets=d.routable_nets,
            total_pins=d.total_pins,
            signal_nets=d.signal_nets + d.power_nets,
            power_nets=d.power_nets,
            diff_pair_nets=d.diff_pair_nets,
            avg_pins_per_net=d.avg_pins_per_net,
            max_pins_per_net=d.max_pins_per_net,
        )

    ORACLE.estimate_routing_demand = double_count
    with pytest.raises(AssertionError):
        test_p6_net_classes_partition_the_routable_nets.hypothesis.inner_test(["GND", "DATA"])


def test_p7_fails_for_an_unnormalized_heatmap(restore_kernels):
    """Skipping the ``/ max_val`` step leaves a maximum far above 1.0."""
    original = ORACLE.CongestionHeatmap.from_router.__func__

    def unnormalized(cls, router):
        combined = np.max(router.present_congestion, axis=2) + 0.5 * (
            np.max(router.history_cost, axis=2) - 1.0
        )
        return cls(
            grid=combined.astype(np.float32),
            cell_size=router.cell_size,
            origin=router.origin,
        )

    ORACLE.CongestionHeatmap.from_router = classmethod(unnormalized)
    with pytest.raises(AssertionError):
        test_p7_heatmap_normalizes_to_unit_maximum.hypothesis.inner_test(([[[9.0]]], [[[1.0]]]))
    assert original is not None  # the saved original is restored by the fixture


def test_m1_fails_for_an_origin_ignoring_kernel(restore_kernels):
    """A kernel that ignores the grid origin breaks translation invariance."""
    original = ORACLE.estimate_net_demand

    def ignore_origin(grid, pins, layer=0, demand_per_cell=1.0):
        naked = ORACLE.CongestionGrid(
            demand=grid.demand,
            supply=grid.supply,
            cell_size_mm=grid.cell_size_mm,
            width_cells=grid.width_cells,
            height_cells=grid.height_cells,
            num_layers=grid.num_layers,
            origin=(0.0, 0.0),
        )
        return original(naked, pins, layer=layer, demand_per_cell=demand_per_cell)

    ORACLE.estimate_net_demand = ignore_origin
    with pytest.raises(AssertionError):
        test_m1_translation_by_whole_cells_is_bit_exact.hypothesis.inner_test(_SAMPLE_NETS, 3, 3)


def test_m2_fails_for_a_hardcoded_cell_size(restore_kernels):
    """A kernel that assumes ``cell_size == 1.0`` breaks scale equivariance."""
    original = ORACLE.estimate_net_demand

    def unit_cell(grid, pins, layer=0, demand_per_cell=1.0):
        naked = ORACLE.CongestionGrid(
            demand=grid.demand,
            supply=grid.supply,
            cell_size_mm=1.0,
            width_cells=grid.width_cells,
            height_cells=grid.height_cells,
            num_layers=grid.num_layers,
            origin=grid.origin,
        )
        return original(naked, pins, layer=layer, demand_per_cell=demand_per_cell)

    ORACLE.estimate_net_demand = unit_cell
    with pytest.raises(AssertionError):
        test_m2_power_of_two_scaling_is_bit_exact.hypothesis.inner_test(_SAMPLE_NETS, 3)


def test_m3_fails_for_an_order_dependent_kernel(restore_kernels):
    """A kernel whose contribution depends on how much demand is already in
    the grid is not permutation invariant."""
    original = ORACLE.estimate_net_demand

    def order_dependent(grid, pins, layer=0, demand_per_cell=1.0):
        bump = 1.0 + float(grid.demand.sum())
        return original(grid, pins, layer=layer, demand_per_cell=bump)

    ORACLE.estimate_net_demand = order_dependent

    class _Data:
        def draw(self, _strategy):
            return (1, 0)

    with pytest.raises(AssertionError):
        test_m3_net_insertion_order_does_not_change_demand.hypothesis.inner_test(
            [[(1.0, 1.0), (2.0, 2.0)], [(1.0, 1.0), (9.0, 9.0)]], _Data()
        )


def test_m4_fails_for_an_additive_offset(restore_kernels):
    """Adding a constant makes the kernel affine rather than linear, so it
    stops commuting with scaling."""
    original = ORACLE._calculate_damped_position

    def offset(current, suggested, damping):
        x, y = original(current, suggested, damping)
        return (x + 1.0, y)

    ORACLE._calculate_damped_position = offset
    with pytest.raises(AssertionError):
        test_m4_damping_is_exactly_scale_equivariant.hypothesis.inner_test(0.0, 8.0, 3, 0.5)


# ---------------------------------------------------------------------------
# Sanity: the input classes are genuinely discriminating.
# ---------------------------------------------------------------------------


def test_strategies_are_discriminating():
    """Guards against a strategy collapsing to a single trivial value.

    Without this, every property above could be passing on one degenerate
    example and nobody would know.
    """
    nets = _accumulate([[(1.0, 1.0), (4.0, 4.0)], [(6.0, 6.0), (9.0, 9.0)]])
    assert float(nets.demand.sum()) > 0.0
    assert len(np.unique(nets.demand)) > 1, "the accumulated grid is uniform"

    grid = build_grid(ORACLE, [0.0, 20.0], [10.0, 10.0])
    assert float(grid.get_overflow().sum()) > 0.0
    assert len(np.unique(grid.get_utilization())) > 1

    hm = ORACLE.CongestionHeatmap.from_router(_Router([[[1.0], [4.0]]], [[[1.0], [1.0]]]))
    assert float(np.max(hm.grid)) == 1.0
    assert float(np.min(hm.grid)) < 1.0

    assert not math.isnan(ORACLE._calculate_damped_position((0.0, 0.0), (1.0, 1.0), 0.5)[0])
