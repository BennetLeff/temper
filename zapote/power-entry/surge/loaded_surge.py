#!/usr/bin/env python3
"""Loaded differential surge calculation for V150LA10AP under REQ-EMC-03.

The question this answers
-------------------------
Does V150LA10AP protect the proposed bridge and controller under the adopted
differential surge (IEC 61000-4-5, 1 kV, combination wave, 2 ohm generator)?

Why it is not the datasheet's 50 A point
----------------------------------------
"500 A" is the generator's PROSPECTIVE SHORT-CIRCUIT current (1 kV / 2 ohm). The
actual MOV current is lower, because the MOV clamps: the operating point is where
the MOV's V-I curve meets the generator's load line

    V = V_oc - Z_source * I        (load line)
    V = V_mov(I)                   (device characteristic)

so I and V must be solved together. The datasheet tabulates ONE point, 395 V
MAXIMUM at 50 A; the curve used here is the vector-extracted typical curve from
Figure 10, validated against three tabulated maxima (see extract_la_vi_curve.py).

Stdlib only: reads the committed curve data.
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
CURVE = HERE / "data" / "v150la10a_vi_curve.json"

# --- the committed contract (docs/specs/SURGE_CONTRACT.md) -------------------
V_OC = 1000.0  # differential level, volts
Z_SOURCE = 2.0  # combination-wave generator, ohms
V_PROSPECTIVE = V_OC / Z_SOURCE

# --- applicable transient limits --------------------------------------------
TEA2209T_OPERATING = 440.0  # continuous operating rating, V
TEA2209T_TRANSIENT = 700.0  # mains-transient rating, V (datasheet p.8, p.12)
I_TM = 4500.0  # MOV peak current rating, 8/20 us
BRIDGE_CLASS = 600.0  # proposed active-bridge class, V

# --- the 8/20 us surge, as the standard defines it by two time markers -------
FRONT_US = 1.2  # open-circuit voltage front time
HALF_US = 50.0  # open-circuit voltage time to half value
DT = 5e-9


def load_curve() -> list[tuple[float, float]]:
    pts = json.loads(CURVE.read_text())["points"]
    return [(p["i_a"], p["v"]) for p in pts]


def scale_curve(curve, factor):
    return [(i, v * factor) for i, v in curve]


def v_mov(curve, i: float) -> float:
    """Monotone interpolant in log-log, clamped to the curve's domain."""
    if i <= curve[0][0]:
        return curve[0][1]
    if i >= curve[-1][0]:
        # Extrapolate on the terminal log-log slope rather than flattening.
        (i0, v0), (i1, v1) = curve[-2], curve[-1]
        s = math.log(v1 / v0) / math.log(i1 / i0)
        return v1 * (i / i1) ** s
    lo, hi = 0, len(curve) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if curve[mid][0] <= i:
            lo = mid
        else:
            hi = mid
    i0, v0 = curve[lo]
    i1, v1 = curve[hi]
    t = (math.log(i) - math.log(i0)) / (math.log(i1) - math.log(i0))
    return math.exp(math.log(v0) + t * (math.log(v1) - math.log(v0)))


def solve_bisect(f, lo: float, hi: float) -> float:
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if f(mid) > 0:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def crossing(w, level: float, t_start: float = 0.0, t_max: float = 2000e-6,
             rising: bool = True) -> float:
    """First crossing of `level`, searching forward from t_start.

    A fixed bracket cannot be used: the shape rises and falls, so an arbitrary
    upper bound is usually on the same side of the level as the lower one, and a
    naive bisection then collapses to a bound and silently reports ~0. The
    rising/falling distinction matters too -- the time to HALF value is on the
    falling edge, not the first rise through 0.5.
    """
    prev_t, prev = t_start, w(t_start) - level
    n = 400000
    for k in range(1, n + 1):
        t = t_start + (t_max - t_start) * k / n
        cur = w(t) - level
        if (prev <= 0.0 < cur) if rising else (prev >= 0.0 > cur):
            g = (lambda x: w(x) - level) if rising else (lambda x: level - w(x))
            return solve_bisect(g, prev_t, t)
        prev_t, prev = t, cur
    raise ValueError(f"shape never crosses {level}")


def operating_point(curve, v_oc: float, z: float) -> tuple[float, float]:
    """Where the load line meets the MOV characteristic."""
    i = solve_bisect(lambda i: z * i + v_mov(curve, i) - v_oc, 0.0, v_oc / z)
    return i, v_mov(curve, i)


def double_exp(tau_decay_us: float, tau_rise_us: float):
    """Normalised impulse shape, peak 1."""
    td, tr = tau_decay_us * 1e-6, tau_rise_us * 1e-6
    raw = lambda t: math.exp(-t / td) - math.exp(-t / tr)
    peak = raw(td_tr_peak(tau_decay_us, tau_rise_us))
    return lambda t: raw(t) / peak


def td_tr_peak(tau_decay_us: float, tau_rise_us: float) -> float:
    """Time of the double-exponential's maximum."""
    td, tr = tau_decay_us * 1e-6, tau_rise_us * 1e-6
    return td * tr / (td - tr) * math.log(td / tr)


