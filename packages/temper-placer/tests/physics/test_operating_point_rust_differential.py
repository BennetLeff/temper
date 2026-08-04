"""R1a differential: temper-thermal's operating-point kernels vs the
pinned pure-Python oracle (Wave 4, Phase 4).

The pre-migration arithmetic is pinned **verbatim** in
`_operating_point_py_oracle.py`.  Floats are compared through
`float.hex()` (never a tolerance) and every leaf carries its concrete
type, so an int/float or f32/f64 drift cannot hide behind numeric
equality (`_leafcmp`).

Only the numeric core moved: the `OperatingPointConfig` dataclass and
its validation, the `Violation`/`GateResult` construction, the SPICE
cross-check and the `_coupling_l_eff_fn` test hook all stay in Python,
and `P_device` keeps delegating to `physics/device_power.py` (issue
#140 — one power-source formula).  The differential therefore pins the
kernels *and* the assembled `Violation` payloads.

Catalog classes exercised here: **B5** (CPython builtin `max`/`min`
first-argument NaN semantics at the endpoint envelope), **B7** (the
`(R_jc + R_cs) + R_sa`, `T_amb + P*R`, `V_BR * derate`,
`num / di_dt` and `worst * (1 +/- 1e-12)` chains), **B8** (denormal
`L_eff`).
"""

from __future__ import annotations

import math
import random

import pytest
import temper_thermal as _tt

from temper_placer.physics import operating_point as mod
from tests.physics._leafcmp import assert_same
from tests.physics._operating_point_py_oracle import (
    _INTERIOR_GRID_POINTS,
    _l_eff,
    _oracle_compute_extremes,
    _oracle_interior_records,
)

BASE_CONFIG = {
    "V_bus": 325.0,
    "V_BR": 1200.0,
    "I_load_rms": 16.0,
    "L_coil": 100e-6,
    "L_leakage": 10e-6,
    "f_sw": 25000.0,
}


def _cfg(**overrides):
    return mod._validate_config({**BASE_CONFIG, **overrides})


def _random_cfg(rng):
    return _cfg(
        V_bus=rng.choice([325.0, 12.0, rng.uniform(1.0, 800.0)]),
        V_BR=rng.choice([1200.0, 600.0, rng.uniform(1.0, 1700.0)]),
        I_load_rms=rng.choice([16.0, rng.uniform(0.001, 100.0)]),
        L_coil=rng.choice([100e-6, rng.uniform(1e-9, 1e-2)]),
        L_leakage=rng.choice([10e-6, rng.uniform(1e-9, 1e-2)]),
        f_sw=rng.choice([25000.0, rng.uniform(100.0, 200000.0)]),
        T_amb=rng.choice([40.0, rng.uniform(-40.0, 85.0)]),
        T_j_max=rng.choice([150.0, rng.uniform(80.0, 200.0)]),
        R_theta_jc=rng.choice([0.6, rng.uniform(0.05, 3.0)]),
        R_theta_cs=rng.choice([0.25, rng.uniform(0.01, 2.0)]),
        R_theta_sa=rng.choice([1.0, rng.uniform(0.1, 10.0)]),
        derate=rng.choice([0.80, rng.uniform(0.05, 1.0)]),
        min_feasible_L_loop=rng.choice([5e-9, rng.uniform(1e-12, 1e-6)]),
    )


def _interior_samples(cfg, fn=None):
    fn = fn or (lambda k: _l_eff(cfg, k))
    return [(k, fn(k)) for k in _tt.operating_point_interior_k_grid_py(_INTERIOR_GRID_POINTS)]


# ---------------------------------------------------------------------------
# Direct Rust pins
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(12))
def test_direct_l_eff_bit_exact(seed):
    """`L_coil * (1 - k) + L_leakage * k`, operation order preserved."""
    rng = random.Random(seed)
    for _ in range(60):
        cfg = _random_cfg(rng)
        k = rng.choice([0.0, 1.0, 0.5, rng.uniform(0.0, 1.0), rng.uniform(-5.0, 5.0)])
        assert_same(
            _tt.operating_point_l_eff_py(cfg.L_coil, cfg.L_leakage, k),
            _l_eff(cfg, k),
            f"l_eff(L_coil={cfg.L_coil!r}, L_leak={cfg.L_leakage!r}, k={k!r})",
        )


def test_direct_l_eff_endpoints_are_exact():
    """k=0 and k=1 must reproduce the endpoints *bit-exactly*, not to
    within an epsilon -- the whole bounding argument rests on it."""
    cfg = _cfg()
    assert_same(_tt.operating_point_l_eff_py(cfg.L_coil, cfg.L_leakage, 0.0), cfg.L_coil)
    assert_same(_tt.operating_point_l_eff_py(cfg.L_coil, cfg.L_leakage, 1.0), cfg.L_leakage)


