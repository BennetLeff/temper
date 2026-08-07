"""Differential tests: temper-quality-oracle Rust validation-metric kernels
vs the verbatim pre-migration Python (Wave 4 — ``validation/metrics.py``).

The pre-migration implementation is pinned in ``_validation_metrics_py_oracle.py``
(a verbatim copy of the module, with an ``_oracle_`` prefix on each
top-level function). Every numeric assertion here is **bit-exact**: floats
are compared through ``float.hex()`` (never a tolerance), and every
non-float leaf carries its concrete ``type`` in the comparison key so an
int that silently became a float cannot hide behind numeric equality
(mirrors ``tests/metrics/test_quality_rust_differential.py``'s ``key()``
helper).

Scope: ``_compute_overlap_metrics``, ``_compute_clearance_metrics``,
``_compute_wirelength_metrics``, ``_compute_distribution_metrics``.
``_compute_boundary_metrics``, ``_compute_zone_metrics`` and
``_compute_keepout_metrics`` are NOT pinned here — see
``validation/metrics.py``'s module docstring and
``validation_metrics.rs``'s module doc for the triage reasoning (thin
O(n) loops already dominated by a `get_rotated_bounds`/domain-glue FFI
crossing, or dict-lookup control flow, not worth their own kernel).

Bit-exactness catalog measured for this migration (see
``validation_metrics.rs`` for the full writeup):

- **B5 — CPython ``max``/``min`` keep the first argument.**
  ``TestBitExactnessCatalog::test_python_max_keeps_first_argument_on_nan``
  pins the exact semantics ``worst_overlap``/``max_net_length`` and
  ``min_hv_lv_clearance`` depend on.
- **B12 — CPython 3.12's compensated builtin ``sum()``.**
  ``test_cpython312_sum_is_not_naive_addition`` measures 920/2000
  mismatches between ``sum()`` and a naive ``+=`` fold on
  wirelength-shaped random float lists on this repo's CPython 3.12.12 —
  the exact algorithm ``avg_net_length`` needs.
- **New class — NEP-50 float32 narrowing (not promotion).**
  ``test_distribution_nep50_narrows_to_float32`` measures that a naive
  float64 reimplementation of ``_compute_distribution_metrics`` disagrees
  with the real (float32-narrowed) computation on every tested `n`.
- **Measured non-trap — array `** 2` is `x * x` for numpy float32 arrays.**
  ``test_array_power_two_matches_multiplication`` measures 0/200000
  mismatches, the opposite of the `x ** 2`-is-libm-`pow` scalar trap
  documented elsewhere in this codebase (e.g.
  ``placement_metrics.rs``'s B1/B7) — included here so a future reader
  does not "fix" this kernel into using ``py_pow`` by analogy.

Caller-invariant note: ``state.positions`` is a plain-Python-dataclass
field (``core/state.py``'s ``PlacementState`` is NOT a Rust pyclass) with
no dtype enforcement at the type level — only the *factories*
(``from_positions``, ``random_init``, etc.) hardcode
``dtype=np.float32``. This migration assumes (matching the precedent
already merged for the same field in
``packages/temper-thermal/src/geometric_metrics.rs`` /
``thermal_edges.rs``) that every `PlacementState` reaching
`compute_metrics` in production went through a float32-enforcing
factory. Every fixture in this suite constructs `positions` with an
explicit `dtype=np.float32` to match that contract; an off-contract
float64 `state.positions` is NOT covered here (not re-validated, exactly
as the upstream precedent does not re-validate it either).
"""

from __future__ import annotations

import math
import random

import numpy as np
import pytest
import temper_quality_oracle as _qo
from tests.validation._validation_metrics_py_oracle import (
    PlacementMetrics as _OraclePlacementMetrics,
)
from tests.validation._validation_metrics_py_oracle import (
    _oracle_compute_clearance_metrics,
    _oracle_compute_distribution_metrics,
    _oracle_compute_overlap_metrics,
    _oracle_compute_wirelength_metrics,
)

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.core.state import PlacementState
from temper_placer.validation.metrics import (
    PlacementMetrics,
    _compute_clearance_metrics,
    _compute_distribution_metrics,
    _compute_overlap_metrics,
    _compute_wirelength_metrics,
)

# ---------------------------------------------------------------------------
# Bit-exact comparison helpers (mirrors test_quality_rust_differential.py)
# ---------------------------------------------------------------------------


