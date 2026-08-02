"""Property-based tests for the Rust per-device power kernel
(``temper_thermal.single_device_power_py``, Wave 4 Phase A #2 —
migration of ``temper_placer/physics/device_power.py``'s canonical
per-device power model, issue #140).

The kernel is pure closed-form f64 arithmetic over a three-way branch
(DIODE conduction+switching, IGBT/MOSFET conduction × {energy-method or
waveform} switching).  Every property below is a direct statement about
correctly-rounded IEEE-754 operations, and each is vacuity-guarded (its
docstring says why a constant / degenerate implementation fails it).

Exactness notes:

- ``I_load_rms**2`` is CPython `float.__pow__` → host-libm
  ``pow(x, 2.0)`` — the kernel resolves ``pow`` through ``dlsym`` (B1)
  so it agrees with the Python oracle bit-for-bit even where
  ``pow(x, 2.0) != x * x`` (measured ~0.14% of random floats, pinned in
  the differential suite).
- ``math.sqrt(2)`` in the waveform fallback is likewise resolved through
  ``dlsym`` (B1).
- Op order is pinned: ``I_avg = I * 0.5`` → ``P_cond = I_avg * V_f`` →
  ``P_sw = E_rr * f_sw`` → ``P_cond + P_sw`` (DIODE);
  ``pow(I, 2.0) * R_ds_on`` or ``I * V_ce_sat``; ``(E_on + E_off) * f_sw``
  or ``0.5 * V_bus * I_peak * f_sw * (t_rise + t_fall)``; final
  ``P_cond + P_sw`` (B7).
- Bit-exact closed-form relations (P2/P3/P4/P7, M1/M2/M3/M4/M5) hold
  because both sides evaluate the same op chain; power-of-two scaling
  relations are exact because scaling by a power of two commutes through
  multiplication without rounding (barring overflow/underflow, which the
  strategies' magnitudes avoid).
"""

from __future__ import annotations

import math
import random

import pytest
import temper_thermal as _tt
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.physics.device_power import DeviceLossConfig

MAX_EXAMPLES = 200

# --- Input strategies (finite, physically meaningful, non-degenerate) --------

_i_rms = st.floats(min_value=1e-3, max_value=100.0, allow_nan=False, allow_infinity=False)
_v_bus = st.floats(min_value=10.0, max_value=800.0, allow_nan=False, allow_infinity=False)
# f_sw is bounded away from 0 (min 1e-6) so every switching intermediate
# stays in the NORMAL f64 range: the power-of-two scale metamorphic
# relations (M1/M2/M5) are exact only for normal-magnitude intermediates
# — round(2^k·z) == 2^k·round(z) fails in the denormal band, where the
# ulp is fixed in absolute terms (the B8 denormal parity itself is pinned
# in the differential suite, where both sides run the identical chain).
_f_sw = st.floats(min_value=1e-6, max_value=200000.0, allow_nan=False, allow_infinity=False)
_t = st.floats(min_value=1e-9, max_value=1e-6, allow_nan=False, allow_infinity=False)
_v_f = st.floats(min_value=0.1, max_value=3.0, allow_nan=False, allow_infinity=False)
_e_rr = st.floats(min_value=0.0, max_value=5e-3, allow_nan=False, allow_infinity=False)
_v_ce = st.floats(min_value=0.5, max_value=3.0, allow_nan=False, allow_infinity=False)
_e_sw = st.floats(min_value=0.0, max_value=1e-3, allow_nan=False, allow_infinity=False)
_r_ds = st.floats(min_value=0.001, max_value=1.0, allow_nan=False, allow_infinity=False)


def _diode(v_f, e_rr):
    return DeviceLossConfig(
        name="D1", device_type="DIODE", V_f=v_f, E_rr=e_rr,
        V_f_because="t", E_rr_because="t",
    )


def _igbt(v_ce, e_on, e_off):
    return DeviceLossConfig(
        name="Q1", device_type="IGBT", V_ce_sat=v_ce, E_on=e_on, E_off=e_off,
        V_ce_sat_because="t", E_on_because="t", E_off_because="t",
    )


def _mosfet(r_ds):
    return DeviceLossConfig(
        name="Q1", device_type="IGBT", V_ce_sat=0.0, R_ds_on=r_ds,
        E_on=0.0, E_off=0.0, V_ce_sat_because="t", E_on_because="t",
        E_off_because="t",
    )


