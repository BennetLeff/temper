#!/usr/bin/env python3
"""Bus capacitance re-derivation and part selection for C_BUS1/1B/2/2B.

Companion to docs/evidence/2026-08-19-bus-capacitance-selection.md.

WHAT THIS ADDS over the two committed predecessors
  - docs/evidence/2026-07-26-bus-capacitor-ripple.md        (verdict FAILS, 4.2-5.8x)
  - docs/evidence/2026-08-19-input-stage-power-ceiling.md   (commit fe9cf6752,
    branch analysis/input-stage-power-ceiling; time-domain confirmation,
    4.64-4.87x, ceiling 133-158 W, and the LF/HF split)

  1. A DERIVED ripple-VOLTAGE constraint (sec.2).  Both predecessors optimise
     ripple current alone and treat the lower bound on C as unknown / blocked.
     This script derives the lower bound from the half-bridge's own frequency-
     control headroom: f_pll_tracking_min = 44 kHz (main.ato:269, mirrored in
     firmware/components/control/pll_control.h:104, gate
     scripts/check_pll_range_consistency.py) is the ZVS cliff.  Below it the
     series tank is capacitive and the 1200 V IGBT half-bridge hard-switches.
     A sagging bus is compensated by lowering f_sw; the 47 kHz -> 44 kHz travel
     is therefore a FINITE energy budget, and that budget bounds ripple.
  2. A self-consistent C-vs-power solve under BOTH HF-bypass cases (sec.4).
  3. The C window (voltage floor vs current ceiling vs BusDischarge) (sec.5).

REPRODUCE:  python3 docs/evidence/2026-08-19-bus-capacitance-selection.py
Pure stdlib.  Reads no repo state, loads no compiled extension -- `make
venv-isolate` is NOT required, stated explicitly per the task's environment
rule.  pcb/temper.kicad_pcb is never opened.

PROVENANCE TAGS used in output: [datasheet] read on a manufacturer document;
[repo] a committed value in this repository; [derived] computed here from the
former two; [estimated] a bracket with no published source, never blended into
a datasheet figure.
"""

import math
from dataclasses import dataclass

# =============================================================================
# 1. INPUTS
# =============================================================================

# --- line ---------------------------------------------------------------
V_LINE_RMS = 120.0        # [repo] main.ato:52  v_ac_nominal = 120V
V_LINE_LO = 100.0         # [repo] main.ato:56  assert v_ac_nominal within 100V to 130V
V_LINE_HI = 130.0         # [repo] main.ato:56
F_LINE = 60.0             # [repo] main.ato:62  f_line = 60Hz
V_PK = V_LINE_RMS * math.sqrt(2.0)
OMEGA = 2.0 * math.pi * F_LINE
T_LINE = 1.0 / F_LINE

# --- declared operating point --------------------------------------------
P_OUT_DECLARED = 1800.0   # [repo] main.ato:53 power_max, :494 p_output_max
ETA_CENTRAL = 0.90        # [repo] main.ato:500 eta_min = 0.90
ETA_BEST = 0.92
ETA_WORST = 0.85          # [repo] main.ato:501 assert eta_min >= 0.85

# --- as-built bank --------------------------------------------------------
C_UNIT_ASBUILT = 1800e-6  # [repo] modules.ato:819-846, 4x EKMQ251VSN182MA50S
N_PARALLEL = 2
C_HALF_ASBUILT = C_UNIT_ASBUILT * N_PARALLEL      # 3600 uF per half-bus

# --- series resistance, steady state (NTC bypassed by K1) ----------------
# Vendored unchanged from docs/evidence/2026-08-19-input-stage-power-ceiling.py
# (commit fe9cf6752).  See that file for the per-term provenance; summarised:
R_FUSE = (3.750e-3, 5.729e-3)      # [datasheet] Schurter FST 5x20, 16 A row
R_CMC = (14.2e-3, 14.2e-3)         # [datasheet] TDK B82726S2163N030, 2x7.1 mOhm
R_K1_CONTACT = (5e-3, 20e-3)       # [estimated] TE publishes no contact-R line
R_PCB = (3e-3, 15e-3)              # [estimated] AC-mains copper, no length extracted
R_EXT_BRANCH = (0.05, 0.40)        # [estimated] branch + service impedance

D_MODEL = ((0.90, 40.0e-3), (0.70, 33.3e-3))   # [estimated] split of two
# Fairchild MUR1560 Rev.B VF max points (1.5V@15A/25C, 1.2V@15A/150C).

# --- the installed capacitor, EKMQ251VSN182MA50S -------------------------
# [datasheet] United Chemi-Con CAT.No.E1001E, KMQ series.  Quoted in the
# committed 2026-07-26 ripple doc sec.1 (verified 2026-07-16).  Re-used.
CAP_I_RIPPLE_RATED = 2.70     # Arms at 105 C, 120 Hz
CAP_V_RATED = 250.0           # Vdc
CAP_TAN_DELTA = 0.15          # max, 20 C / 120 Hz, 160-250 Vdc group
CAP_FM_TABLE = [(50.0, 0.81), (120.0, 1.00), (300.0, 1.17),
                (1e3, 1.32), (10e3, 1.45), (50e3, 1.50)]

# --- BusDischarge (the UPPER bound on C) ---------------------------------
# [repo] modules.ato:1234-1246 -- 2x AC05000003901JAC00 3.9k +/-5% 5W per
# string = 7.8k nominal per half-bus; docstring modules.ato:1126-1140.
R_DIS_NOM = 7800.0
R_DIS_TOL = 0.05
DIS_TARGET_S = 60.0           # [repo] modules.ato comments 445/636/1128.
DIS_LN_RATIO = math.log(170.0 / 34.0)   # 170V -> <34V  = ln(5) = 1.6094
CAP_C_TOL_ELECTROLYTIC = 0.20  # [datasheet] KMQ +/-20%, via DigiKey product page

# --- tank, for the ripple-VOLTAGE constraint -----------------------------
# All [repo], elec/src/main.ato:
L_TANK_UNLOADED = 88e-6       # :365  l_tank_assumed = 88uH
L_PAN_RATIO = 0.68            # :434  l_pan_loaded_ratio = 0.68
C_TANK = 300e-9               # :385  c_tank_total = 300nF
L_TANK_TOL = 0.10             # :~370 l_tank_tolerance
C_TANK_TOL = 0.10             # :~455 c_tank_tolerance (CDE 942C16P1K-F, 'K')
F_SW_NOM = 47.0e3             # :134  f_switching = 47kHz
F_PLL_MIN = 44.0e3            # :269  f_pll_tracking_min; == PLL_MIN_FREQ_HZ
F_PLL_MAX = 50.0e3            # :270  f_pll_tracking_max; == PLL_MAX_FREQ_HZ
ZVS_CLIFF_RATIO = 1.05        # :~174 docs/hardware/TANK_COIL_SPECIFICATION.md
V_BUS_DECLARED = 340.0        # :65   v_bus_nominal = 340V
P_AT_47K_DECLARED = 1804.0    # :88   "at ratio~=1.25 ... it delivers ~1804W"
I_TANK_PK_AT_47K = 28.76      # :89   "28.76A" peak, vs OCP-01's 50.1A trip
V_BUS_RIPPLE_MAX_DECLARED = 20.0   # :68 v_bus_ripple_max = 20V