def test_direct_interior_k_grid_bit_exact():
    """`k = i / (N - 1)` for the interior indices only."""
    got = _tt.operating_point_interior_k_grid_py(_INTERIOR_GRID_POINTS)
    want = [i / (_INTERIOR_GRID_POINTS - 1) for i in range(1, _INTERIOR_GRID_POINTS - 1)]
    assert_same(got, want, "interior_k_grid")
    assert_same(_tt.operating_point_interior_k_grid_py(1), [])
    assert_same(_tt.operating_point_interior_k_grid_py(0), [])


@pytest.mark.parametrize("seed", range(14))
def test_direct_extremes_bit_exact(seed):
    """The thermal chain and both ceiling checks, bit-for-bit."""
    rng = random.Random(100 + seed)
    for _ in range(30):
        cfg = _random_cfg(rng)
        p_device = rng.choice([0.0, 1e-300, rng.uniform(0.0, 500.0)])
        (t_j, r_th, di0, ll0, f0, di1, ll1, f1) = _tt.operating_point_extremes_py(
            p_device, cfg.T_amb, cfg.R_theta_jc, cfg.R_theta_cs, cfg.R_theta_sa,
            cfg.V_BR, cfg.derate, cfg.V_bus, cfg.T_j_max, cfg.min_feasible_L_loop,
            cfg.L_coil, cfg.L_leakage,
        )
        k0, k1 = _oracle_compute_extremes(cfg, p_device)
        assert_same(
            (t_j, r_th, di0, ll0, f0, di1, ll1, f1),
            (
                k0.T_j,
                cfg.R_theta_jc + cfg.R_theta_cs + cfg.R_theta_sa,
                k0.di_dt, k0.L_loop_max, k0.feasible,
                k1.di_dt, k1.L_loop_max, k1.feasible,
            ),
            f"extremes(P={p_device!r}, V_bus={cfg.V_bus!r})",
        )


def test_direct_extremes_denormal_power_is_not_flushed():
    """B8: a denormal `P_device` must survive `T_amb + P * R_th` on both
    sides -- with T_amb = 0.0 the sum IS the denormal."""
    cfg = _cfg(T_amb=0.0, R_theta_jc=1.0, R_theta_cs=0.0, R_theta_sa=0.0)
    tiny = 5e-320
    got = _tt.operating_point_extremes_py(
        tiny, cfg.T_amb, cfg.R_theta_jc, cfg.R_theta_cs, cfg.R_theta_sa,
        cfg.V_BR, cfg.derate, cfg.V_bus, cfg.T_j_max, cfg.min_feasible_L_loop,
        cfg.L_coil, cfg.L_leakage,
    )
    k0, _ = _oracle_compute_extremes(cfg, tiny)
    assert_same(got[0], k0.T_j, "denormal T_j")
    assert 0.0 < k0.T_j < 1e-300, "expected a denormal T_j, not 0.0"


def test_direct_extremes_zero_headroom_gives_exactly_zero_ceiling():
    """`V_BR * derate <= V_bus` makes `num <= 0`, and `L_loop_max` is the
    literal 0.0 -- a branch, not a limit."""
    cfg = _cfg(V_bus=1000.0, V_BR=1000.0, derate=1.0)
    got = _tt.operating_point_extremes_py(
        10.0, cfg.T_amb, cfg.R_theta_jc, cfg.R_theta_cs, cfg.R_theta_sa,
        cfg.V_BR, cfg.derate, cfg.V_bus, cfg.T_j_max, cfg.min_feasible_L_loop,
        cfg.L_coil, cfg.L_leakage,
    )
    k0, k1 = _oracle_compute_extremes(cfg, 10.0)
    assert_same((got[3], got[6]), (k0.L_loop_max, k1.L_loop_max), "zero-headroom ceiling")
    assert float(k0.L_loop_max).hex() == 0.0.hex()


@pytest.mark.parametrize("seed", range(14))
def test_direct_interior_scan_bit_exact(seed):
    """The endpoint envelope and every interior verdict."""
    rng = random.Random(200 + seed)
    for _ in range(25):
        cfg = _random_cfg(rng)
        samples = _interior_samples(cfg)
        got = _tt.operating_point_interior_scan_py(
            cfg.V_bus, cfg.V_BR, cfg.derate, cfg.min_feasible_L_loop,
            _l_eff(cfg, 0.0), _l_eff(cfg, 1.0), samples,
        )
        want = _oracle_interior_records(cfg)
        assert_same(got, want, f"interior_scan(V_bus={cfg.V_bus!r})")