def _p(device, v_bus, i_rms, f_sw, t_rise, t_fall):
    """Kernel call (direct pyfunction, the migrated surface)."""
    return _tt.single_device_power_py(
        device.device_type, device.V_ce_sat, device.R_ds_on, device.E_on,
        device.E_off, device.V_f, device.E_rr, v_bus, i_rms, f_sw, t_rise, t_fall,
    )


# ---------------------------------------------------------------------------
# P1..P6: five+ non-vacuous properties (each vacuity-guarded)
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(v_bus=_v_bus, i_rms=_i_rms, f_sw=_f_sw, v_f=_v_f, e_rr=_e_rr, v_ce=_v_ce, e_on=_e_sw, e_off=_e_sw)
def test_power_positive_and_rich(v_bus, i_rms, f_sw, v_f, e_rr, v_ce, e_on, e_off):
    """P1 — positive inputs produce positive power, and the mapping is
    rich (a constant kernel fails: it cannot stay > 0 across the range
    while also separating the input classes)."""
    devs = [_diode(v_f, e_rr), _igbt(v_ce, e_on, e_off), _mosfet(0.1)]
    outs = {_p(d, v_bus, i_rms, f_sw, 50e-9, 50e-9) for d in devs}
    assert all(p > 0.0 for p in outs)
    # The three device paths separate (DIODE != IGBT-energy != MOSFET
    # conduction) for the drawn inputs — proves non-constant behavior.
    assert len(outs) >= 2


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(i_rms=_i_rms, f_sw=_f_sw, v_f=_v_f, e_rr=_e_rr)
def test_diode_closed_form_bit_exact(i_rms, f_sw, v_f, e_rr):
    """P2 — DIODE closed form, bit-exact: P == (I*0.5)*V_f + E_rr*f_sw
    (same three-op chain both sides).  A kernel that omits the 0.5
    (uses I*V_f) or the switching term fails."""
    dev = _diode(v_f, e_rr)
    got = _p(dev, 325.0, i_rms, f_sw, 50e-9, 50e-9)
    expected = (i_rms * 0.5) * v_f + e_rr * f_sw
    assert got == expected, f"diode: rust={got!r} closed-form={expected!r}"


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(i_rms=_i_rms, f_sw=_f_sw, v_ce=_v_ce,
       e_on=st.floats(min_value=1e-9, max_value=1e-3, allow_nan=False, allow_infinity=False),
       e_off=_e_sw)
def test_igbt_energy_method_closed_form_bit_exact(i_rms, f_sw, v_ce, e_on, e_off):
    """P3 — IGBT energy method, bit-exact: P == I*V_ce_sat +
    (E_on+E_off)*f_sw (with E_on > 0 so the energy branch is
    deterministically taken).  A kernel that drops the conduction term
    or the switching term fails."""
    dev = _igbt(v_ce, e_on, e_off)
    got = _p(dev, 325.0, i_rms, f_sw, 50e-9, 50e-9)
    expected = i_rms * v_ce + (e_on + e_off) * f_sw
    assert got == expected, f"igbt energy: rust={got!r} closed-form={expected!r}"


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(i_rms=_i_rms, r_ds=_r_ds)
def test_mosfet_conduction_closed_form_bit_exact(i_rms, r_ds):
    """P4 — MOSFET conduction, bit-exact: with E=0 and f_sw=0 the
    waveform switching term is exactly 0.0, so P == I**2 * R_ds_on
    (host-libm pow on both sides).  A kernel that uses the linear
    I*R_ds_on (or x*x) fails."""
    dev = _mosfet(r_ds)
    got = _p(dev, 325.0, i_rms, 0.0, 50e-9, 50e-9)
    expected = i_rms**2 * r_ds
    assert got == expected, f"mosfet: rust={got!r} closed-form={expected!r}"


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(v_bus=_v_bus, i_rms=_i_rms, f_sw=_f_sw, v_ce=_v_ce, e_on=_e_sw, e_off=_e_sw,
       delta=st.floats(min_value=1e-3, max_value=50.0, allow_nan=False, allow_infinity=False))