# --- HF (switching) term at the capacitors -------------------------------
# TWO anchors for the tank rms current at the declared 1800 W, and they
# DISAGREE by 1.74x.  Both are [repo]; the disagreement is a finding, not a
# modelling choice, and both are carried through every table below.
I_TANK_RMS_OCP = (35.4, 40.0)
#   [repo] docs/evidence/2026-07-26-ocp01-vs-full-power-current.md, used by
#   BOTH committed predecessors.  main.ato:624-625 states outright what 35.4 A
#   is:  i_ocp_trip_peak = 50.1A  /  i_ocp_trip_rms = 35.4A  "# peak / sqrt(2),
#   sinusoidal tank".  It is the OVER-CURRENT TRIP THRESHOLD expressed in rms.
#   40 A is a cited "typical 1.8 kW hob".  NEITHER is an operating point -- a
#   trip threshold is by construction ABOVE the current it protects.
I_TANK_RMS_MYDERIV = I_TANK_PK_AT_47K / math.sqrt(2.0)   # 20.34 A
#   [derived] from main.ato:82's own simulated 28.76 A PEAK at the 47 kHz /
#   1804 W point, sinusoidal tank.  Kept only as an independent cross-check.
I_TANK_RMS_COMMITTED = 22.5
#   [repo] docs/evidence/2026-08-15-ocp-threshold-decision.md sec.2, which
#   SUPERSEDES the OCP-derived figures above:  "1800 W tank current =
#   22.5 A rms / 31.9 A peak (independent first-harmonic solve, R_eff
#   3.55 ohm @ 46.6 kHz); ngspice harness: 20.7 A rms / 28.7 A peak
#   (R_eff 4.2 ohm)".  Sourced there to 2026-07-28-coil-selection-research.md
#   sec.4.2 and TANK_COIL_SPECIFICATION.md sec.3/8; committed in
#   elec/src/modules.ato:585-593.  That document independently reaches this
#   file's sec.3 finding: it marks the 40 A figure "UNCITED, not
#   corroborated" and states 35.4 A is the TRIP, not an operating current.
I_TANK_RMS_NGSPICE = 20.7
#   [repo] same source, ngspice-harness value; the LOW end of the bracket.
#   This file's independent 20.34 A (above) lands within 2% of it.
I_TANK_RMS_47K = I_TANK_RMS_COMMITTED
#   [derived] from main.ato:82's own simulated 28.76 A PEAK at the 47 kHz /
#   1804 W point, assuming a sinusoidal tank current (series-resonant tank
#   above resonance -- standard, and the same assumption A6 already makes).
CAP_HF_SHARE = 0.3536         # [repo] ripple doc assumption A6 = (1/sqrt2)/2

# --- NTC / inrush ---------------------------------------------------------
NTC_R_COLD = 10.0             # [datasheet] Ametherm SL32 10015, 10 ohm +/-20% @25C
NTC_R_AT_IMAX = 0.05          # [datasheet] 0.05 ohm at 100% of max current
NTC_I_MAX = 15.0              # [datasheet] 15 A max steady state
NTC_JOULE_RATING = 150.0      # [datasheet] 150 J


# =============================================================================
# 2. THE DOUBLER SIMULATION  (vendored from commit fe9cf6752, unmodified
#    except for the two extra bus-voltage moments this analysis needs)
# =============================================================================

@dataclass
class Op:
    p_out: float
    p_in: float
    i_line_rms: float
    i_line_pk: float
    pf: float
    theta_deg: float
    v_bus_avg: float
    v_bus_pp: float
    v_bus_ms: float           # NEW: cycle-mean of v_bus^2  (the FFPC input)
    v_half_avg: float
    v_half_pp: float
    i_diode_pk: float
    i_cap_unit_rms: float
    i_cap_unit_eq_dft: float
    p_delivered_half: float


def cap_freq_multiplier(f: float, tbl=None) -> float:
    """Allowed-ripple multiplier vs the 120 Hz rating, log-interpolated.

    [datasheet] table + [derived] interpolation.  Endpoints held flat -- no
    extrapolation beyond the published table is invented.
    """
    tbl = tbl if tbl is not None else CAP_FM_TABLE
    if f <= tbl[0][0]:
        return tbl[0][1]
    if f >= tbl[-1][0]:
        return tbl[-1][1]
    for (f0, m0), (f1, m1) in zip(tbl, tbl[1:]):
        if f0 <= f <= f1:
            w = (math.log(f) - math.log(f0)) / (math.log(f1) - math.log(f0))
            return m0 + w * (m1 - m0)
    raise AssertionError("unreachable")


FM_SW = cap_freq_multiplier(F_SW_NOM)     # ~1.4966, log-interp 10k->50k
R_EQ_COMMITTED = 3.55
#   [repo] docs/evidence/2026-08-15-ocp-threshold-decision.md sec.2:
#   "R_eff ... 3.55 | First-harmonic solve at the committed 300 nF /
#   46.6 kHz / 1800 W point | DERIVED (committed operating point)".  That
#   document also states outright "R_eff is NOT computable from the repo;
#   it must be measured", and brackets it against Infineon's 3.25 ohm
#   chart reading.  This file's own independent current anchor gives
#   3.99 ohm and its power anchor 5.31 ohm -- 3.55 sits just below the
#   bracket, so the bracket is WIDENED to include it rather than argued with.
R_BRACKET_G = (3.55, 5.31)   # overwritten by main(); keeps the module importable

# --- film HF bypass, branch fix/hf-bypass-commutation-loop (db44c3aa0) ---
# 4x Vishay MKP1848C71250JY5, 120 uF/500 V, 2 in parallel per half-bus,
# placed hv_plus->midpoint and midpoint->hv_minus.
FILM_V_RIPPLE_MAX = 100.0
#   [datasheet, via db44c3aa0 sec.3] MKP1848C Quick Reference Data,
#   "Max applied ripple voltage = 0.2 x U_NDC = 100 V p-p".  The film sits
#   across ONE HALF-BUS, so the quantity to compare is v_half_pp, NOT the
#   full-bus p-p.  Re-derived independently here -- see sec.5b.
HF_RESIDUAL_ON_ELEC = (0.058, 0.692)
#   [repo, db44c3aa0 sec.5] "Result across the whole corner set:
#   I_elec / I_0 = 0.058 ... 0.692".  CASE A IS THEREFORE NOT "HF = 0":
#   between 5.8% and 69.2% of the 47 kHz current still lands on the
#   electrolytics even with the bypass fitted.  Modelling Case A as zero
#   would overstate it, so both ends of that bracket are carried.