def test_direct_interior_scan_non_positive_endpoint_is_silent():
    """`L_eff(0) <= 0` or `L_eff(1) <= 0` returns no violations at all."""
    cfg = _cfg()
    for l0, l1 in [(0.0, 1e-5), (1e-5, 0.0), (-1.0, 1e-5), (0.0, 0.0)]:
        got = _tt.operating_point_interior_scan_py(
            cfg.V_bus, cfg.V_BR, cfg.derate, cfg.min_feasible_L_loop,
            l0, l1, [(0.5, 1e-5)],
        )
        assert got[0] is False and got[5] == []


def test_direct_interior_scan_nan_endpoint_keeps_the_first_argument():
    """B5: `max(NaN, x)` is NaN and `min(NaN, x)` is NaN in CPython
    (first argument wins).  `f64::max`/`f64::min` would have discarded
    the NaN and produced a *finite* envelope -- silently widening the
    bound the gate enforces."""
    cfg = _cfg()
    nan = float("nan")
    # A NaN L_eff(0) makes di_dt_k0 NaN; `NaN <= 0` is False, so the scan
    # still runs and the envelope inherits the NaN through the builtins.
    got = _tt.operating_point_interior_scan_py(
        cfg.V_bus, cfg.V_BR, cfg.derate, cfg.min_feasible_L_loop,
        nan, cfg.L_leakage, [(0.5, 5e-5)],
    )
    want_worst_di_dt = max(cfg.V_bus / nan, cfg.V_bus / cfg.L_leakage)
    assert math.isnan(want_worst_di_dt), "the oracle envelope must be NaN here"
    assert math.isnan(got[1]), f"Rust envelope discarded the NaN: {got[1]!r}"


# ---------------------------------------------------------------------------
# Module-level pins (full delegation path)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(14))
def test_module_compute_extremes_bit_exact(seed):
    """`compute_extremes` through the delegating module, every field."""
    rng = random.Random(300 + seed)
    for _ in range(20):
        cfg = _random_cfg(rng)
        k0, k1 = mod.compute_extremes(cfg)
        o0, o1 = _oracle_compute_extremes(cfg, k0.P_device)
        for got, want, label in ((k0, o0, "k0"), (k1, o1, "k1")):
            assert_same(
                (got.label, got.coupling, got.di_dt, got.P_device, got.T_j,
                 got.L_loop_max, got.feasible),
                (want.label, want.coupling, want.di_dt, want.P_device, want.T_j,
                 want.L_loop_max, want.feasible),
                f"compute_extremes {label} (V_bus={cfg.V_bus!r})",
            )


@pytest.mark.parametrize("seed", range(12))
def test_module_interior_check_violation_payloads_bit_exact(seed):
    """The assembled `Violation` objects: count, severity, threshold and
    every float in `context` must match the oracle's arithmetic."""
    rng = random.Random(400 + seed)
    for _ in range(20):
        cfg = _random_cfg(rng)
        violations = mod._interior_bounding_soundness_check(cfg)
        (_, worst_di, worst_ll, _, _, records) = _oracle_interior_records(cfg)
        expected = []
        for k, di_dt, l_loop, breach, worse_di, worse_ll in records:
            if breach:
                expected.append(("min_feasible", k, di_dt, l_loop))
            if worse_di:
                expected.append(("di_dt", k, di_dt, None))
            if worse_ll:
                expected.append(("l_loop", k, l_loop, None))
        assert len(violations) == len(expected), (
            f"violation count {len(violations)} != oracle {len(expected)}"
        )
        for v, (kind, k, a, b) in zip(violations, expected):
            assert_same(v.context["coupling"], k, f"{kind} coupling")
            if kind == "min_feasible":
                assert_same(v.context["di_dt_A_per_s"], a, "min_feasible di_dt")
                assert_same(v.context["L_loop_max_H"], b, "min_feasible L_loop_max")
                assert_same(v.context["endpoint_worst_di_dt"], worst_di, "envelope di_dt")
                assert_same(
                    v.context["endpoint_worst_L_loop_max"], worst_ll, "envelope L_loop"
                )
            elif kind == "di_dt":
                assert_same(v.context["di_dt_A_per_s"], a, "di_dt")
                assert_same(v.context["endpoint_worst_di_dt"], worst_di, "envelope di_dt")
            else:
                assert_same(v.context["L_loop_max_H"], a, "L_loop_max")
                assert_same(
                    v.context["endpoint_worst_L_loop_max"], worst_ll, "envelope L_loop"
                )


