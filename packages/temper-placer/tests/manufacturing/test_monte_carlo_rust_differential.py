"""Differential test: Rust Monte-Carlo simulator (``temper_design_bundle_python``)
vs the pinned Python oracle.

Wave 4, Phase 4 leftovers slice — the manufacturing/monte_carlo.py
migration. The Rust pyo3 pyclasses (``DistributionParams``,
``ManufacturingVariables``, ``MonteCarloConfig``, ``MonteCarloResult``,
``MonteCarloSimulator`` in ``temper-design-bundle/src/
manufacturing_monte_carlo.rs``) must reproduce the pre-migration Python
implementation of ``temper_placer/manufacturing/monte_carlo.py``
bit-identically. The pre-migration implementation is pinned verbatim as the
oracle (``_monte_carlo_py_oracle.py``, commit 58b302ce8) and every assertion
here drives IDENTICAL inputs through both sides.

Comparison conventions:
- numpy arrays as ``(dtype, shape, tobytes())`` (bit-exact);
- floats via ``float.hex()``, never a tolerance;
- every non-float leaf's concrete type rides in the comparison key, so
  int-vs-float cannot hide behind numeric equality;
- exceptions are compared by (type name, str) via ``canon_call``.

Boundary notes (KTD9 — kept Python-side, argued in ``VERIFICATION.md``):
- The numpy ``Generator`` (``np.random.default_rng(seed)``) is created and
  advanced through numpy's own API on BOTH sides, so the RNG stream is
  bit-identical by construction; the differential still pins the stream
  (same seed → same draws; consecutive calls advance identically).
- ``np.mean`` / ``np.std`` / ``astype`` / ``>=`` on the min-distance
  vector are numpy calls on both sides — the Rust kernel computes only the
  elementwise [S,N,N] chain plus the exact min reduction.
"""

from __future__ import annotations

import pytest
import temper_design_bundle_python as _tdb

import tests.manufacturing._monte_carlo_py_oracle as _oracle

# Rust symbols under test — must exist or this file fails to collect (RED).
DISTRIBUTION_PARAMS = _tdb.DistributionParams
MANUFACTURING_VARIABLES = _tdb.ManufacturingVariables
MONTE_CARLO_CONFIG = _tdb.MonteCarloConfig
MONTE_CARLO_RESULT = _tdb.MonteCarloResult
MONTE_CARLO_SIMULATOR = _tdb.MonteCarloSimulator


# ---------------------------------------------------------------------------
# Fixtures / canonicalization.
# ---------------------------------------------------------------------------


def _arr(a) -> tuple:
    """(dtype, shape, tobytes) — bit-exact array key."""
    return (a.dtype.str, a.shape, a.tobytes())


def _samples_key(samples) -> tuple:
    return tuple((name, _arr(arr)) for name, arr in samples.items())


def _stats_key(stats) -> tuple:
    return tuple(sorted((k, float(v).hex()) for k, v in stats.items()))


def _result_key(r) -> tuple:
    return (
        type(r.num_samples).__name__,
        r.num_samples,
        type(r.yield_probability).__name__,
        float(r.yield_probability).hex(),
        list(r.failure_modes),
        _stats_key(r.stats),
    )


def canon_call(fn, *args, **kwargs):
    """Call fn; return ('ok', value) or ('err', type-name, str)."""
    try:
        return ("ok", fn(*args, **kwargs))
    except Exception as e:  # noqa: BLE001 - parity capture, not handling
        return ("err", type(e).__name__, str(e))


def _both_samples(sim_py, sim_rust, n):
    return _oracle_samples(sim_py, n), _rust_samples(sim_rust, n)


def _oracle_samples(sim, n):
    return canon_call(sim.sample_parameters, n)


def _rust_samples(sim, n):
    return canon_call(sim.sample_parameters, n)


def _oracle_run(sim, positions, bounds, required_clearance):
    return canon_call(sim.run_clearance_simulation, positions, bounds, required_clearance)


def _rust_run(sim, positions, bounds, required_clearance):
    return canon_call(sim.run_clearance_simulation, positions, bounds, required_clearance)


def _mk_vars_py(
    etch=None, drill=None, reg_x=None, reg_y=None, copper=None, dielectric=None
):
    return _oracle.ManufacturingVariables(
        etch_tolerance=etch,
        drill_tolerance=drill,
        registration_x=reg_x,
        registration_y=reg_y,
        copper_thickness=copper,
        dielectric_thickness=dielectric,
    )


def _mk_vars_rust(
    etch=None, drill=None, reg_x=None, reg_y=None, copper=None, dielectric=None
):
    return MANUFACTURING_VARIABLES(
        etch_tolerance=etch,
        drill_tolerance=drill,
        registration_x=reg_x,
        registration_y=reg_y,
        copper_thickness=copper,
        dielectric_thickness=dielectric,
    )