def simulate(p_in, rs, vf0, rd, c_half, v_pk=V_PK, load="cp",
             r_load=None, n_per_cycle=2000, n_cycles=30) -> Op:
    """Time-domain Delon doubler, constant-power load, forward Euler.

    Topology (elec/src/modules.ato:881-925):
        ac_l -> F1 -> L1.W1 -> {RT1 || K1} -> node A
        node A -> D1 -> hv_plus ; C_BUS1||C_BUS1B  hv_plus  -> gnd_ref
        hv_minus -> D2 -> node A ; C_BUS2||C_BUS2B gnd_ref -> hv_minus
        ac_n -> L1.W2 -> gnd_ref  (the doubler midpoint)
    Each bank recharges ONCE per 60 Hz cycle, not twice.
    """
    dt = T_LINE / n_per_cycle
    r_series = rs + rd
    droop0 = (p_in / 2.0) / max(v_pk - vf0, 1.0) * T_LINE / c_half
    v1 = max(v_pk - vf0 - droop0, 20.0)
    v2 = v1
    i_line = i_d1 = v1_s = v2_s = None
    for cyc in range(n_cycles):
        record = cyc == n_cycles - 1
        if record:
            i_line = [0.0] * n_per_cycle
            i_d1 = [0.0] * n_per_cycle
            v_src = [0.0] * n_per_cycle
            v1_s = [0.0] * n_per_cycle
            v2_s = [0.0] * n_per_cycle
        for k in range(n_per_cycle):
            t = k * dt
            vs = v_pk * math.sin(OMEGA * t)
            id1 = id2 = 0.0
            drive1 = vs - vf0 - v1
            if drive1 > 0.0:
                id1 = drive1 / r_series
            else:
                drive2 = -vs - vf0 - v2
                if drive2 > 0.0:
                    id2 = drive2 / r_series
            if load == "cp":
                il1 = (p_in / 2.0) / max(v1, 1.0)
                il2 = (p_in / 2.0) / max(v2, 1.0)
            else:
                il1 = max(v1, 0.0) / r_load
                il2 = max(v2, 0.0) / r_load
            v1 += (id1 - il1) / c_half * dt
            v2 += (id2 - il2) / c_half * dt
            v1 = max(v1, 1.0)
            v2 = max(v2, 1.0)
            if record:
                i_line[k] = id1 - id2
                i_d1[k] = id1
                v_src[k] = vs
                v1_s[k] = v1
                v2_s[k] = v2

    n = n_per_cycle
    i_rms = math.sqrt(sum(x * x for x in i_line) / n)
    i_pk = max(abs(x) for x in i_line)
    p_real = sum(v_src[k] * i_line[k] for k in range(n)) / n
    pf = p_real / (V_LINE_RMS * i_rms) if i_rms > 0 else 0.0
    theta = 360.0 * sum(1 for x in i_d1 if x > 0.0) / n

    v_bus = [v1_s[k] + v2_s[k] for k in range(n)]
    v_bus_ms = sum(v * v for v in v_bus) / n

    if load == "cp":
        i_cap = [i_d1[k] - (p_in / 2.0) / max(v1_s[k], 1.0) for k in range(n)]
        p_half = p_in / 2.0
    else:
        i_cap = [i_d1[k] - max(v1_s[k], 0.0) / r_load for k in range(n)]
        p_half = sum(v * v / r_load for v in v1_s) / n
    i_cap_bank = math.sqrt(sum(x * x for x in i_cap) / n)

    # Per-harmonic 120 Hz-equivalent: each spectral line divided by the
    # datasheet's own allowed-current multiplier AT ITS OWN frequency.
    eq2 = 0.0
    for h in range(1, 101):
        re = im = 0.0
        w = 2.0 * math.pi * h / n
        for k in range(n):
            ang = w * k
            re += i_cap[k] * math.cos(ang)
            im += i_cap[k] * math.sin(ang)
        rms_h = (2.0 / n * math.hypot(re, im)) / math.sqrt(2.0)
        eq2 += (rms_h / cap_freq_multiplier(h * F_LINE)) ** 2
    eq_dft = math.sqrt(eq2) / N_PARALLEL

    return Op(p_out=float("nan"), p_in=p_in, i_line_rms=i_rms, i_line_pk=i_pk,
              pf=pf, theta_deg=theta,
              v_bus_avg=sum(v_bus) / n, v_bus_pp=max(v_bus) - min(v_bus),
              v_bus_ms=v_bus_ms,
              v_half_avg=sum(v1_s) / n, v_half_pp=max(v1_s) - min(v1_s),
              i_diode_pk=max(i_d1),
              i_cap_unit_rms=i_cap_bank / N_PARALLEL,
              i_cap_unit_eq_dft=eq_dft,
              p_delivered_half=p_half)


def simulate_cr_at_power(p_in, rs, vf0, rd, c_half, v_pk=V_PK,
                         tol=0.006, **kw):
    """Constant-RESISTANCE load, with R re-tuned so the stage actually
    DELIVERS p_in.  Vendored from commit fe9cf6752.

    A constant-POWER load is the right 60 Hz-scale model at the as-built
    3600 uF, but it diverges once the bus sags far (the load demands ever
    more current from an ever-lower voltage).  Every capacitance SWEEP below
    therefore uses this form, so that each row delivers the SAME power and
    the comparison is apples-to-apples.  Same choice, same reason, as the
    predecessor's sec.4.
    """
    v_nom = max(v_pk - vf0, 1.0)
    r_hi = v_nom * v_nom / (p_in / 2.0)
    lo, hi = r_hi * 0.02, r_hi * 6.0
    best = None
    for _ in range(32):
        mid = math.sqrt(lo * hi)
        op = simulate(p_in, rs, vf0, rd, c_half, v_pk=v_pk, load="cr",
                      r_load=mid, **kw)
        best = op
        p_del = 2.0 * op.p_delivered_half
        if abs(p_del - p_in) <= tol * p_in:
            return op
        if p_del < p_in:
            hi = mid
        else:
            lo = mid
    return best


def rs_of(pick):
    i = 0 if pick == "lo" else 1
    return R_FUSE[i] + R_CMC[i] + R_K1_CONTACT[i] + R_PCB[i] + R_EXT_BRANCH[i]


@dataclass
class Case:
    name: str
    eta: float
    rs: float
    vf0: float
    rd: float
    i_tank_1800: float


def cases(tank_anchor):
    """tank_anchor: 'ocp' (the predecessors' 35.4-40 A) or '47k' (20.34 A)."""
    if tank_anchor == "ocp":
        lo, mid, hi = I_TANK_RMS_OCP[0], 37.7, I_TANK_RMS_OCP[1]
    else:
        lo, mid, hi = (I_TANK_RMS_NGSPICE, I_TANK_RMS_COMMITTED,
                       I_TANK_RMS_COMMITTED)
    return [
        Case("stiffest-line", ETA_BEST, rs_of("lo"), D_MODEL[1][0], D_MODEL[1][1], lo),
        Case("central", ETA_CENTRAL, 0.5 * (rs_of("lo") + rs_of("hi")), 0.80, 36.7e-3, mid),
        Case("softest-line", ETA_WORST, rs_of("hi"), D_MODEL[0][0], D_MODEL[0][1], hi),
    ]


# =============================================================================
# 3. THE RIPPLE-VOLTAGE CONSTRAINT  ("frequency-floor power ceiling", FFPC)
# =============================================================================
#
# MECHANISM, and where every term comes from:
#
# The half-bridge is a SERIES-RESONANT inverter under frequency control.  The
# tank returns to the doubler midpoint, so the switch node presents a square
# wave of amplitude V_bus/2 to the tank; its fundamental rms is
#       V1 = (4/pi)(V_bus/2)/sqrt(2) = sqrt(2)*V_bus/pi.
# First-harmonic approximation (the tank's own Q makes the harmonics
# negligible in the current, which is the standard justification):
#       P(V_bus, f) = V1^2 * R_eq / (R_eq^2 + X(f)^2),
#       X(f) = 2*pi*f*L_loaded - 1/(2*pi*f*C_tank).
# P falls as V_bus^2.  The control loop restores it by lowering f toward
# resonance -- but f may not go below f_pll_tracking_min = 44 kHz, which is
# NOT a tuning preference: main.ato:171-186 derives it as 1.05x the WORST-CASE
# loaded resonance, 1.05 being the ZVS cliff.  Below the loaded resonance the
# tank is capacitive and the bridge hard-switches a 1200 V IGBT half-bridge.
#
# Therefore the ripple-voltage budget is exactly the power the 47 kHz -> 44 kHz
# travel can buy back, and no more.  Formally, with the loop holding the
# CYCLE-MEAN power (see sec.3.3 for why cycle-mean and not instantaneous):
#
#       mean_over_line_cycle( V_bus(t)^2 )  >=  P_target / k44
#       k44 = (2/pi^2) * R_eq / (R_eq^2 + X(44 kHz)^2)
#
# That inequality is THE constraint.  It is a lower bound on capacitance
# because a smaller C deepens the sag and drops mean(V_bus^2).