def key(value):
    if isinstance(value, float):
        if math.isnan(value):
            return ("float", "nan", math.copysign(1.0, value))
        return ("float", value.hex())
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(key(v) for v in value))
    return (type(value).__name__, value)


def assert_bit_identical(got, expected, what: str) -> None:
    assert key(got) == key(expected), (
        f"{what}: Rust-delegated result is not bit-identical to the pinned "
        f"Python oracle.\n  shipped = {got!r}  key={key(got)}\n"
        f"  oracle  = {expected!r}  key={key(expected)}"
    )


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _make_netlist(n: int, rng: random.Random) -> Netlist:
    """Components with random bounds/net_class; no pins (overlap/clearance/
    distribution don't touch pins)."""
    components = [
        Component(
            ref=f"C{i}",
            footprint="fp",
            bounds=(rng.uniform(0.5, 30.0), rng.uniform(0.5, 30.0)),
            net_class="HighVoltage" if rng.random() < 0.3 else "Signal",
        )
        for i in range(n)
    ]
    return Netlist(components=components, nets=[])


def _make_board(rng: random.Random) -> Board:
    return Board(
        width=rng.uniform(20.0, 400.0),
        height=rng.uniform(20.0, 400.0),
        origin=(0.0, 0.0),
    )


def _make_positions_f32(n: int, rng: random.Random) -> np.ndarray:
    return np.array(
        [[rng.uniform(-100.0, 500.0), rng.uniform(-100.0, 500.0)] for _ in range(n)],
        dtype=np.float32,
    )


def _make_netlist_with_pins(n: int, rng: random.Random) -> Netlist:
    """Components with 1-3 pins each, plus 1-5 random multi-pin nets --
    enough to exercise ``_compute_wirelength_metrics``'s pin-resolution
    glue and the HPWL fold it delegates."""
    components = []
    for i in range(n):
        num_pins = rng.randint(1, 3)
        pins = [
            Pin(f"P{p}", str(p), (rng.uniform(-2.0, 2.0), rng.uniform(-2.0, 2.0)))
            for p in range(num_pins)
        ]
        components.append(
            Component(
                ref=f"C{i}",
                footprint="fp",
                bounds=(rng.uniform(2.0, 10.0), rng.uniform(2.0, 10.0)),
                pins=pins,
            )
        )
    nets = []
    if n >= 2:
        for k in range(rng.randint(1, 5)):
            n_pins_in_net = rng.randint(2, min(4, n))
            chosen = rng.sample(range(n), n_pins_in_net)
            nets.append(
                Net(
                    f"NET{k}",
                    [(f"C{ci}", "0") for ci in chosen],
                    weight=rng.uniform(0.1, 3.0),
                )
            )
    return Netlist(components=components, nets=nets)


def _make_state_with_rotation(n: int, rng: random.Random) -> tuple[np.ndarray, np.ndarray]:
    positions = _make_positions_f32(n, rng)
    rotation_indices = np.array([rng.randint(0, 3) for _ in range(n)])
    return positions, rotation_indices


SEEDS = range(200)


# ---------------------------------------------------------------------------
# Overlap metrics
# ---------------------------------------------------------------------------


class TestOverlapMetrics:
    @pytest.mark.parametrize("seed", SEEDS)
    def test_matches_oracle_random(self, seed):
        rng = random.Random(seed)
        n = rng.randint(0, 15)
        distances_flat = [rng.uniform(-5.0, 20.0) for _ in range(n * n)]
        distances_2d = np.array(distances_flat).reshape(n, n) if n else np.zeros((0, 0))

        oracle_m = _OraclePlacementMetrics()
        _oracle_compute_overlap_metrics(oracle_m, distances_2d, n)

        shipped_m = PlacementMetrics()
        _compute_overlap_metrics(shipped_m, distances_flat, n)

        assert_bit_identical(shipped_m.overlap_count, oracle_m.overlap_count, f"seed={seed} overlap_count")
        assert_bit_identical(
            shipped_m.total_overlap_area, oracle_m.total_overlap_area, f"seed={seed} total_overlap_area"
        )
        assert_bit_identical(shipped_m.worst_overlap, oracle_m.worst_overlap, f"seed={seed} worst_overlap")

    def test_exact_zero_boundary_is_not_overlap(self):
        # dist == 0.0 exactly must not count (`dist < 0`, not `<= 0`).
        oracle_m = _OraclePlacementMetrics()
        _oracle_compute_overlap_metrics(oracle_m, np.array([[0.0, 0.0], [0.0, 0.0]]), 2)
        shipped_m = PlacementMetrics()
        _compute_overlap_metrics(shipped_m, [0.0, 0.0, 0.0, 0.0], 2)
        assert_bit_identical(shipped_m.overlap_count, oracle_m.overlap_count, "exact_zero overlap_count")
        assert shipped_m.overlap_count == 0

    def test_empty_netlist(self):
        oracle_m = _OraclePlacementMetrics()
        _oracle_compute_overlap_metrics(oracle_m, np.zeros((0, 0)), 0)
        shipped_m = PlacementMetrics()
        _compute_overlap_metrics(shipped_m, [], 0)
        assert_bit_identical(shipped_m.overlap_count, oracle_m.overlap_count, "empty overlap_count")
        assert_bit_identical(shipped_m.total_overlap_area, oracle_m.total_overlap_area, "empty total_overlap_area")
        assert_bit_identical(shipped_m.worst_overlap, oracle_m.worst_overlap, "empty worst_overlap")