def test_module_interior_check_with_injected_non_monotone_model():
    """The `_coupling_l_eff_fn` test hook must still reach the kernel, so
    a non-monotone model produces the same violations on both sides."""
    cfg = _cfg()

    def dip(k):
        return _l_eff(cfg, k) - 200e-6 * k * (1.0 - k)

    violations = mod._interior_bounding_soundness_check(cfg, coupling_l_eff_fn=dip)
    (_, _, _, _, _, records) = _oracle_interior_records(cfg, coupling_l_eff_fn=dip)
    n_expected = sum(int(r[3]) + int(r[4]) + int(r[5]) for r in records)
    assert n_expected > 0, "the injected model must actually break the bound"
    assert len(violations) == n_expected
    for v in violations:
        assert "non-monotone" in v.description


def test_module_interior_check_never_reports_an_envelope_breach():
    """The proven-monotone `_l_eff` must never trip the *bounding*
    predicates.

    Note what this does NOT claim: the safeguard's first predicate
    (`L_loop_max < min_feasible_L_loop`) is a genuine ceiling check that
    fires for configs with no bus headroom (`V_BR * derate <= V_bus`
    makes `L_loop_max` exactly 0.0 everywhere), and the oracle agrees.
    The soundness claim is only about the two envelope predicates.
    """
    breached = 0
    for seed in range(80):
        cfg = _random_cfg(random.Random(500 + seed))
        (_, _, _, _, _, records) = _oracle_interior_records(cfg)
        for k, _di, _ll, breach, worse_di, worse_ll in records:
            assert not worse_di, f"di/dt envelope broken at k={k} (seed {seed})"
            assert not worse_ll, f"L_loop envelope broken at k={k} (seed {seed})"
            breached += int(breach)
        # With headroom AND a satisfiable floor the safeguard is silent.
        if cfg.V_BR * cfg.derate > cfg.V_bus:
            headroom_only = mod._interior_bounding_soundness_check(
                mod._validate_config(
                    {**BASE_CONFIG, "V_bus": cfg.V_bus, "V_BR": cfg.V_BR,
                     "L_coil": cfg.L_coil, "L_leakage": cfg.L_leakage,
                     "derate": cfg.derate, "min_feasible_L_loop": 0.0}
                )
            )
            assert headroom_only == [], headroom_only
    assert breached > 0, (
        "no config exercised the min_feasible ceiling branch -- widen the sweep"
    )


# ---------------------------------------------------------------------------
# R1h / R24 — BMC-exhaustive validation on small N
# ---------------------------------------------------------------------------


def test_bmc_exhaustive_small_n_operating_point():
    """**BMC-exhaustive (R24.2).** Enumerate the full cross product of a
    small config lattice -- 3 buses x 3 breakdowns x 3 coil inductances
    x 3 leakage inductances x 2 derates x 2 thermal chains = 324
    configurations -- and check every reported quantity against the
    oracle bit-for-bit.  No sampling, no tolerance.
    """
    checked = 0
    for v_bus in (12.0, 325.0, 600.0):
        for v_br in (100.0, 600.0, 1200.0):
            for l_coil in (1e-9, 10e-6, 1e-3):
                for l_leak in (1e-9, 10e-6, 1e-3):
                    for derate in (0.5, 0.8):
                        for chain in ((0.6, 0.25, 1.0), (0.1, 0.1, 0.1)):
                            cfg = _cfg(
                                V_bus=v_bus, V_BR=v_br, L_coil=l_coil, L_leakage=l_leak,
                                derate=derate, R_theta_jc=chain[0],
                                R_theta_cs=chain[1], R_theta_sa=chain[2],
                            )
                            k0, k1 = mod.compute_extremes(cfg)
                            o0, o1 = _oracle_compute_extremes(cfg, k0.P_device)
                            assert_same(
                                (k0.di_dt, k0.L_loop_max, k0.T_j, k0.feasible,
                                 k1.di_dt, k1.L_loop_max, k1.feasible),
                                (o0.di_dt, o0.L_loop_max, o0.T_j, o0.feasible,
                                 o1.di_dt, o1.L_loop_max, o1.feasible),
                                f"BMC[{v_bus},{v_br},{l_coil},{l_leak},{derate},{chain}]",
                            )
                            got = _tt.operating_point_interior_scan_py(
                                cfg.V_bus, cfg.V_BR, cfg.derate, cfg.min_feasible_L_loop,
                                _l_eff(cfg, 0.0), _l_eff(cfg, 1.0), _interior_samples(cfg),
                            )
                            assert_same(got, _oracle_interior_records(cfg), "BMC scan")
                            checked += 1
    assert checked == 3 * 3 * 3 * 3 * 2 * 2, f"BMC sweep was truncated at {checked}"