def fit_waveform(front_us: float, half_us: float, front_factor: float) -> tuple:
    """Fit (tau_decay, tau_rise) to the standard's two defining markers.

    front_factor is 1.67 for the 1.2/50 voltage wave and 1.25 for the 8/20
    current wave -- the standard defines their front times with different
    multipliers, so they must not be conflated.
    """
    def markers(p):
        w = double_exp(*p)
        t10 = crossing(w, 0.10)
        t90 = crossing(w, 0.90)
        # The standard measures BOTH times from the virtual origin: where the
        # line through the 10% and 90% points crosses zero. It matters for the
        # 8/20 wave (front ~40% of the half-value time) and is negligible for
        # 1.2/50.
        t_virtual = t10 - 0.125 * (t90 - t10)
        t_pk = td_tr_peak(*p)
        t_half = crossing(w, 0.5, t_start=t_pk, rising=False)
        return front_factor * (t90 - t10) * 1e6, (t_half - t_virtual) * 1e6

    # The markers are coupled -- changing tau_decay moves the front time too --
    # so the two one-dimensional fits are alternated to convergence rather than
    # run once each.
    tau_decay, tau_rise = 70.0, 0.5
    for _ in range(60):
        lo, hi = 1e-3, 30.0
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if markers((tau_decay, mid))[0] < front_us:
                lo = mid
            else:
                hi = mid
        tau_rise = 0.5 * (lo + hi)

        lo, hi = 1.0, 5000.0
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if markers((mid, tau_rise))[1] < half_us:
                lo = mid
            else:
                hi = mid
        tau_decay = 0.5 * (lo + hi)

    return (tau_decay, tau_rise), markers((tau_decay, tau_rise))


def energy_vsource(curve, v_oc_peak: float, z: float, shape) -> tuple[float, float, float]:
    """Energy absorbed, generator modelled as V_oc(t) behind Z_source.

    This is a voltage-source sensitivity model, not a validated combination-wave
    generator: its fixed resistance cannot produce a different short-circuit
    waveform from the open-circuit voltage waveform.
    """
    e = pk_i = pk_v = 0.0
    t, t_end = 0.0, 400e-6
    while t < t_end:
        i, v = operating_point(curve, v_oc_peak * shape(t), z)
        e += v * i * DT
        pk_i, pk_v = max(pk_i, i), max(pk_v, v)
        t += DT
    return e, pk_i, pk_v


def main() -> int:
    curve = load_curve()
    table_max_at_50 = 395.0
    typical_at_50 = v_mov(curve, 50.0)
    max_curve = scale_curve(curve, table_max_at_50 / typical_at_50)

    # Only the 1.2/50 open-circuit voltage wave is fitted. A 8/20 current-wave
    # cross-check was attempted and REMOVED: a two-exponential cannot reproduce
    # the standard's 8/20 markers under the 1.25 front-time convention (the
    # narrowest achievable front/half ratio is ~3.8 against the 2.5 required), so
    # rather than force a fit the check is dropped and this is said out loud.
    v_pars, v_mark = fit_waveform(1.2, 50.0, 1.67)
    v_shape = double_exp(*v_pars)

    # Refuse to report an energy computed with a waveform that did not fit.
    (front_got, half_got) = v_mark
    print(f"  waveform 1.2/50 V front = {front_got:7.3f} us  (want 1.2)")
    print(f"  waveform 1.2/50 V half  = {half_got:7.3f} us  (want 50.0)")
    bad = []
    if abs(front_got - 1.2) / 1.2 > 0.02:
        bad.append(("front", round(front_got, 3)))
    if abs(half_got - 50.0) / 50.0 > 0.02:
        bad.append(("half", round(half_got, 3)))
    if bad:
        print(f"  REFUSING to report an energy: waveform did not converge: {bad}")
        return 1
    print("  SCREEN ONLY: fixed-resistance voltage source; not a validated combination-wave generator.")
    print("  Scaled curve is a sensitivity, not a guaranteed maximum. No qualification verdict.")
    print(f"  prospective short-circuit current = V_oc/Z = {V_OC:.0f}/{Z_SOURCE:.0f} = {V_PROSPECTIVE:.0f} A")
    print()

    for name, c in (("typical curve", curve), ("scaled to match the 50 A maximum (assumed shape)", max_curve)):
        e_v, pk_i, pk_v = energy_vsource(c, V_OC, Z_SOURCE, v_shape)
        print(f"  {name}")
        print(f"    operating point at peak: I = {pk_i:6.1f} A, V = {pk_v:6.1f} V")
        print(f"    absorbs {100 * pk_i / V_PROSPECTIVE:.0f}% of the {V_PROSPECTIVE:.0f} A prospective"
              f" -> the MOV current is NOT the prospective current")
        print(f"    absorbed energy {e_v:5.2f} J; catalog ratio (different waveform): peak current is "
              f"{I_TM / pk_i:.1f}x below I_TM = {I_TM:.0f} A (8/20 us)")
        print()

    v_op_max = operating_point(max_curve, V_OC, Z_SOURCE)[1]
    print("  scalar rating comparisons for the assumed scaled curve (not worst-case limits):")
    for label, lim in (("TEA2209T continuous operating", TEA2209T_OPERATING),
                       ("TEA2209T mains transient", TEA2209T_TRANSIENT)):
        flag = "  <-- EXCEEDS" if v_op_max > lim else ""
        print(f"    {label:<30} {lim:5.0f} V : {v_op_max / lim:.3f} of limit{flag}")
    print(f"    {'proposed bridge class':<30} {BRIDGE_CLASS:5.0f} V : {BRIDGE_CLASS / v_op_max:.2f}x voltage ratio (not qualified margin)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