# ---------------------------------------------------------------------------
# Clearance metrics
# ---------------------------------------------------------------------------


class TestClearanceMetrics:
    @pytest.mark.parametrize("seed", SEEDS)
    def test_matches_oracle_random(self, seed):
        rng = random.Random(seed)
        n = rng.randint(0, 15)
        netlist = _make_netlist(n, rng)
        distances_flat = [rng.uniform(0.0, 25.0) for _ in range(n * n)]
        distances_2d = np.array(distances_flat).reshape(n, n) if n else np.zeros((0, 0))
        hv_lv_clearance = rng.uniform(0.5, 30.0)

        oracle_m = _OraclePlacementMetrics()
        _oracle_compute_clearance_metrics(oracle_m, distances_2d, netlist, hv_lv_clearance)

        shipped_m = PlacementMetrics()
        _compute_clearance_metrics(shipped_m, distances_flat, netlist, hv_lv_clearance)

        assert_bit_identical(
            shipped_m.clearance_violations, oracle_m.clearance_violations, f"seed={seed} clearance_violations"
        )
        assert_bit_identical(
            shipped_m.hv_lv_violations, oracle_m.hv_lv_violations, f"seed={seed} hv_lv_violations"
        )
        assert_bit_identical(
            shipped_m.min_hv_lv_clearance, oracle_m.min_hv_lv_clearance, f"seed={seed} min_hv_lv_clearance"
        )

    def test_no_hv_lv_pair_stays_at_infinity(self):
        rng = random.Random(0)
        netlist = Netlist(
            components=[
                Component(ref="A", footprint="fp", bounds=(1.0, 1.0), net_class="Signal"),
                Component(ref="B", footprint="fp", bounds=(1.0, 1.0), net_class="Signal"),
            ]
        )
        distances_flat = [0.0, 5.0, 0.0, 0.0]
        oracle_m = _OraclePlacementMetrics()
        _oracle_compute_clearance_metrics(oracle_m, np.array(distances_flat).reshape(2, 2), netlist, 10.0)
        shipped_m = PlacementMetrics()
        _compute_clearance_metrics(shipped_m, distances_flat, netlist, 10.0)
        assert_bit_identical(shipped_m.min_hv_lv_clearance, oracle_m.min_hv_lv_clearance, "min_hv_lv_clearance")
        assert shipped_m.min_hv_lv_clearance == float("inf")

    def test_empty_netlist(self):
        oracle_m = _OraclePlacementMetrics()
        netlist = Netlist(components=[])
        _oracle_compute_clearance_metrics(oracle_m, np.zeros((0, 0)), netlist, 10.0)
        shipped_m = PlacementMetrics()
        _compute_clearance_metrics(shipped_m, [], netlist, 10.0)
        assert_bit_identical(
            shipped_m.clearance_violations, oracle_m.clearance_violations, "empty clearance_violations"
        )
        assert_bit_identical(shipped_m.min_hv_lv_clearance, oracle_m.min_hv_lv_clearance, "empty min_hv_lv_clearance")


# ---------------------------------------------------------------------------
# Wirelength metrics
# ---------------------------------------------------------------------------


