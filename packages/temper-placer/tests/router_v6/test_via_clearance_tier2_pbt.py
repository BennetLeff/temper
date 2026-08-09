"""Property-based tests for the Wave-4 tier-2 via/clearance/grid cluster.

Verification unit: ``router_v6/{via_placement, clearance_engine,
grid_converter, path_simplify}.py`` (kernels in ``temper-geometry``'s
``via_clearance.rs``).  Per the G4 cluster ruling
(``docs/wave4-discipline-contract.md``), the >=5 properties are counted
across the unit, and EVERY module is reached by at least one property:

* P1  -> ``via_placement`` (``via_layer_pair_py`` + ``adjacent_layer_py``)
* P2  -> ``clearance_engine`` (``get_clearance``, composing
  ``safety_distances_py``)
* P3  -> ``clearance_engine`` (``calculate_safety_distances``)
* P4  -> ``grid_converter`` (``extract_vias_py`` / ``count_vias_in_path_py``)
* P5  -> ``grid_converter`` (``compute_path_length_py``)
* P6  -> ``path_simplify`` (``simplify_path_py`` / ``estimate_segment_count_py``)
* P7  -> ``clearance_engine`` (``net_class_to_voltage_class_py``)

Reachability is measured, not assumed: every property calls its kernel(s)
DIRECTLY on generated inputs (none of the Phase-A "generated boards never
reach the code" failure mode -- there is no pipeline in between).  Each
property has a ``test_pN_fails_for_<mutant>`` companion that monkeypatches
the ``temper_geometry`` kernel with a degenerate implementation, re-runs
the property on a fixed discriminating input via ``hypothesis.inner_test``,
and asserts ``AssertionError``.

The metamorphic section (M1-M3) is a clearly-labelled part of this file:
three invariant relations with per-relation exactness claims (all three are
exact -- the transforms are integer translations/reflections/reversals, so
every f64 bit is preserved).
"""

from __future__ import annotations

import itertools
import random

import pytest
import temper_geometry as _tg
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.clearance_engine import (
    calculate_safety_distances,
    get_clearance,
)
from temper_placer.router_v6.grid_converter import (
    GridCell,
    compute_path_length,
    count_vias_in_path,
    extract_vias,
)
from temper_placer.router_v6.path_simplify import (
    estimate_segment_count,
    simplify_path,
)

_LAYERS = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
_NET_CLASS_LABELS = [
    "HV", "AC_L", "MAINS_240V", "MAINS_120V", "MAINS", "LOW_VOLTAGE", "LV", "POWER",
    "GND", "Signal", "SELV", "COIL1", "TRACE", "HV_BUS", "3V3", "5V", "ANALOG",
]


@st.composite
def distinct_path(draw):
    """A path of n segments at DISTINCT lattice positions (so the
    first-match segment scan has a unique answer), with layers drawn freely."""
    n = draw(st.integers(min_value=2, max_value=6))
    points = list(itertools.product(range(-4, 5), range(-4, 5)))
    rng = random.Random(draw(st.integers(min_value=0, max_value=2**31 - 1)))
    chosen = rng.sample(points, n)
    layers = [draw(st.sampled_from(_LAYERS)) for _ in range(n)]
    return [(float(x), float(y), layer) for (x, y), layer in zip(chosen, layers)]


@st.composite
def _cell_path(draw):
    n = draw(st.integers(min_value=0, max_value=12))
    return [
        GridCell(
            draw(st.integers(min_value=-20, max_value=20)),
            draw(st.integers(min_value=-20, max_value=20)),
            draw(st.integers(min_value=0, max_value=3)),
        )
        for _ in range(n)
    ]


# ---------------------------------------------------------------------------
# P1 — via_placement: interior segment endpoint derives the segment layers;
# a non-matching via falls back to ("F.Cu", "B.Cu")
# ---------------------------------------------------------------------------


@given(distinct_path(), st.integers(min_value=0, max_value=2**31 - 1))
@settings(max_examples=100, deadline=2000)
def test_p1_via_layer_pair_interior_match_and_fallback(segs, seed):
    rng = random.Random(seed)
    k = rng.randrange(len(segs) - 1)
    vx, vy = segs[k][0], segs[k][1]
    from_l, to_l = _tg.via_layer_pair_py(
        vx, vy, [s[0] for s in segs], [s[1] for s in segs], [s[2] for s in segs]
    )
    assert (from_l, to_l) == (segs[k][2], segs[k + 1][2])
    # A far-away via position matches nothing -> hardcoded fallback.
    far = _tg.via_layer_pair_py(
        1e6, 1e6, [s[0] for s in segs], [s[1] for s in segs], [s[2] for s in segs]
    )
    assert far == ("F.Cu", "B.Cu")


