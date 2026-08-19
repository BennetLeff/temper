#!/usr/bin/env python3
"""Maximum continuous output power of Temper's PFC-less doubler input stage.

provenance: commit=eb5022510d8f1272adf0a27d76c849aa2bb6e210 dirty=false
    pcb/temper.kicad_pcb sha256=26981fea2dbc425f456010d4d4e755cdebdefee2b535
    5ad915086352b90c110b -- verified before and after; never opened for writing.

WHAT THIS ANSWERS
    "What is the maximum continuous output power this input stage can actually
    deliver while every component stays inside its own datasheet rating, and
    what would it take to reach the declared 1800 W?"

METHOD
    A time-domain simulation of the as-drawn Delon (half-wave cascade) voltage
    doubler in ``elec/src/modules.ato`` ``PowerInput``, driven by a 120 V/60 Hz
    source through the real series impedance of the input stage, loaded by a
    constant-power half-bridge.  Unlike the repo's existing rectangular-pulse
    model (2026-07-26-bus-capacitor-ripple.md sec.3, A4/A5), the conduction
    angle here is NOT an assumed input -- it FALLS OUT of the capacitance, the
    load and the series resistance.  That closes the single largest estimated
    input in the prior derivation (43d056e15 sec.7 item 1).

    Then each component's rating is turned into an output-power ceiling by
    bisection, and the minimum of those ceilings is the answer.

PROVENANCE TAGS -- never blended:
    [datasheet]     printed in a manufacturer document read this session or
                    quoted verbatim in elec/src with a verification date
    [repo]          a committed value in this repository
    [derived]       computed here from [datasheet]/[repo] inputs only
    [estimated]     not published anywhere reachable; a bracket, not a value
    [UNOBTAINABLE]  named and left unquantified

RUNTIME
    Pure stdlib.  Reads no repo state, writes no files, touches no board file.
    ``make venv-isolate`` is therefore NOT required to reproduce this.

    python3 docs/evidence/2026-08-19-input-stage-power-ceiling.py
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# =============================================================================
# 1. INPUTS
# =============================================================================

# --- line -------------------------------------------------------------------
V_LINE_RMS = 120.0        # [repo] main.ato:52  v_ac_nominal = 120V
F_LINE = 60.0             # [repo] main.ato:62  f_line = 60Hz
V_PK = V_LINE_RMS * math.sqrt(2.0)
OMEGA = 2.0 * math.pi * F_LINE
T_LINE = 1.0 / F_LINE

# --- declared operating point -----------------------------------------------
P_OUT_DECLARED = 1800.0   # [repo] main.ato:53 power_max, :494 p_output_max
ETA_CENTRAL = 0.90        # [repo] main.ato:500 eta_min = 0.90
ETA_BEST = 0.92           # [repo] STRATEGY EFF-02 target (unmeasured)
ETA_WORST = 0.85          # [repo] main.ato:501 assert eta_min >= 0.85

# --- bus capacitance --------------------------------------------------------
# [repo] modules.ato:819-846 -- 4x EKMQ251VSN182MA50S, 2 in parallel per half.
C_UNIT = 1800e-6
N_PARALLEL = 2
C_HALF = C_UNIT * N_PARALLEL          # 3600 uF per half-bus

# --- series resistance in the L->doubler->N loop, steady state (NTC bypassed)-
# Each entry is (low, high) in ohms.
R_FUSE = (3.750e-3, 5.729e-3)
#   [datasheet] Schurter FST 5x20 ratings table, typ_fst_5x20.pdf rev 21.07.2026,
#   16 A row: 60 mV at 1.0*In -> 3.750 mOhm; 3300 mW at 1.5*In -> 5.729 mOhm.
#   Fetched and text-extracted by the 2026-08-19 EMI/ESR derivation (43d056e15
#   sec.2.3); reused here rather than re-fetched.  The "1.0*In max" cell is
#   blank in Schurter's own table, so no maximum exists to cite.
R_CMC = (14.2e-3, 14.2e-3)
#   [datasheet] via elec/src/components.ato:253-275, which quotes the TDK
#   B82726S2163N030 April-2025 datasheet verbatim with a 2026-07-16
#   verification date: "R_typ 7.1 mOhm/winding".  Both windings are in the
#   L-N loop (W1 = line, W2 = neutral), so the loop sees 2 x 7.1 mOhm.
#   No max DCR is published -- only R_typ -- so this is a point, not a bracket.
R_K1_CONTACT = (5e-3, 20e-3)
#   [estimated] TE Schrack RT33K012's Contact Data block publishes NO
#   contact-resistance line (verified by the 2026-08-19 derivation).  5-20 mOhm
#   is the industry-typical band for a 16-20 A power relay contact.  NOT a
#   datasheet value and never treated as one.
R_PCB = (3e-3, 15e-3)
#   [estimated] AC-mains copper, 2.5 mm nominal trace width (constraints.ato
#   ACMains.trace_width).  No routed length for the L-N loop was extracted --
#   pcb/temper.kicad_pcb is not opened by this script.  Bracket only.
R_EXT_BRANCH = (0.05, 0.40)
#   [estimated] NEC 15 A branch circuit + service impedance seen at the outlet.
#   NOT under this design's control and NOT a component of it.  0.05 ohm is a
#   short 14 AWG run on a stiff service; 0.40 ohm is a long run on a soft one.
#   This is the single largest term in the loop and it is the one the designer
#   cannot specify -- which is itself a finding (see the .md, sec.3).

# --- rectifier diodes D1/D2 -------------------------------------------------
# [datasheet] Fairchild MUR1540/MUR1560/RURP1540/RURP1560 Rev.B (2002), read
# this session.  Absolute Maximum Ratings, MUR1560 column:
D_IF_AV = 15.0            # A,  Average Rectified Forward Current, TC = 145 C
D_IFRM = 30.0             # A,  Repetitive Peak Surge Current (square wave 20kHz)
D_IFSM = 200.0            # A,  Nonrepetitive Peak Surge (halfwave 1 phase 60Hz)
D_PD_MAX = 100.0          # W,  Maximum Power Dissipation
D_RTH_JC = 1.5            # C/W, RthJC
# Electrical Specifications, MUR1560 column: VF max 1.5 V at IF = 15 A (TC=25C);
# VF max 1.2 V at IF = 15 A, TC = 150 C.  Fairchild publishes no typ column and
# no knee/slope split -- only the two max points above and an unreadable
# Figure 1 curve.  Splitting them into an offset + slope is [estimated]:
D_MODEL = (
    # (Vf0 [V], rd [ohm], label)
    (0.90, 40.0e-3, "25C max point (1.5V@15A) split 0.90V + 40 mOhm"),
    (0.70, 33.3e-3, "150C max point (1.2V@15A) split 0.70V + 33.3 mOhm"),
)

# --- NTC inrush limiter RT1 -------------------------------------------------
# [datasheet] Ametherm SL32 10015 datasheet page, fetched this session:
NTC_R_COLD = 10.0         # ohm +/- 20% at 25 C
NTC_I_MAX = 15.0          # A max steady-state current  [repo modules.ato:752 agrees]
NTC_R_AT_IMAX = 0.05      # ohm at 100% of max current
NTC_BODY_T_AT_IMAX = 228.0  # C body temperature at max current
# Ambient derating curve: Ametherm publishes it only as an image
# (ametherm.com/inrush-current/imax-derating-curve); the numerical table is
# [UNOBTAINABLE].  15 A is therefore used un-derated, which FAVOURS the design.

# --- bus capacitor EKMQ251VSN182MA50S ---------------------------------------
# [datasheet] United Chemi-Con CAT.No.E1001E, KMQ series, quoted in
# docs/evidence/2026-07-26-bus-capacitor-ripple.md sec.1 (committed, verified
# 2026-07-16).  Re-used, not re-fetched.
CAP_I_RIPPLE_RATED = 2.70     # Arms at 105 C, 120 Hz
CAP_V_RATED = 250.0           # Vdc
CAP_TAN_DELTA = 0.15          # max, 20 C / 120 Hz, 160-250 Vdc group
# Frequency multipliers, 160-250 Vdc column (allowed current vs the 120 Hz rating):
CAP_FM_TABLE = [(50.0, 0.81), (120.0, 1.00), (300.0, 1.17),
                (1e3, 1.32), (10e3, 1.45), (50e3, 1.50)]

# --- other component ratings ------------------------------------------------
I_BRANCH_DECLARED = 15.0  # [repo] constraints.ato:12 ACMainsConstraints.i_max
I_BRANCH_NEC_CONT = 12.0  # [derived] NEC 210.19(A)(1)/210.23(A): a continuous
                          # load may not exceed 80% of the branch rating.  A
                          # cooktop run at power for >3 h is a continuous load.
I_FUSE_RATED = 16.0       # [repo] modules.ato:658; Schurter 0034.3129 In = 16 A
I_CMC_RATED = 16.0        # [datasheet] TDK B82726S2163N030, "16A rated
                          # (referred to 50Hz, T_R +60C)" via components.ato:260
I_K1_UL = 20.0            # [repo] modules.ato:768 contact_current = 20A;
                          # modules.ato:760-761 "20A UL508/16A IEC 1-Form-A"
I_K1_IEC = 16.0           # [repo] same line -- the IEC-rated contact current

# --- the ONLY HF bypass across the DC bus -----------------------------------
# [repo] modules.ato:347-355 (HalfBridge): c_dc_hf = 0.47 uF / 630 VDC PP film
# (EPCOS B32671L6474K000), connected hv_plus -> hv_minus.
C_DC_HF = 0.47e-6

# --- tank / high-frequency term ---------------------------------------------
# [repo] docs/evidence/2026-07-26-ocp01-vs-full-power-current.md, via
# STRATEGY.md: 1800 W requires 35.4-40 A rms in the tank.  Taken as an
# externally-sourced bound; NOT re-derived (L_TANK still has no committed value).
I_TANK_AT_1800W = (35.4, 40.0)
F_SW = 47.0e3             # [repo] main.ato -- 1800 W point is 47.1 kHz nominal,
                          # PLL band 44-50 kHz.
# [repo] 2026-07-26 ripple doc assumption A6: each half-bus bank carries the
# tank current only while its own switch conducts -> per-cap share of I_tank,rms
CAP_HF_SHARE = 0.3536     # = (1/sqrt(2)) / 2


# =============================================================================
# 2. THE DOUBLER SIMULATION
# =============================================================================

@dataclass
class Op:
    """One steady-state operating point."""
    p_out: float
    p_in: float
    i_line_rms: float
    i_line_pk: float
    p_real_source: float
    pf: float
    crest: float
    theta_deg: float          # conduction angle of one diode, degrees
    v_bus_avg: float          # total bus, hv_plus - hv_minus
    v_bus_pp: float           # total bus ripple, peak-to-peak
    v_half_avg: float
    v_half_pp: float
    i_diode_avg: float
    i_diode_rms: float
    i_diode_pk: float
    i_cap_bank_rms: float     # per half-bus BANK (both parallel caps)
    i_cap_unit_rms: float     # per capacitor, ideal 50/50 sharing
    i_cap_unit_eq_flat: float # 120 Hz-equivalent, single FM(60Hz) method
    i_cap_unit_eq_dft: float  # 120 Hz-equivalent, per-harmonic method
    p_delivered_half: float   # actual mean power drawn from ONE half-bus
    converged: bool


def cap_freq_multiplier(f: float) -> float:
    """Allowed-ripple multiplier vs the 120 Hz rating, log-interpolated.

    [datasheet] table + [derived] interpolation.  Below 50 Hz and above 50 kHz
    the endpoints are held flat (no extrapolation is invented).
    """
    tbl = CAP_FM_TABLE
    if f <= tbl[0][0]:
        return tbl[0][1]
    if f >= tbl[-1][0]:
        return tbl[-1][1]
    for (f0, m0), (f1, m1) in zip(tbl, tbl[1:]):
        if f0 <= f <= f1:
            w = (math.log(f) - math.log(f0)) / (math.log(f1) - math.log(f0))
            return m0 + w * (m1 - m0)
    raise AssertionError("unreachable")


FM_60_LOG = cap_freq_multiplier(60.0)     # 0.8496 -- log interpolation
FM_60_LINEAR = 0.81 + (1.00 - 0.81) * (60.0 - 50.0) / (120.0 - 50.0)  # 0.8371
# The 2026-07-26 committed doc says "log-interpolate ... -> FM(60Hz) ~ 0.837".
# 0.837 is the LINEAR-in-f interpolation, not the log one (log gives 0.8496).
# The disagreement is 1.5% and immaterial to every verdict below.  This script
# uses the committed 0.837 for the "flat" method so the two documents stay
# comparable, and the log curve inside the per-harmonic method.
FM_SW = cap_freq_multiplier(F_SW)         # 1.50 at 47 kHz


def simulate(p_in: float, rs: float, vf0: float, rd: float,
             c_half: float = C_HALF, load: str = "cp",
             r_load_override: float | None = None,
             n_per_cycle: int = 6000, n_cycles: int = 40) -> Op:
    """Time-domain Delon doubler, constant-power load, forward Euler.

    Topology (elec/src/modules.ato:881-925):
        ac_l -> F1 -> L1.W1 -> {RT1 || K1} -> node A
        node A -> D1 -> hv_plus ; C_BUS1||C_BUS1B from hv_plus to gnd_ref
        hv_minus -> D2 -> node A ; C_BUS2||C_BUS2B from gnd_ref to hv_minus
        ac_n -> L1.W2 -> gnd_ref  (the doubler midpoint)
    D1 charges the upper bank on the positive half-cycle, D2 the lower bank on
    the negative -- each bank recharges ONCE per 60 Hz cycle, not twice.

    The half-bridge draws p_in/2 from each half-bus.  At 47 kHz the switching
    period is 280x shorter than the line period, so a constant-power draw is
    the correct 60 Hz-scale model.  main.ato:167 confirms a power-seeking
    control loop, i.e. the converter holds power as the bus sags rather than
    behaving as a fixed resistance.
    """
    dt = T_LINE / n_per_cycle
    r_series = rs + rd          # one diode is in the loop at any instant

    # Constant-resistance equivalent, referenced to the ideal peak-charged
    # half-bus (each half supplies p_in/2 at V_pk - vf0).
    v_nom = max(V_PK - vf0, 1.0)
    r_load = (r_load_override if r_load_override is not None
              else v_nom * v_nom / (p_in / 2.0))

    # Initial guess: peak charge minus one full-period droop.
    droop0 = (p_in / 2.0) / max(V_PK - vf0, 1.0) * T_LINE / c_half
    v1 = max(V_PK - vf0 - droop0, 20.0)
    v2 = v1

    last_rms = None
    for cyc in range(n_cycles):
        record = cyc == n_cycles - 1
        if record:
            i_line = [0.0] * n_per_cycle
            i_d1 = [0.0] * n_per_cycle
            v_src_s = [0.0] * n_per_cycle
            v1_s = [0.0] * n_per_cycle
            v2_s = [0.0] * n_per_cycle
        acc_i2 = 0.0
        for k in range(n_per_cycle):
            t = k * dt
            vs = V_PK * math.sin(OMEGA * t)

            # Diode conduction (mutually exclusive: D1 needs vs > 0, D2 vs < 0)
            id1 = 0.0
            id2 = 0.0
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
            if v1 < 1.0:
                v1 = 1.0
            if v2 < 1.0:
                v2 = 1.0

            i = id1 - id2          # line current, + = into L
            acc_i2 += i * i
            if record:
                i_line[k] = i
                i_d1[k] = id1
                v_src_s[k] = vs
                v1_s[k] = v1
                v2_s[k] = v2
        rms = math.sqrt(acc_i2 / n_per_cycle)
        converged = last_rms is not None and abs(rms - last_rms) < 1e-3 * max(rms, 1e-9)
        last_rms = rms

    n = n_per_cycle
    i_line_rms = math.sqrt(sum(x * x for x in i_line) / n)
    i_line_pk = max(abs(x) for x in i_line)
    p_real = sum(v_src_s[k] * i_line[k] for k in range(n)) / n
    pf = p_real / (V_LINE_RMS * i_line_rms) if i_line_rms > 0 else 0.0
    crest = i_line_pk / i_line_rms if i_line_rms > 0 else 0.0

    n_cond = sum(1 for x in i_d1 if x > 0.0)
    theta_deg = 360.0 * n_cond / n

    i_d1_avg = sum(i_d1) / n
    i_d1_rms = math.sqrt(sum(x * x for x in i_d1) / n)
    i_d1_pk = max(i_d1)

    v_half_avg = sum(v1_s) / n
    v_half_pp = max(v1_s) - min(v1_s)
    v_bus = [v1_s[k] + v2_s[k] for k in range(n)]
    v_bus_avg = sum(v_bus) / n
    v_bus_pp = max(v_bus) - min(v_bus)

    # Upper-bank capacitor current = diode current minus the load draw.
    if load == "cp":
        i_cap = [i_d1[k] - (p_in / 2.0) / max(v1_s[k], 1.0) for k in range(n)]
    else:
        i_cap = [i_d1[k] - max(v1_s[k], 0.0) / r_load for k in range(n)]
    p_out_bank = (sum((p_in / 2.0) for _ in range(n)) / n if load == "cp"
                  else sum(v * v / r_load for v in v1_s) / n)
    i_cap_bank_rms = math.sqrt(sum(x * x for x in i_cap) / n)
    i_cap_unit = i_cap_bank_rms / N_PARALLEL

    # (a) "flat" 120 Hz-equivalent: treat the whole LF term as 60 Hz.
    eq_flat = i_cap_unit / FM_60_LINEAR

    # (b) per-harmonic 120 Hz-equivalent.  The recharge pulse is NOT a 60 Hz
    #     sinusoid; its harmonics land where the datasheet ALLOWS MORE current,
    #     so (a) is conservative and (b) is the honest number.  DC is excluded
    #     (a capacitor passes no DC; charge balance already makes it ~0).
    n_harm = 100
    eq2 = 0.0
    for h in range(1, n_harm + 1):
        re = 0.0
        im = 0.0
        w = 2.0 * math.pi * h / n
        for k in range(n):
            ang = w * k
            re += i_cap[k] * math.cos(ang)
            im += i_cap[k] * math.sin(ang)
        amp = 2.0 / n * math.hypot(re, im)       # peak amplitude of harmonic h
        rms_h = amp / math.sqrt(2.0)
        eq2 += (rms_h / cap_freq_multiplier(h * F_LINE)) ** 2
    eq_dft = math.sqrt(eq2) / N_PARALLEL   # bank -> per capacitor

    return Op(p_out=float("nan"), p_in=p_in, i_line_rms=i_line_rms,
              i_line_pk=i_line_pk, p_real_source=p_real, pf=pf, crest=crest,
              theta_deg=theta_deg, v_bus_avg=v_bus_avg, v_bus_pp=v_bus_pp,
              v_half_avg=v_half_avg, v_half_pp=v_half_pp,
              i_diode_avg=i_d1_avg, i_diode_rms=i_d1_rms, i_diode_pk=i_d1_pk,
              i_cap_bank_rms=i_cap_bank_rms, i_cap_unit_rms=i_cap_unit,
              i_cap_unit_eq_flat=eq_flat, i_cap_unit_eq_dft=eq_dft,
              p_delivered_half=p_out_bank, converged=converged)


def simulate_cr_at_power(p_in: float, rs: float, vf0: float, rd: float,
                         c_half: float, tol: float = 0.005, **kw) -> Op:
    """Constant-RESISTANCE load, but with R re-tuned so the converter actually
    DELIVERS p_in.  This is what makes the sec.4 capacitance sweep an
    apples-to-apples comparison: same delivered power, different capacitor.

    Returns None if no finite R delivers p_in at this capacitance -- i.e. the
    bus sags so hard that the requested power is simply not reachable, which
    is itself the answer for that capacitance.
    """
    v_nom = max(V_PK - vf0, 1.0)
    r_hi = v_nom * v_nom / (p_in / 2.0)      # R for p_in at an un-sagged bus
    lo, hi = r_hi * 0.02, r_hi * 4.0
    best = None
    for _ in range(34):
        mid = math.sqrt(lo * hi)
        op = simulate(p_in, rs, vf0, rd, c_half=c_half, load="cr",
                      r_load_override=mid, **kw)
        p_del = 2.0 * op.p_delivered_half
        best = op
        if abs(p_del - p_in) <= tol * p_in:
            return op
        if p_del < p_in:
            hi = mid          # need a SMALLER resistance
        else:
            lo = mid
    return best


# =============================================================================
# 3. CASE BRACKET
# =============================================================================

@dataclass
class Case:
    name: str
    eta: float
    rs: float
    vf0: float
    rd: float
    i_tank_1800: float
    note: str = ""


def rs_of(pick: str) -> float:
    idx = 0 if pick == "lo" else 1
    return (R_FUSE[idx] + R_CMC[idx] + R_K1_CONTACT[idx]
            + R_PCB[idx] + R_EXT_BRANCH[idx])


CASES = [
    Case("stiffest-line", ETA_BEST, rs_of("lo"), D_MODEL[1][0], D_MODEL[1][1],
         I_TANK_AT_1800W[0],
         "lowest series R (short branch, low-R contact) -> narrowest pulse, "
         "HIGHEST rms line current.  Worst for every current rating."),
    Case("central", ETA_CENTRAL, 0.5 * (rs_of("lo") + rs_of("hi")),
         0.80, 36.7e-3, 37.7,
         "midpoint of every bracket."),
    Case("softest-line", ETA_WORST, rs_of("hi"), D_MODEL[0][0], D_MODEL[0][1],
         I_TANK_AT_1800W[1],
         "highest series R (long branch, high-R contact) -> widest pulse, "
         "LOWEST rms line current, but lowest bus voltage."),
]


def cap_equiv_total(op: Op, i_tank_1800: float, p_out: float,
                    tank_scaling: str = "sqrt") -> float:
    """Per-capacitor 120 Hz-equivalent ripple, LF (+) HF in quadrature."""
    if tank_scaling == "sqrt":
        # Series-resonant inverter into a fixed reflected pan resistance:
        # P = I_tank^2 * R_eq  ->  I_tank proportional to sqrt(P).
        scale = math.sqrt(max(p_out, 0.0) / P_OUT_DECLARED)
    else:
        scale = max(p_out, 0.0) / P_OUT_DECLARED
    i_tank = i_tank_1800 * scale
    hf_actual = CAP_HF_SHARE * i_tank
    hf_eq = hf_actual / FM_SW
    lf_eq = op.i_cap_unit_eq_dft
    return math.hypot(lf_eq, hf_eq)


# =============================================================================
# 4. RATING CEILINGS BY BISECTION
# =============================================================================

def op_at(case: Case, p_out: float, **kw) -> Op:
    op = simulate(p_out / case.eta, case.rs, case.vf0, case.rd, **kw)
    op.p_out = p_out
    return op


def ceiling(case: Case, metric, limit: float,
            lo: float = 20.0, hi: float = 3000.0, tol: float = 2.0) -> float:
    """Output power at which `metric(op, p_out)` first reaches `limit`."""
    f_lo = metric(op_at(case, lo), lo) - limit
    f_hi = metric(op_at(case, hi), hi) - limit
    if f_lo > 0:
        return 0.0            # over the rating even at 20 W
    if f_hi < 0:
        return float("inf")   # never reaches the rating below 3 kW
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if metric(op_at(case, mid), mid) - limit < 0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# =============================================================================
# 5. REPORT
# =============================================================================

def hr(c: str = "=") -> None:
    print(c * 78)


def main() -> None:
    print(__doc__.strip().splitlines()[0])
    hr()
    print(f"C per half-bus        {C_HALF*1e6:.0f} uF   "
          f"({N_PARALLEL} x {C_UNIT*1e6:.0f} uF)          [repo]")
    print(f"Vpk                   {V_PK:.2f} V")
    print(f"FM(60Hz) linear       {FM_60_LINEAR:.4f}  (committed 2026-07-26 value)")
    print(f"FM(60Hz) log          {FM_60_LOG:.4f}  (this script's own interp)")
    print(f"FM({F_SW/1e3:.0f}kHz)          {FM_SW:.4f}")
    print()
    print("Series resistance in the L->doubler->N loop (steady state, NTC bypassed):")
    for label, br, tag in (("F1 Schurter FST 16A", R_FUSE, "[datasheet]"),
                           ("L1 TDK CMC, 2 wdgs ", R_CMC, "[datasheet]"),
                           ("K1 contact         ", R_K1_CONTACT, "[estimated]"),
                           ("PCB AC-mains copper", R_PCB, "[estimated]"),
                           ("branch + service   ", R_EXT_BRANCH, "[estimated]")):
        print(f"   {label}  {br[0]*1e3:7.2f} - {br[1]*1e3:7.2f} mOhm   {tag}")
    print(f"   {'LOOP TOTAL':19}  {rs_of('lo')*1e3:7.2f} - {rs_of('hi')*1e3:7.2f} mOhm")
    print("   + one MUR1560 dynamic resistance, 33.3 - 40.0 mOhm  [estimated split")
    print("     of the datasheet VF max points; the offset Vf0 carries the rest]")
    print()

    # ---------------------------------------------------------------- sec.1
    hr()
    print("1. WHAT THE INPUT STAGE ACTUALLY DRAWS AT THE DECLARED 1800 W")
    hr("-")
    print(f"{'case':<16}{'Rs':>8}{'Pin':>8}{'theta':>8}{'Iline':>9}"
          f"{'Ipk':>8}{'CF':>6}{'PF':>7}{'Vbus':>8}{'Vpp':>7}")
    print(f"{'':<16}{'mOhm':>8}{'W':>8}{'deg':>8}{'Arms':>9}"
          f"{'A':>8}{'':>6}{'':>7}{'V':>8}{'V':>7}")
    ops_1800 = {}
    for c in CASES:
        op = op_at(c, P_OUT_DECLARED)
        ops_1800[c.name] = op
        print(f"{c.name:<16}{c.rs*1e3:8.1f}{op.p_in:8.0f}{op.theta_deg:8.1f}"
              f"{op.i_line_rms:9.2f}{op.i_line_pk:8.1f}{op.crest:6.2f}"
              f"{op.pf:7.3f}{op.v_bus_avg:8.1f}{op.v_bus_pp:7.1f}")
    print()
    print("Cross-check -- the repo's own rectangular-pulse identity")
    print("  I_line,rms = I_dc,half * sqrt(2/delta),  delta = theta/360")
    print("  (2026-07-26-bus-capacitor-ripple.md sec.3 / 43d056e15 sec.1)")
    print(f"{'case':<16}{'theta(sim)':>12}{'Iline(sim)':>12}"
          f"{'Iline(rect)':>13}{'ratio':>8}")
    for c in CASES:
        op = ops_1800[c.name]
        i_dc_half = (op.p_in / 2.0) / op.v_half_avg
        delta = op.theta_deg / 360.0
        i_rect = i_dc_half * math.sqrt(2.0 / delta)
        print(f"{c.name:<16}{op.theta_deg:12.1f}{op.i_line_rms:12.2f}"
              f"{i_rect:13.2f}{i_rect/op.i_line_rms:8.3f}")
    print()
    print("Sensitivity of theta (and therefore of everything) to series R:")
    print(f"{'Rs mOhm':>9}{'theta deg':>11}{'Iline Arms':>12}{'PF':>8}{'Ipk A':>8}")
    for rs_m in (30, 50, 80, 120, 200, 300, 450, 600):
        op = simulate(P_OUT_DECLARED / ETA_CENTRAL, rs_m * 1e-3, 0.80, 36.7e-3)
        print(f"{rs_m:9.0f}{op.theta_deg:11.1f}{op.i_line_rms:12.2f}"
              f"{op.pf:8.3f}{op.i_line_pk:8.1f}")
    print()
    print("theta is NOT a free parameter.  It is set by charge balance:")
    print("  cos(theta_start) = V_min/V_pk,  V_min = V_pk - I_dc*T/C,")
    print("  widened by the series R.  The 2026-07-26 doc's assumed 30-60 deg")
    print("  band is checked against the simulation above, not assumed here.")
    print()

    # ---------------------------------------------------------------- sec.2
    hr()
    print("2. THE BINDING CONSTRAINT -- output power at which each rating is hit")
    hr("-")

    def m_line(op, p):
        return op.i_line_rms

    def m_diode_pk(op, p):
        return op.i_diode_pk

    def m_diode_avg(op, p):
        return op.i_diode_avg

    checks = [
        ("branch circuit, NEC continuous (80%)", m_line, I_BRANCH_NEC_CONT, "[derived]"),
        ("branch circuit, declared i_max",       m_line, I_BRANCH_DECLARED, "[repo]"),
        ("NTC RT1 SL32 10015 (if K1 open)",      m_line, NTC_I_MAX,         "[datasheet]"),
        ("F1 fuse Schurter 0034.3129 In",        m_line, I_FUSE_RATED,      "[repo]"),
        ("L1 CMC TDK B82726S2163N030",           m_line, I_CMC_RATED,       "[datasheet]"),
        ("K1 contact, IEC rating",               m_line, I_K1_IEC,          "[repo]"),
        ("K1 contact, UL508 rating",             m_line, I_K1_UL,           "[repo]"),
        ("D1/D2 MUR1560 IF(AV) @ TC=145C",       m_diode_avg, D_IF_AV,      "[datasheet]"),
        ("D1/D2 MUR1560 IFRM repetitive peak",   m_diode_pk, D_IFRM,        "[datasheet]"),
    ]

    results = {}
    for c in CASES:
        print(f"\n  --- case: {c.name} (Rs = {c.rs*1e3:.1f} mOhm, eta = {c.eta}) ---")
        print(f"    {'rating':<40}{'limit':>9}{'P_out ceiling':>16}")
        rows = []
        for label, metric, limit, tag in checks:
            p = ceiling(c, metric, limit)
            rows.append((label, limit, p, tag))
            s = "no limit <3kW" if math.isinf(p) else f"{p:8.0f} W"
            print(f"    {label:<40}{limit:9.2f}{s:>16}   {tag}")
        for scaling in ("sqrt", "linear"):
            def m_cap(op, p, c=c, scaling=scaling):
                return cap_equiv_total(op, c.i_tank_1800, p, scaling)
            p = ceiling(c, m_cap, CAP_I_RIPPLE_RATED)
            lbl = f"C_BUS x4 ripple (I_tank ~ P^{'0.5' if scaling=='sqrt' else '1.0'})"
            rows.append((lbl, CAP_I_RIPPLE_RATED, p, "[datasheet]"))
            s = "no limit <3kW" if math.isinf(p) else f"{p:8.0f} W"
            print(f"    {lbl:<40}{CAP_I_RIPPLE_RATED:9.2f}{s:>16}   [datasheet]")
        results[c.name] = rows
        binding = min((r for r in rows if not math.isinf(r[2])), key=lambda r: r[2])
        print(f"    >>> BINDING: {binding[0]}  at  {binding[2]:.0f} W output")

    # ---------------------------------------------------------------- sec.2b
    print()
    hr()
    print("2b. WHICH TERM DRIVES THE CAPACITOR CEILING -- LF vs HF, SEPARATELY")
    hr("-")
    print("The two ripple terms have INDEPENDENT causes.  LF is the 60 Hz")
    print("doubler recharge pulse (input-topology driven).  HF is the 47 kHz")
    print("tank current the half-bridge pulls out of each half-bus bank")
    print("(2026-07-26 ripple doc assumption A6) -- nothing to do with the")
    print("rectifier.  Each is compared to the 2.70 A rating ON ITS OWN.")
    print()
    print("The only HF bypass across the DC bus is c_dc_hf, 0.47 uF film")
    print(f"(modules.ato:348).  |Z| at {F_SW/1e3:.0f} kHz = "
          f"{1.0/(2*math.pi*F_SW*C_DC_HF):.2f} ohm.  The electrolytic bank's own")
    print(f"120 Hz ESR is tan(d)/(2*pi*f*C) = "
          f"{CAP_TAN_DELTA/(2*math.pi*120*C_UNIT):.4f} ohm/cap and falls with")
    print("frequency.  The film cap is 2 orders of magnitude the higher")
    print("impedance and ALSO sits hv_plus->hv_minus, which does not span the")
    print("Q_high/tank/midpoint loop at all.  It relieves the electrolytics of")
    print("essentially none of the HF current -- A6 stands.")
    print()
    print(f"{'case':<16}{'P_out':>8}{'LF/cap':>9}{'HF/cap':>9}{'total':>8}"
          f"{'x rated':>9}   dominant")
    for c in CASES:
        for p_o in (1800.0, 900.0, 400.0, 150.0):
            o = op_at(c, p_o)
            lf = o.i_cap_unit_eq_dft
            hf = CAP_HF_SHARE * c.i_tank_1800 * math.sqrt(p_o / P_OUT_DECLARED) / FM_SW
            tot = math.hypot(lf, hf)
            dom = "LF (rectifier)" if lf > hf else "HF (tank)"
            print(f"{c.name:<16}{p_o:8.0f}{lf:9.2f}{hf:9.2f}{tot:8.2f}"
                  f"{tot/CAP_I_RIPPLE_RATED:9.2f}   {dom}")
    print()
    print("Ceiling from EACH term alone (P_out at which it alone hits 2.70 A):")
    print(f"{'case':<16}{'LF alone':>12}{'HF alone':>12}{'both':>12}")
    for c in CASES:
        def m_lf(op, p):
            return op.i_cap_unit_eq_dft

        def m_hf(op, p, c=c):
            return CAP_HF_SHARE * c.i_tank_1800 * math.sqrt(max(p, 0) / P_OUT_DECLARED) / FM_SW

        def m_both(op, p, c=c):
            return cap_equiv_total(op, c.i_tank_1800, p, "sqrt")
        a = ceiling(c, m_lf, CAP_I_RIPPLE_RATED)
        b = ceiling(c, m_hf, CAP_I_RIPPLE_RATED)
        d = ceiling(c, m_both, CAP_I_RIPPLE_RATED)
        f = lambda x: ("inf" if math.isinf(x) else f"{x:.0f} W")
        print(f"{c.name:<16}{f(a):>12}{f(b):>12}{f(d):>12}")
    print()

    # ---------------------------------------------------------------- sec.3
    hr()
    print("3. HEADROOM TO 1800 W, AND WHAT PFC WOULD DO")
    hr("-")
    print("First, the arithmetic that no component choice can move:")
    va15 = V_LINE_RMS * I_BRANCH_DECLARED
    va12 = V_LINE_RMS * I_BRANCH_NEC_CONT
    print(f"   A 15 A / 120 V branch circuit delivers at most "
          f"{va15:.0f} VA.")
    print(f"   The declared output is {P_OUT_DECLARED:.0f} W.")
    print(f"   P_out = V * I * PF * eta  ->  required PF * eta = "
          f"{P_OUT_DECLARED/va15:.3f}")
    print( "   i.e. 1800 W output on a 15 A branch needs UNITY power factor AND")
    print( "   100% efficiency simultaneously.  There is no headroom of any kind.")
    print(f"   At the repo's own eta bracket the ceiling is:")
    for eta in (ETA_BEST, ETA_CENTRAL, ETA_WORST):
        print(f"      PF=1.00, eta={eta:.2f}  ->  P_out <= {va15*eta:6.0f} W "
              f"(15 A)   |  {va12*eta:6.0f} W (NEC 12 A continuous)")
    print()
    print("Now PFC.  At PF = 0.95+ the line current becomes a sinusoid,")
    print("I = P_in / (V_line * PF), crest factor sqrt(2):")
    print(f"{'eta':>6}{'PF':>7}{'Pin W':>9}{'Iline Arms':>12}{'Ipk A':>8}  verdict")
    for eta in (ETA_BEST, ETA_CENTRAL, ETA_WORST):
        for pf in (1.00, 0.99, 0.95):
            p_in = P_OUT_DECLARED / eta
            il = p_in / (V_LINE_RMS * pf)
            fails = [lbl for lbl, lim in
                     (("NEC-12", I_BRANCH_NEC_CONT), ("branch-15", I_BRANCH_DECLARED),
                      ("fuse-16", I_FUSE_RATED), ("CMC-16", I_CMC_RATED),
                      ("K1-IEC-16", I_K1_IEC), ("K1-UL-20", I_K1_UL))
                     if il > lim]
            v = "clears every rating" if not fails else "STILL EXCEEDS " + ", ".join(fails)
            print(f"{eta:6.2f}{pf:7.2f}{p_in:9.0f}{il:12.2f}"
                  f"{il*math.sqrt(2):8.2f}  {v}")
    print()
    print("What branch circuit would 1800 W actually need?")
    print(f"{'branch':>10}{'VA':>8}{'cont. VA (80%)':>16}"
          f"{'P_out at PF=0.95':>19}{'  continuous-rule P_out':>24}")
    for amps in (15, 20, 30):
        va = V_LINE_RMS * amps
        vac = va * 0.8
        print(f"{amps:9d}A{va:8.0f}{vac:16.0f}"
              f"{va*0.95*ETA_WORST:9.0f}-{va*0.95*ETA_BEST:<9.0f}"
              f"{vac*0.95*ETA_WORST:12.0f}-{vac*0.95*ETA_BEST:<9.0f}")
    print("   -> 1800 W output is NOT reachable on a 15 A/120 V branch under")
    print("      any power factor or efficiency this repo asserts, and is only")
    print("      marginal on a 20 A/120 V branch once the continuous-load rule")
    print("      is applied.  This is a branch-circuit-class decision, not a")
    print("      component-selection one.")
    print()
    print("Highest P_out a PF-corrected front end could take from each rating:")
    for lbl, lim in (("NEC 12 A continuous", I_BRANCH_NEC_CONT),
                     ("declared 15 A", I_BRANCH_DECLARED),
                     ("fuse / CMC / K1-IEC 16 A", I_CMC_RATED),
                     ("K1 UL508 20 A", I_K1_UL)):
        p95 = V_LINE_RMS * lim * 0.95
        print(f"   {lbl:<26} PF=0.95: P_out = {p95*ETA_WORST:5.0f} W (eta .85)"
              f" .. {p95*ETA_BEST:5.0f} W (eta .92)")
    print()
    print("And the bus capacitors under PFC -- does that close too?")
    print("A boost PFC removes the 60 Hz recharge pulse but replaces it with")
    print("the unavoidable 120 Hz second-harmonic bus current of any")
    print("single-phase PFC, I_120 = P_in / (2 * V_bus) [derived], and it does")
    print("NOT touch the 47 kHz tank term at all:")
    for c in CASES:
        p_in = P_OUT_DECLARED / c.eta
        for v_bus_pfc in (340.0, 400.0):
            i_lf_unit = p_in / (2.0 * v_bus_pfc) / N_PARALLEL
            hf = CAP_HF_SHARE * c.i_tank_1800 / FM_SW
            tot = math.hypot(i_lf_unit, hf)
            print(f"   {c.name:<16} Vbus={v_bus_pfc:.0f} V:  120Hz "
                  f"{i_lf_unit:5.2f} A/cap + HF {hf:5.2f} A/cap = "
                  f"{tot:5.2f} A  ->  {tot/CAP_I_RIPPLE_RATED:5.2f}x rated")
    print()

    # ---------------------------------------------------------------- sec.4
    hr()
    print("4. IS THE BUS-CAP OVERAGE THE TOPOLOGY, OR AN INDEPENDENT SELECTION ERROR?")
    hr("-")
    print("Hold the topology fixed; sweep ONLY the capacitance.  Load model is")
    print("constant-RESISTANCE here (see simulate() docstring): a fixed-frequency")
    print("SRC into a fixed pan delivers P proportional to V_bus^2, and a")
    print("constant-power load is unconditionally unstable on a deliberately")
    print("soft bus, so constant power would report a collapse that is an")
    print("artefact of the load model, not of the capacitor.")
    print()
    c = CASES[1]
    print("Every row below delivers the SAME 1800 W output (2000 W in): the")
    print("load resistance is re-solved at each capacitance so the comparison")
    print("is apples-to-apples.  'unreachable' means no finite load resistance")
    print("gets 1800 W out of a bus that sagged that hard.")
    print()
    print(f"{'C/half uF':>10}{'theta':>8}{'Iline A':>9}{'PF':>7}{'Vhalf':>8}"
          f"{'Vpp':>7}{'Pout W':>8}{'LF/cap':>8}{'HF/cap':>8}{'x rated':>9}")
    p_in_t = P_OUT_DECLARED / c.eta
    for c_uf in (100, 200, 330, 470, 680, 1000, 1500, 2200, 3600, 5000):
        op = simulate_cr_at_power(p_in_t, c.rs, c.vf0, c.rd, c_uf * 1e-6)
        p_del_out = 2.0 * op.p_delivered_half * c.eta
        if p_del_out < 0.9 * P_OUT_DECLARED:
            print(f"{c_uf:10d}{op.theta_deg:8.1f}{op.i_line_rms:9.2f}"
                  f"{op.pf:7.3f}{op.v_half_avg:8.1f}{op.v_half_pp:7.1f}"
                  f"{p_del_out:8.0f}   unreachable at this capacitance")
            continue
        hf = CAP_HF_SHARE * c.i_tank_1800 * math.sqrt(
            max(p_del_out, 0.0) / P_OUT_DECLARED) / FM_SW
        tot = math.hypot(op.i_cap_unit_eq_dft, hf)
        print(f"{c_uf:10d}{op.theta_deg:8.1f}{op.i_line_rms:9.2f}{op.pf:7.3f}"
              f"{op.v_half_avg:8.1f}{op.v_half_pp:7.1f}{p_del_out:8.0f}"
              f"{op.i_cap_unit_eq_dft:8.2f}{hf:8.2f}"
              f"{tot/CAP_I_RIPPLE_RATED:9.2f}")
    print()
    print("Read the two ripple columns separately.")
    print("  LF/cap  falls steeply with capacitance -- THAT part of the overage")
    print("          is the 3600 uF choice, and it is fixable by capacitance")
    print("          alone (the direction the committed architecture review,")
    print("          2026-07-26-bus-capacitor-architecture-review.md sec.4,")
    print("          already argued from the Hsieh 2023 precedent).")
    print("  HF/cap  is FLAT in capacitance at constant delivered power -- it")
    print("          is the 47 kHz tank current with no adequate HF bypass, an")
    print("          INDEPENDENT selection error that no capacitance value, and")
    print("          no PFC, removes.")
    print()
    print("At the SAME 1800 W, what does the 60 Hz term alone need?")
    for c2 in CASES:
        p_in2 = P_OUT_DECLARED / c2.eta
        hit = None
        for c_uf in (100, 150, 200, 250, 330, 400, 470, 560, 680, 820,
                     1000, 1200, 1500, 1800, 2200, 2700, 3300, 3600):
            op = simulate_cr_at_power(p_in2, c2.rs, c2.vf0, c2.rd,
                                      c_uf * 1e-6, n_cycles=30)
            p_del_out = 2.0 * op.p_delivered_half * c2.eta
            if p_del_out < 0.9 * P_OUT_DECLARED:
                continue
            if op.i_cap_unit_eq_dft <= CAP_I_RIPPLE_RATED and hit is None:
                hit = (c_uf, op)
        if hit:
            o = hit[1]
            print(f"   {c2.name:<16} C/half {hit[0]:5d} uF -> LF "
                  f"{o.i_cap_unit_eq_dft:5.2f} A/cap at 1800 W, but Iline "
                  f"{o.i_line_rms:5.2f} A, PF {o.pf:.3f}, Vhalf "
                  f"{o.v_half_avg:5.1f} V ({o.v_half_pp:.0f} Vpp)")
        else:
            print(f"   {c2.name:<16} NO capacitance in 100-3600 uF gets the LF"
                  f" term under 2.70 A/cap while still delivering 1800 W")
    print()

    # ---------------------------------------------------------------- sec.5
    hr()
    print("5. CROSS-CHECKS AGAINST OTHER COMMITTED REPO ASSERTIONS")
    hr("-")
    op = ops_1800["central"]
    print("main.ato:65  v_bus_ripple_max = 20V, assert < 10% of 340V")
    print(f"    simulated total bus ripple at 1800 W, central: "
          f"{op.v_bus_pp:.1f} Vpp  -> {'VIOLATED' if op.v_bus_pp > 20 else 'ok'}")
    print("main.ato:63  v_bus_nominal = 340V, assert within 280V to 380V")
    print(f"    simulated average total bus at 1800 W, central: "
          f"{op.v_bus_avg:.1f} V  -> "
          f"{'VIOLATED' if not (280 <= op.v_bus_avg <= 380) else 'ok'}")
    for c in CASES:
        o = ops_1800[c.name]
        flag = "VIOLATED" if not (280 <= o.v_bus_avg <= 380) else "ok"
        print(f"      ({c.name}: {o.v_bus_avg:.1f} V, {o.v_bus_pp:.1f} Vpp -> {flag})")
    print("main.ato:49  i_peak_max = 25A; constraints ACMains.i_max = 15A")
    for c in CASES:
        o = ops_1800[c.name]
        print(f"      ({c.name}: line PEAK {o.i_line_pk:.1f} A at 1800 W)")
    print()
    print("Diode loading at 1800 W (each MUR1560; IF(AV)=15A, IFRM=30A, PD=100W):")
    print(f"{'case':<16}{'Iavg A':>9}{'Irms A':>9}{'Ipk A':>9}{'IFRM x':>9}"
          f"{'Pdiss W':>10}{'Tj rise':>9}")
    for c in CASES:
        o = ops_1800[c.name]
        pdiss = c.vf0 * o.i_diode_avg + c.rd * o.i_diode_rms ** 2
        print(f"{c.name:<16}{o.i_diode_avg:9.2f}{o.i_diode_rms:9.2f}"
              f"{o.i_diode_pk:9.1f}{o.i_diode_pk/D_IFRM:9.2f}{pdiss:10.1f}"
              f"{pdiss*D_RTH_JC:9.1f}")
    print("    (Tj rise is junction-to-CASE only, RthJC = 1.5 C/W [datasheet];")
    print("     no heatsink or RthCA for D1/D2 is committed anywhere -> the")
    print("     case temperature itself is [UNOBTAINABLE] from repo state.)")
    print()

    hr()
    print("6. NUMERICAL CONVERGENCE")
    hr("-")
    print(f"{'samples/cycle':>15}{'cycles':>8}{'Iline A':>10}{'theta':>8}{'Icap/u':>9}")
    for npc, ncy in ((3000, 40), (6000, 40), (12000, 40), (6000, 80)):
        o = simulate(P_OUT_DECLARED / ETA_CENTRAL, CASES[1].rs, CASES[1].vf0,
                     CASES[1].rd, n_per_cycle=npc, n_cycles=ncy)
        print(f"{npc:15d}{ncy:8d}{o.i_line_rms:10.3f}{o.theta_deg:8.2f}"
              f"{o.i_cap_unit_rms:9.3f}")
    print()
    hr()


if __name__ == "__main__":
    main()