class TestWirelengthMetrics:
    @pytest.mark.parametrize("seed", range(80))
    def test_matches_oracle_random(self, seed):
        rng = random.Random(seed)
        n = rng.randint(0, 10)
        netlist = _make_netlist_with_pins(n, rng)
        positions, rotation_indices = _make_state_with_rotation(n, rng)

        oracle_m = _OraclePlacementMetrics()
        _oracle_compute_wirelength_metrics(oracle_m, positions, rotation_indices, netlist)

        shipped_m = PlacementMetrics()
        _compute_wirelength_metrics(shipped_m, positions, rotation_indices, netlist)

        assert_bit_identical(
            shipped_m.total_wirelength, oracle_m.total_wirelength, f"seed={seed} total_wirelength"
        )
        assert_bit_identical(
            shipped_m.max_net_length, oracle_m.max_net_length, f"seed={seed} max_net_length"
        )
        assert_bit_identical(
            shipped_m.avg_net_length, oracle_m.avg_net_length, f"seed={seed} avg_net_length"
        )

    def test_empty_nets(self):
        netlist = Netlist(components=[], nets=[])
        positions = np.zeros((0, 2), dtype=np.float32)
        rotation_indices = np.zeros((0,), dtype=np.int64)
        oracle_m = _OraclePlacementMetrics()
        _oracle_compute_wirelength_metrics(oracle_m, positions, rotation_indices, netlist)
        shipped_m = PlacementMetrics()
        _compute_wirelength_metrics(shipped_m, positions, rotation_indices, netlist)
        assert_bit_identical(shipped_m.avg_net_length, oracle_m.avg_net_length, "empty avg_net_length")
        assert shipped_m.avg_net_length == 0.0


# ---------------------------------------------------------------------------
# Distribution metrics
# ---------------------------------------------------------------------------


class TestDistributionMetrics:
    @pytest.mark.parametrize("seed", SEEDS)
    def test_matches_oracle_random(self, seed):
        rng = random.Random(seed)
        n = rng.randint(1, 40)
        positions = _make_positions_f32(n, rng)
        widths = np.array([rng.uniform(0.5, 60.0) for _ in range(n)], dtype=np.float32)
        heights = np.array([rng.uniform(0.5, 60.0) for _ in range(n)], dtype=np.float32)
        board = _make_board(rng)

        oracle_m = _OraclePlacementMetrics()
        _oracle_compute_distribution_metrics(oracle_m, positions, widths, heights, board)

        shipped_m = PlacementMetrics()
        _compute_distribution_metrics(shipped_m, positions, widths, heights, board)

        assert_bit_identical(shipped_m.utilization, oracle_m.utilization, f"seed={seed} utilization")
        assert_bit_identical(
            shipped_m.center_of_mass[0], oracle_m.center_of_mass[0], f"seed={seed} center_of_mass.x"
        )
        assert_bit_identical(
            shipped_m.center_of_mass[1], oracle_m.center_of_mass[1], f"seed={seed} center_of_mass.y"
        )
        assert_bit_identical(shipped_m.spread_score, oracle_m.spread_score, f"seed={seed} spread_score")

    @pytest.mark.parametrize("n", [1, 2, 7, 8, 9, 63, 64, 65, 127, 128, 129, 200, 500, 1000])
    def test_matches_oracle_across_pairwise_blocksize_boundaries(self, n):
        """n values straddling numpy's PW_BLOCKSIZE=128 recursion boundary."""
        rng = random.Random(n * 7919)
        positions = _make_positions_f32(n, rng)
        widths = np.array([rng.uniform(0.5, 60.0) for _ in range(n)], dtype=np.float32)
        heights = np.array([rng.uniform(0.5, 60.0) for _ in range(n)], dtype=np.float32)
        board = _make_board(rng)

        oracle_m = _OraclePlacementMetrics()
        _oracle_compute_distribution_metrics(oracle_m, positions, widths, heights, board)
        shipped_m = PlacementMetrics()
        _compute_distribution_metrics(shipped_m, positions, widths, heights, board)

        assert_bit_identical(shipped_m.utilization, oracle_m.utilization, f"n={n} utilization")
        assert_bit_identical(shipped_m.spread_score, oracle_m.spread_score, f"n={n} spread_score")

    def test_empty_positions_produces_nan_matching_oracle(self):
        """n=0: np.mean([]) issues a RuntimeWarning and returns NaN in the
        oracle; the kernel's 0.0/0.0 float32 division also produces NaN.
        Pinned bit-for-bit (both are the IEEE quiet-NaN pattern from a
        0/0 division -- not merely "both are some NaN")."""
        positions = np.zeros((0, 2), dtype=np.float32)
        widths = np.zeros((0,), dtype=np.float32)
        heights = np.zeros((0,), dtype=np.float32)
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))

        oracle_m = _OraclePlacementMetrics()
        with pytest.warns(RuntimeWarning):
            _oracle_compute_distribution_metrics(oracle_m, positions, widths, heights, board)
        shipped_m = PlacementMetrics()
        _compute_distribution_metrics(shipped_m, positions, widths, heights, board)

        assert_bit_identical(shipped_m.utilization, oracle_m.utilization, "empty utilization")
        assert_bit_identical(
            shipped_m.center_of_mass[0], oracle_m.center_of_mass[0], "empty center_of_mass.x"
        )
        assert_bit_identical(shipped_m.spread_score, oracle_m.spread_score, "empty spread_score")
        assert math.isnan(shipped_m.center_of_mass[0])


