"""Differential tests: temper-quality-oracle placement-metric kernels vs the
verbatim pre-migration Python (Wave 4 Phase 4 — ``metrics/quality.py``).

The pre-migration implementation is pinned in ``_quality_py_oracle.py`` (a
character-identical copy of the module at ``origin/main`` ``ebf9326ff``).
Every assertion here is **bit-exact**: floats are compared through
``float.hex()``, never a tolerance, and every non-float leaf carries its
concrete ``type`` in the comparison key so an int that silently became a
float cannot hide behind numeric equality (``0 == 0.0`` is True in Python;
``("violations_3mm", "int", 0) == ("violations_3mm", "float", 0.0)`` is not).

Bit-exactness notes (catalog: ``docs/wave4-discipline-contract.md`` §2):

- **B1/B7 — ``**`` is libm ``pow``.** The clearance kernels compute
  ``(dx**2 + dy**2) ** 0.5``.  Measured on this platform over 200k random
  inputs: ``x ** 0.5`` differs from ``math.sqrt(x)`` on 263 of them and
  ``x ** 2`` differs from ``x * x`` on 256.  Substituting ``sqrt``/``x*x`` in
  Rust would therefore fail here on roughly one input in 800 —
  ``test_pow_is_not_interchangeable_with_sqrt`` pins that the divergence is
  real on the machine running the suite, so this is not a theoretical note.
- **B5 — CPython ``min``/``max`` keep the first argument.** Every clamp in
  the oracle puts the *constant* first (``max(0.0, ...)``, ``min(1.0, ...)``)
  except the accumulator folds (``min(min_found, clearance)``,
  ``max(actual_area, min_possible_area)``).  The Rust side mirrors the
  argument order through ``py_max2``/``py_min2``.
Ordering (the aggregation trap this module was flagged for)
------------------------------------------------------------
``thermal_score`` accumulates over a ``set``.  We do **not** assert that the
result is permutation-invariant — it is not, and asserting so would be false.
What we assert is stronger and true: for *every* permutation of the input,
Rust reproduces Python's result for *that same permutation*, bit for bit
(``test_thermal_score_tracks_python_under_every_permutation``), and that at
least one permutation genuinely changes the low bits
(``test_thermal_score_is_genuinely_order_sensitive``) — so the permutation
sweep is not vacuous.

Empty-input semantics
---------------------
Every aggregate here has a vacuous-``1.0`` default on empty input (the class
``scripts/check_vacuous_gates.py`` exists for).  Each one is enumerated and
pinned in ``TestEmptyInputSemantics`` — including the *type* of the returned
value and the ``0``-vs-``0.0`` distinction on the violation counts.
"""

from __future__ import annotations

import math
import random
from types import SimpleNamespace

import numpy as np
import pytest
import temper_quality_oracle as _tqo
from tests.metrics._quality_py_oracle import (
    _oracle_compactness_score,
    _oracle_connectivity_clustering_score,
    _oracle_dual_rail_clearance_report,
    _oracle_hv_lv_clearance_score,
    _oracle_loop_area_score,
    _oracle_thermal_score,
    _oracle_zone_compliance_score,
)

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.core.state import PlacementState
from temper_placer.metrics import quality as mod

# ---------------------------------------------------------------------------
# Bit-exact comparison helpers
# ---------------------------------------------------------------------------


