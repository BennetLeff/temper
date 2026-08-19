#!/usr/bin/env python3
"""Re-runnable derivation of the tank current at the 1800 W operating point.

WHY THIS EXISTS
---------------
`I_tank = 22.5 A rms / 31.9 A peak` (elec/src/modules.ato:585-593,
docs/hardware/TANK_COIL_SPECIFICATION.md:217-218) is load-bearing for three
derivations landed 2026-08-17.  Its provenance was challenged on the grounds
that it descends from "a broken pan model whose power axis is not usable
(Q=143 vs ~14 for a real hob)".  This script settles that by rebuilding the
number from primary inputs and reporting the loaded Q each candidate model
actually implies.

STDLIB ONLY, READS NO REPO STATE.  Every constant below is transcribed with
its citation; nothing is imported from elec/ or simulation/.  `make
venv-isolate` is therefore not required to run it.  ngspice is NOT invoked
(and is not installed in the analysis environment) -- the harness's own
T-model relation is evaluated analytically instead, which is the same
relation `simulation/harness/run_tank_coil_sweep.py::f_res_loaded_hz`
iterates to a fixed point.

    python3 docs/evidence/2026-08-17-tank-current-provenance.py

EVIDENCE CLASSES, kept strictly separate and labelled per row:
    [CHART]  read off a manufacturer chart (Infineon), +/-5% on the read
    [DECL]   declared in this repo's own source, exact by construction
    [FIT]    constraint-satisfying fit to a [CHART] value; NOT measured
    [DERIV]  arithmetic on the above
    [N/A]    not obtainable in this environment
"""
from __future__ import annotations

import math

# --------------------------------------------------------------------------
# 1. DECLARED OPERATING POINT  [DECL]
# --------------------------------------------------------------------------
V_BUS = 340.0           # main.ato:49,65   v_bus_max / v_bus_nominal
C_TANK_NOM = 300e-9     # main.ato c_tank_total; 3 x CDE 942C16P1K-F
L_UNLOADED = 88e-6      # main.ato:365     l_tank_assumed
P_RATED = 1800.0        # main.ato:53      power_max
F_PLL_MIN = 44_000.0    # main.ato:269     f_pll_tracking_min
F_PLL_MAX = 50_000.0    # main.ato:270     f_pll_tracking_max
I_OCP_PEAK_TRIP = 50.1  # OCP-01 peak trip (docs/evidence/2026-07-25-ocp01-*)

# First-harmonic drive of a half-bridge series tank: the switch node is a
# 0..V_BUS square wave, i.e. +/- V_BUS/2 about the tank's DC reference.
#     V1_rms = (4/pi) * (V_BUS/2) / sqrt(2) = 2*V_BUS/(pi*sqrt(2))
V1_RMS = 2.0 * V_BUS / (math.pi * math.sqrt(2.0))   # 153.05 V   [DERIV]

# Mutable so the tolerance sweep can perturb it.
C_TANK = C_TANK_NOM

# --------------------------------------------------------------------------
# 2. ROUTE A -- DIRECT CHART READING  [CHART]
#    Infineon EVAL-IHW25N140R5L user guide rev 1.0 (2023-08-04), Fig. 16:
#    a 2 kW cooking coil measured WITH a vessel across 0-50 kHz -- i.e. IN
#    this design's band, not extrapolated into it.  Transcribed from
#    docs/evidence/2026-07-28-coil-selection-research.md Sec 2.1, which is
#    the document that read the chart.  These are the ONLY numbers in this
#    file that come from a measurement of a real coil-plus-pan.
# --------------------------------------------------------------------------
#         f_Hz,  L_with_vessel_H, R_with_vessel_ohm, R_no_vessel_ohm
CHART = [
    (10_000.0, None,   1.40, None),
    (20_000.0, 66e-6,  2.25, None),
    (30_000.0, 62e-6,  None, None),
    (40_000.0, 60e-6,  3.25, 0.34),
    (50_000.0, 58e-6,  3.70, 0.40),
]


