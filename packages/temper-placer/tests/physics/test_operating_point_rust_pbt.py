"""Property-based + metamorphic battery for the Rust operating-point
kernels (Wave 4 Phase 4, gates G4 and G5).

Same structure as the thermal-potential battery: properties P1..P6 are
standalone predicates over kernel callables so a mutant can be injected,
every property has a `test_pN_fails_for_<mutant>` vacuity guard, and the
metamorphic relations MR1..MR4 each state their exactness claim.
"""

from __future__ import annotations

import math

import pytest
import temper_thermal as _tt
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.physics import operating_point as mod

pytestmark = pytest.mark.property

BASE = {
    "V_bus": 325.0,
    "V_BR": 1200.0,
    "I_load_rms": 16.0,
    "L_coil": 100e-6,
    "L_leakage": 10e-6,
    "f_sw": 25000.0,
}


def _cfg(**overrides):
    return mod._validate_config({**BASE, **overrides})


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

inductances = st.floats(1e-9, 1e-2, allow_nan=False, allow_infinity=False)
voltages = st.floats(1.0, 800.0, allow_nan=False, allow_infinity=False)
resistances = st.floats(0.01, 10.0, allow_nan=False, allow_infinity=False)


@st.composite
def configs(draw):
    return _cfg(
        V_bus=draw(voltages),
        V_BR=draw(st.floats(1.0, 1700.0, allow_nan=False, allow_infinity=False)),
        L_coil=draw(inductances),
        L_leakage=draw(inductances),
        R_theta_jc=draw(resistances),
        R_theta_cs=draw(resistances),
        R_theta_sa=draw(resistances),
        T_amb=draw(st.floats(-40.0, 85.0, allow_nan=False, allow_infinity=False)),
        derate=draw(st.floats(0.05, 1.0, allow_nan=False, allow_infinity=False)),
    )


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


def _prop_p1_l_eff_stays_between_the_endpoints(cfg, l_eff=None):
    """P1: `L_eff(k)` lies between `L_coil` and `L_leakage` for every `k`
    in [0, 1] **up to the f64 evaluation floor**, and hits each endpoint
    *exactly*.

    This is the interval half of the R24 conservative-bound proof.  The
    two endpoint clauses are exact and stay exact — `L*(1-0) + L*0` and
    `L*(1-1) + L*1` each reduce to a single unrounded term — and they are
    what the bounding argument actually rests on.

    The interior clause carries a 2-ulp floor for the same measured
    reason as P2: when `L_coil` and `L_leakage` are equal or near-equal,
    `L_coil*(1-k) + L_leakage*k` rounds to one ulp *below* the common
    value (falsifying example found by Hypothesis: `L_coil == L_leakage
    == 0.0004817578204641488`, `k = 0.09375`).  The pure-Python oracle
    does exactly the same and the Rust kernel reproduces it bit-for-bit,
    so this is a documented accuracy floor of the reference, not a
    migration defect.  A genuinely non-monotone model escapes the
    interval by ~1e-1 relative and is still caught (vacuity guards
    below).
    """
    l_eff = l_eff or (lambda k: mod._l_eff(cfg, k))
    lo, hi = sorted((cfg.L_coil, cfg.L_leakage))
    floor = 2.0 * math.ulp(hi)
    for i in range(0, 65):
        k = i / 64.0
        v = l_eff(k)
        assert lo - floor <= v <= hi + floor, (
            f"L_eff({k}) = {v} escaped [{lo}, {hi}] by more than the "
            f"{floor} evaluation floor"
        )
    assert l_eff(0.0) == cfg.L_coil, "L_eff(0) is not exactly L_coil"
    assert l_eff(1.0) == cfg.L_leakage, "L_eff(1) is not exactly L_leakage"