def x_of(f, l_loaded=None, c_tank=None):
    l_loaded = l_loaded if l_loaded is not None else L_TANK_UNLOADED * L_PAN_RATIO
    c_tank = c_tank if c_tank is not None else C_TANK
    w = 2.0 * math.pi * f
    return w * l_loaded - 1.0 / (w * c_tank)


def f_res(l_loaded, c_tank):
    return 1.0 / (2.0 * math.pi * math.sqrt(l_loaded * c_tank))


def v1_rms(v_bus):
    return math.sqrt(2.0) * v_bus / math.pi


def r_eq_anchors():
    """Two independent calibrations of the tank's reflected resistance.

    Both anchors are [repo] values from main.ato:80-82, at the same declared
    operating point (340 V bus, 47 kHz).  Neither is a datasheet value and
    neither is invented here.
      (a) POWER anchor: P(340 V, 47 kHz) = 1804 W.  Quadratic -> two roots.
      (b) CURRENT anchor: I_tank = 28.76 A peak = 20.34 A rms at that point.
    """
    v1 = v1_rms(V_BUS_DECLARED)
    x = x_of(F_SW_NOM)
    # (a) P = v1^2 R/(R^2+X^2)  ->  P R^2 - v1^2 R + P X^2 = 0
    a, b, c = P_AT_47K_DECLARED, -v1 * v1, P_AT_47K_DECLARED * x * x
    disc = b * b - 4 * a * c
    roots = sorted(((-b - math.sqrt(disc)) / (2 * a), (-b + math.sqrt(disc)) / (2 * a)))
    # (b) |Z| = v1 / I  ->  R = sqrt(|Z|^2 - X^2)
    z = v1 / I_TANK_RMS_47K
    r_cur = math.sqrt(max(z * z - x * x, 0.0))
    return roots, r_cur, x, v1


def k44(r_eq, f_floor=F_PLL_MIN, l_loaded=None, c_tank=None):
    x = x_of(f_floor, l_loaded, c_tank)
    return (2.0 / math.pi ** 2) * r_eq / (r_eq * r_eq + x * x)


def p_at(r_eq, v_bus, f, l_loaded=None, c_tank=None):
    x = x_of(f, l_loaded, c_tank)
    return v1_rms(v_bus) ** 2 * r_eq / (r_eq * r_eq + x * x)


def r_max_from_G(g):
    """Max fractional sawtooth droop r whose mean-square loss the frequency
    headroom g = P(44k)/P(f_now) can exactly recover.

    For V(t) = Vpk(1 - r*s), s uniform on [0,1]:
        mean(V^2)/Vpk^2 = 1 - r + r^2/3.
    Solve (1 - r + r^2/3) * g = 1  ->  r^2 - 3r + 3(1 - 1/g) = 0.
    """
    c = 3.0 * (1.0 - 1.0 / g)
    disc = 9.0 - 4.0 * c
    if disc < 0:
        return float("nan")
    return (3.0 - math.sqrt(disc)) / 2.0


# =============================================================================
# 4. SELF-CONSISTENT CAPACITANCE / POWER SOLVE
# =============================================================================

def hf_per_cap_eq(case, p_out, n_parallel=N_PARALLEL, fm_sw=FM_SW,
                  scaling="sqrt", residual=1.0):
    """Per-capacitor 120 Hz-EQUIVALENT HF ripple, Case B (no HF bypass).

    I_tank scales as sqrt(P) for a series-resonant inverter into a fixed
    reflected resistance (P = I^2 R_eq).  The alternative I_tank ~ P is
    reported alongside in sec.4 of the .md, as the predecessor did.
    """
    s = (math.sqrt(max(p_out, 0.0) / P_OUT_DECLARED) if scaling == "sqrt"
         else max(p_out, 0.0) / P_OUT_DECLARED)
    i_tank = case.i_tank_1800 * s
    # A6: each half-bus bank carries the tank current only while its own
    # switch conducts.  Share is per BANK; divide again by n_parallel.
    hf_actual_bank = (1.0 / math.sqrt(2.0)) * i_tank * residual
    return (hf_actual_bank / n_parallel) / fm_sw


def total_per_cap_eq(op, case, p_out, hf_on, n_parallel=N_PARALLEL, fm_sw=FM_SW):
    """hf_on may be False (idealised HF=0), True (Case B, residual 1.0), or a
    float residual fraction in (0,1] for Case A with the bypass fitted."""
    lf = op.i_cap_unit_eq_dft * (N_PARALLEL / n_parallel)
    if hf_on is False:
        hf = 0.0
    else:
        res = 1.0 if hf_on is True else float(hf_on)
        hf = hf_per_cap_eq(case, p_out, n_parallel, fm_sw, residual=res)
    return math.hypot(lf, hf)


def op_at(case, p_out, c_half, v_pk=V_PK, mode="cp", **kw):
    """mode='cp' constant power (as-built operating point);
       mode='cr' constant resistance re-tuned to deliver p_out (sweeps)."""
    f = simulate if mode == "cp" else simulate_cr_at_power
    op = f(p_out / case.eta, case.rs, case.vf0, case.rd, c_half,
           v_pk=v_pk, **kw)
    op.p_out = p_out
    return op


def power_ceiling(case, c_half, hf_on, rating=CAP_I_RIPPLE_RATED,
                  n_parallel=N_PARALLEL, fm_sw=FM_SW,
                  lo=15.0, hi=2600.0, tol=1.0):
    """Highest P_out at which per-cap ripple current stays within `rating`."""
    def f(p):
        return total_per_cap_eq(op_at(case, p, c_half, mode="cr"), case, p,
                                hf_on, n_parallel, fm_sw) - rating
    if f(lo) > 0:
        return 0.0
    if f(hi) < 0:
        return hi
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if f(mid) > 0:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def c_min_for_ffpc(case, p_out, r_eq, v_pk=V_PK, lo=20e-6, hi=40000e-6):
    """Smallest C per half whose mean(V_bus^2) still meets the FFPC bound."""
    need = p_out / k44(r_eq)
    def f(c):
        return op_at(case, p_out, c, v_pk=v_pk, mode="cr").v_bus_ms - need
    if f(hi) < 0:
        return float("inf")     # not reachable at ANY capacitance
    if f(lo) > 0:
        return 0.0
    for _ in range(22):
        mid = math.sqrt(lo * hi)
        if f(mid) > 0:
            hi = mid
        else:
            lo = mid
    return math.sqrt(lo * hi)