def test_power_non_decreasing_in_current(v_bus, i_rms, f_sw, v_ce, e_on, e_off, delta):
    """P5 — non-decreasing in I_load_rms for a fixed device: raising the
    load current never lowers the power (conduction and waveform
    switching are both non-decreasing in I; the energy method is
    I-independent).  A kernel that decreases in I fails."""
    i1 = min(i_rms, 100.0 - delta)
    i2 = i1 + delta
    for dev in (_igbt(v_ce, e_on, e_off), _diode(1.0, 1e-4), _mosfet(0.1)):
        p1 = _p(dev, v_bus, i1, f_sw, 50e-9, 50e-9)
        p2 = _p(dev, v_bus, i2, f_sw, 50e-9, 50e-9)
        assert p2 >= p1, f"{dev.device_type}: P({i2})={p2!r} < P({i1})={p1!r}"


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(v_bus=_v_bus, i_rms=_i_rms, f_sw=_f_sw, v_ce=_v_ce,
       e_on=st.floats(min_value=1e-9, max_value=1e-3, allow_nan=False, allow_infinity=False),
       e_off=_e_sw)
def test_energy_method_v_bus_irrelevant(v_bus, i_rms, f_sw, v_ce, e_on, e_off):
    """P6 — V_bus irrelevance (bit-exact) on the energy-method path: with
    E_on > 0 the switching energy does not depend on the bus
    voltage, so P is bit-identical across any V_bus.  A kernel that
    sneaks a V_bus term into the energy method fails."""
    dev = _igbt(v_ce, e_on, e_off)
    p_a = _p(dev, v_bus, i_rms, f_sw, 50e-9, 50e-9)
    p_b = _p(dev, v_bus + 100.0, i_rms, f_sw, 50e-9, 50e-9)
    assert p_a == p_b, f"energy method V_bus-dependent: {p_a!r} vs {p_b!r}"


# ---------------------------------------------------------------------------
# Metamorphic relations (>= 3 required)
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(i_rms=_i_rms, v_f=_v_f, e_rr=_e_rr)
def test_mr1_diode_power_of_two_current_scale(i_rms, v_f, e_rr):
    """M1 — bit-exact power-of-two I-scale on the DIODE path at f_sw = 0
    (P_sw = E_rr*0 = 0.0 exactly, so P is conduction-only):
    P(2^k*I) == 2^k * P(I), bit-exact.  (Power-of-two scaling commutes
    through the multiply chain without rounding: round(2^k·z) = 2^k·round(z)
    for every intermediate z, barring overflow/underflow, which the
    strategy magnitudes avoid.  NOTE: the relation is written WITHOUT
    subtracting the switching term — (X + p_sw) - p_sw re-rounds and is
    NOT X; the f_sw = 0 degeneracy makes the subtraction unnecessary.)"""
    dev = _diode(v_f, e_rr)
    for k in (1, 2, 3):
        c = float(2**k)
        p_base = _p(dev, 325.0, i_rms, 0.0, 50e-9, 50e-9)
        p_scaled = _p(dev, 325.0, c * i_rms, 0.0, 50e-9, 50e-9)
        assert p_scaled == c * p_base, (
            f"diode scale k={k}: P({c}*I)={p_scaled!r} vs {c}*P(I)={c * p_base!r}"
        )


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(i_rms=_i_rms, f_sw=_f_sw, v_bus=_v_bus, t_rise=_t, t_fall=_t)
def test_mr2_waveform_power_of_two_v_bus_scale(i_rms, f_sw, v_bus, t_rise, t_fall):
    """M2 — bit-exact power-of-two V_bus scale on the waveform path with
    V_ce_sat = 0 and R_ds_on = 0 (P_cond = I*0 = 0.0 exactly, so P is
    switching-only): P(2^k*V) == 2^k * P(V), bit-exact.  (The 0.5 factor
    and every multiply commute with power-of-two scaling exactly.)"""
    dev = _igbt(0.0, 0.0, 0.0)  # V_ce_sat = 0 → P_cond = 0; E=0 → waveform
    for k in (1, 2):
        c = float(2**k)
        p_base = _p(dev, v_bus, i_rms, f_sw, t_rise, t_fall)
        p_scaled = _p(dev, c * v_bus, i_rms, f_sw, t_rise, t_fall)
        assert p_scaled == c * p_base, (
            f"waveform v_bus scale k={k}: P({c}*V)={p_scaled!r} vs "
            f"{c}*P(V)={c * p_base!r}"
        )


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(i_rms=_i_rms, f_sw=_f_sw, v_ce=_v_ce, v_bus=_v_bus, t_rise=_t, t_fall=_t)
def test_mr3_waveform_closed_form_bit_exact(i_rms, f_sw, v_ce, v_bus, t_rise, t_fall):
    """M3 — waveform closed form, bit-exact: the fallback switching term
    equals the same host-op chain written in Python —
    0.5*V_bus*(I*math.sqrt(2))*f_sw*(t_rise+t_fall) — because the kernel
    resolves sqrt via dlsym (B1) and preserves the left-to-right op order
    (B7)."""
    dev = _igbt(v_ce, 0.0, 0.0)
    got = _p(dev, v_bus, i_rms, f_sw, t_rise, t_fall)
    p_cond = i_rms * v_ce
    i_peak = i_rms * math.sqrt(2)
    p_sw = 0.5 * v_bus * i_peak * f_sw * (t_rise + t_fall)
    assert got == p_cond + p_sw, f"waveform: rust={got!r} closed-form={p_cond + p_sw!r}"


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(i_rms=_i_rms, v_ce=_v_ce, e_on=_e_sw, e_off=_e_sw, v_f=_v_f, e_rr=_e_rr)
def test_mr4_zero_f_sw_is_conduction_only(i_rms, v_ce, e_on, e_off, v_f, e_rr):
    """M4 — bit-exact f_sw = 0 degeneracy: every switching term is
    exactly 0.0 at f_sw = 0 (E*f_sw, E_rr*f_sw, and the waveform chain
    all contain a *f_sw factor), so P == the conduction-only value on
    every device path."""
    igbt = _igbt(v_ce, e_on, e_off)
    diode = _diode(v_f, e_rr)
    mos = _mosfet(0.1)
    assert _p(igbt, 325.0, i_rms, 0.0, 50e-9, 50e-9) == i_rms * v_ce
    assert _p(diode, 325.0, i_rms, 0.0, 50e-9, 50e-9) == (i_rms * 0.5) * v_f
    assert _p(mos, 325.0, i_rms, 0.0, 50e-9, 50e-9) == i_rms**2 * 0.1


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(i_rms=_i_rms, f_sw=_f_sw,
       e_on=st.floats(min_value=1e-9, max_value=1e-3, allow_nan=False, allow_infinity=False),
       e_off=_e_sw)