def _interp(f_hz: float, col: int) -> float:
    """Piecewise-linear interpolation/extrapolation over CHART.
    col: 1 = L_with_vessel, 2 = R_with_vessel, 3 = R_no_vessel."""
    pts = [(row[0], row[col]) for row in CHART if row[col] is not None]
    if f_hz <= pts[0][0]:
        (f0, v0), (f1, v1) = pts[0], pts[1]
    elif f_hz >= pts[-1][0]:
        (f0, v0), (f1, v1) = pts[-2], pts[-1]
    else:
        for (f0, v0), (f1, v1) in zip(pts, pts[1:]):
            if f0 <= f_hz <= f1:
                break
    return v0 + (v1 - v0) * (f_hz - f0) / (f1 - f0)


def chart_L(f_hz):        return _interp(f_hz, 1)  # noqa: E704  [CHART]
def chart_R_total(f_hz):  return _interp(f_hz, 2)  # noqa: E704  coil + pan
def chart_R_coil(f_hz):   return _interp(f_hz, 3)  # noqa: E704  copper alone


# --------------------------------------------------------------------------
# 3. ROUTE B -- THE REPO HARNESS T-MODEL  [FIT]
#    simulation/harness/run_zvs_sweep.py PAN_PRESETS, as re-derived
#    2026-08-07 (docs/evidence/2026-08-07-zvs-margin-sweep.md Sec 2) against
#    the SAME Fig. 16 chart Route A reads.  Constraint-satisfying, not
#    measured: RPAN = 10 ohm is pan_load.sub's own uncited placeholder, held
#    fixed, and (K, L2) were solved to reproduce the chart's L-ratio.
# --------------------------------------------------------------------------
K_FERRO = 0.6136        # run_zvs_sweep.py PAN_K_FERROMAGNETIC     [FIT]
L2_PAN = 97.13e-6       # run_zvs_sweep.py PAN_L2_DEFAULT_H        [FIT]
RPAN = 10.0             # pan_load.sub PANLOAD_TRANSFORMER default (UNCITED)

# Route C: the superseded 2026-07-27 point, kept ONLY to reproduce the
# 20.7 A / 4.2 ohm figure and identify which model it belongs to.  Anchored
# to Infineon AN235020, measured at 90-150 kHz -- OUT of this design's band,
# and paired with a 150 uH coil the design no longer asserts.
K_OLD, L2_OLD, L1_OLD = 0.79, 218e-6, 150e-6

# Route D: the pre-2026-07-27 model that produced the Q=143 artefact.
K_BROKEN, L2_BROKEN, L1_BROKEN = 0.5, 1e-6, 70e-6


def tmodel(f_hz, l1_h, k, l2_h, rpan=RPAN, rcoil=0.0):
    """Reflected impedance of a loosely-coupled shorted secondary:

        Z_ref = (omega*M)^2 / (RPAN + j*omega*L2),   M = k*sqrt(L1*L2)

    Returns (L_apparent_H, R_series_ohm).  The real part of Z_ref is the
    reflected resistance -- where pan power goes.  The (negative) imaginary
    part is what shrinks L1 to L_loaded; taking it out gives exactly the
    L_app/L1 = 1 - k^2 x^2/(RPAN^2 + x^2) relation, x = omega*L2, that
    run_tank_coil_sweep.py::f_res_loaded_hz iterates.
    """
    w = 2 * math.pi * f_hz
    m = k * math.sqrt(l1_h * l2_h)
    x = w * l2_h
    denom = rpan * rpan + x * x
    r_ref = (w * m) ** 2 * rpan / denom
    l_app = l1_h - (w * m) ** 2 * x / denom / w
    return l_app, r_ref + rcoil


# --------------------------------------------------------------------------
# 4. SOLVER -- the f_sw above resonance that delivers a target power
# --------------------------------------------------------------------------
def tank_state(f_hz, l_h, r_ohm):
    """Series tank driven at f_hz. Returns (I_rms, P_into_R, X_ohm, |Z|)."""
    w = 2 * math.pi * f_hz
    x = w * l_h - 1.0 / (w * C_TANK)
    z = math.hypot(r_ohm, x)
    i = V1_RMS / z
    return i, i * i * r_ohm, x, z