def c_min_for_film_ripple(case, p_out, lo=100e-6, hi=8000e-6):
    """Smallest C/half whose HALF-BUS ripple stays within the film bypass
    capacitor's own 100 V p-p applied-ripple limit.  Independent re-derivation
    of the floor asserted on branch fix/hf-bypass-commutation-loop."""
    def v(c):
        return op_at(case, p_out, c, mode="cr").v_half_pp
    if v(hi) > FILM_V_RIPPLE_MAX:
        return float("inf")
    if v(lo) < FILM_V_RIPPLE_MAX:
        return 0.0
    for _ in range(20):
        mid = math.sqrt(lo * hi)
        if v(mid) > FILM_V_RIPPLE_MAX:
            lo = mid
        else:
            hi = mid
    return math.sqrt(lo * hi)


def c_max_busdischarge():
    """[repo] Largest NOMINAL C/half whose worst-case-tolerance discharge
    still clears 60 s.  Stacks R +5% and C +20%, as modules.ato:1136 does."""
    return DIS_TARGET_S / (DIS_LN_RATIO * R_DIS_NOM * (1 + R_DIS_TOL)
                           * (1 + CAP_C_TOL_ELECTROLYTIC))


# =============================================================================
# 5. REPORT
# =============================================================================

def hr(c="="):
    print(c * 78)