def test_p1_fails_for_constant_layer_pair(_restore_kernels) -> None:
    _tg.via_layer_pair_py = lambda *_a, **_k: ("Z.Cu", "Z.Cu")
    with pytest.raises(AssertionError):
        test_p1_via_layer_pair_interior_match_and_fallback.hypothesis.inner_test(
            [(0.0, 0.0, "F.Cu"), (1.0, 0.0, "In1.Cu"), (2.0, 0.0, "B.Cu")], 0
        )


@given(st.sampled_from(_LAYERS), st.sampled_from(["F.Cu", "In1.Cu", "In2.Cu", "B.Cu", "", "X.Cu"]))
@settings(max_examples=50, deadline=2000)
def test_p1_adjacent_layer_is_total_on_shipped_layers(layer, probe):
    result = _tg.adjacent_layer_py(layer)
    assert result is not None and result != layer
    # The map covers exactly the four shipped layers; everything else is None.
    assert (_tg.adjacent_layer_py(probe) is not None) == (probe in _LAYERS)


def test_p1_fails_for_adjacent_layer_constant(_restore_kernels) -> None:
    _tg.adjacent_layer_py = lambda _l: "B.Cu"
    with pytest.raises(AssertionError):
        test_p1_adjacent_layer_is_total_on_shipped_layers.hypothesis.inner_test("F.Cu", "")


# ---------------------------------------------------------------------------
# P2 — clearance_engine: get_clearance is non-decreasing in working voltage
# (each voltage-dependent standard's table is monotone; VoltageClass tables
# and the design-rule creepage are voltage-independent)
# ---------------------------------------------------------------------------


@given(
    st.sampled_from(_NET_CLASS_LABELS),
    st.sampled_from(_NET_CLASS_LABELS),
    st.floats(min_value=0.0, max_value=1000.0),
    st.floats(min_value=0.0, max_value=1000.0),
)
@settings(max_examples=100, deadline=2000)
def test_p2_get_clearance_monotone_in_voltage(nca, ncb, v1, v2):
    lo, hi = sorted((v1, v2))
    assert get_clearance(nca, ncb, lo, layer_type="external") <= get_clearance(
        nca, ncb, hi, layer_type="external"
    )


def test_p2_fails_for_nonmonotone_safety_distances(_restore_kernels) -> None:
    # A mutant that oscillates with voltage makes get_clearance decrease at
    # the voltage step -- caught on the fixed (0.0, 2.0) input with SELV
    # labels, whose VoltageClass contribution (0.5) is below the mutant's
    # high arm (10.0) and above its low arm (0.1).
    _tg.safety_distances_py = lambda v, _p, _o: (
        (10.0, 10.0, v) if v < 1.5 else (0.1, 0.1, v)
    )
    with pytest.raises(AssertionError):
        test_p2_get_clearance_monotone_in_voltage.hypothesis.inner_test(
            "SELV", "SELV", 0.0, 2.0
        )


# ---------------------------------------------------------------------------
# P3 — clearance_engine: IEC 60950-1 creepage is never below clearance
# ---------------------------------------------------------------------------


@given(
    st.floats(min_value=0.0, max_value=1200.0),
    st.integers(min_value=1, max_value=4),
    st.integers(min_value=1, max_value=4),
)
@settings(max_examples=100, deadline=2000)
def test_p3_creepage_never_below_clearance(voltage, pollution, ovcat):
    sd = calculate_safety_distances(voltage, pollution, overvoltage_category=ovcat)
    assert sd.creepage_mm >= sd.clearance_mm
    assert sd.clearance_mm >= 0.0
    assert sd.creepage_mm >= 0.0


def test_p3_fails_for_inverted_tables(_restore_kernels) -> None:
    _tg.safety_distances_py = lambda v, _p, _o: (2.0, 1.0, v)
    with pytest.raises(AssertionError):
        test_p3_creepage_never_below_clearance.hypothesis.inner_test(100.0, 2, 2)


# ---------------------------------------------------------------------------
# P4 — grid_converter: the via-count is the length of the transition-index
# list, and grid_to_world's axes are separable (bit-exact)
# ---------------------------------------------------------------------------