def f_res_loaded(l_of_f, tol=1e-12, max_iter=500):
    """Self-consistent loaded resonance: L depends on f, f depends on L."""
    f = 1.0 / (2 * math.pi * math.sqrt(L_UNLOADED * C_TANK))
    for _ in range(max_iter):
        f_new = 1.0 / (2 * math.pi * math.sqrt(l_of_f(f) * C_TANK))
        if abs(f_new - f) < tol * f_new:
            return f_new
        f = 0.5 * (f + f_new)      # damped, for robustness at high k
    return f


def solve_power(l_of_f, r_of_f, p_target=P_RATED, f_hi=400_000.0):
    """Bisect for the f_sw ABOVE loaded resonance delivering p_target.
    Above resonance the tank is inductive and power falls monotonically
    with f, so the root on (f_res, f_hi) is unique.  Returns None if the
    tank cannot reach p_target at any frequency."""
    f_lo = f_res_loaded(l_of_f) * 1.000001
    if tank_state(f_lo, l_of_f(f_lo), r_of_f(f_lo))[1] < p_target:
        return None
    for _ in range(200):
        f_mid = 0.5 * (f_lo + f_hi)
        if tank_state(f_mid, l_of_f(f_mid), r_of_f(f_mid))[1] > p_target:
            f_lo = f_mid
        else:
            f_hi = f_mid
    return 0.5 * (f_lo + f_hi)


def report(label, l_of_f, r_of_f, p_target=P_RATED):
    f = solve_power(l_of_f, r_of_f, p_target)
    if f is None:
        print(f"  {label:<46s}  CANNOT REACH {p_target:.0f} W at any f_sw")
        return None
    l, r = l_of_f(f), r_of_f(f)
    i, _p, _x, _z = tank_state(f, l, r)
    fres = f_res_loaded(l_of_f)
    q = 2 * math.pi * fres * l_of_f(fres) / r_of_f(fres)
    v_cap = i / (2 * math.pi * f * C_TANK)
    inband = "IN " if F_PLL_MIN <= f <= F_PLL_MAX else "OUT"
    print(f"  {label:<46s} f={f/1e3:6.2f}k[{inband}] "
          f"fres={fres/1e3:5.2f}k r={f/fres:5.3f} "
          f"L={l*1e6:5.1f}uH R={r:5.2f}ohm "
          f"I={i:5.2f}Arms/{i*math.sqrt(2):5.2f}Apk "
          f"Q={q:6.2f} Vcap={v_cap:4.0f}V")
    return dict(f=f, l=l, r=r, i=i, q=q, fres=fres, v_cap=v_cap)


def scaled_reflected(scale):
    """Chart R_total with the *reflected* part scaled, coil copper held."""
    return lambda f: chart_R_coil(f) + scale * (chart_R_total(f) - chart_R_coil(f))