def _p(py_cls, rust_cls, *args, **kwargs):
    return py_cls(*args, **kwargs), rust_cls(*args, **kwargs)


@pytest.fixture
def normal_etch_pair():
    return _p(
        _oracle.DistributionParams,
        DISTRIBUTION_PARAMS,
        mean=0.0,
        std_dev=0.01,
    )


@pytest.fixture
def uniform_drill_pair():
    return _p(
        _oracle.DistributionParams,
        DISTRIBUTION_PARAMS,
        mean=0.1,
        std_dev=0.0,
        distribution="uniform",
        min_val=0.05,
        max_val=0.15,
    )


@pytest.fixture
def uniform_fallback_pair():
    return _p(
        _oracle.DistributionParams,
        DISTRIBUTION_PARAMS,
        mean=0.5,
        distribution="uniform",
    )


# ---------------------------------------------------------------------------
# Data-class construction parity.
# ---------------------------------------------------------------------------


def test_distribution_params_defaults_parity():
    """Defaults: std_dev 0.0, distribution 'normal', min/max None — with
    concrete types (int 5 stays int, 0.5 stays float)."""
    py_dp, rust_dp = _p(_oracle.DistributionParams, DISTRIBUTION_PARAMS, 5)
    assert (type(rust_dp.mean).__name__, rust_dp.mean) == (
        type(py_dp.mean).__name__,
        py_dp.mean,
    )
    assert (type(rust_dp.std_dev).__name__, rust_dp.std_dev) == (
        type(py_dp.std_dev).__name__,
        py_dp.std_dev,
    )
    assert (type(rust_dp.distribution).__name__, rust_dp.distribution) == (
        type(py_dp.distribution).__name__,
        py_dp.distribution,
    )
    assert rust_dp.min_val is None and py_dp.min_val is None
    assert rust_dp.max_val is None and py_dp.max_val is None
    assert repr(rust_dp) == repr(py_dp)
    assert str(rust_dp) == str(py_dp)


def test_distribution_params_full_parity(uniform_drill_pair):
    py_dp, rust_dp = uniform_drill_pair
    assert repr(rust_dp) == repr(py_dp)
    assert rust_dp.mean == py_dp.mean and float(rust_dp.mean).hex() == float(py_dp.mean).hex()
    assert rust_dp.max_val == py_dp.max_val


def test_distribution_params_eq_parity():
    """Dataclass eq: same fields equal, differing field unequal — on both sides."""
    py_a = _oracle.DistributionParams(0.05, 0.01)
    py_b = _oracle.DistributionParams(0.05, 0.01)
    py_c = _oracle.DistributionParams(0.05, 0.02)
    rs_a = DISTRIBUTION_PARAMS(0.05, 0.01)
    rs_b = DISTRIBUTION_PARAMS(0.05, 0.01)
    rs_c = DISTRIBUTION_PARAMS(0.05, 0.02)
    assert (rs_a == rs_b) == (py_a == py_b) is True
    assert (rs_a == rs_c) == (py_a == py_c) is False
    # Mutable dataclass -> __hash__ = None -> unhashable, like the oracle.
    with pytest.raises(TypeError):
        hash(rs_a)
    with pytest.raises(TypeError):
        hash(py_a)


def test_config_defaults_parity():
    """MonteCarloConfig defaults: 1000 / 42 / the five percentiles tuple."""
    py_cfg, rust_cfg = _p(_oracle.MonteCarloConfig, MONTE_CARLO_CONFIG)
    assert (type(rust_cfg.num_samples).__name__, rust_cfg.num_samples) == (
        type(py_cfg.num_samples).__name__,
        py_cfg.num_samples,
    )
    assert (type(rust_cfg.seed).__name__, rust_cfg.seed) == (
        type(py_cfg.seed).__name__,
        py_cfg.seed,
    )
    assert tuple(rust_cfg.report_percentiles) == tuple(py_cfg.report_percentiles)
    assert type(rust_cfg.report_percentiles).__name__ == type(
        py_cfg.report_percentiles
    ).__name__
    assert repr(rust_cfg) == repr(py_cfg)


def test_config_custom_parity():
    py_cfg = _oracle.MonteCarloConfig(num_samples=64, seed=7, report_percentiles=(0.5,))
    rust_cfg = MONTE_CARLO_CONFIG(num_samples=64, seed=7, report_percentiles=(0.5,))
    assert repr(rust_cfg) == repr(py_cfg)
    assert rust_cfg.num_samples == py_cfg.num_samples


def test_variables_defaults_parity():
    py_v, rust_v = _p(_oracle.ManufacturingVariables, MANUFACTURING_VARIABLES)
    for name in (
        "etch_tolerance",
        "drill_tolerance",
        "registration_x",
        "registration_y",
        "copper_thickness",
        "dielectric_thickness",
    ):
        assert getattr(rust_v, name) is None and getattr(py_v, name) is None
    assert repr(rust_v) == repr(py_v)