def _prop_p2_di_dt_is_monotone_in_coupling(cfg, l_eff=None):
    """P2: `di/dt(k) = V_bus / L_eff(k)` is monotone in `k` **up to the
    f64 evaluation floor**.

    The *model* is exactly monotone (see the `_l_eff` proof).  Its
    *evaluation* is not, and this is a measured property of the reference,
    not of the migration: when `L_coil` and `L_leakage` are within a few
    ulp of each other, `L_coil*(1-k) + L_leakage*k` wobbles by ~1.2e-16
    relative as `k` sweeps, so consecutive `di/dt` samples can step
    backwards.  The pure-Python oracle does exactly the same thing and the
    Rust kernel reproduces it bit-for-bit (pinned in the differential), so
    this is a documented accuracy floor rather than a soundness gap: the
    envelope predicates the gate actually enforces carry the reference's
    own 1e-12 relative guard band, ~1e4 times the observed wobble.

    The claim asserted here is therefore: every step either moves in the
    endpoint-to-endpoint direction, or is no larger than 4 ulp.  A
    genuinely non-monotone coupling model dips by ~1e-1 relative and is
    still caught (see the vacuity guard).
    """
    l_eff = l_eff or (lambda k: mod._l_eff(cfg, k))
    series = [cfg.V_bus / l_eff(i / 64.0) for i in range(65)]
    rising = series[-1] >= series[0]
    for i, (a, b) in enumerate(zip(series, series[1:])):
        if (b >= a) if rising else (b <= a):
            continue
        floor = 4.0 * abs(math.ulp(max(abs(a), abs(b))))
        assert abs(b - a) <= floor, (
            f"di/dt reversed by {abs(b - a)} at k={i / 64.0}, "
            f"far beyond the {floor} evaluation floor"
        )


def _prop_p3_endpoints_bound_the_interior(cfg, l_eff=None):
    """P3 (**R24 soundness**): no interior coupling value produces a worse
    `di/dt` or a worse `L_loop_max` than the endpoint envelope."""
    l_eff = l_eff or (lambda k: mod._l_eff(cfg, k))
    dense = [(i / 128.0, l_eff(i / 128.0)) for i in range(1, 128)]
    scan = _tt.operating_point_interior_scan_py(
        cfg.V_bus, cfg.V_BR, cfg.derate, cfg.min_feasible_L_loop,
        l_eff(0.0), l_eff(1.0), dense,
    )
    if not scan[0]:
        return
    for k, _di, _ll, _breach, worse_di, worse_ll in scan[5]:
        assert not worse_di, f"di/dt envelope broken at k={k}"
        assert not worse_ll, f"L_loop_max envelope broken at k={k}"


def _prop_p4_junction_temperature_is_above_ambient(cfg, extremes=None):
    """P4: with non-negative power and non-negative thermal resistances,
    `T_j >= T_amb`.  A sign flip in the `T_amb + P*R` chain (an R4 bug
    class) makes the device look *colder* than ambient under load."""
    extremes = extremes or mod.compute_extremes
    k0, k1 = extremes(cfg)
    assert k0.T_j == k1.T_j, "T_j must not depend on coupling"
    assert k0.T_j >= cfg.T_amb, f"T_j {k0.T_j} below ambient {cfg.T_amb}"
    assert k0.P_device >= 0.0, "negative device power"


def _prop_p5_feasibility_matches_its_own_ceilings(cfg, extremes=None):
    """P5: the `feasible` flag is exactly the conjunction it claims —
    `T_j <= T_j_max and L_loop_max >= min_feasible_L_loop`.  A *loosened
    bound* (an R4 bug class) shows up here and nowhere else."""
    extremes = extremes or mod.compute_extremes
    for point in extremes(cfg):
        expected = (
            point.T_j <= cfg.T_j_max and point.L_loop_max >= cfg.min_feasible_L_loop
        )
        assert point.feasible == expected, (
            f"{point.label}: feasible={point.feasible} but ceilings say {expected}"
        )


def _prop_p6_audit_agrees_with_the_gate(cfg, extremes=None):
    """P6 (**R24 post-solve audit**): recomputing every ceiling from the
    raw config reproduces exactly what the gate reported."""
    extremes = extremes or mod.compute_extremes
    k0, k1 = extremes(cfg)
    findings = mod.audit_operating_point(cfg, k0, k1, n_samples=65)
    assert findings == [], f"audit disagreed with the gate: {findings}"


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@given(cfg=configs())
@settings(max_examples=40, deadline=None)
def test_p1_l_eff_stays_between_the_endpoints(cfg):
    _prop_p1_l_eff_stays_between_the_endpoints(cfg)


@given(cfg=configs())
@settings(max_examples=40, deadline=None)
def test_p2_di_dt_is_monotone_in_coupling(cfg):
    _prop_p2_di_dt_is_monotone_in_coupling(cfg)


@given(cfg=configs())
@settings(max_examples=40, deadline=None)
def test_p3_endpoints_bound_the_interior(cfg):
    _prop_p3_endpoints_bound_the_interior(cfg)