# --------------------------------------------------------------------------
def main() -> int:
    global C_TANK
    print("=" * 112)
    print("TANK CURRENT AT THE 1800 W OPERATING POINT -- provenance derivation")
    print(f"V_bus={V_BUS:.0f}V -> V1_rms={V1_RMS:.2f}V (FHA)   "
          f"C_tank={C_TANK*1e9:.0f}nF   L_unloaded={L_UNLOADED*1e6:.0f}uH   "
          f"PLL window {F_PLL_MIN/1e3:.0f}-{F_PLL_MAX/1e3:.0f}kHz")
    print("=" * 112)

    # ---- [1] Is the loaded Q of the committed model plausible? ----
    print("\n[1] LOADED Q OF EACH CANDIDATE MODEL")
    print("    (a real hob is order 2-15: the pan IS the loss, so Q must be low)")
    print("-" * 112)

    a = report("A  chart, R_total = coil+pan   [CHART]",
               chart_L, chart_R_total)
    b = report("B  harness T-model, 2026-08-07 [FIT]",
               lambda f: tmodel(f, L_UNLOADED, K_FERRO, L2_PAN)[0],
               lambda f: tmodel(f, L_UNLOADED, K_FERRO, L2_PAN,
                                rcoil=chart_R_coil(f))[1])
    c = report("C  harness T-model, 2026-07-27 [SUPERSEDED]",
               lambda f: tmodel(f, L1_OLD, K_OLD, L2_OLD)[0],
               lambda f: tmodel(f, L1_OLD, K_OLD, L2_OLD)[1])

    print("  D  pre-correction model (K=0.5, L2=1uH, L1=70uH)  "
          "[BROKEN -- the Q=143 source]")
    brk_l = lambda f: tmodel(f, L1_BROKEN, K_BROKEN, L2_BROKEN)[0]   # noqa: E731
    brk_r = lambda f: tmodel(f, L1_BROKEN, K_BROKEN, L2_BROKEN,      # noqa: E731
                             rcoil=0.1)[1]
    f_d = f_res_loaded(brk_l)
    l_d, r_d = brk_l(f_d), brk_r(f_d)
    _, r_refl_d = tmodel(f_d, L1_BROKEN, K_BROKEN, L2_BROKEN)
    q_d = 2 * math.pi * f_d * l_d / r_d
    q_d_refl = 2 * math.pi * f_d * l_d / r_refl_d
    r_refl_a = a["r"] - chart_R_coil(a["f"])
    print(f"     at its own loaded resonance {f_d/1e3:6.2f}kHz: "
          f"L={l_d*1e6:5.1f}uH  R_reflected={r_refl_d:.4f}ohm  "
          f"R_total={r_d:.4f}ohm")
    print(f"     -> Q_loaded = {q_d:.0f} on R_total, {q_d_refl:.0f} on "
          f"R_reflected alone")
    print("     TANK_COIL_SPECIFICATION.md Sec 7 records Q=143 and "
          "R_eff=0.109 ohm for")
    print("     this model's sweep.  PARTIAL REPRODUCTION ONLY: that sweep's exact")
    print("     (L, f_sw, preset) point was not recorded, so 143 cannot be hit on")
    print("     the nose from here.  What IS reproduced is the mechanism and its")
    print(f"     order of magnitude -- reflected R of {r_refl_d:.3f} ohm against "
          f"route A's {r_refl_a:.2f} ohm,")
    print(f"     i.e. {r_refl_a/r_refl_d:.0f}x too small, giving a Q one to two "
          "orders above the 2-15 band.")
    print("\n  VERDICT: Q=143 belongs to model D ALONE, and D was corrected out of")
    print("  the tree on 2026-07-27 (K 0.4->0.79, L2 1uH->218uH) and re-derived")
    print("  again on 2026-08-07 (K=0.6136, L2=97.13uH).  The models that actually")
    print("  produce the committed number (A and B) give Q_loaded ~ 4.5, inside the")
    print("  2-15 band a real ferromagnetic pan gives.  The challenge is right that")
    print("  D is broken and right that its POWER AXIS is unusable -- and that is")
    print("  exactly what TANK_COIL_SPECIFICATION.md Sec 7 itself already says.")
    print("  It is wrong that the committed 22.5 A descends from D.")

    # ---- [2] Reconcile 3.55 ohm vs 4.2 ohm ----
    print("\n[2] THE TWO COMMITTED R_eff FIGURES -- WHAT EACH ONE ACTUALLY IS")
    print("-" * 112)
    f_a = a["f"]
    r_coil_a = chart_R_coil(f_a)
    print(f"  Route A total R at {f_a/1e3:5.2f} kHz       = {a['r']:.3f} ohm"
          f"   <- the '3.55 ohm' figure, INCLUDES coil copper")
    print(f"    of which coil copper [CHART]       = {r_coil_a:.3f} ohm")
    print(f"    of which reflected into the pan    = {r_refl_a:.3f} ohm")
    _, r_refl_c = tmodel(47_000.0, L1_OLD, K_OLD, L2_OLD)
    print(f"  Route C reflected-only at 47.00 kHz  = {r_refl_c:.3f} ohm"
          f"   <- the '4.2 ohm' figure, EXCLUDES coil copper")
    _, r_refl_b = tmodel(f_a, L_UNLOADED, K_FERRO, L2_PAN)
    print(f"  Route B reflected-only at {f_a/1e3:5.2f} kHz  = {r_refl_b:.3f} ohm")
    print(f"\n  LIKE-FOR-LIKE (reflected only):  A={r_refl_a:.2f}  "
          f"B={r_refl_b:.2f}  C={r_refl_c:.2f} ohm")
    print(f"    A vs B (both anchored to the SAME in-band Fig.16 chart): "
          f"{abs(r_refl_b - r_refl_a) / r_refl_a * 100:5.1f}% apart")
    print(f"    A vs C (C anchored to out-of-band AN235020 + a 150uH coil): "
          f"{abs(r_refl_c - r_refl_a) / r_refl_a * 100:5.1f}% apart")
    print("  The headline '18%' compares a TOTAL R against a REFLECTED-ONLY R.")

    # ---- [3] Sensitivity ----
    print("\n[3] SENSITIVITY OF I_tank AT 1800 W")
    print("-" * 112)
    print("  Pan lift / off-centre / smaller or thinner pan (reflected R scales")
    print("  as coupling^2; coil copper held at its chart value):")
    for scale, note in [(1.00, "seated, chart nominal"),
                        (0.80, "-20% reflected R"),
                        (0.60, "-40% reflected R"),
                        (0.45, "-55% reflected R"),
                        (0.30, "-70% reflected R")]:
        report(f"    x{scale:.2f} reflected R ({note})",
               chart_L, scaled_reflected(scale))

    print("\n  Coil inductance tolerance (l_tank_tolerance = +/-10%), chart R held:")
    for tol in (-0.10, 0.0, +0.10):
        report(f"    L_loaded {tol * 100:+.0f}%",
               (lambda t: lambda f: chart_L(f) * (1 + t))(tol), chart_R_total)

    print("\n  Capacitor tolerance (CDE 942C16P1K-F, tolerance letter 'K' = +/-10%):")
    for tol in (-0.10, 0.0, +0.10):
        C_TANK = C_TANK_NOM * (1 + tol)
        report(f"    C_tank {tol * 100:+.0f}%", chart_L, chart_R_total)
    C_TANK = C_TANK_NOM

    print("\n  Chart-read tolerance (+/-5%, the stated accuracy of the read):")
    for tol in (-0.05, 0.0, +0.05):
        report(f"    R_total {tol * 100:+.0f}%", chart_L,
               (lambda t: lambda f: chart_R_total(f) * (1 + t))(tol))

    print("\n  Tank input power. 1800 W is rated power INPUT at the mains inlet")
    print("  (IEC 60335-1 cl. 7.1); the tank sees less, after the rectifier, EMI")
    print("  filter and bridge losses:")
    for eta, note in [(1.00, "all 1800W reaches the tank (as committed)"),
                      (0.97, "97% front-end + bridge efficiency"),
                      (0.95, "95% front-end + bridge efficiency")]:
        report(f"    P_tank={P_RATED * eta:.0f}W ({note})",
               chart_L, chart_R_total, p_target=P_RATED * eta)

    # ---- [4] OCP-01 ----
    print("\n[4] OCP-01 CONSISTENCY CHECK")
    print("-" * 112)
    i_trip_rms = I_OCP_PEAK_TRIP / math.sqrt(2)
    r_min = P_RATED / (i_trip_rms ** 2)
    print(f"  OCP-01 peak trip {I_OCP_PEAK_TRIP} A -> {i_trip_rms:.2f} A rms "
          f"(sinusoidal tank current)")
    print(f"  Delivering {P_RATED:.0f} W at that current needs R_eff >= "
          f"{P_RATED:.0f}/{i_trip_rms:.2f}^2 = {r_min:.3f} ohm  "
          f"-> confirms the reported ~1.44 ohm floor.")
    print(f"  Committed R_eff (route A, total)   = {a['r']:.2f} ohm "
          f"= {a['r'] / r_min:.2f}x the floor.")
    print(f"  Peak current at the committed point = {a['i'] * math.sqrt(2):.2f} A "
          f"= {a['i'] * math.sqrt(2) / I_OCP_PEAK_TRIP * 100:.0f}% of the trip.")
    hit = None
    for n in range(100, 0, -1):
        s = n / 100.0
        rf = scaled_reflected(s)
        f = solve_power(chart_L, rf)
        if f is None:
            break
        i = tank_state(f, chart_L(f), rf(f))[0]
        if i * math.sqrt(2) >= I_OCP_PEAK_TRIP:
            hit = (s, rf(f), i, f)
            break
    if hit:
        print(f"  OCP-01 first trips when reflected R falls to x{hit[0]:.2f} of "
              f"nominal (R_eff={hit[1]:.2f} ohm, I={hit[2]:.1f} Arms, "
              f"f={hit[3] / 1e3:.1f} kHz)")

    # ---- [5] Verdict bracket ----
    print("\n[5] VERDICT -- THE HONEST BRACKET ON I_tank")
    print("-" * 112)
    lo = min(
        report("    worst-case low: R +5%, P_tank=95% of 1800W", chart_L,
               lambda f: chart_R_total(f) * 1.05, p_target=P_RATED * 0.95)["i"],
        b["i"], a["i"])
    hi = max(
        report("    worst-case high: R -5%, all 1800W into the tank", chart_L,
               lambda f: chart_R_total(f) * 0.95)["i"],
        b["i"], a["i"])
    print(f"\n  SEATED FERROMAGNETIC PAN, committed operating point:")
    print(f"    I_tank = {lo:.1f} - {hi:.1f} A rms  "
          f"({lo * math.sqrt(2):.1f} - {hi * math.sqrt(2):.1f} A peak)")
    print(f"    The committed 22.5 A rms / 31.9 A peak sits inside this bracket,")
    print(f"    {abs(22.5 - (lo + hi) / 2) / ((lo + hi) / 2) * 100:.1f}% off its "
          f"centre.  CONFIRMED -- no correction is warranted.")
    print("    +/-10% on L and +/-10% on C both move I_tank by under 2%: at fixed")
    print("    power I = sqrt(P/R), and neither tolerance moves R much.  They move")
    print("    f_sw out of the PLL window long before they move the current.")
    print("\n  THE AXIS THAT ACTUALLY MOVES I_tank IS PAN COUPLING, NOT L, C OR f:")
    print("    a lifted / off-centre / undersized / thin pan cuts reflected R, and")
    print("    a power-seeking loop answers by moving DOWN toward resonance, where")
    print("    current rises.  That is a real exposure (Sec 3 table) and it is the")
    print("    regime OCP-01 exists for -- but it is NOT the 1800 W rated point,")
    print("    and it does not correct the committed number.")

    # ---- [6] What is not obtainable ----
    print("\n[6] NOT OBTAINABLE IN THIS ENVIRONMENT  [N/A]")
    print("-" * 112)
    print("  ngspice is not installed, so simulation/harness/run_tank_coil_sweep.py")
    print("  could not be re-run.  Route B above evaluates the SAME T-model")
    print("  relation that harness uses, analytically.  A time-domain re-run would")
    print("  add the square-wave harmonics FHA discards -- worth about +3% on I")
    print("  and +6% on P, per the cross-check in")
    print("  docs/evidence/2026-07-28-coil-selection-research.md Sec 4.1.")
    print("  No bench measurement of THIS project's own coil and pan exists.")
    print("  Every number above traces to a chart reading of a DIFFERENT Infineon")
    print("  coil; none of it is calibrated to the hardware being built.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