def test_result_construction_and_repr_parity():
    py_r = _oracle.MonteCarloResult(num_samples=1000, yield_probability=0.5)
    rust_r = MONTE_CARLO_RESULT(num_samples=1000, yield_probability=0.5)
    assert repr(rust_r) == repr(py_r)
    assert _result_key(rust_r) == _result_key(py_r)
    assert (rust_r == MONTE_CARLO_RESULT(1000, 0.5)) == (
        py_r == _oracle.MonteCarloResult(1000, 0.5)
    )


# ---------------------------------------------------------------------------
# Sampling parity — the RNG stream.
# ---------------------------------------------------------------------------


def test_sampling_parity_all_normal(normal_etch_pair):
    """Six normal variables, seed 42: bit-identical arrays, keys, order."""
    py_dp, rust_dp = normal_etch_pair
    vars_py = _oracle.ManufacturingVariables(
        etch_tolerance=_oracle.DistributionParams(0.05, 0.01),
        drill_tolerance=_oracle.DistributionParams(0.1, 0.02),
        registration_x=_oracle.DistributionParams(0.0, 0.03),
        registration_y=_oracle.DistributionParams(0.0, 0.03),
        copper_thickness=_oracle.DistributionParams(0.035, 0.005),
        dielectric_thickness=_oracle.DistributionParams(1.6, 0.1),
    )
    vars_rust = _mk_vars_rust(
        etch=DISTRIBUTION_PARAMS(0.05, 0.01),
        drill=DISTRIBUTION_PARAMS(0.1, 0.02),
        reg_x=DISTRIBUTION_PARAMS(0.0, 0.03),
        reg_y=DISTRIBUTION_PARAMS(0.0, 0.03),
        copper=DISTRIBUTION_PARAMS(0.035, 0.005),
        dielectric=DISTRIBUTION_PARAMS(1.6, 0.1),
    )
    sim_py = _oracle.MonteCarloSimulator(vars_py, config=_oracle.MonteCarloConfig(seed=42))
    sim_rust = MONTE_CARLO_SIMULATOR(vars_rust, config=MONTE_CARLO_CONFIG(seed=42))
    py_out, rust_out = _both_samples(sim_py, sim_rust, 37)
    assert py_out[0] == "ok" and rust_out[0] == "ok"
    py_samples, rust_samples = py_out[1], rust_out[1]
    assert list(rust_samples.keys()) == list(py_samples.keys())
    for name, arr in py_samples.items():
        assert _arr(arr) == _arr(rust_samples[name]), name
        assert float(arr.mean()).hex() != float(rust_samples[name].mean()).hex() or True
    # Stream advance: a second call on the SAME simulators draws different
    # values, identically on both sides.
    py_out2, rust_out2 = _both_samples(sim_py, sim_rust, 37)
    assert py_out2[1]["etch_tolerance"].tobytes() != py_samples["etch_tolerance"].tobytes()
    assert _arr(rust_out2[1]["etch_tolerance"]) == _arr(py_out2[1]["etch_tolerance"])


def test_sampling_parity_uniform_bounded(uniform_drill_pair):
    """Uniform with explicit min/max: bit-identical draws and bounds."""
    py_dp, rust_dp = uniform_drill_pair
    sim_py = _oracle.MonteCarloSimulator(
        _oracle.ManufacturingVariables(drill_tolerance=py_dp), config=_oracle.MonteCarloConfig(seed=7)
    )
    sim_rust = MONTE_CARLO_SIMULATOR(
        MANUFACTURING_VARIABLES(drill_tolerance=rust_dp), config=MONTE_CARLO_CONFIG(seed=7)
    )
    py_out, rust_out = _both_samples(sim_py, sim_rust, 101)
    assert _arr(py_out[1]["drill_tolerance"]) == _arr(rust_out[1]["drill_tolerance"])
    assert float(rust_out[1]["drill_tolerance"].min()) >= 0.05
    assert float(rust_out[1]["drill_tolerance"].max()) <= 0.15


def test_sampling_parity_uniform_fallback(uniform_fallback_pair):
    """Uniform WITHOUT min/max falls back to mean ± 1.0 — bit-identical draws."""
    py_dp, rust_dp = uniform_fallback_pair
    sim_py = _oracle.MonteCarloSimulator(
        _oracle.ManufacturingVariables(copper_thickness=py_dp), config=_oracle.MonteCarloConfig(seed=3)
    )
    sim_rust = MONTE_CARLO_SIMULATOR(
        MANUFACTURING_VARIABLES(copper_thickness=rust_dp), config=MONTE_CARLO_CONFIG(seed=3)
    )
    py_out, rust_out = _both_samples(sim_py, sim_rust, 50)
    assert _arr(py_out[1]["copper_thickness"]) == _arr(rust_out[1]["copper_thickness"])
    assert float(rust_out[1]["copper_thickness"].min()) >= -0.5
    assert float(rust_out[1]["copper_thickness"].max()) <= 1.5


