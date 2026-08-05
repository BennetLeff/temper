"""Property-based tests for the Rust Monte-Carlo simulator
(``temper_design_bundle_python``) — Wave 4 Phase 4 leftovers slice.

The Rust implementation must satisfy the same algebraic invariants the
pre-migration Python implementation satisfies, asserted INDEPENDENTLY of the
oracle (the differential test owns bit-parity; this file owns the closed-form
properties). Every property is fail-capable: each pins a formula, a boundary,
a fallback, or a monotonicity direction that a wrong implementation would
break.

R1c: properties P1-P7 (>= 5).  R1d: MR1-MR4 (>= 3).
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import temper_design_bundle_python as _tdb

DISTRIBUTION_PARAMS = _tdb.DistributionParams
MANUFACTURING_VARIABLES = _tdb.ManufacturingVariables
MONTE_CARLO_CONFIG = _tdb.MonteCarloConfig
MONTE_CARLO_SIMULATOR = _tdb.MonteCarloSimulator


def _hex(v: float) -> str:
    return float(v).hex()


_finite = st.floats(min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False)
_width = st.floats(min_value=1e-6, max_value=1e2, allow_nan=False, allow_infinity=False)
_etch_mean = st.floats(min_value=-0.1, max_value=0.1, allow_nan=False, allow_infinity=False)
_etch_std = st.floats(min_value=1e-6, max_value=0.05, allow_nan=False, allow_infinity=False)
_clearance = st.floats(min_value=-1.0, max_value=5.0, allow_nan=False, allow_infinity=False)
_n_comp = st.integers(min_value=1, max_value=6)


# ---------------------------------------------------------------------------
# P1: closed-form min-distance — the kernel's elementwise chain reproduced
# in pure Python arithmetic, bit-exact per sample (single-component and
# two-component closed forms).
# ---------------------------------------------------------------------------


def _kernel_expected(positions, bounds, etch, reg_x, reg_y):
    """Straight-line transcription of the oracle's kernel (no numpy
    vectorization, left-to-right IEEE ops) for N <= 2."""
    s = len(etch)
    n = len(positions)
    out = []
    for si in range(s):
        m = None
        for i in range(n):
            for j in range(n):
                dx = abs((positions[i][0] + reg_x[si]) - (positions[j][0] + reg_x[si]))
                dy = abs((positions[i][1] + reg_y[si]) - (positions[j][1] + reg_y[si]))
                mw = ((bounds[i][0] + 2.0 * etch[si]) + (bounds[j][0] + 2.0 * etch[si])) / 2.0
                mh = ((bounds[i][1] + 2.0 * etch[si]) + (bounds[j][1] + 2.0 * etch[si])) / 2.0
                d = dx - mw if dx - mw >= dy - mh else dy - mh
                d = 1e6 if i == j else d
                m = d if m is None else (d if d < m else m)
        out.append(m)
    return out


@pytest.mark.property
@given(
    n=_n_comp,
    mean=_etch_mean,
    std=_etch_std,
    reg_mean=_finite,
    reg_std=_etch_std,
)
@settings(max_examples=50, deadline=30000)
def test_p1_kernel_matches_closed_form(n, mean, std, reg_mean, reg_std):
    """run_clearance_simulation's stats mean is the mean of the closed-form
    per-sample min distances (bit-exact) — pins the kernel arithmetic and the
    (a + b) / 2.0 parenthesization. The expected vectors are drawn from a
    manually-advanced stream that mirrors the simulator's own (seed 1,
    declaration order: etch, reg_x, reg_y), so run() consumes exactly the
    same samples the closed form was computed from."""
    rng = np.random.default_rng(1)
    etch = rng.normal(mean, std, size=64)
    reg_x = rng.normal(reg_mean, reg_std, size=64)
    reg_y = rng.normal(reg_mean, reg_std, size=64)
    pos_rng = np.random.default_rng(0)
    positions = pos_rng.uniform(-10.0, 10.0, size=(n, 2))
    bounds = pos_rng.uniform(0.5, 3.0, size=(n, 2))
    sim = MONTE_CARLO_SIMULATOR(
        MANUFACTURING_VARIABLES(
            etch_tolerance=DISTRIBUTION_PARAMS(mean, std),
            registration_x=DISTRIBUTION_PARAMS(reg_mean, reg_std),
            registration_y=DISTRIBUTION_PARAMS(reg_mean, reg_std),
        ),
        config=MONTE_CARLO_CONFIG(num_samples=64, seed=1),
    )
    result = sim.run_clearance_simulation(positions, bounds, 0.5)
    expected = _kernel_expected(positions.tolist(), bounds.tolist(), etch.tolist(), reg_x.tolist(), reg_y.tolist())
    assert _hex(result.stats["mean_min_clearance"]) == _hex(float(np.mean(expected)))
    assert _hex(result.stats["std_min_clearance"]) == _hex(float(np.std(expected)))


# ---------------------------------------------------------------------------
# P2: yield is a monotone non-increasing function of required_clearance.
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(c1=_clearance, c2=_clearance)
@settings(max_examples=50, deadline=30000)
def test_p2_yield_monotone_in_clearance(c1, c2):
    """Lower required clearance never yields a smaller yield probability —
    compared on the SAME sample stream (two simulators, same seed)."""
    rng = np.random.default_rng(3)
    positions = rng.uniform(-5.0, 5.0, size=(3, 2))
    bounds = rng.uniform(1.0, 2.0, size=(3, 2))
    vars_ = MANUFACTURING_VARIABLES(
        etch_tolerance=DISTRIBUTION_PARAMS(0.01, 0.005),
        registration_x=DISTRIBUTION_PARAMS(0.0, 0.01),
    )
    sim_low = MONTE_CARLO_SIMULATOR(vars_, config=MONTE_CARLO_CONFIG(num_samples=200, seed=4))
    sim_high = MONTE_CARLO_SIMULATOR(vars_, config=MONTE_CARLO_CONFIG(num_samples=200, seed=4))
    y1 = sim_low.run_clearance_simulation(positions, bounds, min(c1, c2)).yield_probability
    y2 = sim_high.run_clearance_simulation(positions, bounds, max(c1, c2)).yield_probability
    if max(c1, c2) > min(c1, c2):
        assert y1 >= y2
    else:
        assert _hex(y1) == _hex(y2)


# ---------------------------------------------------------------------------
# P3: etch-only two-component closed form — yield is 1 exactly when the
# nominal gap exceeds the required clearance for every sample.
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(gap=_width, req=_clearance)
@settings(max_examples=50, deadline=30000)
def test_p3_nominal_two_component_yield(gap, req):
    """No variables: yield == (1.0 if the COMPUTED separation >= req else
    0.0), deterministically — no RNG consumption, exact comparison. The
    computed separation is (10.0 + gap) - 10.0 in IEEE arithmetic (the
    representation of 10.0 + gap rounds, so the separation is not always
    bit-equal to the ideal gap — the kernel must reproduce exactly that)."""
    positions = np.array([[0.0, 0.0], [10.0 + gap, 0.0]])
    bounds = np.array([[10.0, 10.0], [10.0, 10.0]])
    sim = MONTE_CARLO_SIMULATOR(
        MANUFACTURING_VARIABLES(), config=MONTE_CARLO_CONFIG(num_samples=1, seed=6)
    )
    result = sim.run_clearance_simulation(positions, bounds, req)
    sep = (10.0 + gap) - 10.0
    expected = 1.0 if sep >= req else 0.0
    assert _hex(result.yield_probability) == _hex(expected)
    # num_samples=1: np.mean of a single value is exact.
    assert _hex(result.stats["mean_min_clearance"]) == _hex(sep)


# ---------------------------------------------------------------------------
# P4: same-stream etch comparison — identical seeds and scale, larger etch
# mean ⇒ smaller yield (etch only ever shrinks the separation).
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(std=_etch_std)
@settings(max_examples=50, deadline=30000)
def test_p4_larger_etch_lowers_yield(std):
    """etch mean 0.0 vs 0.05, same seed: the underlying draws are identical
    (normal is a location-scale transform), so any yield difference is
    caused by the etch term alone."""
    positions = np.array([[0.0, 0.0], [10.1, 0.0]])
    bounds = np.array([[10.0, 10.0], [10.0, 10.0]])
    sim0 = MONTE_CARLO_SIMULATOR(
        MANUFACTURING_VARIABLES(etch_tolerance=DISTRIBUTION_PARAMS(0.0, std)),
        config=MONTE_CARLO_CONFIG(num_samples=256, seed=42),
    )
    sim1 = MONTE_CARLO_SIMULATOR(
        MANUFACTURING_VARIABLES(etch_tolerance=DISTRIBUTION_PARAMS(0.05, std)),
        config=MONTE_CARLO_CONFIG(num_samples=256, seed=42),
    )
    y0 = sim0.run_clearance_simulation(positions, bounds, 0.1).yield_probability
    y1 = sim1.run_clearance_simulation(positions, bounds, 0.1).yield_probability
    assert y1 <= y0


# ---------------------------------------------------------------------------
# P5: uniform sampling stays within [min_val, max_val] for every sample.
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(lo=_finite, hi=_finite)
@settings(max_examples=50, deadline=30000)
def test_p5_uniform_bounds_respected(lo, hi):
    """Every uniform draw lies in [min(lo, hi), max(lo, hi)] — both with
    explicit bounds and with the mean±1.0 fallback."""
    if lo > hi:
        lo, hi = hi, lo
    if lo == hi:
        hi = lo + 0.5
    sim = MONTE_CARLO_SIMULATOR(
        MANUFACTURING_VARIABLES(
            drill_tolerance=DISTRIBUTION_PARAMS(
                (lo + hi) / 2.0, 0.0, distribution="uniform", min_val=lo, max_val=hi
            )
        ),
        config=MONTE_CARLO_CONFIG(num_samples=100, seed=8),
    )
    samples = sim.sample_parameters(100)
    arr = samples["drill_tolerance"]
    assert float(arr.min()) >= lo
    assert float(arr.max()) <= hi
    assert arr.shape == (100,)


@pytest.mark.property
@given(mean=_finite)
@settings(max_examples=50, deadline=30000)
def test_p5b_uniform_fallback_bounds(mean):
    """Fallback [mean - 1.0, mean + 1.0] respected."""
    sim = MONTE_CARLO_SIMULATOR(
        MANUFACTURING_VARIABLES(
            copper_thickness=DISTRIBUTION_PARAMS(mean, distribution="uniform")
        ),
        config=MONTE_CARLO_CONFIG(num_samples=80, seed=9),
    )
    arr = sim.sample_parameters(80)["copper_thickness"]
    assert float(arr.min()) >= mean - 1.0
    assert float(arr.max()) <= mean + 1.0


# ---------------------------------------------------------------------------
# P6: sampling shapes/dtypes — every drawn array is (n,) float64.
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(n=st.integers(min_value=0, max_value=50), mean=_finite, std=_etch_std)
@settings(max_examples=50, deadline=30000)
def test_p6_sample_shapes_and_dtypes(n, mean, std):
    """Drawn arrays are (n,) float64 for n=0 too; keys match the declared
    variable names only."""
    sim = MONTE_CARLO_SIMULATOR(
        MANUFACTURING_VARIABLES(
            etch_tolerance=DISTRIBUTION_PARAMS(mean, std),
            registration_y=DISTRIBUTION_PARAMS(0.0, std),
        ),
        config=MONTE_CARLO_CONFIG(num_samples=n, seed=10),
    )
    samples = sim.sample_parameters(n)
    assert list(samples.keys()) == ["etch_tolerance", "registration_y"]
    for arr in samples.values():
        assert arr.shape == (n,)
        assert arr.dtype == np.float64


# ---------------------------------------------------------------------------
# P7: result metadata — num_samples rides through; failure_modes default.
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(n=st.integers(min_value=1, max_value=200))
@settings(max_examples=50, deadline=30000)
def test_p7_result_metadata(n):
    """result.num_samples == config.num_samples; failure_modes is a fresh
    empty list; stats carries exactly the two keys."""
    positions = np.array([[0.0, 0.0], [10.0, 0.0]])
    bounds = np.array([[9.0, 9.0], [9.0, 9.0]])
    sim = MONTE_CARLO_SIMULATOR(
        MANUFACTURING_VARIABLES(), config=MONTE_CARLO_CONFIG(num_samples=n, seed=11)
    )
    result = sim.run_clearance_simulation(positions, bounds, 1.0)
    assert result.num_samples == n
    assert result.failure_modes == []
    assert set(result.stats.keys()) == {"mean_min_clearance", "std_min_clearance"}


# ---------------------------------------------------------------------------
# MR1: seed-invariance of the no-variable configuration — with no sampling
# there is no RNG consumption, so the result is independent of the seed.
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(seed1=st.integers(min_value=0, max_value=1000), seed2=st.integers(min_value=0, max_value=1000))
@settings(max_examples=50, deadline=30000)
def test_mr1_seed_invariance_without_variables(seed1, seed2):
    positions = np.array([[0.0, 0.0], [10.1, 0.0]])
    bounds = np.array([[10.0, 10.0], [10.0, 10.0]])
    r1 = MONTE_CARLO_SIMULATOR(
        MANUFACTURING_VARIABLES(), config=MONTE_CARLO_CONFIG(num_samples=64, seed=seed1)
    ).run_clearance_simulation(positions, bounds, 0.1)
    r2 = MONTE_CARLO_SIMULATOR(
        MANUFACTURING_VARIABLES(), config=MONTE_CARLO_CONFIG(num_samples=64, seed=seed2)
    ).run_clearance_simulation(positions, bounds, 0.1)
    assert _hex(r1.yield_probability) == _hex(r2.yield_probability)
    assert _hex(r1.stats["mean_min_clearance"]) == _hex(r2.stats["mean_min_clearance"])


# ---------------------------------------------------------------------------
# MR2: component-order permutation invariance — swapping two rows of
# positions/bounds leaves the per-pair separation multiset unchanged, so the
# min per sample (and therefore yield and stats) is invariant.
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(n=_n_comp)
@settings(max_examples=50, deadline=30000)
def test_mr2_component_permutation_invariance(n):
    rng = np.random.default_rng(12)
    positions = rng.uniform(-8.0, 8.0, size=(n, 2))
    bounds = rng.uniform(0.5, 2.5, size=(n, 2))
    perm = np.random.RandomState(3).permutation(n)
    vars_ = MANUFACTURING_VARIABLES(
        etch_tolerance=DISTRIBUTION_PARAMS(0.01, 0.005),
        registration_x=DISTRIBUTION_PARAMS(0.0, 0.01),
        registration_y=DISTRIBUTION_PARAMS(0.0, 0.01),
    )
    sim = MONTE_CARLO_SIMULATOR(vars_, config=MONTE_CARLO_CONFIG(num_samples=128, seed=13))
    base = sim.run_clearance_simulation(positions, bounds, 0.5)
    perm_sim = MONTE_CARLO_SIMULATOR(vars_, config=MONTE_CARLO_CONFIG(num_samples=128, seed=13))
    swapped = perm_sim.run_clearance_simulation(positions[perm], bounds[perm], 0.5)
    assert _hex(base.yield_probability) == _hex(swapped.yield_probability)
    assert _hex(base.stats["mean_min_clearance"]) == _hex(swapped.stats["mean_min_clearance"])
    assert _hex(base.stats["std_min_clearance"]) == _hex(swapped.stats["std_min_clearance"])


# ---------------------------------------------------------------------------
# MR3: uniform-fallback equivalence — omitting min/max equals spelling the
# mean±1.0 bounds explicitly (same stream, bit-identical draws).
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(mean=_finite)
@settings(max_examples=50, deadline=30000)
def test_mr3_uniform_fallback_equivalence(mean):
    a = MONTE_CARLO_SIMULATOR(
        MANUFACTURING_VARIABLES(
            drill_tolerance=DISTRIBUTION_PARAMS(mean, distribution="uniform")
        ),
        config=MONTE_CARLO_CONFIG(seed=14),
    ).sample_parameters(64)
    b = MONTE_CARLO_SIMULATOR(
        MANUFACTURING_VARIABLES(
            drill_tolerance=DISTRIBUTION_PARAMS(
                mean, distribution="uniform", min_val=mean - 1.0, max_val=mean + 1.0
            )
        ),
        config=MONTE_CARLO_CONFIG(seed=14),
    ).sample_parameters(64)
    assert a["drill_tolerance"].tobytes() == b["drill_tolerance"].tobytes()


# ---------------------------------------------------------------------------
# MR4: power-of-two scaling invariance — scaling positions, bounds and the
# required clearance by 2**m (m <= 3, with no sampling so the registration/
# etch terms stay zero) scales every intermediate exactly: each IEEE op on
# 2**m-scaled operands is itself an exponent shift, so the result stats
# scale bit-exactly and the yield is invariant. (A general translation MR is
# NOT bit-exact: (p + t) + reg rounds differently from p + (reg + t).)
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(m=st.integers(min_value=1, max_value=3))
@settings(max_examples=50, deadline=30000)
def test_mr4_power_of_two_scaling_invariance(m):
    rng = np.random.default_rng(15)
    positions = rng.uniform(-2.0, 2.0, size=(3, 2))
    bounds = rng.uniform(0.5, 1.5, size=(3, 2))
    k = 2.0**m
    sim = MONTE_CARLO_SIMULATOR(
        MANUFACTURING_VARIABLES(), config=MONTE_CARLO_CONFIG(num_samples=128, seed=16)
    )
    base = sim.run_clearance_simulation(positions, bounds, 0.5)
    sim2 = MONTE_CARLO_SIMULATOR(
        MANUFACTURING_VARIABLES(), config=MONTE_CARLO_CONFIG(num_samples=128, seed=16)
    )
    scaled = sim2.run_clearance_simulation(positions * k, bounds * k, 0.5 * k)
    assert _hex(base.yield_probability) == _hex(scaled.yield_probability)
    assert _hex(scaled.stats["mean_min_clearance"]) == _hex(k * base.stats["mean_min_clearance"])
    assert _hex(scaled.stats["std_min_clearance"]) == _hex(k * base.stats["std_min_clearance"])