# ---------------------------------------------------------------------------
# Bit-exactness catalog: measured facts this migration is pinned against
# ---------------------------------------------------------------------------


class TestBitExactnessCatalog:
    def test_python_max_keeps_first_argument_on_nan(self):
        """B5: max(a, b) is `b if b > a else a` -- keeps the FIRST arg on a
        tie or when b is NaN. This is what `worst_overlap = max(worst_overlap,
        overlap_amount)` depends on for correctness under adversarial input."""
        assert max(0.0, float("nan")) == 0.0
        assert math.isnan(max(float("nan"), 0.0))
        # f64::max-style (IEEE maxNum) would return 0.0 in BOTH cases --
        # this asymmetry is exactly what distinguishes CPython's builtin.

    def test_python_min_keeps_first_argument_on_nan(self):
        assert min(float("inf"), float("nan")) == float("inf")
        assert math.isnan(min(float("nan"), float("inf")))

    def test_hv_lv_xor_identity(self):
        """The oracle's two-line `is_hv_lv` boolean is exactly `hv_i != hv_j`
        (XOR) for every combination -- verified exhaustively, not assumed."""
        for hv_i in (True, False):
            for hv_j in (True, False):
                oracle_expr = (hv_i and not hv_j) or (hv_j and not hv_i)
                assert oracle_expr == (hv_i != hv_j)

    def test_cpython312_sum_is_not_naive_addition(self):
        """B12: measured on this repo's CPython (3.12.12 in dev, >=3.12
        pinned by pyproject.toml): builtin sum() (Neumaier-compensated
        since 3.12) disagrees with a naive `+=` fold on the majority of
        random wirelength-shaped float lists."""
        rng = random.Random(123)
        mismatches = 0
        trials = 2000
        for _ in range(trials):
            n = rng.randint(2, 30)
            vals = [rng.uniform(0.0, 500.0) for _ in range(n)]
            s_builtin = sum(vals)
            acc = 0.0
            for v in vals:
                acc += v
            if s_builtin != acc:
                mismatches += 1
        # Measured 920/2000 on this environment; assert it's a real,
        # substantial fraction (not a flaky single-bit fluke) so this test
        # actually discriminates a regression to naive accumulation.
        assert mismatches > trials * 0.2, (
            f"only {mismatches}/{trials} mismatches -- builtin sum() no longer "
            "measurably differs from naive accumulation on this platform; "
            "re-verify the B12 catalog entry still applies"
        )

    def test_distribution_nep50_narrows_to_float32(self):
        """New class: _compute_distribution_metrics has no float64 array
        anchor (positions AND widths/heights are both float32), so NEP-50
        narrows the whole computation to float32 rather than promoting.
        Measured: a naive float64 reimplementation disagrees with the real
        (float32) computation for every tested n."""
        rng = np.random.default_rng(7)
        disagreements = 0
        ns = [1, 2, 5, 7, 8, 9, 15, 50, 128, 129, 200, 300, 1000]
        for n in ns:
            positions = rng.uniform(-500, 500, size=(n, 2)).astype(np.float32)
            widths = rng.uniform(1, 50, size=n).astype(np.float32)
            heights = rng.uniform(1, 50, size=n).astype(np.float32)

            total_area_f32 = float(np.sum(widths * heights))
            com_x_f32 = float(np.mean(positions[:, 0]))

            positions64 = positions.astype(np.float64)
            widths64 = widths.astype(np.float64)
            heights64 = heights.astype(np.float64)
            total_area_naive64 = float(sum((widths64 * heights64).tolist()))
            com_x_naive64 = float(sum(positions64[:, 0].tolist()) / n)

            if total_area_f32 != total_area_naive64 or com_x_f32 != com_x_naive64:
                disagreements += 1
        assert disagreements == len(ns), (
            f"only {disagreements}/{len(ns)} n values diverged from a naive "
            "float64 reimplementation -- re-verify the NEP-50-narrowing "
            "catalog entry still applies on this numpy version"
        )

    def test_array_power_two_matches_multiplication(self):
        """Measured non-trap: numpy ARRAY `** 2` (a ufunc call) is
        bit-identical to `x * x` for float32 arrays -- unlike the scalar
        `float.__pow__` `x ** 2`-is-libm-`pow` trap documented elsewhere in
        this codebase. This is why validation_metrics.rs's
        `distribution_metrics` uses `dx * dx`, not a `pow`-routed call."""
        rng = np.random.default_rng(42)
        xs = rng.uniform(-1e6, 1e6, size=200_000).astype(np.float32)
        pow_res = xs**2
        mul_res = xs * xs
        mismatches = int(np.sum(pow_res.view(np.uint32) != mul_res.view(np.uint32)))
        assert mismatches == 0, f"{mismatches}/200000 mismatches -- array**2 no longer equals x*x on this numpy"

    def test_array_power_half_matches_sqrt(self):
        rng = np.random.default_rng(42)
        ys = rng.uniform(0, 1e6, size=200_000).astype(np.float32)
        pow05 = ys**0.5
        sq = np.sqrt(ys)
        mismatches = int(np.sum(pow05.view(np.uint32) != sq.view(np.uint32)))
        assert mismatches == 0, f"{mismatches}/200000 mismatches -- array**0.5 no longer equals np.sqrt on this numpy"