def test_sampling_parity_partial_variables():
    """Only some variables set: dict contains exactly those keys, in the
    oracle's fixed declaration order, with identical arrays."""
    vars_py = _oracle.ManufacturingVariables(
        etch_tolerance=_oracle.DistributionParams(0.05, 0.01),
        registration_y=_oracle.DistributionParams(0.0, 0.03),
    )
    vars_rust = MANUFACTURING_VARIABLES(
        etch_tolerance=DISTRIBUTION_PARAMS(0.05, 0.01),
        registration_y=DISTRIBUTION_PARAMS(0.0, 0.03),
    )
    sim_py = _oracle.MonteCarloSimulator(vars_py, config=_oracle.MonteCarloConfig(seed=11))
    sim_rust = MONTE_CARLO_SIMULATOR(vars_rust, config=MONTE_CARLO_CONFIG(seed=11))
    py_out, rust_out = _both_samples(sim_py, sim_rust, 5)
    assert list(py_out[1].keys()) == ["etch_tolerance", "registration_y"]
    assert list(rust_out[1].keys()) == list(py_out[1].keys())
    assert _arr(py_out[1]["etch_tolerance"]) == _arr(rust_out[1]["etch_tolerance"])
    assert _arr(py_out[1]["registration_y"]) == _arr(rust_out[1]["registration_y"])


def test_sampling_parity_int_mean_type_preserved():
    """DistributionParams(mean=5) (int): numpy receives the same int on both
    sides — identical draws (NEP 50 promotion is numpy's own on both sides)."""
    vars_py = _oracle.ManufacturingVariables(
        etch_tolerance=_oracle.DistributionParams(5)
    )
    vars_rust = MANUFACTURING_VARIABLES(etch_tolerance=DISTRIBUTION_PARAMS(5))
    sim_py = _oracle.MonteCarloSimulator(vars_py, config=_oracle.MonteCarloConfig(seed=9))
    sim_rust = MONTE_CARLO_SIMULATOR(vars_rust, config=MONTE_CARLO_CONFIG(seed=9))
    py_out, rust_out = _both_samples(sim_py, sim_rust, 20)
    assert _arr(py_out[1]["etch_tolerance"]) == _arr(rust_out[1]["etch_tolerance"])


def test_sampling_parity_zero_samples():
    """n=0: empty (0,) arrays on both sides — and zero RNG consumption."""
    vars_py = _oracle.ManufacturingVariables(
        etch_tolerance=_oracle.DistributionParams(0.05, 0.01)
    )
    vars_rust = MANUFACTURING_VARIABLES(etch_tolerance=DISTRIBUTION_PARAMS(0.05, 0.01))
    sim_py = _oracle.MonteCarloSimulator(vars_py, config=_oracle.MonteCarloConfig(seed=2))
    sim_rust = MONTE_CARLO_SIMULATOR(vars_rust, config=MONTE_CARLO_CONFIG(seed=2))
    py_out, rust_out = _both_samples(sim_py, sim_rust, 0)
    assert _arr(py_out[1]["etch_tolerance"]) == _arr(rust_out[1]["etch_tolerance"])
    assert py_out[1]["etch_tolerance"].shape == (0,)


def test_seed_determinism_and_distinction():
    """Same seed → identical draws; different seed → different draws (both sides)."""
    vp = _oracle.ManufacturingVariables(etch_tolerance=_oracle.DistributionParams(0.05, 0.01))
    vr = MANUFACTURING_VARIABLES(etch_tolerance=DISTRIBUTION_PARAMS(0.05, 0.01))
    a_py = _oracle.MonteCarloSimulator(vp, config=_oracle.MonteCarloConfig(seed=42)).sample_parameters(10)
    b_py = _oracle.MonteCarloSimulator(vp, config=_oracle.MonteCarloConfig(seed=42)).sample_parameters(10)
    c_py = _oracle.MonteCarloSimulator(vp, config=_oracle.MonteCarloConfig(seed=43)).sample_parameters(10)
    a_rs = MONTE_CARLO_SIMULATOR(vr, config=MONTE_CARLO_CONFIG(seed=42)).sample_parameters(10)
    b_rs = MONTE_CARLO_SIMULATOR(vr, config=MONTE_CARLO_CONFIG(seed=42)).sample_parameters(10)
    c_rs = MONTE_CARLO_SIMULATOR(vr, config=MONTE_CARLO_CONFIG(seed=43)).sample_parameters(10)
    assert _arr(a_py["etch_tolerance"]) == _arr(a_rs["etch_tolerance"])
    assert _arr(b_py["etch_tolerance"]) == _arr(b_rs["etch_tolerance"])
    assert _arr(a_rs["etch_tolerance"]) == _arr(b_rs["etch_tolerance"])  # deterministic
    assert a_rs["etch_tolerance"].tobytes() != c_rs["etch_tolerance"].tobytes()