@given(cfg=configs())
@settings(max_examples=30, deadline=None)
def test_p4_junction_temperature_is_above_ambient(cfg):
    _prop_p4_junction_temperature_is_above_ambient(cfg)


@given(cfg=configs())
@settings(max_examples=30, deadline=None)
def test_p5_feasibility_matches_its_own_ceilings(cfg):
    _prop_p5_feasibility_matches_its_own_ceilings(cfg)


@given(cfg=configs())
@settings(max_examples=25, deadline=None)
def test_p6_audit_agrees_with_the_gate(cfg):
    _prop_p6_audit_agrees_with_the_gate(cfg)


# ---------------------------------------------------------------------------
# Vacuity guards
# ---------------------------------------------------------------------------


def _quadratic_dip_model(cfg, depth=200e-6):
    """R4 bug class: a non-monotone coupling model -- the exact scenario
    the interior safeguard was added for."""
    return lambda k: mod._l_eff(cfg, k) - depth * k * (1.0 - k)


def _reversed_l_eff(cfg):
    """R4 bug class: index/argument mis-orientation -- the endpoints
    swapped, so L_eff(0) is the leakage inductance."""
    return lambda k: mod._l_eff(cfg, 1.0 - k)


def _sign_flipped_extremes(cfg):
    """R4 bug class: sign flip in `T_amb + P * R_th`."""
    k0, k1 = mod.compute_extremes(cfg)
    flip = lambda p: type(p)(  # noqa: E731 - local, single-expression rebind
        label=p.label, coupling=p.coupling, di_dt=p.di_dt, P_device=p.P_device,
        T_j=cfg.T_amb - (p.T_j - cfg.T_amb), L_loop_max=p.L_loop_max,
        feasible=p.feasible,
    )
    return flip(k0), flip(k1)


def _loosened_feasibility(cfg):
    """R4 bug class: loosened bound -- `feasible` reported True regardless."""
    k0, k1 = mod.compute_extremes(cfg)
    loosen = lambda p: type(p)(  # noqa: E731
        label=p.label, coupling=p.coupling, di_dt=p.di_dt, P_device=p.P_device,
        T_j=p.T_j, L_loop_max=p.L_loop_max, feasible=True,
    )
    return loosen(k0), loosen(k1)


def _widened_ceiling(cfg):
    """R4 bug class: loosened bound -- `L_loop_max` doubled."""
    k0, k1 = mod.compute_extremes(cfg)
    widen = lambda p: type(p)(  # noqa: E731
        label=p.label, coupling=p.coupling, di_dt=p.di_dt, P_device=p.P_device,
        T_j=p.T_j, L_loop_max=p.L_loop_max * 2.0, feasible=p.feasible,
    )
    return widen(k0), widen(k1)


def test_p1_fails_for_a_dipping_coupling_model():
    cfg = _cfg()
    with pytest.raises(AssertionError):
        _prop_p1_l_eff_stays_between_the_endpoints(cfg, l_eff=_quadratic_dip_model(cfg))


def test_p1_fails_for_reversed_endpoints():
    cfg = _cfg()
    with pytest.raises(AssertionError):
        _prop_p1_l_eff_stays_between_the_endpoints(cfg, l_eff=_reversed_l_eff(cfg))


def test_p2_fails_for_a_dipping_coupling_model():
    cfg = _cfg()
    with pytest.raises(AssertionError):
        _prop_p2_di_dt_is_monotone_in_coupling(cfg, l_eff=_quadratic_dip_model(cfg))


def test_p3_fails_for_a_dipping_coupling_model():
    cfg = _cfg()
    with pytest.raises(AssertionError):
        _prop_p3_endpoints_bound_the_interior(cfg, l_eff=_quadratic_dip_model(cfg))


def test_p4_fails_for_a_sign_flipped_thermal_chain():
    cfg = _cfg(T_amb=40.0)
    with pytest.raises(AssertionError):
        _prop_p4_junction_temperature_is_above_ambient(
            cfg, extremes=lambda c: _sign_flipped_extremes(c)
        )