def test_mr5_energy_method_f_sw_power_of_two_scale(i_rms, f_sw, e_on, e_off):
    """M5 — bit-exact power-of-two f_sw scale on the energy-method path
    with V_ce_sat = 0 (P_cond = 0.0 exactly): P(2^k*f) == 2^k*P(f),
    bit-exact.  (E_on+E_off) is evaluated once on both sides, and
    scaling the product by a power of two preserves rounding."""
    dev = _igbt(0.0, e_on, e_off)  # V_ce_sat = 0 → P_cond = 0
    for k in (1, 2, 3):
        c = float(2**k)
        p_base = _p(dev, 325.0, i_rms, f_sw, 50e-9, 50e-9)
        p_scaled = _p(dev, 325.0, i_rms, c * f_sw, 50e-9, 50e-9)
        assert p_scaled == c * p_base, (
            f"energy f_sw scale k={k}: P({c}*f)={p_scaled!r} vs "
            f"{c}*P(f)={c * p_base!r}"
        )


def test_pbt_smoke_deterministic_seed():
    """The PBT strategies are non-vacuous in aggregate: a quick seeded
    sweep over the property inputs must produce strictly more than one
    distinct power (guards against the whole suite silently degenerating
    to a single input class)."""
    rng = random.Random(0xDEAD)
    distinct = set()
    for _ in range(300):
        dev = rng.choice(
            [_diode(rng.uniform(0.1, 3.0), rng.uniform(0, 5e-3)),
             _igbt(rng.uniform(0.5, 3.0), rng.uniform(0, 1e-3), rng.uniform(0, 1e-3)),
             _mosfet(rng.uniform(0.001, 1.0))]
        )
        distinct.add(
            _p(dev, rng.uniform(10, 800), rng.uniform(1e-3, 100),
               rng.uniform(0, 200000), 50e-9, 50e-9)
        )
    assert len(distinct) > 50


# ---------------------------------------------------------------------------
# Vacuity mutants (G4 evidence pattern)
# ---------------------------------------------------------------------------


@pytest.fixture
def _restore_kernel():
    original = _tt.single_device_power_py
    yield
    _tt.single_device_power_py = original