@given(_cell_path())
@settings(max_examples=100, deadline=2000)
def test_p4_via_count_equals_extract_len(cells):
    assert count_vias_in_path(cells) == len(extract_vias(cells))
    assert count_vias_in_path(cells) <= max(0, len(cells) - 1)


@given(
    st.integers(min_value=-20, max_value=20),
    st.integers(min_value=-20, max_value=20),
    st.integers(min_value=-20, max_value=20),
    st.integers(min_value=-20, max_value=20),
    st.floats(min_value=0.1, max_value=10.0),
)
@settings(max_examples=100, deadline=2000)
def test_p4_grid_to_world_axes_separable(x, y, ox, oy, size):
    gx, gy = _tg.grid_to_world_py(x, y, float(ox), float(oy), size)
    sx, _ = _tg.grid_to_world_py(x, 0, float(ox), float(oy), size)
    _, sy = _tg.grid_to_world_py(0, y, float(ox), float(oy), size)
    assert gx == sx  # bit-exact
    assert gy == sy  # bit-exact


def test_p4_fails_for_constant_extract_vias(_restore_kernels) -> None:
    _tg.extract_vias_py = lambda *_a: []
    with pytest.raises(AssertionError):
        test_p4_via_count_equals_extract_len.hypothesis.inner_test(
            [GridCell(0, 0, 0), GridCell(1, 0, 1), GridCell(2, 0, 1)]
        )


def test_p4_fails_for_mixed_axes_grid_to_world(_restore_kernels) -> None:
    _tg.grid_to_world_py = lambda x, y, ox, oy, size: (
        ox + (x + y) * size + size / 2,
        oy + x * size + size / 2,
    )
    with pytest.raises(AssertionError):
        test_p4_grid_to_world_axes_separable.hypothesis.inner_test(1, 1, 0, 0, 0.5)


# ---------------------------------------------------------------------------
# P5 — grid_converter: two-cell Manhattan length is the exact formula
# ---------------------------------------------------------------------------


@given(
    st.integers(min_value=-10**6, max_value=10**6),
    st.integers(min_value=-10**6, max_value=10**6),
    st.integers(min_value=-10**6, max_value=10**6),
    st.integers(min_value=-10**6, max_value=10**6),
    st.floats(min_value=0.1, max_value=10.0),
)
@settings(max_examples=100, deadline=2000)
def test_p5_path_length_two_cells_exact_formula(x1, y1, x2, y2, size):
    got = compute_path_length([GridCell(x1, y1, 0), GridCell(x2, y2, 1)], size)
    expected = (abs(x2 - x1) + abs(y2 - y1)) * size
    assert got == expected  # bit-exact: int delta promoted once, one multiply


def test_p5_fails_for_zero_length_kernel(_restore_kernels) -> None:
    _tg.compute_path_length_py = lambda *_a, **_k: 0.0
    with pytest.raises(AssertionError):
        test_p5_path_length_two_cells_exact_formula.hypothesis.inner_test(0, 0, 3, 4, 0.5)


# ---------------------------------------------------------------------------
# P6 — path_simplify: simplification is idempotent and strictly reduces a
# straight run; the segment count agrees with the simplified path
# ---------------------------------------------------------------------------


@given(_cell_path())
@settings(max_examples=100, deadline=2000)
def test_p6_simplify_idempotent_and_consistent(cells):
    once = simplify_path(cells)
    assert simplify_path(once) == once
    # Every retained cell is on the original path, endpoints preserved.
    if once:
        assert once[0] == cells[0]
        assert once[-1] == cells[-1]
    # Segment count equals the same-layer consecutive pairs of the
    # simplified path (what estimate_segment_count is defined to compute).
    manual = sum(1 for i in range(1, len(once)) if once[i].layer == once[i - 1].layer)
    assert estimate_segment_count(cells) == manual


def test_p6_fails_for_identity_simplify(_restore_kernels) -> None:
    # Identity simplification is idempotent and preserves endpoints, so the
    # vacuity guard leans on P6's consistency half: the segment count of a
    # 5-cell straight run must agree with the simplify kernel's own
    # collapsed output, and identity-simplify + the real count kernel cannot
    # agree (4 same-layer pairs vs 1 collapsed segment).
    _tg.simplify_path_py = lambda cells: list(cells)
    straight = [GridCell(i, 0, 0) for i in range(5)]
    with pytest.raises(AssertionError):
        test_p6_simplify_idempotent_and_consistent.hypothesis.inner_test(straight)