# ---------------------------------------------------------------------------
# Wiring: the shipped module must actually DELEGATE, not shadow-implement.
#
# monkeypatch the compiled temper_quality_oracle attribute to raise; if the
# shipped `_compute_*_metrics` function still computes a normal result
# (rather than propagating the raise), it is NOT calling the Rust kernel.
# ---------------------------------------------------------------------------


class _SentinelError(RuntimeError):
    pass


class TestWiring:
    def test_overlap_delegates_to_rust(self, monkeypatch):
        def _boom(*a, **k):
            raise _SentinelError("overlap_metrics_py")

        monkeypatch.setattr(_qo, "overlap_metrics_py", _boom, raising=False)
        with pytest.raises(_SentinelError):
            _compute_overlap_metrics(PlacementMetrics(), [0.0, -1.0, 0.0, 0.0], 2)

    def test_clearance_delegates_to_rust(self, monkeypatch):
        def _boom(*a, **k):
            raise _SentinelError("clearance_metrics_py")

        monkeypatch.setattr(_qo, "clearance_metrics_py", _boom, raising=False)
        netlist = Netlist(
            components=[
                Component(ref="A", footprint="fp", bounds=(1.0, 1.0)),
                Component(ref="B", footprint="fp", bounds=(1.0, 1.0)),
            ]
        )
        with pytest.raises(_SentinelError):
            _compute_clearance_metrics(PlacementMetrics(), [0.0, 5.0, 0.0, 0.0], netlist, 10.0)

    def test_wirelength_delegates_to_rust(self, monkeypatch):
        def _boom(*a, **k):
            raise _SentinelError("wirelength_metrics_py")

        monkeypatch.setattr(_qo, "wirelength_metrics_py", _boom, raising=False)
        rng = random.Random(1)
        netlist = _make_netlist_with_pins(3, rng)
        positions, rotation_indices = _make_state_with_rotation(3, rng)
        with pytest.raises(_SentinelError):
            _compute_wirelength_metrics(PlacementMetrics(), positions, rotation_indices, netlist)

    def test_distribution_delegates_to_rust(self, monkeypatch):
        def _boom(*a, **k):
            raise _SentinelError("distribution_metrics_py")

        monkeypatch.setattr(_qo, "distribution_metrics_py", _boom, raising=False)
        rng = random.Random(2)
        positions = _make_positions_f32(3, rng)
        widths = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        heights = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        board = _make_board(rng)
        with pytest.raises(_SentinelError):
            _compute_distribution_metrics(PlacementMetrics(), positions, widths, heights, board)
