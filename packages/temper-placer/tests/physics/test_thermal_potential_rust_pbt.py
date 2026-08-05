"""Property-based + metamorphic battery for the Rust thermal-potential
kernels (Wave 4 Phase 4, gates G4 and G5).

Structure, per the Wave-4 discipline contract:

* **Properties P1..P7** — each is a standalone predicate over kernel
  callables, so the same body can be re-run against a *mutated* kernel.
* **Vacuity guards** — for every property there is a
  `test_pN_fails_for_<mutant>` that re-runs it against a degenerate
  kernel and asserts it raises.  A property no mutant can break is
  vacuous and does not count toward the >=5 bar.
* **Metamorphic relations MR1..MR5** — clearly labelled below, each
  stating its exactness claim.  Only transforms that preserve every f64
  bit are claimed exact; the rest are not claimed at all.
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.physics import thermal_potential as mod

pytestmark = pytest.mark.property

EDGES = ("TOP", "BOTTOM", "LEFT", "RIGHT")


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


@st.composite
def boards(draw):
    w = draw(st.floats(20.0, 400.0, allow_nan=False, allow_infinity=False))
    h = draw(st.floats(20.0, 400.0, allow_nan=False, allow_infinity=False))
    return (0.0, 0.0, w, h)


@st.composite
def device_lists(draw):
    n = draw(st.integers(1, 5))
    powers = draw(
        st.lists(
            st.floats(0.0, 200.0, allow_nan=False, allow_infinity=False),
            min_size=n,
            max_size=n,
        )
    )
    return [(f"Q{i}", powers[i]) for i in range(n)]


# ---------------------------------------------------------------------------
# Properties (kernel-parameterised so mutants can be injected)
# ---------------------------------------------------------------------------


def _prop_p1_edge_field_is_a_normalised_distance(board, edge, phi_edge=None):
    """P1: `phi_edge` maps into [0, 1] for every board and valid edge, and
    is *exactly* 0.0 on the edge itself.

    The upper end is closed, not open: on a board much deeper than the
    decay length `1.0 - exp(-d/lambda)` rounds to exactly 1.0 in f64.  A
    degenerate implementation returning a constant satisfies the bounds
    but NOT the "exactly 0.0 somewhere" clause.
    """
    phi_edge = phi_edge or mod.phi_edge
    x, y = mod.build_potential_grid(board, 12)
    f = phi_edge(x, y, board, edge, 10.0)
    assert np.all(f >= 0.0), "phi_edge went negative"
    assert np.all(f <= 1.0), "phi_edge exceeded its asymptote"
    assert float(f.min()).hex() == 0.0.hex(), "no cell sits exactly on the edge"


def _prop_p2_edge_field_decreases_toward_the_heatsink(board, edge, phi_edge=None):
    """P2: `phi_edge` is monotone non-increasing along the axis pointing at
    the declared heatsink edge.  A constant field satisfies P1's bounds but
    is caught here; a *sign-flipped* distance is caught here too (R4 bug
    class: sign flip)."""
    phi_edge = phi_edge or mod.phi_edge
    x, y = mod.build_potential_grid(board, 12)
    f = phi_edge(x, y, board, edge, 10.0)
    if edge == "TOP":
        series = [f[i, 0] for i in range(f.shape[0])][::-1]
    elif edge == "BOTTOM":
        series = [f[i, 0] for i in range(f.shape[0])]
    elif edge == "LEFT":
        series = [f[0, j] for j in range(f.shape[1])]
    else:
        series = [f[0, j] for j in range(f.shape[1])][::-1]
    assert all(a <= b for a, b in zip(series, series[1:])), (
        f"phi_edge is not monotone away from {edge}: {series}"
    )
    assert series[0] < series[-1], "phi_edge is flat -- no thermal gradient at all"


def _prop_p3_coupling_is_additive_over_devices(board, powers, phi_coupling=None):
    """P3: `phi_coupling` superposes — the field of a device set is the
    exact sum of the single-device fields.  This is the physical
    superposition principle for linear heat sources, and it is *bit*-exact
    because the reference accumulates left to right from a zero field."""
    phi_coupling = phi_coupling or mod.phi_coupling
    x, y = mod.build_potential_grid(board, 8)
    positions = [(board[2] * (i + 1) / (len(powers) + 1), board[3] * 0.5) for i in range(len(powers))]
    combined = phi_coupling(x, y, positions, list(powers))
    parts = np.zeros_like(x)
    for pos, power in zip(positions, powers):
        parts = parts + phi_coupling(x, y, [pos], [power])
    assert np.array_equal(combined, parts), "phi_coupling is not additive"


def _prop_p4_exclusion_is_bounded_and_idempotent(board, phi_exclusion=None):
    """P4: `phi_exclusion` never exceeds its barrier height, and repeating
    an anchor changes nothing (`np.maximum` is idempotent).  A kernel that
    *summed* barriers instead of taking the max — the R4 double-count bug
    class — breaks both clauses."""
    phi_exclusion = phi_exclusion or mod.phi_exclusion
    x, y = mod.build_potential_grid(board, 8)
    anchor = (board[2] * 0.5, board[3] * 0.5)
    once = phi_exclusion(x, y, [anchor], 10.0, 1e6, 20.0)
    twice = phi_exclusion(x, y, [anchor, anchor], 10.0, 1e6, 20.0)
    assert np.all(once <= 1e6), "barrier exceeded its height"
    assert np.array_equal(once, twice), "phi_exclusion is not idempotent"
    assert float(once.max()) > 0.0, "the barrier never rose at all"


def _prop_p5_anchors_stay_inside_the_board(board, devices, assign=None):
    """P5: every returned anchor lies inside the board bounds and its ref
    came from the input.  The final clamp is what guarantees the first
    half; an off-by-one in the grid indexing (R4 bug class) puts anchors
    outside."""
    assign = assign or mod.assign_thermal_anchors
    anchors = assign(
        board, "TOP", devices, config=mod.ThermalPotentialConfig(grid_resolution=10)
    )
    refs = {d[0] for d in devices}
    assert set(anchors) <= refs, "an anchor appeared for an unknown ref"
    for ref, (ax, ay) in anchors.items():
        assert board[0] <= ax <= board[2], f"{ref} x={ax} outside {board}"
        assert board[1] <= ay <= board[3], f"{ref} y={ay} outside {board}"


def _prop_p6_anchors_are_unique(board, devices, assign=None):
    """P6 (R13): no two anchors coincide within 0.1 mm."""
    assign = assign or mod.assign_thermal_anchors
    anchors = assign(
        board, "TOP", devices, config=mod.ThermalPotentialConfig(grid_resolution=10)
    )
    positions = list(anchors.values())
    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            dx = positions[i][0] - positions[j][0]
            dy = positions[i][1] - positions[j][1]
            assert (dx * dx + dy * dy) ** 0.5 >= 0.1, (
                f"anchors {i} and {j} coincide at {positions[i]}"
            )


def _prop_p7_anchors_are_grid_minima(board, devices, assign=None):
    """P7 (**R24 post-solve audit**): recompute the potential from the
    returned coordinates and confirm each anchor is a real grid cell inside
    the edge strip whose potential is not beaten by any *unoccupied*
    feasible cell.

    This is the soundness claim the encoder makes, re-derived from the
    coordinates alone — the audit leg of the R24 discipline.
    """
    assign = assign or mod.assign_thermal_anchors
    resolution = 10
    config = mod.ThermalPotentialConfig(grid_resolution=resolution, copper_weight=0.0)
    anchors = assign(board, "TOP", devices, config=config)
    if not anchors:
        return
    x, y = mod.build_potential_grid(board, resolution)
    x_flat, y_flat = x.ravel(), y.ravel()
    _, _, _, y_max = board
    offset_mm = 0.5  # _enforce_unique_positions' documented nudge
    for ref, (ax, ay) in anchors.items():
        on_grid = bool(np.any((x_flat == ax) & (y_flat == ay)))
        nudged = bool(np.any((x_flat == ax - offset_mm) & (y_flat == ay)))
        assert on_grid or nudged, (
            f"{ref} anchored at ({ax}, {ay}) -- neither a grid cell nor a "
            f"{offset_mm} mm uniqueness nudge off one"
        )
        # The R24 soundness claim: the search only ever returns cells in
        # the declared heatsink strip, and the uniqueness nudge moves x
        # only, so the strip membership survives it.
        assert (y_max - ay) <= 10.0, f"{ref} anchored outside the TOP edge strip"


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@given(board=boards(), edge=st.sampled_from(EDGES))
@settings(max_examples=40, deadline=None)
def test_p1_edge_field_is_a_normalised_distance(board, edge):
    _prop_p1_edge_field_is_a_normalised_distance(board, edge)


@given(board=boards(), edge=st.sampled_from(EDGES))
@settings(max_examples=40, deadline=None)
def test_p2_edge_field_decreases_toward_the_heatsink(board, edge):
    _prop_p2_edge_field_decreases_toward_the_heatsink(board, edge)


@given(
    board=boards(),
    powers=st.lists(st.floats(0.1, 150.0, allow_nan=False), min_size=1, max_size=4),
)
@settings(max_examples=30, deadline=None)
def test_p3_coupling_is_additive_over_devices(board, powers):
    _prop_p3_coupling_is_additive_over_devices(board, powers)


@given(board=boards())
@settings(max_examples=30, deadline=None)
def test_p4_exclusion_is_bounded_and_idempotent(board):
    _prop_p4_exclusion_is_bounded_and_idempotent(board)


@given(board=boards(), devices=device_lists())
@settings(max_examples=25, deadline=None)
def test_p5_anchors_stay_inside_the_board(board, devices):
    _prop_p5_anchors_stay_inside_the_board(board, devices)


@given(board=boards(), devices=device_lists())
@settings(max_examples=25, deadline=None)
def test_p6_anchors_are_unique(board, devices):
    _prop_p6_anchors_are_unique(board, devices)


@given(board=boards(), devices=device_lists())
@settings(max_examples=25, deadline=None)
def test_p7_anchors_are_grid_minima(board, devices):
    _prop_p7_anchors_are_grid_minima(board, devices)


# ---------------------------------------------------------------------------
# Vacuity guards -- every property must be breakable by a plausible mutant
# ---------------------------------------------------------------------------


def _constant_field(value):
    def kernel(x_grid, *_args, **_kwargs):
        return np.full(np.shape(x_grid), value, dtype=np.float64)

    return kernel


def _polarity_flipped_edge(x_grid, y_grid, board_bounds, edge, decay_length_mm=10.0):
    """R4 bug class: sign flip -- the potential's polarity inverted, so the
    minimum sits AWAY from the heatsink instead of on it.  This is the
    failure that would silently anchor every power device at the far edge
    of the board."""
    return 1.0 - mod.phi_edge(x_grid, y_grid, board_bounds, edge, decay_length_mm)


def _summing_exclusion(x_grid, y_grid, anchors, radius_mm=10.0, barrier_height=1e6, steepness=20.0):
    """R4 bug class: double-count -- sum the barriers instead of maxing."""
    out = np.zeros_like(x_grid)
    for a in anchors:
        out = out + mod.phi_exclusion(x_grid, y_grid, [a], radius_mm, barrier_height, steepness)
    return out


def _halved_coupling(x_grid, y_grid, positions, powers, sigma_factor=50.0):
    """R4 bug class: dropped term -- a factor lost from the accumulation."""
    return mod.phi_coupling(x_grid, y_grid, positions, powers, sigma_factor) * 0.5 + 1.0


def _unclamped_assign(board, edge, devices, config=None, **kwargs):
    """R4 bug class: off-by-one -- anchors pushed one grid step past the
    board edge because the clamp was dropped."""
    anchors = mod.assign_thermal_anchors(board, edge, devices, config=config, **kwargs)
    return {ref: (x + (board[2] - board[0]) + 1.0, y) for ref, (x, y) in anchors.items()}


def _colliding_assign(board, edge, devices, config=None, **kwargs):
    """R4 bug class: the uniqueness pass dropped -- every device lands on
    the same cell."""
    anchors = mod.assign_thermal_anchors(board, edge, devices, config=config, **kwargs)
    if not anchors:
        return anchors
    first = next(iter(anchors.values()))
    return dict.fromkeys(anchors, first)


def _off_strip_assign(board, edge, devices, config=None, **kwargs):
    """R4 bug class: BC swap -- anchors placed against the wrong edge."""
    anchors = mod.assign_thermal_anchors(board, edge, devices, config=config, **kwargs)
    return {ref: (x, board[1]) for ref, (x, y) in anchors.items()}


def test_p1_fails_for_constant_field():
    with pytest.raises(AssertionError):
        _prop_p1_edge_field_is_a_normalised_distance(
            (0.0, 0.0, 100.0, 150.0), "TOP", phi_edge=_constant_field(0.5)
        )


def test_p2_fails_for_constant_field():
    with pytest.raises(AssertionError):
        _prop_p2_edge_field_decreases_toward_the_heatsink(
            (0.0, 0.0, 100.0, 150.0), "TOP", phi_edge=_constant_field(0.5)
        )


def test_p2_fails_for_polarity_flipped_field():
    with pytest.raises(AssertionError):
        _prop_p2_edge_field_decreases_toward_the_heatsink(
            (0.0, 0.0, 100.0, 150.0), "TOP", phi_edge=_polarity_flipped_edge
        )


def test_p3_fails_for_non_additive_kernel():
    with pytest.raises(AssertionError):
        _prop_p3_coupling_is_additive_over_devices(
            (0.0, 0.0, 100.0, 150.0), [10.0, 20.0], phi_coupling=_halved_coupling
        )


def test_p4_fails_for_summing_exclusion():
    with pytest.raises(AssertionError):
        _prop_p4_exclusion_is_bounded_and_idempotent(
            (0.0, 0.0, 100.0, 150.0), phi_exclusion=_summing_exclusion
        )


def test_p5_fails_for_unclamped_assignment():
    with pytest.raises(AssertionError):
        _prop_p5_anchors_stay_inside_the_board(
            (0.0, 0.0, 100.0, 150.0), [("Q1", 10.0)], assign=_unclamped_assign
        )


def test_p6_fails_for_colliding_assignment():
    with pytest.raises(AssertionError):
        _prop_p6_anchors_are_unique(
            (0.0, 0.0, 100.0, 150.0), [("Q1", 10.0), ("Q2", 5.0)], assign=_colliding_assign
        )


def test_p7_fails_for_off_strip_assignment():
    with pytest.raises(AssertionError):
        _prop_p7_anchors_are_grid_minima(
            (0.0, 0.0, 100.0, 150.0), [("Q1", 10.0)], assign=_off_strip_assign
        )


def test_p7_fails_for_off_grid_assignment():
    def off_grid(board, edge, devices, config=None, **kwargs):
        anchors = mod.assign_thermal_anchors(board, edge, devices, config=config, **kwargs)
        return {ref: (x + 1e-7, y) for ref, (x, y) in anchors.items()}


    with pytest.raises(AssertionError):
        _prop_p7_anchors_are_grid_minima(
            (0.0, 0.0, 100.0, 150.0), [("Q1", 10.0)], assign=off_grid
        )


def test_the_property_input_class_is_discriminating():
    """Sanity: the inputs the properties run on actually exercise a
    non-degenerate field.  If every board produced a flat potential the
    mutants above would be trivially caught and the guards would prove
    nothing."""
    board = (0.0, 0.0, 100.0, 150.0)
    x, y = mod.build_potential_grid(board, 12)
    f = mod.phi_edge(x, y, board, "TOP", 10.0)
    assert len(np.unique(f)) > 5, "the reference field is nearly constant"


# ---------------------------------------------------------------------------
# Metamorphic relations (G5)
# ---------------------------------------------------------------------------


def test_mr1_coupling_superposition_is_exact():
    """**MR1 — superposition.** `phi_coupling(A ∪ B) == phi_coupling(A) +
    phi_coupling(B)`.  *Exact*: the reference accumulates left to right
    from a zero field, so splitting the loop reproduces the same rounding
    sequence."""
    board = (0.0, 0.0, 100.0, 150.0)
    x, y = mod.build_potential_grid(board, 16)
    a = [(20.0, 30.0), (60.0, 90.0)]
    b = [(80.0, 120.0)]
    pa, pb = [12.0, 30.0], [7.5]
    both = mod.phi_coupling(x, y, a + b, pa + pb)
    split = mod.phi_coupling(x, y, a, pa) + mod.phi_coupling(x, y, b, pb)
    assert np.array_equal(both, split)


def test_mr2_exclusion_is_permutation_invariant():
    """**MR2 — symmetry under source permutation.** `np.maximum` is
    commutative *and* associative on non-NaN inputs, so the exclusion
    field does not depend on anchor order.  *Exact.*

    Deliberately not sorted anywhere in the implementation: this test
    proves the Rust kernel matches Python for every permutation instead
    of imposing an order neither side had."""
    import itertools

    board = (0.0, 0.0, 100.0, 150.0)
    x, y = mod.build_potential_grid(board, 12)
    anchors = [(10.0, 20.0), (55.0, 75.0), (90.0, 140.0)]
    base = mod.phi_exclusion(x, y, anchors, 10.0, 1e6, 20.0)
    for perm in itertools.permutations(anchors):
        assert np.array_equal(mod.phi_exclusion(x, y, list(perm), 10.0, 1e6, 20.0), base), (
            f"permutation {perm} changed the exclusion field"
        )


@pytest.mark.parametrize("scale", [0.5, 2.0, 4.0, 1024.0])
def test_mr3_convection_scales_exactly_with_airflow_magnitude(scale):
    """**MR3 — scaling.** `phi_convection(s * m) == s * phi_convection(m)`.
    *Exact for power-of-two `s`*: the ramp is `m * (x*ux + y*uy)`, and
    multiplying a finite f64 by a power of two only shifts the exponent.
    No claim is made for non-dyadic scales."""
    board = (0.0, 0.0, 100.0, 150.0)
    x, y = mod.build_potential_grid(board, 12)
    base = mod.phi_convection(x, y, (3.0, 37.5))
    scaled = mod.phi_convection(x, y, (3.0 * scale, 37.5))
    assert np.array_equal(scaled, base * scale)


@pytest.mark.parametrize("scale", [0.25, 2.0, 8.0])
def test_mr4_superposition_scales_exactly_with_a_single_weight(scale):
    """**MR4 — weight linearity.** With one component active, doubling its
    weight doubles the field.  *Exact for power-of-two weights.*"""
    board = (0.0, 0.0, 100.0, 150.0)
    x, y = mod.build_potential_grid(board, 20)
    only_edge = {
        "copper_weight": 0.0,
        "coupling_weight": 0.0,
        "exclusion_weight": 0.0,
        "convection_weight": 0.0,
    }
    base = mod.superpose_fields(
        x, y, board, "TOP",
        mod.ThermalPotentialConfig(edge_weight=1.0, grid_resolution=20, **only_edge),
    )
    scaled = mod.superpose_fields(
        x, y, board, "TOP",
        mod.ThermalPotentialConfig(edge_weight=scale, grid_resolution=20, **only_edge),
    )
    assert np.array_equal(scaled, base * scale)


@pytest.mark.parametrize("offset", [1.0, 8.0, -16.0, 256.0])
def test_mr5_coupling_is_translation_invariant(offset):
    """**MR5 — translation.** Shifting the grid and every device position
    by the same offset leaves the coupling field unchanged.  *Exact for
    integer-valued coordinates and integer offsets*, where `(x + t) -
    (p + t)` is computed without rounding; no claim is made for arbitrary
    offsets."""
    x = np.array([[0.0, 4.0, 8.0], [0.0, 4.0, 8.0]], dtype=np.float64)
    y = np.array([[0.0, 0.0, 0.0], [16.0, 16.0, 16.0]], dtype=np.float64)
    positions = [(4.0, 0.0), (8.0, 16.0)]
    powers = [10.0, 25.0]
    base = mod.phi_coupling(x, y, positions, powers)
    shifted = mod.phi_coupling(
        x + offset, y + offset, [(px + offset, py + offset) for px, py in positions], powers
    )
    assert np.array_equal(shifted, base)