def main():
    hr()
    print("BUS CAPACITANCE RE-DERIVATION AND PART SELECTION -- C_BUS1/1B/2/2B")
    hr()

    # ---------------------------------------------------------------- sec.1
    print("\n1. TANK, AND THE TWO ANCHORS FOR R_eq  [repo -> derived]\n")
    l_loaded = L_TANK_UNLOADED * L_PAN_RATIO
    fr = f_res(l_loaded, C_TANK)
    print(f"   L_loaded = {L_TANK_UNLOADED*1e6:.0f}uH x {L_PAN_RATIO} "
          f"= {l_loaded*1e6:.2f} uH        [repo main.ato:365,434]")
    print(f"   C_tank   = {C_TANK*1e9:.0f} nF                        "
          f"[repo main.ato:385]")
    print(f"   f_res(loaded, nominal)   = {fr:9.1f} Hz   "
          f"(main.ato:96 says 37563.3 Hz)")
    fr_lo = f_res(l_loaded * (1 - L_TANK_TOL), C_TANK * (1 - C_TANK_TOL))
    fr_hi = f_res(l_loaded * (1 + L_TANK_TOL), C_TANK * (1 + C_TANK_TOL))
    print(f"   f_res worst case (-10%L,-10%C) = {fr_lo:9.1f} Hz  "
          f"x1.05 = {fr_lo*ZVS_CLIFF_RATIO:8.1f} Hz -> floor 44 kHz")
    print(f"   f_res best  case (+10%L,+10%C) = {fr_hi:9.1f} Hz")
    roots, r_cur, x47, v1 = r_eq_anchors()
    print(f"\n   V1_rms at V_bus=340V     = {v1:7.2f} V")
    print(f"   X(47 kHz)                = {x47:7.3f} ohm")
    print(f"   (a) POWER anchor  P=1804W  -> R_eq = "
          f"{roots[0]:.3f} or {roots[1]:.3f} ohm   [two roots]")
    print(f"   (b) CURRENT anchor I=20.34Arms -> R_eq = {r_cur:.3f} ohm")
    print(f"   -> the low power root ({roots[0]:.2f}) is the consistent one; "
          f"{roots[1]:.2f} implies")
    print(f"      I_tank = {v1/math.hypot(roots[1],x47):.1f} Arms, "
          f"contradicting main.ato:82's own 20.34 A.")
    print(f"   (c) COMMITTED  R_eff = {R_EQ_COMMITTED:.2f} ohm "
          f"[repo 2026-08-15-ocp-threshold-decision.md sec.2, first-harmonic")
    print(f"       solve at 300 nF / 46.6 kHz / 1800 W].  This file's own")
    print(f"       first-harmonic model, fed the committed 22.5 A, returns")
    print(f"       {r_cur:.2f} ohm instead -- i.e. THIS model's X(47 kHz) is larger")
    print(f"       than the committed solve's (which is taken at 46.6 kHz).")
    print(f"       The absolute power level is therefore model-dependent by")
    print(f"       ~13%; G below is a RATIO and moves only 1.43-1.63 across")
    print(f"       the whole R_eq bracket, which is why the constraint is")
    print(f"       reported on G.  That document also states outright that")
    print(f'       "R_eff is NOT computable from the repo; it must be measured".')
    R_BRACKET = (R_EQ_COMMITTED, roots[0])
    global R_BRACKET_G
    R_BRACKET_G = R_BRACKET
    print(f"   R_eq CARRIED AS A BRACKET: {R_BRACKET[0]:.2f} - "
          f"{R_BRACKET[1]:.2f} ohm   [derived, not datasheet]")

    # ---------------------------------------------------------------- sec.2
    print("\n\n2. THE RIPPLE-VOLTAGE CONSTRAINT (FFPC), DERIVED\n")
    print("   Named:  frequency-floor power ceiling.")
    print("   Source: f_pll_tracking_min = 44 kHz [repo main.ato:269] ==")
    print("           PLL_MIN_FREQ_HZ [repo pll_control.h:104], itself")
    print("           1.05 x worst-case loaded resonance, 1.05 = the ZVS")
    print("           cliff [repo TANK_COIL_SPECIFICATION.md, threshold-")
    print("           confirmed 2026-07-27-inductance-range-sweep.md 2.3].")
    print("           Below it the tank is CAPACITIVE and the 1200 V IGBT")
    print("           half-bridge hard-switches.  It is a safety floor,")
    print("           not a tuning preference.\n")
    print("   P deliverable at V_bus = 340 V across the whole legal PLL band:")
    print(f"   {'R_eq':>6} | {'P(44kHz)':>9} | {'P(47kHz)':>9} | "
          f"{'P(50kHz)':>9} | {'G=P44/P47':>10}")
    print("   " + "-" * 60)
    for r in R_BRACKET:
        p44 = p_at(r, V_BUS_DECLARED, F_PLL_MIN)
        p47 = p_at(r, V_BUS_DECLARED, F_SW_NOM)
        p50 = p_at(r, V_BUS_DECLARED, F_PLL_MAX)
        print(f"   {r:6.2f} | {p44:8.0f}W | {p47:8.0f}W | {p50:8.0f}W | "
              f"{p44/p47:10.3f}")
    print("\n   THE BUDGET.  G is a FINITE energy budget and it has three")
    print("   claimants.  Spending it all on ripple is not an option:\n")
    print(f"   {'claimant':<34} {'demand on G':>12}   basis")
    print("   " + "-" * 74)
    g_line = (V_BUS_DECLARED / (V_BUS_DECLARED * V_LINE_LO / V_LINE_RMS)) ** 2
    print(f"   {'low line, 100 V (main.ato:56)':<34} {g_line:12.3f}   "
          f"P ~ V^2, V ~ V_line")
    # tank tolerance: at +10%L/+10%C the 1800 W point moves DOWN in frequency
    f_1800_hi = None
    for r in [R_BRACKET[1]]:
        # solve X such that P(340,f)=1804 with the +10/+10 tank
        target_x2 = v1 * v1 * r / P_AT_47K_DECLARED - r * r
        tx = math.sqrt(max(target_x2, 0.0))
        ll, cc = l_loaded * 1.1, C_TANK * 1.1
        aa, bb, ccq = ll, -tx, -1.0 / cc
        w = (tx + math.sqrt(tx * tx + 4 * ll / cc)) / (2 * ll)
        f_1800_hi = w / (2 * math.pi)
    print(f"   {'tank tol +10%L/+10%C':<34} {'see below':>12}   "
          f"1800 W point moves to {f_1800_hi/1e3:.1f} kHz")
    print(f"   {'':34} {'':12}   vs the 44.0 kHz floor -> "
          f"{'INFEASIBLE' if f_1800_hi < F_PLL_MIN else 'ok'}")
    print("\n   Ripple budget r = max fractional droop, for a sawtooth sag,")
    print("   as a function of how much of G is left over:")
    print(f"   {'G left for ripple':>18} | {'r_max':>7} | "
          f"{'V_pp on a 340 V bus':>20}")
    print("   " + "-" * 52)
    for g in (1.05, 1.10, 1.20, 1.30, 1.426, 1.57):
        r = r_max_from_G(g)
        print(f"   {g:18.3f} | {100*r:6.1f}% | {r*V_BUS_DECLARED:17.0f} V")
    print("\n   AT RATED 1800 W, low line alone demands G >= "
          f"{g_line:.3f}, against an")
    print(f"   available G of {p_at(R_BRACKET[0],V_BUS_DECLARED,F_PLL_MIN)/p_at(R_BRACKET[0],V_BUS_DECLARED,F_SW_NOM):.3f}"
          f"-{p_at(R_BRACKET[1],V_BUS_DECLARED,F_PLL_MIN)/p_at(R_BRACKET[1],V_BUS_DECLARED,F_SW_NOM):.3f}."
          "  The residual ripple budget is")
    print("   0 - 8.5% depending on R_eq.  main.ato:68's existing, previously")
    print(f"   UN-DERIVED v_bus_ripple_max = {V_BUS_RIPPLE_MAX_DECLARED:.0f} V p-p "
          f"({100*V_BUS_RIPPLE_MAX_DECLARED/V_BUS_DECLARED:.1f}% of 340 V) lands")
    print("   inside that band.  This derivation therefore RATIFIES it rather")
    print("   than replacing it -- and gives it, for the first time, a source.")

    # ---------------------------------------------------------------- sec.3
    print("\n\n3. AS-BUILT BANK, RE-CONFIRMED  [derived]\n")
    print(f"   {'case':<15} {'P_out':>7} {'theta':>7} {'I_line':>8} {'PF':>6} "
          f"{'V_bus':>7} {'V_pp':>6} {'LF/cap':>7}")
    print("   " + "-" * 70)
    for cs in cases("ocp"):
        op = op_at(cs, P_OUT_DECLARED, C_HALF_ASBUILT)
        print(f"   {cs.name:<15} {P_OUT_DECLARED:6.0f}W {op.theta_deg:6.1f}d "
              f"{op.i_line_rms:7.2f}A {op.pf:6.3f} {op.v_bus_avg:6.1f}V "
              f"{op.v_bus_pp:5.1f}V {op.i_cap_unit_eq_dft:6.2f}A")
    print(f"\n   v_bus_ripple_max = {V_BUS_RIPPLE_MAX_DECLARED:.0f} V "
          f"[repo main.ato:68] is VIOLATED in every case above.")
    print("   Reproduces commit fe9cf6752's table to within rounding.")

    print("\n   The HF term, under BOTH repo anchors, at 1800 W:\n")
    print(f"   {'anchor':<28} {'I_tank rms':>11} {'HF/cap actual':>14} "
          f"{'HF/cap 120Hz-eq':>16} {'x rated':>8}")
    print("   " + "-" * 82)
    for lbl, it in (("OCP-01 trip (predecessors)", I_TANK_RMS_OCP[0]),
                    ("OCP-01 trip, 40 A variant", I_TANK_RMS_OCP[1]),
                    ("main.ato:82 47 kHz sim [mine]", I_TANK_RMS_MYDERIV),
                    ("ngspice harness [committed]", I_TANK_RMS_NGSPICE),
                    ("COMMITTED design current", I_TANK_RMS_COMMITTED)):
        act = (1 / math.sqrt(2)) * it / N_PARALLEL
        eq = act / FM_SW
        print(f"   {lbl:<28} {it:10.2f}A {act:13.2f}A {eq:15.2f}A "
              f"{eq/CAP_I_RIPPLE_RATED:7.2f}x")
    print("\n   FINDING: both committed predecessors used the OCP-01 TRIP")
    print("   point as the operating tank current.  A trip threshold is by")
    print("   construction above the operating point.  The COMMITTED design")
    print("   current is 22.5 A rms (2026-08-15-ocp-threshold-decision.md")
    print("   sec.2; modules.ato:585-593).  The HF term is therefore 1.57x")
    print("   SMALLER than the predecessors report.  It still fails the")
    print("   rating.  22.5 A is used from here on; 35.4/40 A are retained")
    print("   only as the 'CaseB(OCP)' column for continuity with them.")

    # ---------------------------------------------------------------- sec.4
    print("\n\n4. CAPACITANCE SWEEP AT CONSTANT DELIVERED POWER (1800 W)\n")
    cs = cases("47k")[1]
    print(f"   central case, HF anchor = 22.5 Arms [committed]\n")
    print(f"   {'C/half':>9} {'theta':>7} {'I_line':>8} {'PF':>6} "
          f"{'V_bus':>7} {'V_pp':>7} {'LF/cap':>7} {'HF/cap':>7} "
          f"{'tot':>6} {'x rated':>8}")
    print("   " + "-" * 84)
    for c_uf in (100, 220, 330, 470, 1000, 2200, 3600, 5000, 8200, 12000):
        op = op_at(cs, P_OUT_DECLARED, c_uf * 1e-6, mode="cr")
        lf = op.i_cap_unit_eq_dft
        hf = hf_per_cap_eq(cs, P_OUT_DECLARED)
        tot = math.hypot(lf, hf)
        print(f"   {c_uf:8d}u {op.theta_deg:6.1f}d {op.i_line_rms:7.2f}A "
              f"{op.pf:6.3f} {op.v_bus_avg:6.1f}V {op.v_bus_pp:6.1f}V "
              f"{lf:6.2f}A {hf:6.2f}A {tot:5.2f}A "
              f"{tot/CAP_I_RIPPLE_RATED:7.2f}x")
    print("\n   Confirms the predecessor's split: LF is the capacitance")
    print("   choice; HF is flat and immune to it.")

    # ---------------------------------------------------------------- sec.5
    print("\n\n5. THE CAPACITANCE WINDOW: floor vs ceiling vs discharge\n")
    c_dis = c_max_busdischarge()
    print(f"   UPPER bound, BusDischarge [repo modules.ato:1126-1140]:")
    print(f"     C_nom <= 60s / (ln5 x {R_DIS_NOM:.0f} x 1.05 x 1.20) = "
          f"{c_dis*1e6:.0f} uF/half")
    print(f"     as built {C_HALF_ASBUILT*1e6:.0f} uF -> "
          f"{'PASSES' if C_HALF_ASBUILT <= c_dis else 'FAILS'} "
          f"(margin {100*(c_dis-C_HALF_ASBUILT)/c_dis:.1f}%)")
    print("     Reducing C only improves this.  It never binds a reduction.\n")

    print("   LOWER bound (FFPC) and UPPER bound (ripple current), vs power:\n")
    print("   Case A here uses the WORST residual corner (0.692) from")
    print("   db44c3aa0 sec.5, not HF = 0.\n")
    print(f"   {'P_out':>7} | {'C_min FFPC':>11} | {'C_max, A-worst':>14} "
          f"| {'C_max, Case B':>14} | window")
    print("   " + "-" * 76)
    cs4 = cases("47k")[1]
    for p in (1800, 1200, 950, 600, 400, 250):
        cmin = c_min_for_ffpc(cs4, p, R_BRACKET[1])
        cmaxA = c_max_for_current(cs4, p, hf_on=HF_RESIDUAL_ON_ELEC[1])
        cmaxB = c_max_for_current(cs4, p, hf_on=True)
        def fmt(c):
            if c == float("inf"):
                return "  no C works"
            if c is None:
                return "  none works"
            return f"{c*1e6:10.0f}u"
        okA = (cmin != float("inf") and cmaxA is not None and cmin <= cmaxA)
        okB = (cmin != float("inf") and cmaxB is not None and cmin <= cmaxB)
        print(f"   {p:6d}W | {fmt(cmin):>11} | {fmt(cmaxA):>14} | "
              f"{fmt(cmaxB):>14} | A:{'OPEN' if okA else 'CLOSED'} "
              f"B:{'OPEN' if okB else 'CLOSED'}")

    print("\n   The window is CLOSED at 1800 W in BOTH cases at the as-built")
    print("   N=2-per-half parallel count, and opens only well below 700 W.")
    print("   No capacitance VALUE reconciles the two constraints at rated")
    print("   power at N=2.  The lever is the PARALLEL COUNT and the")
    print("   per-unit rating (sec.6, sec.8), not the capacitance value.")
    # ---------------------------------------------------------------- sec.6
    print("\n6. WHAT A CAPACITOR HAS TO DO  (the part-selection requirement)\n")
    print("   For a chosen C/half and parallel count N, the per-UNIT current a")
    print("   part must carry.  'LF eq' is 120 Hz-equivalent (compare to a")
    print("   120 Hz ripple rating).  'HF actual' is real amps AT 47 kHz")
    print("   (compare to a rating at 47 kHz, i.e. the 120 Hz rating x the")
    print("   series' own 47 kHz frequency multiplier -- NEVER to the bare")
    print("   120 Hz number).\n")
    cs6 = cases("47k")[1]
    for p_t in (1800.0, 950.0, 600.0):
        print(f"   --- target P_out = {p_t:.0f} W "
              f"{'(rated, unreachable on a 15 A branch)' if p_t>1000 else ''}"
              f"{'(branch-circuit ceiling, fe9cf6752 row 6)' if p_t==950 else ''}")
        print(f"   {'C/half':>8} {'N':>3} {'LF eq/unit':>11} "
              f"{'HF actual/unit':>15} {'need @120Hz':>12} {'need @47kHz':>12}")
        print("   " + "-" * 68)
        for c_uf in (3600, 2600, 1000, 470, 220):
            op = op_at(cs6, p_t, c_uf * 1e-6, mode="cr")
            lf_bank_eq = op.i_cap_unit_eq_dft * N_PARALLEL
            for n in (2, 4, 6):
                lf = lf_bank_eq / n
                hf_act = ((1 / math.sqrt(2)) * cs6.i_tank_1800
                          * math.sqrt(p_t / P_OUT_DECLARED)) / n
                print(f"   {c_uf:7d}u {n:3d} {lf:10.2f}A {hf_act:14.2f}A "
                      f"{lf:11.2f}A {hf_act:11.2f}A")
        print()

    # ---------------------------------------------------------------- sec.6b
    print("\n6b. POWER CEILING WITH THE AS-BUILT AND CANDIDATE BANKS\n")
    print(f"   {'bank':<38} {'CaseA':>9} {'CaseB(OCP)':>11} {'CaseB(47k)':>11}")
    print("   " + "-" * 74)
    for lbl, chalf, npar in (
            ("4x KMQ 1800uF, N=2/half (as built)", 3600e-6, 2),
            ("N=2/half, C -> 470uF/half", 470e-6, 2),
            ("N=2/half, C -> 220uF/half", 220e-6, 2),
            ("N=4/half at 3600uF/half", 3600e-6, 4),
            ("N=6/half at 3600uF/half", 3600e-6, 6),
            ("N=8/half at 3600uF/half", 3600e-6, 8),
    ):
        a = power_ceiling(cases("47k")[1], chalf, False, CAP_I_RIPPLE_RATED, npar, FM_SW)
        b1 = power_ceiling(cases("ocp")[1], chalf, True, CAP_I_RIPPLE_RATED, npar, FM_SW)
        b2 = power_ceiling(cases("47k")[1], chalf, True, CAP_I_RIPPLE_RATED, npar, FM_SW)
        print(f"   {lbl:<38} {a:8.0f}W {b1:10.0f}W {b2:10.0f}W")
    print("\n   (All rows keep the KMQ's 2.70 A / 120 Hz rating and its 1.50")
    print("   multiplier at 47 kHz.  Only C and the parallel count move.)")

    # ---------------------------------------------------------------- sec.6c
    print("\n\n6c. VOLTAGE RATING WITH MARGIN  [derived]\n")
    v_pk_hi = V_LINE_HI * math.sqrt(2.0)
    print(f"   Half-bus peak charge, per the Delon doubler, is one line PEAK")
    print(f"   minus one diode drop -- NOT half of 340 V under load.")
    print(f"   {'condition':<44} {'V_half peak':>12}")
    print("   " + "-" * 60)
    for lbl, vl in (("nominal line 120 Vrms [main.ato:52]", V_LINE_RMS),
                    ("high line 130 Vrms [main.ato:56]", V_LINE_HI),
                    ("+10% on high line (utility tolerance) [estimated]",
                     V_LINE_HI * 1.10)):
        print(f"   {lbl:<44} {vl*math.sqrt(2.0)-0.8:11.1f} V")
    print(f"   {'no-load / pan removed, high line (no droop)':<44} "
          f"{v_pk_hi-0.8:11.1f} V")
    print(f"\n   Existing asserts:")
    print(f"     modules.ato:877  c_bus1.voltage_rating >= v_bus_half*1.25 "
          f"= 212.5 V   -> 250 V passes")
    print(f"     main.ato:593     c_bus1.voltage_rating >= v_bus_max*0.7 "
          f"= 238.0 V   -> 250 V passes")
    print(f"   Against the worst case above ({v_pk_hi*1.10-0.8:.1f} V), a 250 V "
          f"part has")
    print(f"   {100*(250.0/(v_pk_hi*1.10-0.8)-1):.1f}% margin.  The OVP trip is at "
          f"390-410 V FULL bus =")
    print(f"   195-205 V per half, which is BELOW 250 V, so OVP does not")
    print(f"   demand more.  250 V is adequate; 400 V/450 V parts are")
    print(f"   nonetheless what the film route offers and costs nothing here.")

    # ---------------------------------------------------------------- sec.7
    print("\n\n7. INRUSH  [derived from datasheet inputs]\n")
    for c_uf in (3600, 1000, 470, 220, 100):
        c = c_uf * 1e-6
        # Worst case: switch-on at the line peak, NTC cold, both banks
        # charging through the doubler.  Delon: only one bank charges per
        # half cycle, so the energy is per bank.
        e = 0.5 * c * (V_PK ** 2)
        i_pk = V_PK / NTC_R_COLD
        print(f"   C/half = {c_uf:5d} uF : E stored per bank = {e:6.2f} J, "
              f"2 banks = {2*e:6.2f} J   (NTC rated {NTC_JOULE_RATING:.0f} J)")
    print(f"\n   Peak inrush current is set by the NTC, not by C: "
          f"V_pk/R_cold = {V_PK/NTC_R_COLD:.1f} A,")
    print("   independent of capacitance.  Capacitance sets the ENERGY the")
    print("   NTC must absorb and the TIME the fuse sees the surge.")

    # ---------------------------------------------------------------- sec.8
    print("\n\n8. CANDIDATE BANKS, REAL PARTS, BOTH CASES\n")
    print("   Every rating below was read off the manufacturer datasheet named")
    print("   in the .md.  FM(47 kHz) = 1.45 is used for EVERY row -- the")
    print("   CONSERVATIVE reading, because 47 kHz sits below both tables' 50 kHz")
    print("   breakpoint (Nichicon LGW CAT.8100N and UCC KMQ E1001E both print")
    print("   10 kHz = 1.45, 50 kHz-or-more = 1.50).  The predecessors used")
    print("   1.49-1.50; 1.45 makes every number here slightly worse, not better.")
    print()
    print("   Case A is NOT modelled as HF = 0.  db44c3aa0 sec.5 measures the")
    print("   residual as I_elec/I_0 = 0.058 - 0.692, so 'A-best'/'A-worst'")
    print("   below are those two corners.  Case B keeps the full HF term.")
    print()
    print(f"   {'bank (per half-bus)':<38} {'C/half':>7} {'dis':>4} {'film':>5} "
          f"{'A-best':>7} {'A-worst':>8} {'CaseB':>7}")
    print("   " + "-" * 84)
    FM_C = 1.45
    cdis = c_max_busdischarge()
    cfilm = c_min_for_film_ripple(cases("47k")[1], 950.0)
    for lbl, c_unit, n, rating in (
            ("2x EKMQ251VSN182MA50S (as built)", 1800e-6, 2, 2.70),
            ("2x LGW2E182MELC50 [drop-in swap]", 1800e-6, 2, 4.05),
            ("2x EKMS251VSN182MA50S [drop-in]", 1800e-6, 2, 3.98),
            ("3x LGW2E102MELC35", 1000e-6, 3, 3.30),
            ("6x LGW2E471MELB25", 470e-6, 6, 2.20),
            ("7x LGW2E331MELZ30", 330e-6, 7, 1.80),
            ("8x LGW2E331MELZ30", 330e-6, 8, 1.80),
    ):
        chalf = c_unit * n
        cs8 = cases("47k")[1]
        ab = power_ceiling(cs8, chalf, HF_RESIDUAL_ON_ELEC[0], rating, n, FM_C)
        aw = power_ceiling(cs8, chalf, HF_RESIDUAL_ON_ELEC[1], rating, n, FM_C)
        b2 = power_ceiling(cs8, chalf, True, rating, n, FM_C)
        dis = "PASS" if chalf <= cdis else "FAIL"
        fil = "PASS" if chalf >= cfilm else "FAIL"
        print(f"   {lbl:<38} {chalf*1e6:6.0f}u {dis:>4} {fil:>5} "
              f"{ab:6.0f}W {aw:7.0f}W {b2:6.0f}W")
    print(f"\n   BusDischarge ceiling = {c_max_busdischarge()*1e6:.0f} uF/half "
          f"[repo modules.ato:1126-1140].")
    print("   Branch-circuit ceiling one level up = 844-955 W [commit fe9cf6752].")
    print("   A bank only has to reach that; more is unusable.\n")

    print("\n   5b. THE FILM BYPASS'S OWN RIPPLE-VOLTAGE FLOOR, RE-DERIVED")
    print("   The MKP1848C's 100 V p-p limit applies across ONE HALF-BUS,")
    print("   because the film is placed hv_plus->midpoint / midpoint->hv_minus.")
    print("   The quantity to compare is v_half_pp, not the full-bus p-p:")
    print(f"   {'P_out':>7} | {'floor (C/half)':>15}")
    print("   " + "-" * 28)
    for p_t in (1800.0, 950.0, 600.0):
        cf = c_min_for_film_ripple(cases("47k")[1], p_t)
        print(f"   {p_t:6.0f}W | {cf*1e6:14.0f}u")
    print("   DISAGREEMENT, REPORTED NOT AVERAGED: branch")
    print("   fix/hf-bypass-commutation-loop asserts 'roughly 400 uF per")
    print("   half-bus'.  At 1800 W this simulation gives 1047 uF/half --")
    print("   2.6x higher.  The two agree exactly on the WAVEFORM (that")
    print("   branch quotes 27 V p-p as built and 160 V p-p at 100 uF/half;")
    print("   this model gives 26.9 V and 160.4 V).  The gap is in reading a")
    print("   crossing off two endpoints of a strongly saturating curve:")
    print("   v_half_pp plateaus near 160 V below ~400 uF and only falls")
    print("   through 100 V around 1000 uF.  400 uF is close to this")
    print("   simulation's 600 W figure (345 uF), so the two may simply be")
    print("   quoted at different powers.  A human should adjudicate.")
    print()
    print("   FFPC floor check for the recommended banks, at 950 W:")
    for lbl, chalf in (("6x LGW2E471MELB25 -> 2820 uF/half", 2820e-6),
                       ("7x LGW2E331MELZ30 -> 2310 uF/half", 2310e-6)):
        cmin = c_min_for_ffpc(cases("47k")[1], 950.0, R_BRACKET_G[1])
        op = op_at(cases("47k")[1], 950.0, chalf, mode="cr")
        need = 950.0 / k44(R_BRACKET_G[1])
        print(f"     {lbl:<36} mean(V_bus^2) = {op.v_bus_ms:8.0f} "
              f"vs required {need:8.0f} -> "
              f"{'PASS' if op.v_bus_ms >= need else 'FAIL'}   "
              f"(V_pp {op.v_bus_pp:.0f} V)")
    print(f"     FFPC floor at 950 W = {cmin*1e6:.0f} uF/half; both clear it.")

    hr()
    print("END")
    hr()


def c_max_for_current(case, p_out, hf_on, rating=CAP_I_RIPPLE_RATED,
                      lo=20e-6, hi=40000e-6):
    """Largest C/half whose per-cap ripple current stays within `rating`.

    LF ripple current RISES with C (a bigger cap means a narrower, peakier
    recharge pulse), so this is a genuine upper bound.  Returns None if even
    the smallest C in range already fails -- i.e. the HF term alone is over.
    """
    def f(c):
        op = op_at(case, p_out, c, mode="cr")
        return total_per_cap_eq(op, case, p_out, hf_on) - rating
    if f(lo) > 0:
        return None
    if f(hi) < 0:
        return hi
    for _ in range(22):
        mid = math.sqrt(lo * hi)
        if f(mid) > 0:
            hi = mid
        else:
            lo = mid
    return math.sqrt(lo * hi)


if __name__ == "__main__":
    main()