def test_p1_fails_for_constant_kernel(_restore_kernel) -> None:
    """A constant kernel (0.0) cannot be positive AND rich (P1)."""
    _tt.single_device_power_py = lambda *_a, **_k: 0.0
    with pytest.raises(AssertionError):
        test_power_positive_and_rich.hypothesis.inner_test(325.0, 16.0, 25000.0, 1.05, 0.06e-3, 1.7, 0.32e-3, 0.21e-3)


def test_p2_fails_for_diode_missing_half_factor(_restore_kernel) -> None:
    """A DIODE kernel that drops the 0.5 I_avg factor (P = I*V_f + E_rr*f_sw)
    breaks the closed form (P2)."""
    _tt.single_device_power_py = lambda device_type, v_ce_sat, r_ds_on, e_on, e_off, v_f, e_rr, v_bus, i_rms, f_sw, t_rise, t_fall: (  # noqa: ARG005
        (i_rms * v_f + e_rr * f_sw) if device_type == "DIODE" else 0.0
    )
    with pytest.raises(AssertionError):
        test_diode_closed_form_bit_exact.hypothesis.inner_test(16.0, 25000.0, 1.05, 0.06e-3)


def test_p3_fails_for_igbt_missing_conduction(_restore_kernel) -> None:
    """An IGBT energy-method kernel that omits the conduction term
    (P = (E_on+E_off)*f_sw only) breaks the closed form (P3)."""
    _tt.single_device_power_py = lambda device_type, v_ce_sat, r_ds_on, e_on, e_off, v_f, e_rr, v_bus, i_rms, f_sw, t_rise, t_fall: (  # noqa: ARG005
        0.0 if device_type == "DIODE" else (e_on + e_off) * f_sw
    )
    with pytest.raises(AssertionError):
        test_igbt_energy_method_closed_form_bit_exact.hypothesis.inner_test(16.0, 25000.0, 1.7, 0.32e-3, 0.21e-3)


def test_p4_fails_for_mosfet_linear_conduction(_restore_kernel) -> None:
    """A MOSFET kernel that uses linear I*R_ds_on instead of I**2*R_ds_on
    breaks the quadratic closed form (P4)."""
    _tt.single_device_power_py = lambda device_type, v_ce_sat, r_ds_on, e_on, e_off, v_f, e_rr, v_bus, i_rms, f_sw, t_rise, t_fall: (  # noqa: ARG005
        0.0 if device_type == "DIODE" else i_rms * r_ds_on
    )
    with pytest.raises(AssertionError):
        test_mosfet_conduction_closed_form_bit_exact.hypothesis.inner_test(16.0, 0.1)


def test_p5_fails_for_decreasing_kernel(_restore_kernel) -> None:
    """A kernel that DECREASES in I_load_rms (conduction = V_ce_sat / I)
    breaks P5's monotonicity (a constant is trivially monotone, so this
    is the discriminating mutant; P1 covers constants)."""
    _tt.single_device_power_py = lambda device_type, v_ce_sat, r_ds_on, e_on, e_off, v_f, e_rr, v_bus, i_rms, f_sw, t_rise, t_fall: (  # noqa: ARG005
        v_f / i_rms if device_type == "DIODE" else v_ce_sat / i_rms
    )
    with pytest.raises(AssertionError):
        test_power_non_decreasing_in_current.hypothesis.inner_test(325.0, 16.0, 25000.0, 1.7, 0.32e-3, 0.21e-3, 10.0)


def test_p6_fails_for_v_bus_sensitive_energy_method(_restore_kernel) -> None:
    """A kernel that adds a V_bus term to the energy-method path breaks
    V_bus irrelevance (P6)."""
    _tt.single_device_power_py = lambda device_type, v_ce_sat, r_ds_on, e_on, e_off, v_f, e_rr, v_bus, i_rms, f_sw, t_rise, t_fall: (  # noqa: ARG005
        (i_rms * 0.5) * v_f + e_rr * f_sw if device_type == "DIODE"
        else i_rms * v_ce_sat + (e_on + e_off) * f_sw + 0.1 * v_bus
    )
    with pytest.raises(AssertionError):
        test_energy_method_v_bus_irrelevant.hypothesis.inner_test(325.0, 16.0, 25000.0, 1.7, 0.32e-3, 0.21e-3)