def test_bmc_endpoint_bounding_is_exhaustively_sound():
    """**R24.1 soundness, exhaustively validated on small N.** For the
    production `L_eff`, the endpoint pair is a conservative bound on the
    whole coupling interval: sweep k at 1/512 resolution across the same
    lattice and assert no interior point beats the envelope."""
    checked = 0
    for l_coil in (1e-9, 10e-6, 1e-3):
        for l_leak in (1e-9, 10e-6, 1e-3):
            for v_bus in (12.0, 325.0):
                cfg = _cfg(L_coil=l_coil, L_leakage=l_leak, V_bus=v_bus)
                dense = [(i / 512.0, _l_eff(cfg, i / 512.0)) for i in range(1, 512)]
                got = _tt.operating_point_interior_scan_py(
                    cfg.V_bus, cfg.V_BR, cfg.derate, cfg.min_feasible_L_loop,
                    _l_eff(cfg, 0.0), _l_eff(cfg, 1.0), dense,
                )
                for k, _di, _ll, _breach, worse_di, worse_ll in got[5]:
                    assert not worse_di, f"envelope broken at k={k} ({l_coil}, {l_leak})"
                    assert not worse_ll, f"L_loop envelope broken at k={k}"
                checked += len(got[5])
    assert checked > 5000, f"soundness sweep was vacuous: {checked} samples"


def test_bmc_soundness_property_is_fail_capable():
    """R4: the soundness sweep above must be able to FAIL.  A quadratic
    dip below both endpoints is a plausible non-monotone coupling model,
    not a strawman -- and it must trip the envelope check."""
    cfg = _cfg()
    dense = [
        (i / 512.0, _l_eff(cfg, i / 512.0) - 200e-6 * (i / 512.0) * (1.0 - i / 512.0))
        for i in range(1, 512)
    ]
    got = _tt.operating_point_interior_scan_py(
        cfg.V_bus, cfg.V_BR, cfg.derate, cfg.min_feasible_L_loop,
        _l_eff(cfg, 0.0), _l_eff(cfg, 1.0), dense,
    )
    assert any(r[4] for r in got[5]), "non-monotone model went undetected"


# ---------------------------------------------------------------------------
# R1h / R24 — post-solve audit
# ---------------------------------------------------------------------------


def test_audit_is_clean_for_the_production_gate():
    """**R24.3 post-solve audit.** Recompute every reported ceiling from
    the raw configuration and confirm the gate's own numbers survive."""
    for seed in range(30):
        cfg = _random_cfg(random.Random(600 + seed))
        k0, k1 = mod.compute_extremes(cfg)
        findings = mod.audit_operating_point(cfg, k0, k1)
        assert findings == [], f"audit found {findings} on a clean gate (seed {seed})"


def test_audit_catches_a_tampered_ceiling():
    """R4 fail-capable: a report whose `L_loop_max` was widened (the
    plausible "loosen the bound" bug class) must be caught."""
    cfg = _cfg()
    k0, k1 = mod.compute_extremes(cfg)
    tampered = type(k0)(
        label=k0.label, coupling=k0.coupling, di_dt=k0.di_dt, P_device=k0.P_device,
        T_j=k0.T_j, L_loop_max=k0.L_loop_max * 2.0, feasible=k0.feasible,
    )
    findings = mod.audit_operating_point(cfg, tampered, k1)
    assert "LoopInductanceCeilingMismatch" in findings, findings

    hotter = type(k0)(
        label=k0.label, coupling=k0.coupling, di_dt=k0.di_dt, P_device=k0.P_device,
        T_j=k0.T_j - 10.0, L_loop_max=k0.L_loop_max, feasible=k0.feasible,
    )
    findings = mod.audit_operating_point(cfg, hotter, k1)
    assert "JunctionTemperatureMismatch" in findings, findings


def test_audit_catches_an_unsound_coupling_model():
    """The audit's interior sweep is the standing guard against a future
    non-monotone `L_eff`; prove it fires."""
    cfg = _cfg()
    k0, k1 = mod.compute_extremes(cfg)

    def dip(k):
        return _l_eff(cfg, k) - 200e-6 * k * (1.0 - k)

    findings = mod.audit_operating_point(cfg, k0, k1, coupling_l_eff_fn=dip, n_samples=257)
    assert "InteriorSlewRateExceedsEnvelope" in findings, findings