def test_p5_fails_for_loosened_feasibility():
    # A config whose T_j is genuinely over the ceiling, so "always
    # feasible" is a real loosening rather than a coincidence.
    cfg = _cfg(T_j_max=0.0)
    assert not mod.compute_extremes(cfg)[0].feasible, "fixture is not discriminating"
    with pytest.raises(AssertionError):
        _prop_p5_feasibility_matches_its_own_ceilings(
            cfg, extremes=lambda c: _loosened_feasibility(c)
        )


def test_p6_fails_for_a_widened_ceiling():
    cfg = _cfg()
    assert mod.compute_extremes(cfg)[0].L_loop_max > 0.0, "fixture is not discriminating"
    with pytest.raises(AssertionError):
        _prop_p6_audit_agrees_with_the_gate(cfg, extremes=lambda c: _widened_ceiling(c))


def test_the_property_input_class_is_discriminating():
    """Sanity: the production config actually produces a non-degenerate
    envelope (distinct endpoints, positive headroom), so the guards above
    are testing something."""
    cfg = _cfg()
    k0, k1 = mod.compute_extremes(cfg)
    assert k0.di_dt != k1.di_dt, "the two coupling extremes coincide"
    assert k0.L_loop_max > 0.0 and k1.L_loop_max > 0.0, "no bus headroom"


# ---------------------------------------------------------------------------
# Metamorphic relations (G5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scale", [0.5, 2.0, 4.0, 1024.0])
def test_mr1_di_dt_scales_inversely_with_inductance(scale):
    """**MR1 — scaling.** Scaling both inductances by `s` scales `di/dt`
    by `1/s` and `L_loop_max` by `s`.  *Exact for power-of-two `s`*:
    multiplying a finite f64 by a power of two only shifts the exponent,
    and `V_bus / (s*L)` is the correctly-rounded quotient of an exactly
    scaled divisor."""
    base = _cfg()
    scaled = _cfg(L_coil=base.L_coil * scale, L_leakage=base.L_leakage * scale)
    b0, b1 = mod.compute_extremes(base)
    s0, s1 = mod.compute_extremes(scaled)
    for b, s in ((b0, s0), (b1, s1)):
        assert s.di_dt == b.di_dt / scale
        assert s.L_loop_max == b.L_loop_max * scale


def test_mr2_swapping_the_inductances_swaps_the_extremes():
    """**MR2 — permutation.** Exchanging `L_coil` and `L_leakage` exchanges
    the two extremes' `di/dt` and `L_loop_max`.  *Exact*: each endpoint is
    computed from one inductance alone, so no reassociation occurs."""
    base = _cfg()
    swapped = _cfg(L_coil=base.L_leakage, L_leakage=base.L_coil)
    b0, b1 = mod.compute_extremes(base)
    s0, s1 = mod.compute_extremes(swapped)
    assert (s0.di_dt, s0.L_loop_max) == (b1.di_dt, b1.L_loop_max)
    assert (s1.di_dt, s1.L_loop_max) == (b0.di_dt, b0.L_loop_max)


@pytest.mark.parametrize("k", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_mr3_l_eff_is_symmetric_under_endpoint_reflection(k):
    """**MR3 — reflection.** `L_eff(L_a, L_b, k) == L_eff(L_b, L_a, 1-k)`.
    *Exact for dyadic `k`*, where `1 - k` is representable without
    rounding; the two expressions then differ only by the order of an
    IEEE addition, which is commutative."""
    cfg = _cfg()
    swapped = _cfg(L_coil=cfg.L_leakage, L_leakage=cfg.L_coil)
    assert mod._l_eff(cfg, k) == mod._l_eff(swapped, 1.0 - k)


@pytest.mark.parametrize("scale", [2.0, 8.0, 0.25])
def test_mr4_junction_rise_scales_with_thermal_resistance(scale):
    """**MR4 — scaling.** Scaling every thermal resistance by `s` scales
    the junction *rise* above ambient by `s`.  *Exact for power-of-two
    `s`* with `T_amb == 0.0`, so the reported `T_j` IS the rise and no
    cancellation is introduced."""
    base = _cfg(T_amb=0.0)
    scaled = _cfg(
        T_amb=0.0,
        R_theta_jc=base.R_theta_jc * scale,
        R_theta_cs=base.R_theta_cs * scale,
        R_theta_sa=base.R_theta_sa * scale,
    )
    b0, _ = mod.compute_extremes(base)
    s0, _ = mod.compute_extremes(scaled)
    assert math.isfinite(b0.T_j) and b0.T_j > 0.0
    assert s0.T_j == b0.T_j * scale