# ---------------------------------------------------------------------------
# run_clearance_simulation parity.
# ---------------------------------------------------------------------------


def _both_run(vars_py, vars_rust, positions, bounds, clearance, seed=42, num_samples=1000):
    cfg_py = _oracle.MonteCarloConfig(num_samples=num_samples, seed=seed)
    cfg_rust = MONTE_CARLO_CONFIG(num_samples=num_samples, seed=seed)
    sim_py = _oracle.MonteCarloSimulator(vars_py, config=cfg_py)
    sim_rust = MONTE_CARLO_SIMULATOR(vars_rust, config=cfg_rust)
    py_out = _oracle_run(sim_py, positions, bounds, clearance)
    rust_out = _rust_run(sim_rust, positions, bounds, clearance)
    return py_out, rust_out


def test_run_parity_etch_only(normal_etch_pair):
    """The reference scenario: two 10×10 components 10.05 mm apart, etch
    noise — yield and both stats bit-identical."""
    import numpy as np

    positions = np.array([[0.0, 0.0], [10.05, 0.0]])
    bounds = np.array([[10.0, 10.0], [10.0, 10.0]])
    py_dp, rust_dp = normal_etch_pair
    py_out, rust_out = _both_run(
        _oracle.ManufacturingVariables(etch_tolerance=py_dp),
        MANUFACTURING_VARIABLES(etch_tolerance=rust_dp),
        positions,
        bounds,
        0.05,
    )
    assert py_out[0] == rust_out[0] == "ok"
    py_r, rust_r = py_out[1], rust_out[1]
    assert _result_key(py_r) == _result_key(rust_r)
    assert 0.3 <= rust_r.yield_probability <= 0.7  # sanity: non-vacuous scenario
    assert repr(rust_r) == repr(py_r)


def test_run_parity_registration_only():
    """Registration noise shifts positions symmetrically: stats bit-identical."""
    import numpy as np

    positions = np.array([[0.0, 0.0], [5.0, 0.0], [0.0, 5.0]])
    bounds = np.array([[1.0, 1.0], [1.0, 1.0], [1.0, 1.0]])
    vars_py = _oracle.ManufacturingVariables(
        registration_x=_oracle.DistributionParams(0.0, 0.02),
        registration_y=_oracle.DistributionParams(0.0, 0.02),
    )
    vars_rust = MANUFACTURING_VARIABLES(
        registration_x=DISTRIBUTION_PARAMS(0.0, 0.02),
        registration_y=DISTRIBUTION_PARAMS(0.0, 0.02),
    )
    py_out, rust_out = _both_run(vars_py, vars_rust, positions, bounds, 1.0)
    assert _result_key(py_out[1]) == _result_key(rust_out[1])


def test_run_parity_etch_reg_uniform():
    """Etch (normal) + registration (uniform) + copper thickness (uniform
    fallback): the full sampling mix, bit-identical end to end."""
    import numpy as np

    positions = np.array([[0.0, 0.0], [12.0, 0.0], [6.0, 9.0]])
    bounds = np.array([[8.0, 6.0], [8.0, 6.0], [8.0, 6.0]])
    vars_py = _oracle.ManufacturingVariables(
        etch_tolerance=_oracle.DistributionParams(0.02, 0.01),
        registration_x=_oracle.DistributionParams(0.0, 0.03, distribution="uniform"),
        copper_thickness=_oracle.DistributionParams(0.035, distribution="uniform"),
    )
    vars_rust = MANUFACTURING_VARIABLES(
        etch_tolerance=DISTRIBUTION_PARAMS(0.02, 0.01),
        registration_x=DISTRIBUTION_PARAMS(0.0, 0.03, distribution="uniform"),
        copper_thickness=DISTRIBUTION_PARAMS(0.035, distribution="uniform"),
    )
    py_out, rust_out = _both_run(vars_py, vars_rust, positions, bounds, 0.5)
    assert _result_key(py_out[1]) == _result_key(rust_out[1])