def key(value):
    """A comparison key that cannot conflate types or float bit patterns.

    - floats become ``("float", <hex>)`` — ``float.hex()`` is a lossless,
      exactly-round-tripping rendering, so ``==`` on the key is ``==`` on the
      bit pattern (with ``nan``/``inf`` spelled out rather than compared).
    - bools are checked *before* ints (``bool`` is a subclass of ``int``).
    - every other leaf carries ``type(value).__name__`` so ``0`` and ``0.0``,
      or ``True`` and ``1``, never compare equal.
    """
    if isinstance(value, float):
        if math.isnan(value):
            # NaN != NaN, and hex() of a NaN loses the payload; normalise.
            return ("float", "nan", math.copysign(1.0, value))
        return ("float", value.hex())
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, dict):
        return ("dict", tuple((k, key(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(key(v) for v in value))
    return (type(value).__name__, value)


def assert_bit_identical(got, expected, what: str) -> None:
    assert key(got) == key(expected), (
        f"{what}: Rust-delegated result is not bit-identical to the pinned "
        f"Python oracle.\n  rust   = {got!r}  key={key(got)}\n"
        f"  oracle = {expected!r}  key={key(expected)}"
    )


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def make_netlist(refs, bounds=None, net_names=("N1",)):
    comps = [
        Component(
            ref=r,
            footprint="FP",
            bounds=(bounds[i] if bounds else (2.5, 1.25)),
        )
        for i, r in enumerate(refs)
    ]
    nets = [Net(name=n, pins=[]) for n in net_names]
    return Netlist(components=comps, nets=nets)


def make_state(positions, dtype=np.float32):
    return PlacementState.from_positions(np.array(positions, dtype=dtype))


def make_board(width=100.0, height=80.0, zones=None):
    return Board(width=width, height=height, zones=zones or [])


def empty_context(n_nets=0, n_pins=0):
    """A LossContext-shaped stand-in.

    The shipped pipeline always supplies an empty ``net_pin_indices``; the
    differential exercises both the empty and the populated shape.
    """
    return SimpleNamespace(
        net_pin_indices=np.zeros((n_nets, n_pins), dtype=np.int64),
        net_pin_mask=np.zeros((n_nets, n_pins), dtype=bool),
    )


def context_from_nets(net_pin_lists, n_pins=None):
    """Build a context whose row *i* holds ``net_pin_lists[i]``, mask-padded."""
    m = len(net_pin_lists)
    p = n_pins if n_pins is not None else max((len(x) for x in net_pin_lists), default=1)
    p = max(p, 1)
    idx = np.zeros((m, p), dtype=np.int64)
    mask = np.zeros((m, p), dtype=bool)
    for i, pins in enumerate(net_pin_lists):
        for j, v in enumerate(pins):
            idx[i, j] = v
            mask[i, j] = True
    return SimpleNamespace(net_pin_indices=idx, net_pin_mask=mask)


# ---------------------------------------------------------------------------
# B-class pins — these prove the catalog classes bite on THIS machine
# ---------------------------------------------------------------------------


class TestBitExactnessCatalogPins:
    def test_pow_is_not_interchangeable_with_sqrt(self):
        """B1/B7: `x ** 0.5` is libm pow and really does differ from sqrt.

        If this ever stops finding a divergence, the clearance kernels'
        insistence on `py_pow` becomes unfalsifiable and the catalog note
        should be re-measured rather than trusted.
        """
        rng = random.Random(11)
        diffs_root = sum(
            1
            for _ in range(200_000)
            if (lambda x: (x**0.5).hex() != math.sqrt(x).hex())(rng.uniform(0, 1e6))
        )
        assert diffs_root > 0, (
            "x ** 0.5 == math.sqrt(x) for every sampled input on this platform; "
            "the B1/B7 mitigation in placement_metrics.rs is untested here"
        )

    def test_square_is_not_interchangeable_with_multiplication(self):
        """B7: `x ** 2` is libm pow and really does differ from `x * x`."""
        rng = random.Random(11)
        diffs = sum(
            1
            for _ in range(200_000)
            if (lambda x: (x**2).hex() != (x * x).hex())(rng.uniform(0, 1e6))
        )
        assert diffs > 0

# ---------------------------------------------------------------------------
# thermal_score
# ---------------------------------------------------------------------------


class TestThermalScore:
    @pytest.mark.parametrize("edge", ["TOP", "BOTTOM", "LEFT", "RIGHT", "DIAGONAL", "top", ""])
    def test_every_edge_arm_matches(self, edge):
        refs = ["Q1", "Q2", "U3", "D4"]
        nl = make_netlist(refs)
        st = make_state([(3.5, 7.25), (60.0, 2.5), (99.0, 40.0), (0.5, 79.5)])
        bd = make_board()
        therm = set(refs)
        assert_bit_identical(
            mod.thermal_score(st, nl, bd, therm, target_edge=edge),
            _oracle_thermal_score(st, nl, bd, therm, target_edge=edge),
            f"thermal_score(edge={edge!r})",
        )

    @pytest.mark.parametrize("seed", range(40))
    def test_randomized_matches(self, seed):
        rng = random.Random(seed)
        n = rng.randint(1, 9)
        refs = [f"C{i}" for i in range(n)]
        nl = make_netlist(refs)
        st = make_state([(rng.uniform(0, 100), rng.uniform(0, 80)) for _ in range(n)])
        bd = make_board()
        # Include some refs that do NOT resolve, to exercise the KeyError skip.
        therm = set(rng.sample(refs, rng.randint(1, n))) | {"MISSING_A", "MISSING_B"}
        edge = rng.choice(["TOP", "BOTTOM", "LEFT", "RIGHT"])
        md = rng.choice([1.0, 10.0, 0.5, 123.456])
        assert_bit_identical(
            mod.thermal_score(st, nl, bd, therm, target_edge=edge, max_distance=md),
            _oracle_thermal_score(st, nl, bd, therm, target_edge=edge, max_distance=md),
            f"thermal_score(seed={seed})",
        )

    def test_thermal_score_tracks_python_under_every_permutation(self):
        """Order-sensitivity is preserved, not papered over.

        The oracle folds over a `set`, whose traversal order CPython does not
        promise across processes.  The migration's contract is that Rust
        reproduces Python *for the order Python actually used* — so we drive
        the kernel directly with every permutation of a fixed input and check
        each one against a naive Python fold of the same permutation.
        """
        import itertools

        # Values chosen so partial sums land in different binades and
        # reassociation is observable.
        pts = [(0.0, 1.0), (0.0, 1.0 - 2**-52), (0.0, 1e-8), (0.0, 0.3), (0.0, 79.5)]
        bounds = (0.0, 0.0, 100.0, 80.0)
        md = 3.0
        for perm in itertools.permutations(pts):
            total = 0.0
            count = 0
            for _x, y in perm:
                distance = bounds[3] - y
                total += max(0.0, 1.0 - distance / md)
                count += 1
            expected = total / count
            got = _tqo.thermal_score_py(list(perm), *bounds, "TOP", md)
            assert_bit_identical(got, expected, f"thermal_score perm={perm}")

    def test_thermal_score_is_genuinely_order_sensitive(self):
        """Anti-vacuity for the permutation sweep above.

        If every permutation gave identical bits, the sweep would prove
        nothing and sorting the set would be harmless.  These five ordinary
        board coordinates (found by search, not hand-tuned to be pathological)
        produce **two** distinct bit patterns across their 120 permutations —
        a 1-ulp reassociation difference.  That is why the delegation performs
        exactly one pass over the set and hands Rust the order it got.
        """
        import itertools

        pts = [
            (0.0, 70.29578541533122),
            (0.0, 38.69566095651911),
            (0.0, 73.09196652608817),
            (0.0, 56.57520023240947),
            (0.0, 79.90449346487354),
        ]
        bounds = (0.0, 0.0, 100.0, 80.0)
        results = {
            _tqo.thermal_score_py(list(p), *bounds, "TOP", 13.0).hex()
            for p in itertools.permutations(pts)
        }
        assert len(results) > 1, (
            "every permutation produced identical bits; the order-sensitivity "
            "sweep is vacuous and needs sharper operands"
        )

    def test_thermal_score_matches_python_for_each_discriminating_order(self):
        """...and Rust tracks Python on *each* of those diverging orders.

        Order-sensitivity alone is not the contract; reproducing Python's
        answer for whichever order Python used is.
        """
        import itertools

        pts = [
            (0.0, 70.29578541533122),
            (0.0, 38.69566095651911),
            (0.0, 73.09196652608817),
            (0.0, 56.57520023240947),
            (0.0, 79.90449346487354),
        ]
        bounds = (0.0, 0.0, 100.0, 80.0)
        for perm in itertools.permutations(pts):
            total = 0.0
            for _x, y in perm:
                total += max(0.0, 1.0 - (bounds[3] - y) / 13.0)
            assert_bit_identical(
                _tqo.thermal_score_py(list(perm), *bounds, "TOP", 13.0),
                total / len(perm),
                f"thermal_score perm={perm}",
            )

    def test_unknown_edge_uses_max_distance(self):
        nl = make_netlist(["Q1"])
        st = make_state([(10.0, 10.0)])
        bd = make_board()
        assert_bit_identical(
            mod.thermal_score(st, nl, bd, {"Q1"}, target_edge="NORTHWEST"),
            _oracle_thermal_score(st, nl, bd, {"Q1"}, target_edge="NORTHWEST"),
            "thermal_score(unknown edge)",
        )


# ---------------------------------------------------------------------------
# zone_compliance_score
# ---------------------------------------------------------------------------


class TestZoneComplianceScore:
    @pytest.mark.parametrize("seed", range(25))
    def test_randomized_matches(self, seed):
        rng = random.Random(2000 + seed)
        n = rng.randint(1, 8)
        refs = [f"R{i}" for i in range(n)]
        nl = make_netlist(refs)
        st = make_state([(rng.uniform(-5, 105), rng.uniform(-5, 85)) for _ in range(n)])
        zones = [
            Zone(name="ZA", bounds=(0.0, 0.0, 50.0, 40.0)),
            Zone(name="ZB", bounds=(50.0, 40.0, 100.0, 80.0)),
        ]
        bd = make_board(zones=zones)
        assigns = {r: rng.choice(["ZA", "ZB", "ZMISSING"]) for r in refs}
        assigns["GHOST"] = "ZA"  # unresolvable ref -> KeyError skip
        assert_bit_identical(
            mod.zone_compliance_score(st, nl, bd, assigns),
            _oracle_zone_compliance_score(st, nl, bd, assigns),
            f"zone_compliance_score(seed={seed})",
        )

    def test_boundary_inclusive(self):
        """The oracle's bounds test is `<=` on both ends — pin the edge."""
        nl = make_netlist(["R0", "R1"])
        st = make_state([(0.0, 0.0), (50.0, 40.0)])
        bd = make_board(zones=[Zone(name="ZA", bounds=(0.0, 0.0, 50.0, 40.0))])
        assigns = {"R0": "ZA", "R1": "ZA"}
        assert_bit_identical(
            mod.zone_compliance_score(st, nl, bd, assigns),
            _oracle_zone_compliance_score(st, nl, bd, assigns),
            "zone_compliance_score(boundary)",
        )


# ---------------------------------------------------------------------------
# hv_lv_clearance_score / dual_rail_clearance_report
# ---------------------------------------------------------------------------


class TestClearance:
    @pytest.mark.parametrize("seed", range(60))
    def test_hv_lv_randomized_matches(self, seed):
        rng = random.Random(3000 + seed)
        n = rng.randint(2, 8)
        refs = [f"U{i}" for i in range(n)]
        bounds = [(rng.uniform(0.4, 12.0), rng.uniform(0.4, 12.0)) for _ in range(n)]
        nl = make_netlist(refs, bounds=bounds)
        st = make_state([(rng.uniform(0, 60), rng.uniform(0, 60)) for _ in range(n)])
        split = rng.randint(1, n - 1)
        hv = set(refs[:split])
        lv = set(refs[split:])
        mc = rng.choice([3.0, 6.0, 8.0, 0.75])
        assert_bit_identical(
            mod.hv_lv_clearance_score(st, nl, hv, lv, mc),
            _oracle_hv_lv_clearance_score(st, nl, hv, lv, mc),
            f"hv_lv_clearance_score(seed={seed})",
        )

    @pytest.mark.parametrize("seed", range(60))
    def test_dual_rail_randomized_matches(self, seed):
        rng = random.Random(4000 + seed)
        n = rng.randint(2, 8)
        refs = [f"U{i}" for i in range(n)]
        bounds = [(rng.uniform(0.4, 12.0), rng.uniform(0.4, 12.0)) for _ in range(n)]
        nl = make_netlist(refs, bounds=bounds)
        st = make_state([(rng.uniform(0, 40), rng.uniform(0, 40)) for _ in range(n)])
        split = rng.randint(1, n - 1)
        hv = set(refs[:split])
        lv = set(refs[split:])
        assert_bit_identical(
            mod.dual_rail_clearance_report(st, nl, hv, lv),
            _oracle_dual_rail_clearance_report(st, nl, hv, lv),
            f"dual_rail_clearance_report(seed={seed})",
        )

    def test_dual_rail_violation_counts_stay_ints(self):
        """Type drift guard: the counts must be `int`, not `float`.

        `key()` carries the type, so a Rust binding returning `0.0` fails
        here even though `0 == 0.0`.
        """
        nl = make_netlist(["A", "B"], bounds=[(1.0, 1.0), (1.0, 1.0)])
        st = make_state([(0.0, 0.0), (1.5, 0.0)])
        got = mod.dual_rail_clearance_report(st, nl, {"A"}, {"B"})
        assert type(got["violations_3mm"]) is int
        assert type(got["violations_6mm"]) is int
        assert type(got["clearance_score_3mm"]) is float

    def test_overlapping_boxes_take_the_max_branch(self):
        """dx or dy <= 0 -> `max(dx, dy)`, never the pow-diagonal."""
        nl = make_netlist(["A", "B"], bounds=[(10.0, 10.0), (10.0, 10.0)])
        st = make_state([(0.0, 0.0), (3.0, 0.0)])
        for f, o in (
            (mod.hv_lv_clearance_score, _oracle_hv_lv_clearance_score),
            (mod.dual_rail_clearance_report, _oracle_dual_rail_clearance_report),
        ):
            args = (st, nl, {"A"}, {"B"})
            assert_bit_identical(f(*args), o(*args), f"{f.__name__}(overlap)")

    def test_diagonal_branch_exercises_pow(self):
        """dx > 0 and dy > 0 -> `(dx**2 + dy**2) ** 0.5`, the B1/B7 path.

        The bounds are chosen so the diagonal is irrational and the last ulp
        is decided by libm, not by an exact square root.
        """
        nl = make_netlist(["A", "B"], bounds=[(1.0, 1.0), (1.0, 1.0)])
        st = make_state([(0.0, 0.0), (7.3, 11.9)])
        args = (st, nl, {"A"}, {"B"}, 20.0)
        assert_bit_identical(
            mod.hv_lv_clearance_score(*args),
            _oracle_hv_lv_clearance_score(*args),
            "hv_lv_clearance_score(diagonal)",
        )

    # -- Mutation-driven edge cases -------------------------------------
    #
    # The three cases below were added because the anti-vacuity mutation
    # sweep found the randomized cases above did NOT catch:
    #   * substituting `sqrt(dx*dx + dy*dy)` for `(dx**2 + dy**2) ** 0.5`
    #   * substituting `f64::max` for CPython `max` in `max(dx, dy)`
    #   * relaxing the ramp's `>=` boundary to `>`
    # Each is now pinned by a case that discriminates.

    @pytest.mark.parametrize(
        "dx,dy",
        [
            (11.14766403059588, 1.3180351690176246),
            (29.495746552860233, 8.02795562824556),
            (1.3525805655534557, 6.1749727699439765),
        ],
    )
    def test_pow_diagonal_operands_that_sqrt_gets_wrong(self, dx, dy):
        """B1/B7 with teeth: operands where `**` and `sqrt` really differ.

        Found by search (0.13% of random inputs diverge, so the randomized
        cases above miss them most runs).  With zero-size components the
        edge gaps are exactly `dx`/`dy`, and a 100 mm rail keeps the score in
        the ramp's linear region so the final ulp reaches the assertion
        instead of being clamped away to 1.0.
        """
        nl = make_netlist(["A", "B"], bounds=[(0.0, 0.0), (0.0, 0.0)])
        st = make_state([(0.0, 0.0), (dx, dy)], dtype=np.float64)
        args = (st, nl, {"A"}, {"B"}, 100.0)
        assert_bit_identical(
            mod.hv_lv_clearance_score(*args),
            _oracle_hv_lv_clearance_score(*args),
            f"hv_lv_clearance_score(pow-sensitive dx={dx}, dy={dy})",
        )

    def test_nan_position_takes_the_python_max_branch(self):
        """B5 with teeth: `max(dx, dy)` with a NaN arm.

        CPython's `max(dx, dy)` returns `dx` when `dy > dx` is False — and it
        is False when either is NaN — so a NaN `dx` propagates.  Rust's
        `f64::max` discards NaN and would return `dy` instead, changing the
        subsequent `min` reduction and the final score.
        """
        nl = make_netlist(["A", "B"], bounds=[(1.0, 1.0), (1.0, 1.0)])
        st = make_state([(float("nan"), 0.0), (5.0, 0.0)], dtype=np.float64)
        args = (st, nl, {"A"}, {"B"}, 8.0)
        assert_bit_identical(
            mod.hv_lv_clearance_score(*args),
            _oracle_hv_lv_clearance_score(*args),
            "hv_lv_clearance_score(NaN position)",
        )
        assert_bit_identical(
            mod.dual_rail_clearance_report(st, nl, {"A"}, {"B"}),
            _oracle_dual_rail_clearance_report(st, nl, {"A"}, {"B"}),
            "dual_rail_clearance_report(NaN position)",
        )

    def test_zero_threshold_pins_the_ramp_boundary(self):
        """The ramp's `>=` is load-bearing exactly at threshold 0.

        For any positive threshold, `clearance == threshold` scores 1.0 under
        both `>=` and `>` (the ramp would return `threshold/threshold`).  The
        only input that separates them is `min_clearance == 0.0` with a
        touching pair: `>=` returns 1.0, `>` falls through to the
        `clearance <= 0` arm and returns 0.0.
        """
        nl = make_netlist(["A", "B"], bounds=[(2.0, 2.0), (2.0, 2.0)])
        # Edge-to-edge dx = |2 - 0| - 1 - 1 = 0.0 exactly; dy = -2.
        st = make_state([(0.0, 0.0), (2.0, 0.0)], dtype=np.float64)
        args = (st, nl, {"A"}, {"B"}, 0.0)
        got = mod.hv_lv_clearance_score(*args)
        assert_bit_identical(
            got,
            _oracle_hv_lv_clearance_score(*args),
            "hv_lv_clearance_score(zero threshold, touching)",
        )
        assert key(got) == ("float", (1.0).hex())

    def test_unresolvable_refs_on_one_side_give_one(self):
        nl = make_netlist(["A"])
        st = make_state([(0.0, 0.0)])
        args = (st, nl, {"GHOST"}, {"A"})
        assert_bit_identical(
            mod.hv_lv_clearance_score(*args),
            _oracle_hv_lv_clearance_score(*args),
            "hv_lv_clearance_score(unresolvable hv)",
        )
        assert_bit_identical(
            mod.dual_rail_clearance_report(*args),
            _oracle_dual_rail_clearance_report(*args),
            "dual_rail_clearance_report(unresolvable hv)",
        )


# ---------------------------------------------------------------------------
# loop_area_score
# ---------------------------------------------------------------------------


class TestLoopAreaScore:
    @pytest.mark.parametrize("seed", range(40))
    def test_randomized_matches(self, seed):
        rng = random.Random(5000 + seed)
        n = rng.randint(3, 20)
        refs = [f"L{i}" for i in range(n)]
        nl = make_netlist(refs)
        st = make_state([(rng.uniform(0, 50), rng.uniform(0, 50)) for _ in range(n)])
        loops = []
        for _ in range(rng.randint(1, 4)):
            size = rng.randint(1, n)
            loops.append(rng.sample(refs, size))
        loops.append(["GHOST1", "GHOST2", "GHOST3"])  # all-unresolvable -> skipped
        ctx = empty_context()
        assert_bit_identical(
            mod.loop_area_score(st, nl, ctx, loops),
            _oracle_loop_area_score(st, nl, ctx, loops),
            f"loop_area_score(seed={seed})",
        )

    @pytest.mark.parametrize("size", [3, 7, 8, 9, 16, 130, 300])
    def test_loop_sizes_span_the_numpy_pairwise_branches(self, size):
        """A loop with >= 8 vertices sums through numpy's pairwise path.

        This is where a naive Rust shoelace sum breaks; the sizes bracket
        numpy's 8 and 128 thresholds.
        """
        rng = random.Random(6000 + size)
        refs = [f"P{i}" for i in range(size)]
        nl = make_netlist(refs)
        st = make_state(
            [(rng.uniform(-1e3, 1e3), rng.uniform(-1e3, 1e3)) for _ in range(size)],
            dtype=np.float64,
        )
        ctx = empty_context()
        assert_bit_identical(
            mod.loop_area_score(st, nl, ctx, [refs], max_area=1e6),
            _oracle_loop_area_score(st, nl, ctx, [refs], max_area=1e6),
            f"loop_area_score(vertices={size})",
        )

    def test_short_loops_are_skipped_not_scored(self):
        nl = make_netlist(["A", "B", "C"])
        st = make_state([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)])
        ctx = empty_context()
        loops = [["A", "B"], ["A"], ["A", "B", "C"]]
        assert_bit_identical(
            mod.loop_area_score(st, nl, ctx, loops),
            _oracle_loop_area_score(st, nl, ctx, loops),
            "loop_area_score(short loops skipped)",
        )

    def test_partially_resolvable_loop_drops_below_three(self):
        """A 3-ref loop with 1 ghost resolves to 2 vertices -> skipped."""
        nl = make_netlist(["A", "B"])
        st = make_state([(0.0, 0.0), (10.0, 0.0)])
        ctx = empty_context()
        loops = [["A", "B", "GHOST"]]
        assert_bit_identical(
            mod.loop_area_score(st, nl, ctx, loops),
            _oracle_loop_area_score(st, nl, ctx, loops),
            "loop_area_score(partially resolvable)",
        )


# ---------------------------------------------------------------------------
# compactness_score
# ---------------------------------------------------------------------------


class TestCompactnessScore:
    @pytest.mark.parametrize("seed", range(40))
    @pytest.mark.parametrize("dtype", [np.float32, np.float64])
    def test_randomized_matches(self, seed, dtype):
        rng = random.Random(7000 + seed)
        n = rng.randint(2, 12)
        refs = [f"K{i}" for i in range(n)]
        bounds = [(rng.uniform(0.3, 20.0), rng.uniform(0.3, 20.0)) for _ in range(n)]
        nl = make_netlist(refs, bounds=bounds)
        st = make_state(
            [(rng.uniform(0, 100), rng.uniform(0, 80)) for _ in range(n)], dtype=dtype
        )
        bd = make_board()
        assert_bit_identical(
            mod.compactness_score(st, nl, bd),
            _oracle_compactness_score(st, nl, bd),
            f"compactness_score(seed={seed}, dtype={dtype})",
        )

    def test_single_component_is_one(self):
        nl = make_netlist(["A"])
        st = make_state([(1.0, 2.0)])
        bd = make_board()
        assert_bit_identical(
            mod.compactness_score(st, nl, bd),
            _oracle_compactness_score(st, nl, bd),
            "compactness_score(n=1)",
        )

    def test_zero_area_components_stacked(self):
        """placement_area <= 0 -> the 1.0 arm."""
        nl = make_netlist(["A", "B"], bounds=[(0.0, 0.0), (0.0, 0.0)])
        st = make_state([(5.0, 5.0), (5.0, 5.0)])
        bd = make_board()
        assert_bit_identical(
            mod.compactness_score(st, nl, bd),
            _oracle_compactness_score(st, nl, bd),
            "compactness_score(degenerate)",
        )

    def test_overlap_clamps_to_one(self):
        nl = make_netlist(["A", "B"], bounds=[(20.0, 20.0), (20.0, 20.0)])
        st = make_state([(5.0, 5.0), (5.0, 5.0)])
        bd = make_board()
        assert_bit_identical(
            mod.compactness_score(st, nl, bd),
            _oracle_compactness_score(st, nl, bd),
            "compactness_score(overlapping)",
        )


# ---------------------------------------------------------------------------
# connectivity_clustering_score
# ---------------------------------------------------------------------------


class TestConnectivityClusteringScore:
    @pytest.mark.parametrize("seed", range(40))
    @pytest.mark.parametrize("dtype", [np.float32, np.float64])
    def test_randomized_matches(self, seed, dtype):
        rng = random.Random(8000 + seed)
        n = rng.randint(2, 10)
        refs = [f"N{i}" for i in range(n)]
        bounds = [(rng.uniform(0.3, 15.0), rng.uniform(0.3, 15.0)) for _ in range(n)]
        nl = make_netlist(refs, bounds=bounds, net_names=("A", "B"))
        st = make_state(
            [(rng.uniform(0, 100), rng.uniform(0, 80)) for _ in range(n)], dtype=dtype
        )
        pin_lists = [
            rng.sample(range(n), rng.randint(0, n)) for _ in range(rng.randint(1, 4))
        ]
        ctx = context_from_nets(pin_lists, n_pins=n)
        assert_bit_identical(
            mod.connectivity_clustering_score(st, nl, ctx),
            _oracle_connectivity_clustering_score(st, nl, ctx),
            f"connectivity_clustering_score(seed={seed}, dtype={dtype})",
        )

    def test_float32_narrowing_is_reproduced(self):
        """The f32 bbox subtraction is not cosmetic — pin it explicitly.

        `x_max - x_min` happens on raw numpy scalars, so with a float32
        position array the difference rounds to f32 before widening.  A Rust
        kernel that always subtracts in f64 diverges here.
        """
        refs = ["A", "B"]
        nl = make_netlist(refs, bounds=[(1.0, 1.0), (1.0, 1.0)], net_names=("A",))
        ctx = context_from_nets([[0, 1]], n_pins=2)
        positions = [(0.0, 0.0), (1.0 + 2**-20, 0.0)]
        st32 = make_state(positions, dtype=np.float32)
        st64 = make_state(positions, dtype=np.float64)
        for st, label in ((st32, "f32"), (st64, "f64")):
            assert_bit_identical(
                mod.connectivity_clustering_score(st, nl, ctx),
                _oracle_connectivity_clustering_score(st, nl, ctx),
                f"connectivity_clustering_score({label})",
            )

    def test_single_pin_nets_are_skipped(self):
        nl = make_netlist(["A", "B"], net_names=("A",))
        st = make_state([(0.0, 0.0), (10.0, 10.0)])
        ctx = context_from_nets([[0], []], n_pins=2)
        assert_bit_identical(
            mod.connectivity_clustering_score(st, nl, ctx),
            _oracle_connectivity_clustering_score(st, nl, ctx),
            "connectivity_clustering_score(single-pin nets)",
        )

    def test_no_nets_is_one(self):
        nl = Netlist(components=[Component(ref="A", footprint="F", bounds=(1.0, 1.0))], nets=[])
        st = make_state([(0.0, 0.0)])
        ctx = empty_context()
        assert_bit_identical(
            mod.connectivity_clustering_score(st, nl, ctx),
            _oracle_connectivity_clustering_score(st, nl, ctx),
            "connectivity_clustering_score(no nets)",
        )


# ---------------------------------------------------------------------------
# Empty-input semantics — the vacuity class, enumerated
# ---------------------------------------------------------------------------


class TestEmptyInputSemantics:
    """Every aggregate's empty-input value, established and asserted.

    All seven default to a *passing* score.  That is the pre-migration
    behaviour and this migration preserves it exactly — but preserving it
    silently is how vacuous gates are born, so each one is written down here
    with its type.
    """

    def _fixtures(self):
        nl = make_netlist(["A", "B"], net_names=("A",))
        st = make_state([(0.0, 0.0), (10.0, 10.0)])
        return st, nl, make_board(), empty_context()

    def test_thermal_score_empty_set_is_one(self):
        st, nl, bd, _ = self._fixtures()
        got = mod.thermal_score(st, nl, bd, set())
        assert_bit_identical(got, _oracle_thermal_score(st, nl, bd, set()), "thermal empty")
        assert key(got) == ("float", (1.0).hex())

    def test_thermal_score_all_refs_unresolvable_is_one(self):
        """The *other* empty path: a non-empty set that resolves to nothing."""
        st, nl, bd, _ = self._fixtures()
        ghosts = {"G1", "G2"}
        got = mod.thermal_score(st, nl, bd, ghosts)
        assert_bit_identical(got, _oracle_thermal_score(st, nl, bd, ghosts), "thermal ghosts")
        assert key(got) == ("float", (1.0).hex())

    def test_zone_compliance_empty_is_one(self):
        st, nl, bd, _ = self._fixtures()
        for assigns, zones in (({}, []), ({"A": "ZA"}, [])):
            board = make_board(zones=zones)
            got = mod.zone_compliance_score(st, nl, board, assigns)
            assert_bit_identical(
                got, _oracle_zone_compliance_score(st, nl, board, assigns), "zone empty"
            )
            assert key(got) == ("float", (1.0).hex())

    def test_zone_compliance_all_zones_unknown_is_one(self):
        st, nl, _, _ = self._fixtures()
        bd = make_board(zones=[Zone(name="ZA", bounds=(0.0, 0.0, 1.0, 1.0))])
        assigns = {"A": "NO_SUCH_ZONE"}
        got = mod.zone_compliance_score(st, nl, bd, assigns)
        assert_bit_identical(
            got, _oracle_zone_compliance_score(st, nl, bd, assigns), "zone unknown"
        )
        assert key(got) == ("float", (1.0).hex())

    def test_hv_lv_clearance_empty_sides_are_one(self):
        st, nl, _, _ = self._fixtures()
        for hv, lv in ((set(), set()), ({"A"}, set()), (set(), {"B"}), ({"G"}, {"B"})):
            got = mod.hv_lv_clearance_score(st, nl, hv, lv)
            assert_bit_identical(
                got, _oracle_hv_lv_clearance_score(st, nl, hv, lv), f"hv_lv empty {hv}/{lv}"
            )
            assert key(got) == ("float", (1.0).hex())

    def test_dual_rail_empty_sides_are_all_clear(self):
        st, nl, _, _ = self._fixtures()
        for hv, lv in ((set(), set()), ({"A"}, set()), ({"G"}, {"B"})):
            got = mod.dual_rail_clearance_report(st, nl, hv, lv)
            assert_bit_identical(
                got, _oracle_dual_rail_clearance_report(st, nl, hv, lv), "dual_rail empty"
            )
            assert key(got) == key(
                {
                    "clearance_score_3mm": 1.0,
                    "clearance_score_6mm": 1.0,
                    "violations_3mm": 0,
                    "violations_6mm": 0,
                }
            )

    def test_loop_area_empty_is_one(self):
        st, nl, _, ctx = self._fixtures()
        for loops in ([], [["A"]], [["G1", "G2", "G3"]]):
            got = mod.loop_area_score(st, nl, ctx, loops)
            assert_bit_identical(
                got, _oracle_loop_area_score(st, nl, ctx, loops), f"loop empty {loops}"
            )
            assert key(got) == ("float", (1.0).hex())

    def test_compactness_single_component_is_one(self):
        nl = make_netlist(["A"])
        st = make_state([(1.0, 1.0)])
        bd = make_board()
        got = mod.compactness_score(st, nl, bd)
        assert_bit_identical(got, _oracle_compactness_score(st, nl, bd), "compactness n=1")
        assert key(got) == ("float", (1.0).hex())

    def test_connectivity_clustering_empty_is_one(self):
        st, nl, _, ctx = self._fixtures()
        got = mod.connectivity_clustering_score(st, nl, ctx)
        assert_bit_identical(
            got, _oracle_connectivity_clustering_score(st, nl, ctx), "clustering empty"
        )
        assert key(got) == ("float", (1.0).hex())