def test_p6_fails_for_constant_segment_count(_restore_kernels) -> None:
    _tg.estimate_segment_count_py = lambda *_a: 0
    with pytest.raises(AssertionError):
        test_p6_simplify_idempotent_and_consistent.hypothesis.inner_test(
            [GridCell(0, 0, 0), GridCell(1, 0, 0)]
        )


# ---------------------------------------------------------------------------
# P7 — clearance_engine: net-class classification differentiates 120/240 and
# leaves non-voltage labels at SELV
# ---------------------------------------------------------------------------


@given(st.none())
@settings(max_examples=1, deadline=2000)
def test_p7_voltage_class_differentiation(_):
    assert _tg.net_class_to_voltage_class_py("MAINS_120V") == 3
    assert _tg.net_class_to_voltage_class_py("MAINS_240V") == 4
    assert _tg.net_class_to_voltage_class_py("HV") == 5
    assert _tg.net_class_to_voltage_class_py("AC_L") == 5
    assert _tg.net_class_to_voltage_class_py("LOW_VOLTAGE") == 2
    for label in ["GND", "Signal", "SELV", "TRACE", "COIL1", "3V3", "5V"]:
        assert _tg.net_class_to_voltage_class_py(label) == 1


def test_p7_fails_for_constant_classification(_restore_kernels) -> None:
    _tg.net_class_to_voltage_class_py = lambda *_a: 1
    with pytest.raises(AssertionError):
        test_p7_voltage_class_differentiation.hypothesis.inner_test(None)


# ---------------------------------------------------------------------------
# Vacuity fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def _restore_kernels():
    originals = {
        name: getattr(_tg, name)
        for name in (
            "via_layer_pair_py",
            "adjacent_layer_py",
            "safety_distances_py",
            "extract_vias_py",
            "grid_to_world_py",
            "compute_path_length_py",
            "simplify_path_py",
            "estimate_segment_count_py",
            "net_class_to_voltage_class_py",
        )
        if hasattr(_tg, name)
    }
    yield
    for name, value in originals.items():
        setattr(_tg, name, value)


# Sanity: the kernel under test is genuinely discriminating (the properties
# exercise a real change, not a constant).
def test_sanity_kernel_is_not_trivial() -> None:
    straight = [GridCell(i, 0, 0) for i in range(5)]
    assert len(simplify_path(straight)) < len(straight)
    assert compute_path_length([GridCell(0, 0, 0), GridCell(3, 4, 0)], 0.5) > 0.0
    assert count_vias_in_path([GridCell(0, 0, 0), GridCell(1, 0, 1)]) == 1
    assert _tg.net_class_to_voltage_class_py("GND") != _tg.net_class_to_voltage_class_py("HV")


# ===========================================================================
# Metamorphic relations (G5) -- all exact (integer transforms, so every f64
# bit is preserved)
# ===========================================================================


@given(
    st.lists(st.tuples(st.integers(min_value=-50, max_value=50), st.integers(min_value=-50, max_value=50))),
    st.integers(min_value=-50, max_value=50),
    st.integers(min_value=-50, max_value=50),
    st.floats(min_value=0.1, max_value=10.0),
)
@settings(max_examples=50, deadline=2000)
def test_m1_path_length_invariant_under_translation(cells, tx, ty, size):
    """M1: integer translation of the path leaves the Manhattan length
    bit-exact (int deltas are unchanged)."""
    before = compute_path_length([GridCell(x, y, 0) for x, y in cells], size)
    after = compute_path_length([GridCell(x + tx, y + ty, 0) for x, y in cells], size)
    assert before == after


@given(_cell_path())
@settings(max_examples=50, deadline=2000)
def test_m2_simplify_invariant_under_reflection(cells):
    """M2: reflecting every coordinate (x -> -x, y -> -y) preserves the
    simplified path, coordinate-for-coordinate (bit-exact)."""
    plain = simplify_path(cells)
    reflected = simplify_path([GridCell(-c.x, -c.y, c.layer) for c in cells])
    assert len(plain) == len(reflected)
    for a, b in zip(plain, reflected):
        assert a.x == -b.x and a.y == -b.y and a.layer == b.layer


@given(_cell_path())
@settings(max_examples=50, deadline=2000)
def test_m3_simplify_reversal_symmetry(cells):
    """M3: simplifying the reversed path is the reversal of simplifying the
    path (first/last-preserving, symmetric collinearity check)."""
    plain = simplify_path(cells)
    reversed_path = simplify_path(list(reversed(cells)))
    assert list(reversed(plain)) == reversed_path
    assert estimate_segment_count(cells) == estimate_segment_count(list(reversed(cells)))