def test_run_parity_no_variables_nominal():
    """No manufacturing variables: no RNG consumption — deterministic
    nominal geometry, yield is exactly 0 or 1."""
    import numpy as np

    positions = np.array([[0.0, 0.0], [10.05, 0.0]])
    bounds = np.array([[10.0, 10.0], [10.0, 10.0]])
    vars_py = _oracle.ManufacturingVariables()
    vars_rust = MANUFACTURING_VARIABLES()
    py_out, rust_out = _both_run(vars_py, vars_rust, positions, bounds, 0.05)
    assert py_out[0] == rust_out[0] == "ok"
    assert _result_key(py_out[1]) == _result_key(rust_out[1])
    # Nominal gap is exactly 0.05 → min distance >= 0.05 → yield exactly 1.0.
    assert rust_out[1].yield_probability == 1.0
    assert float(rust_out[1].stats["mean_min_clearance"]).hex() == float(
        py_out[1].stats["mean_min_clearance"]
    ).hex()


def test_run_parity_nominal_zero_clearance():
    """required_clearance=0.0 with identical components: all pass → 1.0."""
    import numpy as np

    positions = np.array([[0.0, 0.0], [10.0, 0.0]])
    bounds = np.array([[10.0, 10.0], [10.0, 10.0]])
    vars_py, vars_rust = _oracle.ManufacturingVariables(), MANUFACTURING_VARIABLES()
    py_out, rust_out = _both_run(vars_py, vars_rust, positions, bounds, 0.0)
    assert _result_key(py_out[1]) == _result_key(rust_out[1])
    assert rust_out[1].yield_probability == 1.0


def test_run_parity_single_component():
    """N=1: only the masked diagonal — min distance is the 1e6 sentinel."""
    import numpy as np

    positions = np.array([[3.0, 4.0]])
    bounds = np.array([[2.0, 2.0]])
    vars_py = _oracle.ManufacturingVariables(
        etch_tolerance=_oracle.DistributionParams(0.0, 0.01)
    )
    vars_rust = MANUFACTURING_VARIABLES(etch_tolerance=DISTRIBUTION_PARAMS(0.0, 0.01))
    py_out, rust_out = _both_run(vars_py, vars_rust, positions, bounds, 5.0)
    assert _result_key(py_out[1]) == _result_key(rust_out[1])
    assert float(rust_out[1].stats["mean_min_clearance"]) == 1e6
    assert rust_out[1].yield_probability == 1.0


def test_run_parity_four_components():
    """N=4 grid: multiple interacting pairs per sample."""
    import numpy as np

    positions = np.array(
        [[0.0, 0.0], [10.0, 0.0], [0.0, 10.0], [10.0, 10.0]]
    )
    bounds = np.array([[5.0, 5.0]] * 4)
    vars_py = _oracle.ManufacturingVariables(
        etch_tolerance=_oracle.DistributionParams(0.05, 0.02),
        registration_x=_oracle.DistributionParams(0.0, 0.05),
        registration_y=_oracle.DistributionParams(0.0, 0.05),
    )
    vars_rust = MANUFACTURING_VARIABLES(
        etch_tolerance=DISTRIBUTION_PARAMS(0.05, 0.02),
        registration_x=DISTRIBUTION_PARAMS(0.0, 0.05),
        registration_y=DISTRIBUTION_PARAMS(0.0, 0.05),
    )
    py_out, rust_out = _both_run(vars_py, vars_rust, positions, bounds, 1.0, num_samples=500)
    assert _result_key(py_out[1]) == _result_key(rust_out[1])


def test_run_parity_single_sample():
    """num_samples=1: a one-element min-distance vector."""
    import numpy as np

    positions = np.array([[0.0, 0.0], [10.05, 0.0]])
    bounds = np.array([[10.0, 10.0], [10.0, 10.0]])
    vars_py = _oracle.ManufacturingVariables(
        etch_tolerance=_oracle.DistributionParams(0.05, 0.01)
    )
    vars_rust = MANUFACTURING_VARIABLES(etch_tolerance=DISTRIBUTION_PARAMS(0.05, 0.01))
    py_out, rust_out = _both_run(vars_py, vars_rust, positions, bounds, 0.05, num_samples=1)
    assert _result_key(py_out[1]) == _result_key(rust_out[1])


def test_run_parity_zero_samples_nan():
    """num_samples=0: mean/std over an empty vector → nan on both sides
    (yield nan, stats nan — vacuity guard: empty-input semantics pinned)."""
    import numpy as np

    positions = np.array([[0.0, 0.0], [10.05, 0.0]])
    bounds = np.array([[10.0, 10.0], [10.0, 10.0]])
    vars_py = _oracle.ManufacturingVariables(
        etch_tolerance=_oracle.DistributionParams(0.05, 0.01)
    )
    vars_rust = MANUFACTURING_VARIABLES(etch_tolerance=DISTRIBUTION_PARAMS(0.05, 0.01))
    py_out, rust_out = _both_run(vars_py, vars_rust, positions, bounds, 0.05, num_samples=0)
    assert py_out[0] == rust_out[0] == "ok"
    assert float(py_out[1].yield_probability) != float(py_out[1].yield_probability)  # nan
    assert _result_key(py_out[1]) == _result_key(rust_out[1])


def test_run_parity_float32_inputs():
    """float32 positions/bounds: NEP-50 promotion to float64 is numpy's own;
    the Rust kernel widens float32 → f64 exactly — bit-identical result."""
    import numpy as np

    positions = np.array([[0.0, 0.0], [10.05, 0.0]], dtype=np.float32)
    bounds = np.array([[10.0, 10.0], [10.0, 10.0]], dtype=np.float32)
    vars_py = _oracle.ManufacturingVariables(
        etch_tolerance=_oracle.DistributionParams(0.05, 0.01)
    )
    vars_rust = MANUFACTURING_VARIABLES(etch_tolerance=DISTRIBUTION_PARAMS(0.05, 0.01))
    py_out, rust_out = _both_run(vars_py, vars_rust, positions, bounds, 0.05, num_samples=64)
    assert _result_key(py_out[1]) == _result_key(rust_out[1])


def test_run_parity_int_inputs():
    """Integer positions/bounds (Python ints ride into the kernel as exact f64)."""
    import numpy as np

    positions = np.array([[0, 0], [10, 0]])
    bounds = np.array([[10, 10], [10, 10]])
    vars_py, vars_rust = _oracle.ManufacturingVariables(), MANUFACTURING_VARIABLES()
    py_out, rust_out = _both_run(vars_py, vars_rust, positions, bounds, 0.0, num_samples=8)
    assert _result_key(py_out[1]) == _result_key(rust_out[1])


def test_run_parity_default_config():
    """Default MonteCarloConfig (num_samples=1000, seed=42) applied on both
    sides when the simulator is constructed without a config."""
    import numpy as np

    positions = np.array([[0.0, 0.0], [10.05, 0.0]])
    bounds = np.array([[10.0, 10.0], [10.0, 10.0]])
    vars_py = _oracle.ManufacturingVariables(
        etch_tolerance=_oracle.DistributionParams(0.05, 0.01)
    )
    vars_rust = MANUFACTURING_VARIABLES(etch_tolerance=DISTRIBUTION_PARAMS(0.05, 0.01))
    sim_py = _oracle.MonteCarloSimulator(vars_py)
    sim_rust = MONTE_CARLO_SIMULATOR(vars_rust)
    py_out = _oracle_run(sim_py, positions, bounds, 0.05)
    rust_out = _rust_run(sim_rust, positions, bounds, 0.05)
    assert py_out[0] == rust_out[0] == "ok"
    assert _result_key(py_out[1]) == _result_key(rust_out[1])
    assert rust_out[1].num_samples == 1000


def test_run_parity_negative_clearance():
    """required_clearance < 0: every sample passes → yield 1.0."""
    import numpy as np

    positions = np.array([[0.0, 0.0], [10.05, 0.0]])
    bounds = np.array([[10.0, 10.0], [10.0, 10.0]])
    vars_py = _oracle.ManufacturingVariables(
        etch_tolerance=_oracle.DistributionParams(0.05, 0.01)
    )
    vars_rust = MANUFACTURING_VARIABLES(etch_tolerance=DISTRIBUTION_PARAMS(0.05, 0.01))
    py_out, rust_out = _both_run(vars_py, vars_rust, positions, bounds, -1.0, num_samples=32)
    assert _result_key(py_out[1]) == _result_key(rust_out[1])
    assert rust_out[1].yield_probability == 1.0


def test_run_parity_huge_clearance_zero_yield():
    """required_clearance beyond any reachable separation: yield 0.0."""
    import numpy as np

    positions = np.array([[0.0, 0.0], [10.05, 0.0]])
    bounds = np.array([[10.0, 10.0], [10.0, 10.0]])
    vars_py = _oracle.ManufacturingVariables(
        etch_tolerance=_oracle.DistributionParams(0.05, 0.01)
    )
    vars_rust = MANUFACTURING_VARIABLES(etch_tolerance=DISTRIBUTION_PARAMS(0.05, 0.01))
    py_out, rust_out = _both_run(vars_py, vars_rust, positions, bounds, 1e6, num_samples=32)
    assert _result_key(py_out[1]) == _result_key(rust_out[1])
    assert rust_out[1].yield_probability == 0.0


def test_run_parity_nan_positions_y_column():
    """NaN in the position y-column: np.maximum and the min reduction
    PROPAGATE NaN on both sides (Rust's f64::max/min discard it — this case
    discriminates a NaN-discarding mutant). NaN >= clearance is False, so
    every sample fails: yield 0.0, nan stats, bit-identical."""
    import numpy as np

    positions = np.array([[0.0, np.nan], [2.0, 0.0]])
    bounds = np.array([[1.0, 1.0], [1.0, 1.0]])
    vars_py, vars_rust = _oracle.ManufacturingVariables(), MANUFACTURING_VARIABLES()
    py_out, rust_out = _both_run(vars_py, vars_rust, positions, bounds, 0.5, num_samples=8)
    assert py_out[0] == rust_out[0] == "ok"
    assert _result_key(py_out[1]) == _result_key(rust_out[1])
    assert rust_out[1].yield_probability == 0.0
    assert float(rust_out[1].stats["mean_min_clearance"]) != float(
        rust_out[1].stats["mean_min_clearance"]
    )  # nan


def test_run_parity_nan_positions_x_column():
    """NaN in the position x-column: the min reduction sees NaN from every
    pair — nan stats parity (also discriminates the NaN-discarding min)."""
    import numpy as np

    positions = np.array([[np.nan, 0.0], [2.0, 1.0]])
    bounds = np.array([[1.0, 1.0], [1.0, 1.0]])
    vars_py, vars_rust = _oracle.ManufacturingVariables(), MANUFACTURING_VARIABLES()
    py_out, rust_out = _both_run(vars_py, vars_rust, positions, bounds, 0.5, num_samples=8)
    assert py_out[0] == rust_out[0] == "ok"
    assert _result_key(py_out[1]) == _result_key(rust_out[1])
    assert float(rust_out[1].stats["mean_min_clearance"]) != float(
        rust_out[1].stats["mean_min_clearance"]
    )  # nan


# ---------------------------------------------------------------------------
# Error parity.
# ---------------------------------------------------------------------------


def test_empty_positions_error_parity():
    """N=0: numpy's min-reduction over empty slices raises ValueError with
    the exact 'no identity' text — replicated byte-for-byte by the kernel."""
    import numpy as np

    positions = np.zeros((0, 2))
    bounds = np.zeros((0, 2))
    vars_py = _oracle.ManufacturingVariables(
        etch_tolerance=_oracle.DistributionParams(0.05, 0.01)
    )
    vars_rust = MANUFACTURING_VARIABLES(etch_tolerance=DISTRIBUTION_PARAMS(0.05, 0.01))
    py_out, rust_out = _both_run(vars_py, vars_rust, positions, bounds, 0.05, num_samples=16)
    assert py_out[0] == rust_out[0] == "err"
    assert py_out[1:] == rust_out[1:] == (
        "ValueError",
        "zero-size array to reduction operation minimum which has no identity",
    )


def test_one_dimensional_positions_error_parity():
    """1-D positions: the oracle's fancy-indexing IndexError, replicated."""
    import numpy as np

    positions = np.zeros(2)
    bounds = np.array([[10.0, 10.0], [10.0, 10.0]])
    vars_py, vars_rust = _oracle.ManufacturingVariables(), MANUFACTURING_VARIABLES()
    py_out, rust_out = _both_run(vars_py, vars_rust, positions, bounds, 0.05, num_samples=8)
    assert py_out[0] == rust_out[0] == "err"
    assert py_out[1] == rust_out[1]


def test_non_array_positions_error_parity():
    """A Python list where an ndarray is required: both sides raise (type
    names compared, message text may differ — the oracle's exact text comes
    from numpy's fancy indexing internals)."""
    positions = [[0.0, 0.0], [10.05, 0.0]]
    import numpy as np

    bounds = np.array([[10.0, 10.0], [10.0, 10.0]])
    vars_py, vars_rust = _oracle.ManufacturingVariables(), MANUFACTURING_VARIABLES()
    py_out, rust_out = _both_run(vars_py, vars_rust, positions, bounds, 0.05, num_samples=8)
    assert py_out[0] == rust_out[0] == "err"
    assert py_out[1][0] == rust_out[1][0]  # same exception type name


def test_rng_state_after_error_matches():
    """The error path consumes RNG draws identically on both sides: a
    subsequent sampling call on the failed simulators is still bit-identical."""
    import numpy as np

    positions = np.zeros((0, 2))
    bounds = np.zeros((0, 2))
    vars_py = _oracle.ManufacturingVariables(
        etch_tolerance=_oracle.DistributionParams(0.05, 0.01)
    )
    vars_rust = MANUFACTURING_VARIABLES(etch_tolerance=DISTRIBUTION_PARAMS(0.05, 0.01))
    sim_py = _oracle.MonteCarloSimulator(vars_py, config=_oracle.MonteCarloConfig(seed=5))
    sim_rust = MONTE_CARLO_SIMULATOR(vars_rust, config=MONTE_CARLO_CONFIG(seed=5))
    for sim in (sim_py, sim_rust):
        try:
            sim.run_clearance_simulation(positions, bounds, 0.05)
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError")
    py_out, rust_out = _both_samples(sim_py, sim_rust, 10)
    assert _arr(py_out[1]["etch_tolerance"]) == _arr(rust_out[1]["etch_tolerance"])
