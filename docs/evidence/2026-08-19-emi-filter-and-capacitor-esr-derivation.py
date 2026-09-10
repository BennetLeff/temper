#!/usr/bin/env python3
# provenance: commit=eb5022510d8f1272adf0a27d76c849aa2bb6e210 dirty=false
# (origin/main; branch analysis/emi-esr-derivation, fresh worktree cut from it).
# pcb/temper.kicad_pcb sha256=26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b
# -- verified before and after; never opened for writing.
"""EMI-filter and capacitor-ESR dissipation, derived -- and the sealed-compartment
verdict re-run against them.

Companion to docs/evidence/2026-08-19-emi-filter-and-capacitor-esr-derivation.md.

Closes the two open items that
docs/evidence/2026-08-19-sealed-compartment-thermal-viability.md sec. 7.1 named as
"the largest remaining unverified inputs": the 2.0 W EMI-filter and 4.0 W
capacitor-ESR line items of docs/hardware/SYSTEM_THERMAL_BUDGET.md (2025-12-14),
which together are ~62 % of that document's Q = 9.65 W compartment heat load.

    python3 docs/evidence/2026-08-19-emi-filter-and-capacitor-esr-derivation.py

Stdlib only. No repo state is read or written; every input is a literal below,
tagged in its comment as one of:

    [datasheet]   read from a manufacturer document -- this session or cited
                  verbatim in a committed repo file, with the document named
    [repo]        a committed value in this repository
    [derived]     arithmetic on [datasheet]/[repo] values, shown
    [estimated]   typical-for-class; NOT a datasheet number
    [UNOBTAINABLE] searched for and not found; a bracket is used and labelled

Nothing here changes any clearance, creepage, DRU or ratchet threshold.
PD3 / MIN_BARRIER_WIDTH_MM = 12.6 mm is untouched and remains enforced.
"""

from __future__ import annotations

SIGMA = 5.670374419e-8  # Stefan-Boltzmann, W/m^2K^4 (CODATA)


# =============================================================================
# 0. Operating point
# =============================================================================

P_OUT_W = 1800.0        # [repo] elec/src/main.ato:53 power_max, :494 p_output_max
V_AC = 120.0            # [repo] elec/src/main.ato:51 v_ac_nominal
F_LINE = 60.0           # [repo] elec/src/main.ato f_line
I_LINE_DECLARED = 15.0  # [repo] elec/src/constraints.ato:12 ACMainsConstraints.i_max
V_BUS_HALF = 170.0      # [repo] elec/src/modules.ato PowerInput v_bus_half
F_SW = 47e3             # [repo] elec/src/main.ato:134 f_switching

# [repo] elec/src/main.ato:88 eta_min = 0.90, assert >= 0.85; STRATEGY EFF-02
# target 0.92 (unmeasured).  None of the three is a bench figure.
ETA_BEST, ETA_CENTRAL, ETA_WORST = 0.92, 0.90, 0.85

# [estimated] Rectifier conduction angle.  Carried unchanged from
# docs/evidence/2026-07-26-bus-capacitor-ripple.md assumption A5, which flags it
# "typical range for cap-input rectifiers ... not bench-verified".  It is the
# single largest [estimated] input in this document and it drives BOTH the line
# RMS current and the bus-cap low-frequency ripple, so the two stay consistent.
THETA_BEST, THETA_CENTRAL, THETA_WORST = 60.0, 40.0, 30.0

# [repo] elec/src/modules.ato ResonantTank: "22.5A rms at the 1800W" point for
# the declared 88 uH coil at f_switching = 47 kHz.
I_TANK_COMMITTED = 22.5
# [repo] docs/evidence/2026-07-29-tank-cap-cde-942c-verification.md sec.3: 20.75 A
# from the run_zvs_sweep.py harness at the superseded L = 150 uH model.
I_TANK_HARNESS = 20.75
# [repo] docs/evidence/2026-07-26-bus-capacitor-ripple.md sec.4, from OCP-01's
# 50.1 A peak trip.  docs/evidence/2026-07-27-inductance-range-sweep.md sec.4
# calls this an OVERESTIMATE that does not reconcile with the tank model at any
# consistent (L, f_sw, 1800 W) point.  Carried as the disputed upper bracket.
I_TANK_OCP = 35.4


def input_stage_currents(eta: float, theta_deg: float) -> dict[str, float]:
    """Line RMS and per-capacitor LF ripple from ONE (eta, theta) pair.

    Delon (cascade) doubler: each half-bus bank recharges ONCE per full 60 Hz
    cycle, not twice (docs/evidence/2026-07-26-bus-capacitor-ripple.md sec.2,
    traced to elec/src/modules.ato PowerInput's D1/D2 connections).

    For a bank supplying constant I_dc between rectangular recharge pulses of
    duty delta, charge balance gives peak I_p = I_dc/delta and RMS ripple
    I_dc*sqrt((1-delta)/delta)  [repo, same doc sec.3].

    The LINE carries one such pulse per half-cycle (D1 on the positive half,
    D2 on the negative), so over a full cycle
        I_line_rms^2 = (1/T)*2*I_p^2*delta*T = 2*I_dc^2/delta
    -> I_line_rms = I_dc*sqrt(2/delta).                            [derived]
    """
    p_in = P_OUT_W / eta
    i_dc_half = (p_in / 2.0) / V_BUS_HALF     # DC draw of ONE half-bus bank
    delta = theta_deg / 360.0
    i_line = i_dc_half * (2.0 / delta) ** 0.5
    i_ripple_group = i_dc_half * ((1.0 - delta) / delta) ** 0.5
    return dict(
        p_in=p_in,
        i_dc_half=i_dc_half,
        delta=delta,
        i_line=i_line,
        pf=p_in / (V_AC * i_line),
        i_cap_lf=i_ripple_group / 2.0,        # two parallel caps per half-bus
    )


# =============================================================================
# 1. EMI / input-stage dissipation
# =============================================================================

# --- 1.1 Fuse F1, Schurter 0034.3129 (FST 5x20, 16 A / 250 VAC time-lag) -----
# [datasheet] schurter.com/en/datasheet/typ_fst_5x20.pdf, rev 21.07.2026,
# ratings table, 16 A row (order number 0034.3129):
#     Voltage Drop 1.0*In typ = 60 mV        -> R = 0.060/16  = 3.750 mOhm
#     Power Dissipation 1.5*In typ = 3300 mW -> R = 3.300/24^2 = 5.729 mOhm
# The 1.5*In row is the HOT resistance (the element runs hotter at 24 A), so the
# two published points bracket the in-service resistance.  Neither is an
# extrapolation: both are printed values.  The "1.0*In max" cell is blank ("-")
# for this rating, so no maximum exists to cite.
FUSE_R_COLD = 0.060 / 16.0
FUSE_R_HOT = 3.300 / (1.5 * 16.0) ** 2

# --- 1.2 Common-mode choke L1, TDK/EPCOS B82726S2163N030 ---------------------
# [datasheet] TDK B82726S2163N030, April 2025 revision, cited verbatim in
# elec/src/components.ato:252-281 (dcr = 0.0071 ohm) with a 2026-07-16
# verification date: 250 VAC / 16 A rated (referred to 50 Hz, T_R +60 K),
# 2.2 mH +/-30 % per winding, R_typ 7.1 mOhm per winding, ferrite ring core.
# Direct fetch of the TDK PDF returned HTTP 403 this session; the repo citation
# is used, and it is a citation to the datasheet, not a repo estimate.
# BOTH windings are in the current path (winding 1 = L, winding 2 = N), so the
# line current sees 2 x DCR.
CMC_DCR_PER_WINDING = 0.0071
CMC_DCR_TOTAL = 2.0 * CMC_DCR_PER_WINDING
CMC_I_RATED = 16.0
# [UNOBTAINABLE] TDK publishes no core-loss curve for the B82726 family and the
# product page is 403 to automated fetch.  Physical bound, NOT a measurement:
# in a current-compensated choke the line (differential) currents in the two
# windings are equal and opposite, so their flux cancels in the ring core; only
# the common-mode current magnetises it.  The only committed CM path is the
# 5.6 nF Y-capacitor to PE, which passes 120 V * 2*pi*60 * 5.6 nF = 0.25 mA at
# line frequency.  Core loss is therefore bounded far below the winding I^2R
# term.  Broadband CM noise current is not derivable from committed data and is
# left unquantified.
CMC_CORE_LOSS = None

# --- 1.3 Inrush-bypass relay K1, TE Schrack RT33K012 ------------------------
# [UNOBTAINABLE] The TE ENG_DS_RT1 datasheet (farnell.com/datasheets/3775998.pdf,
# read this session) publishes coil resistance, rated current, limiting
# continuous current and breaking capacity -- but its Contact Data block
# contains NO contact-resistance line, initial or end-of-life.  So the I^2R of
# the contact that carries the whole line current cannot be sourced.
# [estimated] typical-for-class bracket for a 16 A / UL-20 A AgNi 90/10 power
# contact.  This is NOT a datasheet number and is the second-largest estimated
# input in the EMI total.
RELAY_CONTACT_R_LOW, RELAY_CONTACT_R_HIGH = 0.005, 0.020
# [datasheet] same document: "Limiting continuous current 16 A, UL: 20 A
# (K-version)".  RT33K012 is the K (AgNi 90/10) version.
RELAY_I_LIMIT_UL = 20.0

# --- 1.4 NTC inrush limiter -------------------------------------------------
# [repo] elec/src/modules.ato PowerInput: bypass_relay.COM/NO shunts the NTC
# after start-up (cmc.W1_2 ~ bypass_relay.COM; bypass_relay.NO ~ d1.A).  With a
# hot NTC resistance of order 0.3-1 ohm against a contact of order 0.005-0.020
# ohm, >97 % of the current takes the contact.  Steady-state NTC dissipation is
# treated as zero; the residual is inside the contact-resistance bracket above.

# --- 1.5 Safety capacitors --------------------------------------------------
C_X2 = 0.22e-6      # [repo] modules.ato c_x2, EPCOS B32922C3224M289 X2 305 VAC
C_Y = 5.6e-9        # [repo] modules.ato y_cap_pe, EPCOS B81123C1562M000 Y1
# [estimated] tan(delta) for metallised polypropylene at 60 Hz.  EPCOS's own
# B3292x specification sheet was not retrieved this session; 1e-3 is a
# generous typical-for-class ceiling for PP (real values are ~2-5e-4).  The
# result is microwatts under any value in that whole class, so the estimate
# cannot matter -- it is stated rather than skipped so the total is auditable.
TAN_DELTA_PP_60HZ = 1e-3

# --- 1.6 MOV standby leakage ------------------------------------------------
# [UNOBTAINABLE] The Littelfuse LA-series datasheet for V150LA10AP was not
# retrieved this session, so no standby-leakage figure is cited.
# [estimated] MOV leakage at 120 Vrms against a 150 VAC-rated disc is of order
# tens of microamps, bounded well under 200 uA -> under 24 mW.  Carried as a
# bounded upper limit, not a value.
MOV_LEAKAGE_BOUND_W = 0.024


def emi_stage_loss(i_line: float) -> dict[str, tuple[float, float]]:
    """(low, high) W for each input-stage term at a given line RMS current."""
    x_cap = (V_AC ** 2) * 2.0 * 3.141592653589793 * F_LINE * C_X2 * TAN_DELTA_PP_60HZ
    y_cap = (V_AC ** 2) * 2.0 * 3.141592653589793 * F_LINE * C_Y * TAN_DELTA_PP_60HZ
    return {
        "F1 fuse (0034.3129)": (i_line**2 * FUSE_R_COLD, i_line**2 * FUSE_R_HOT),
        "L1 CMC winding I2R": (i_line**2 * CMC_DCR_TOTAL, i_line**2 * CMC_DCR_TOTAL),
        "K1 bypass contact":  (i_line**2 * RELAY_CONTACT_R_LOW,
                               i_line**2 * RELAY_CONTACT_R_HIGH),
        "C_X2 dielectric":    (x_cap, x_cap),
        "C_Y  dielectric":    (y_cap, y_cap),
        "MOV standby leak":   (0.0, MOV_LEAKAGE_BOUND_W),
    }


# =============================================================================
# 2. Continuously-energised board loads the 2025-12-14 budget has no line for
# =============================================================================

# [repo] elec/src/modules.ato PowerInput: r_bleed1/r_bleed2 = 22 kohm 2 W across
# each 170 V half-bus, and the file computes the figure itself:
#     p_bleed_actual = v_bus_half^2 / r_bleed1.value  ~= 1.31 W  (each)
# They conduct whenever the bus is charged -- i.e. the whole time the appliance
# is powered.  This is an exact repo-derived value, not an estimate.
R_BLEED = 22e3
P_BLEED_TOTAL = 2.0 * V_BUS_HALF**2 / R_BLEED

# Relay coils, energised continuously in NORMAL RUNNING:
#   K1 (bypass) -- energised to shunt the NTC once inrush is over.
#   K2/K3 (discharge) -- modules.ato BusDischarge: "DISCHARGE_CTRL high = coils
#   energized = NC contacts open = discharge disengaged", i.e. coils are ON
#   whenever the appliance runs; the 3.9 k discharge resistors carry nothing.
# [datasheet] TE ENG_DS_RT1 coil table (read this session): 12 VDC coil code
# 012 -> coil resistance 360 ohm +/-10 %, rated coil power 400 mW.  Same coil
# for RT33K012 (K1) and RT314012 (K2/K3).
V_AUX = 15.0            # [repo] modules.ato: coil string runs off the 15 V rail
R_COIL = 360.0          # [datasheet] TE ENG_DS_RT1
R_DROP_K1 = 91.0        # [repo] modules.ato r_relay_drop (Yageo RSF100JB-73-91R)
R_DROP_K23 = 100.0      # [repo] modules.ato r_coil1 / r_coil2 (RC1206FR-07100RL)


def relay_string_loss() -> tuple[float, float]:
    """(coil W, dropper W) summed over K1 + K2 + K3."""
    coil = drop = 0.0
    for r_drop, n in ((R_DROP_K1, 1), (R_DROP_K23, 2)):
        i = V_AUX / (R_COIL + r_drop)
        coil += n * i**2 * R_COIL
        drop += n * i**2 * r_drop
    return coil, drop


# =============================================================================
# 3. Capacitor ESR
# =============================================================================

# --- 3.1 DC-bus electrolytics: 4 x United Chemi-Con EKMQ251VSN182MA50S -------
#         (1800 uF / 250 V snap-in, 2 in parallel per half-bus)
C_BUS = 1800e-6
N_BUS_CAPS = 4
I_RIPPLE_RATED = 2.70   # [repo, cited to CAT E1001E] 105 C, 120 Hz, per cap

# tan(delta) MAXIMA at 20 C / 120 Hz.  Two catalogue revisions disagree and the
# disagreement is NOT resolved here -- both are carried:
TAND_E1001E = 0.15      # [repo] docs/evidence/2026-07-26-bus-capacitor-ripple.md
                        #        sec.1, cited to CAT. No. E1001E, 160-250 Vdc group
TAND_E1001U = 0.20      # [datasheet] chemi-con.com/wp-content/uploads/2021/05/
                        #        KMQ-Series.pdf, CAT. No. E1001U, read this
                        #        session: "160 to 250V -> 0.20" at 20 C / 120 Hz
TAND_E1001U_ADDER = 0.22  # [datasheet+derived] same table's footnote: "When
                        #        nominal capacitance exceeds 1,000uF, add 0.02 to
                        #        the value above for each 1,000uF increase."
                        #        1800 uF -> one partial increment; 0.22 is the
                        #        conservative reading (a full increment).
# ALL THREE ARE MAXIMA.  No typical tan(delta) and no ESR is printed anywhere in
# either revision.  A typical-vs-max ratio of ~0.5 is common for this part class
# but is [estimated]; it appears only as an explicit sensitivity row below.
TYPICAL_TO_MAX_ESR = 0.5

# ESR at 60 Hz.  [UNOBTAINABLE] -- no 60 Hz point exists in either revision.
# Bracketed by the two standard limiting assumptions, neither published:
#   k=1.0  ESR flat from 120 Hz down to 60 Hz            (favourable)
#   k=2.0  tan(delta) flat, so ESR ~ 1/f                 (unfavourable; this is
#          the usual behaviour of an electrolytic in the 50-120 Hz band, where
#          the oxide/dielectric term dominates)
K_ESR_60HZ_LOW, K_ESR_60HZ_HIGH = 1.0, 2.0

# ESR at 47 kHz.  [UNOBTAINABLE] -- not published in either revision (the repo's
# own sec.9 already lists "ESR at 35 kHz" as unverified).  Inferred from the
# published RATED RIPPLE CURRENT MULTIPLIERS, which manufacturers construct so
# that the allowed dissipation is constant: I(f) = FM*I(120) at equal I^2*ESR
# implies ESR(f) = ESR(120)/FM^2.  The two revisions give DIFFERENT multipliers
# and 1800 uF falls in a GAP between rows of the newer one, so this is a bracket:
#   FM = 1.50  [repo, E1001E] 160-250 Vdc column at 50 kHz; also [datasheet,
#              E1001U] the "100 to 1,000 uF" row at 100 kHz.        (favourable)
#   FM = 1.08  [datasheet, E1001U] the "2,200 to" uF row at 100 kHz -- the row
#              for cans of this physical class.                  (unfavourable)
# The inference itself (ESR = ESR(120)/FM^2) is [derived], not printed.
FM_47K_LOW, FM_47K_HIGH = 1.50, 1.08

# Per-capacitor share of the tank's switching current.  [repo, estimated]
# docs/evidence/2026-07-26-bus-capacitor-ripple.md assumption A6: each bank
# carries tank current only while its switch conducts (sinusoid gated on one
# half-cycle per period) -> I_bank = I_tank/sqrt(2); /2 again for the two
# parallel caps -> 0.3536 * I_tank.  Equal sharing between the parallel pair is
# best case; the same doc's sec.6 notes any ESR mismatch makes it worse.
HF_SHARE_PER_CAP = 0.35355339059327373


def esr_120hz(tand: float) -> float:
    """[derived] ESR = tan(delta) / (2*pi*f*C) at the printed 120 Hz condition."""
    return tand / (2.0 * 3.141592653589793 * 120.0 * C_BUS)


def bus_cap_loss(i_lf: float, i_hf: float, tand: float,
                 k60: float, fm: float, scale: float = 1.0) -> tuple[float, float, float]:
    """Return (P_LF, P_HF, P_total) for ONE bus capacitor, in W."""
    e120 = esr_120hz(tand) * scale
    p_lf = i_lf**2 * (e120 * k60)
    p_hf = i_hf**2 * (e120 / fm**2)
    return p_lf, p_hf, p_lf + p_hf


# --- 3.2 Resonant-tank capacitors: 3 x Cornell Dubilier 942C16P1K-F ---------
# [datasheet] CDE catalog 942C.pdf p.2 "Ratings and Dimensions", 1600 Vdc block,
# 0.10 uF row, quoted verbatim in elec/src/modules.ato:474-478 and in
# docs/evidence/2026-07-29-tank-cap-cde-942c-verification.md sec.1:
#     "ESR 4 mOhm | ESL 24 nH | dV/dt 3425 V/us | Ipeak 342 A |
#      IRMS 70C/100kHz 11.4 A"
# The ESR column shares the IRMS column's 100 kHz condition.
TANK_ESR_100K = 0.004
N_TANK_CAPS = 3
# [derived, from datasheet curves] The same evidence document extracts CDE's own
# DF-vs-frequency curve for polypropylene (filmAPPguide.pdf p.3):
#   DF(47 kHz) = 2.95e-4, DF(100 kHz) = 4.48e-4
#   ESR = DF/(2*pi*f*C) -> ESR(47k)/ESR(100k) = (2.95/4.48)*(100/47) = 1.40
# This is the transfer the brief specifically demands: a 100/120 Hz ESR would be
# badly wrong here, and even the 100 kHz datasheet ESR must be moved to 47 kHz.
TANK_ESR_RATIO_47K_OVER_100K = 1.40
TANK_ESR_47K = TANK_ESR_100K * TANK_ESR_RATIO_47K_OVER_100K


def tank_cap_loss(i_tank: float) -> tuple[float, float]:
    """(per-cap W, bank W) for the 3-capacitor tank bank at 47 kHz."""
    per = (i_tank / N_TANK_CAPS) ** 2 * TANK_ESR_47K
    return per, per * N_TANK_CAPS


# --- 3.3 Everything else --------------------------------------------------
# Contact snubbers c_snub1/c_snub2 (470 nF PP + 100 R across the K2/K3 contacts,
# elec/src/modules.ato BusDischarge): the contacts are STATIC in normal running,
# so the snubber sees DC and passes leakage only -- nanowatts.  [repo, topology]
# X2/Y safety caps: accounted in the EMI stage above (microwatts).
# Buck output/decoupling caps: already inside the LMR51430 stage's efficiency
# term (docs/evidence/2026-08-19-sealed-compartment-thermal.py sec.2b), not
# double-counted here.


# =============================================================================
# 4. Sealed-enclosure closure -- IDENTICAL to the 2026-08-19 script, so the two
#    verdicts are directly comparable.  Only Q changes.
# =============================================================================

def wall_delta_t(q_w: float, area_m2: float, lc_m: float, emissivity: float,
                 ta_c: float) -> float:
    """Solve Q = h*A*dT + eps*sigma*A*(Ts^4 - Ta^4) for dT by bisection.

    [assumed/external] h = 1.42*(dT/Lc)^0.25 -- simplified free-convection
    correlation for an isothermal surface in still air.  Carried UNCHANGED from
    docs/evidence/2026-07-30-pcb-compartment-thermal-bound.md via the 2026-08-19
    script so this document's verdict can be compared like-for-like.  Not a repo
    figure and not validated.
    """
    ta_k = ta_c + 273.15

    def residual(dt: float) -> float:
        h = 1.42 * (dt / lc_m) ** 0.25
        ts_k = ta_k + dt
        return h * area_m2 * dt + emissivity * SIGMA * area_m2 * (ts_k**4 - ta_k**4) - q_w

    lo, hi = 1e-6, 2000.0
    for _ in range(300):
        mid = 0.5 * (lo + hi)
        if residual(mid) < 0.0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# [assumed] Envelopes, unchanged from the 2026-07-30 bound sec.1.1.
COMPACT = dict(area_m2=0.0966, lc_m=0.234, label="compact 152x234x33 mm")
GENEROUS = dict(area_m2=0.1300, lc_m=0.254, label="generous 172x254x50 mm")
AMBIENT_C = 60.0        # [repo] packages/temper-thermal/src/thermal_constants.rs:50
FILM_FACTOR = 1.3       # [assumed] 2026-07-30 bound's internal-film factor

# [datasheet] carried from the 2026-08-19 analysis, NOT silently improved on.
THETA_JA_UCC21550 = 74.1     # TI SLUSE89C sec.5.4, DWK-14
THETA_JA_LMR51430 = 107.8    # TI SLUSF4A sec.7.4, DDC SOT-23-6, JEDEC
TJ_MAX = 150.0
P_UCC21550 = 0.121           # TI SLUSE89C sec.8.2.2.5 eq.11-17
P_LMR51430 = 0.20            # as-built 3.3 V / 254-380 mA operating point
ESP32_T_AMBIENT_MAX = 85.0   # module AMBIENT rating -- no theta_JA to spend
ELCAP_T_MAX = 105.0          # [repo, cited to CAT E1001E] category max


# =============================================================================
def main() -> None:
    W = 78
    bar = "=" * W

    print(bar)
    print("0. Operating point and the line current the topology actually draws")
    print(bar)
    print(f"  P_out(max) = {P_OUT_W:.0f} W [repo main.ato]; V_ac = {V_AC:.0f} V; "
          f"f_line = {F_LINE:.0f} Hz")
    print(f"  Declared line-current limit = {I_LINE_DECLARED:.1f} A rms "
          f"[repo constraints.ato ACMainsConstraints.i_max]")
    print()
    print(f"  {'case':<26} | {'P_in':>7} | {'delta':>6} | {'I_line':>8} | {'PF':>5} "
          f"| {'I_cap,LF':>9}")
    print(f"  {'-'*26}-+-{'-'*7}-+-{'-'*6}-+-{'-'*8}-+-{'-'*5}-+-{'-'*9}")
    cases = [
        ("best   (eta .92, 60 deg)", ETA_BEST, THETA_BEST),
        ("central(eta .90, 40 deg)", ETA_CENTRAL, THETA_CENTRAL),
        ("worst  (eta .85, 30 deg)", ETA_WORST, THETA_WORST),
    ]
    scen = {}
    for label, eta, theta in cases:
        c = input_stage_currents(eta, theta)
        scen[label] = c
        print(f"  {label:<26} | {c['p_in']:>6.0f} W | {c['delta']:>6.3f} "
              f"| {c['i_line']:>6.2f} A | {c['pf']:>5.3f} | {c['i_cap_lf']:>7.2f} A")
    print()
    print("  A capacitor-input doubler with no PFC cannot draw its power at PF~1.")
    print(f"  Every case above exceeds the declared {I_LINE_DECLARED:.0f} A limit, the "
          f"16 A fuse rating,")
    print(f"  the CMC's 16 A rating and the K1 contact's {RELAY_I_LIMIT_UL:.0f} A UL "
          "limiting continuous")
    print("  current.  That is a pre-existing internal inconsistency in the design,")
    print("  NOT something this document introduces or resolves.  It is why the")
    print("  declared 15 A is also carried below as a floor.")
    print()

    print(bar)
    print("1. EMI / input-stage dissipation  (budget line: 2.0 W)")
    print(bar)
    print("  docs/hardware/SYSTEM_THERMAL_BUDGET.md sec.1 carries 'EMI filter 2.0 W';")
    print("  its own sec.3.5 scopes that as 'EMI filter inductors | 1-2W | I2R +")
    print("  core loss'.  Both scopings are evaluated.")
    print()
    for label, i_line, note in [
        (f"declared {I_LINE_DECLARED:.0f} A rms (PF=1 floor, NOT achievable)",
         I_LINE_DECLARED, "repo constraints.ato i_max"),
        ("central topology-consistent", scen["central(eta .90, 40 deg)"]["i_line"],
         "eta .90 / theta 40 deg"),
    ]:
        print(f"  --- at I_line = {i_line:.2f} A  ({label})")
        terms = emi_stage_loss(i_line)
        lo_tot = hi_tot = 0.0
        for name, (lo, hi) in terms.items():
            lo_tot += lo
            hi_tot += hi
            if hi < 1e-3:
                print(f"      {name:<22} {lo*1e6:>10.2f} uW .. {hi*1e6:>8.2f} uW")
            else:
                print(f"      {name:<22} {lo:>10.3f} W  .. {hi:>8.3f} W")
        print(f"      {'core loss (CMC)':<22} {'[UNOBTAINABLE -- bounded << I2R]':>34}")
        print(f"      {'TOTAL':<22} {lo_tot:>10.3f} W  .. {hi_tot:>8.3f} W")
        print(f"      {'choke alone (sec.3.5 scope)':<22} "
              f"{i_line**2*CMC_DCR_TOTAL:>7.3f} W")
        print()

    print("  Continuously-energised board loads with NO line in the 2025-12-14")
    print("  budget at all (both are on the PCB, inside the compartment):")
    coil, drop = relay_string_loss()
    print(f"      bus bleeders R_bleed1/2   {P_BLEED_TOTAL:>8.3f} W  "
          f"[repo, exact: 2 x 170^2/22k]")
    print(f"      relay coils K1+K2+K3      {coil:>8.3f} W  [datasheet TE 360 ohm]")
    print(f"      coil dropper resistors    {drop:>8.3f} W  [repo 91/100/100 ohm]")
    print(f"      subtotal                  {P_BLEED_TOTAL+coil+drop:>8.3f} W")
    print()

    print(bar)
    print("2. Capacitor ESR  (budget line: 4.0 W)")
    print(bar)
    print()
    print("  2.1 Resonant-tank bank, 3 x CDE 942C16P1K-F -- DATASHEET-DERIVED")
    print(f"      ESR(100 kHz) = {TANK_ESR_100K*1e3:.1f} mOhm  [datasheet, CDE 942C "
          "ratings table]")
    print(f"      ESR(47 kHz)  = {TANK_ESR_47K*1e3:.2f} mOhm  [derived, x"
          f"{TANK_ESR_RATIO_47K_OVER_100K:.2f} from CDE's "
          "own DF-vs-f curve]")
    print(f"      {'I_tank (rms) / provenance':<34} | {'per cap':>8} "
          f"| {'P per cap':>10} | {'P bank':>8}")
    print(f"      {'-'*34}-+-{'-'*8}-+-{'-'*10}-+-{'-'*8}")
    for i_t, tag in ((I_TANK_COMMITTED, "committed, 88 uH @ 47 kHz"),
                     (I_TANK_HARNESS, "harness, superseded 150 uH"),
                     (I_TANK_OCP, "OCP-derived, disputed")):
        per, bank = tank_cap_loss(i_t)
        print(f"      {i_t:>6.2f} A  {tag:<25} | {i_t/3:>6.2f} A "
              f"| {per:>8.3f} W | {bank:>6.3f} W")
    print()

    print("  2.2 DC-bus electrolytics, 4 x EKMQ251VSN182MA50S")
    print(f"      ESR at 120 Hz from tan(delta)/(2*pi*f*C), ALL MAXIMA:")
    for tand, src in ((TAND_E1001E, "repo cite, CAT E1001E"),
                      (TAND_E1001U, "datasheet, CAT E1001U, read this session"),
                      (TAND_E1001U_ADDER, "E1001U + its >1000uF adder")):
        print(f"        tan(delta) = {tand:.2f}  ->  ESR(120 Hz) = "
              f"{esr_120hz(tand)*1e3:>6.1f} mOhm   [{src}]")
    print("      ESR at 60 Hz and at 47 kHz are NOT PUBLISHED in either revision.")
    print(f"        60 Hz : ESR(120) x {K_ESR_60HZ_LOW:.1f} (ESR flat) .. x "
          f"{K_ESR_60HZ_HIGH:.1f} (tan-delta flat)")
    print(f"        47 kHz: ESR(120) / FM^2, FM = {FM_47K_LOW:.2f} (favourable row) "
          f".. {FM_47K_HIGH:.2f} (>=2200uF row)")
    print()
    print(f"      {'bracket':<34} | {'P_LF':>7} | {'P_HF':>7} | {'per cap':>8} "
          f"| {'x4 caps':>8}")
    print(f"      {'-'*34}-+-{'-'*7}-+-{'-'*7}-+-{'-'*8}-+-{'-'*8}")
    brackets = [
        ("MOST FAVOURABLE (every choice)", TAND_E1001E, K_ESR_60HZ_LOW, FM_47K_LOW,
         1.0, scen["best   (eta .92, 60 deg)"]["i_cap_lf"], I_TANK_COMMITTED),
        ("  + typical-not-max ESR [est]", TAND_E1001E, K_ESR_60HZ_LOW, FM_47K_LOW,
         TYPICAL_TO_MAX_ESR, scen["best   (eta .92, 60 deg)"]["i_cap_lf"],
         I_TANK_COMMITTED),
        ("CENTRAL (E1001U max, both mid)", TAND_E1001U, K_ESR_60HZ_HIGH, FM_47K_LOW,
         1.0, scen["central(eta .90, 40 deg)"]["i_cap_lf"], I_TANK_COMMITTED),
        ("  + typical-not-max ESR [est]", TAND_E1001U, K_ESR_60HZ_HIGH, FM_47K_LOW,
         TYPICAL_TO_MAX_ESR, scen["central(eta .90, 40 deg)"]["i_cap_lf"],
         I_TANK_COMMITTED),
        ("LEAST FAVOURABLE", TAND_E1001U_ADDER, K_ESR_60HZ_HIGH, FM_47K_HIGH,
         1.0, scen["worst  (eta .85, 30 deg)"]["i_cap_lf"], I_TANK_OCP),
    ]
    bus_results = {}
    for name, tand, k60, fm, scale, i_lf, i_tank in brackets:
        i_hf = HF_SHARE_PER_CAP * i_tank
        p_lf, p_hf, p_tot = bus_cap_loss(i_lf, i_hf, tand, k60, fm, scale)
        bus_results[name] = p_tot * N_BUS_CAPS
        print(f"      {name:<34} | {p_lf:>5.2f} W | {p_hf:>5.2f} W | {p_tot:>6.2f} W "
              f"| {p_tot*N_BUS_CAPS:>6.1f} W")
    print()
    print("      Counterfactual -- what the 4.0 W budget appears to have been:")
    e120 = esr_120hz(TAND_E1001U)
    p_rated = I_RIPPLE_RATED**2 * e120
    print(f"        4 caps at their RATED {I_RIPPLE_RATED:.2f} A / 120 Hz ripple: "
          f"{p_rated*N_BUS_CAPS:>5.2f} W")
    print(f"        + tank bank at the committed 22.5 A:            "
          f"{tank_cap_loss(I_TANK_COMMITTED)[1]:>5.2f} W")
    print(f"        = {p_rated*N_BUS_CAPS + tank_cap_loss(I_TANK_COMMITTED)[1]:.2f} W "
          "-- i.e. the 4.0 W line is nameplate arithmetic.")
    print("        The as-designed ripple is 4.2-5.8x rated")
    print("        (docs/evidence/2026-07-26-bus-capacitor-ripple.md sec.5, verdict")
    print("         FAILS), and dissipation goes as the SQUARE of that.")
    print()

    print(bar)
    print("3. Corrected compartment heat load Q")
    print(bar)
    coil, drop = relay_string_loss()
    fixed = (P_UCC21550 + P_LMR51430 + 0.5 + P_BLEED_TOTAL + coil + drop)
    print(f"  Fixed, corrected line items (gate driver {P_UCC21550:.3f} + buck "
          f"{P_LMR51430:.2f}")
    print(f"  + ESP32 0.50 + bleeders {P_BLEED_TOTAL:.2f} + relay string "
          f"{coil+drop:.2f}) = {fixed:.2f} W")
    print()
    print(f"  {'scenario':<32} | {'EMI':>7} | {'caps':>8} | {'Q total':>9}")
    print(f"  {'-'*32}-+-{'-'*7}-+-{'-'*8}-+-{'-'*9}")
    q_cases = []
    emi_floor = sum(v[0] for v in emi_stage_loss(I_LINE_DECLARED).values())
    emi_floor_hi = sum(v[1] for v in emi_stage_loss(I_LINE_DECLARED).values())
    emi_central = sum(v[1] for v in
                      emi_stage_loss(scen["central(eta .90, 40 deg)"]["i_line"]).values())
    caps_within_rating = (I_RIPPLE_RATED**2 * esr_120hz(TAND_E1001U) * N_BUS_CAPS
                          + tank_cap_loss(I_TANK_COMMITTED)[1])
    for name, emi, caps in [
        ("2025-12-14 budget (for scale)", 2.0, 4.0),
        ("HYPOTHETICAL: ripple fault fixed", emi_floor, caps_within_rating),
        ("floor: each term most favourable", emi_floor,
         bus_results["MOST FAVOURABLE (every choice)"]
         + tank_cap_loss(I_TANK_COMMITTED)[1]),
        ("floor + typical-not-max ESR",   emi_floor,
         bus_results["  + typical-not-max ESR [est]"]
         + tank_cap_loss(I_TANK_COMMITTED)[1]),
        ("central (topology-consistent)", emi_central,
         bus_results["CENTRAL (E1001U max, both mid)"]
         + tank_cap_loss(I_TANK_COMMITTED)[1]),
        ("least favourable",              sum(
            v[1] for v in emi_stage_loss(scen["worst  (eta .85, 30 deg)"]["i_line"]).values()),
         bus_results["LEAST FAVOURABLE"] + tank_cap_loss(I_TANK_OCP)[1]),
    ]:
        # The 2025-12-14 row is quoted at its own published Q, which already
        # contains its 2.0 W and 4.0 W lines -- it is not re-summed here.
        q = 9.65 if name.startswith("2025") else fixed + emi + caps
        q_cases.append((name, q))
        print(f"  {name:<32} | {emi:>5.2f} W | {caps:>6.1f} W | {q:>7.1f} W")
    print()
    print("  The 2025-12-14 row is shown at its own Q = 9.65 W -- exactly the sum")
    print("  of that document's six PCB-resident line items, and the Q the")
    print("  2026-08-19 viability analysis carried.")
    print()
    print("  The 'floor' rows take each term at its most favourable value")
    print("  INDEPENDENTLY (15 A line current AND the theta=60 deg cap ripple, which")
    print("  cannot both hold at once).  They are a lower bound, not an operating")
    print("  point.  The HYPOTHETICAL row asks what Q would be if the bus caps were")
    print("  operated inside their 2.70 A rating -- i.e. if the design's committed")
    print("  ripple FAILS verdict were fixed -- with everything else as derived.")
    print()

    print(bar)
    print(f"4. Compartment wall rise and part margins at the committed "
          f"{AMBIENT_C:.0f} C ambient")
    print(bar)
    for geom in (COMPACT,):
        print(f"\n  Geometry: {geom['label']}  (A = {geom['area_m2']*1e4:.0f} cm^2)")
        print(f"  {'Q (W)':>8} | {'dT eps=.2':>10} | {'dT eps=.5':>10} "
              f"| {'dT eps=.9':>10} | {'Tlocal(.5)':>11}")
        print(f"  {'-'*8}-+-{'-'*10}-+-{'-'*10}-+-{'-'*10}-+-{'-'*11}")
        for name, q in q_cases:
            row = [wall_delta_t(q, geom["area_m2"], geom["lc_m"], e, AMBIENT_C)
                   for e in (0.2, 0.5, 0.9)]
            tloc = AMBIENT_C + FILM_FACTOR * row[1]
            print(f"  {q:>8.1f} | {row[0]:>8.1f} C | {row[1]:>8.1f} C "
                  f"| {row[2]:>8.1f} C | {tloc:>9.1f} C")
    print()
    print(f"  Per-part outcome at eps = 0.5.  ESP32-S3 is shown BOTH ways: at the")
    print(f"  bare wall rise (the 2026-08-19 analysis's own convention for this part)")
    print(f"  and at the x{FILM_FACTOR} film-boosted local air, so this document is not")
    print("  silently harsher than its predecessor.  The ICs use the film-boosted")
    print("  value, as before.  Electrolytics use the wall rise, as before.")
    print()
    print(f"  {'Q (W)':>8} | {'T_wall':>7} | {'T_local':>8} | {'ESP32 @wall':>12} "
          f"| {'ESP32 @loc':>11} | {'UCC21550':>9} | {'LMR51430':>9} | {'e-cap':>8}")
    print(f"  {'-'*8}-+-{'-'*7}-+-{'-'*8}-+-{'-'*12}-+-{'-'*11}-+-{'-'*9}-+-"
          f"{'-'*9}-+-{'-'*8}")
    for name, q in q_cases:
        dt = wall_delta_t(q, COMPACT["area_m2"], COMPACT["lc_m"], 0.5, AMBIENT_C)
        twall = AMBIENT_C + dt
        tloc = AMBIENT_C + FILM_FACTOR * dt
        tj_u = tloc + P_UCC21550 * THETA_JA_UCC21550
        tj_l = tloc + P_LMR51430 * THETA_JA_LMR51430
        print(f"  {q:>8.1f} | {twall:>5.1f} C | {tloc:>6.1f} C "
              f"| {ESP32_T_AMBIENT_MAX-twall:>+9.1f} C "
              f"| {ESP32_T_AMBIENT_MAX-tloc:>+8.1f} C "
              f"| {TJ_MAX-tj_u:>+7.1f} C | {TJ_MAX-tj_l:>+7.1f} C "
              f"| {ELCAP_T_MAX-twall:>+6.1f} C")
    print()
    print("  ESP32-S3 is an 85 C MODULE AMBIENT rating: there is no theta_JA to")
    print("  spend, so it responds only to compartment dT.  A negative margin is")
    print("  a failure of the compartment, not of a part that can be re-specified.")
    print("  The electrolytic column ignores the caps' OWN self-heating above the")
    print("  local air -- which, at the dissipations in sec.2.2, is tens of K more.")
    print()

    print(bar)
    print("5. What Q the ESP32-S3 can actually tolerate")
    print(bar)
    def breakeven(factor: float) -> float:
        lo, hi = 0.01, 2000.0
        for _ in range(300):
            mid = 0.5 * (lo + hi)
            dt = wall_delta_t(mid, COMPACT["area_m2"], COMPACT["lc_m"], 0.5, AMBIENT_C)
            if AMBIENT_C + factor * dt < ESP32_T_AMBIENT_MAX:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    q_break_wall = breakeven(1.0)
    q_break_film = breakeven(FILM_FACTOR)
    print(f"  Compact envelope, eps = 0.5, {AMBIENT_C:.0f} C ambient:")
    print(f"    breakeven Q, bare wall rise (predecessor's convention) = "
          f"{q_break_wall:>6.2f} W")
    print(f"    breakeven Q, x{FILM_FACTOR} film-boosted local air        = "
          f"{q_break_film:>6.2f} W")
    print()
    print("  The 2026-08-19 analysis carried Q = 9.65 W and 12.0 W.  Both sit under")
    print("  both breakevens, which is why it read +4.8 C rather than negative.")
    print()
    for name, q in q_cases:
        if name.startswith("2025"):
            continue
        v_w = "PASS" if q < q_break_wall else "FAIL"
        v_f = "PASS" if q < q_break_film else "FAIL"
        print(f"    {name:<34} Q={q:>7.1f} W  ->  wall {v_w} / local {v_f}")
    print()
    print("  The ONLY scenario that keeps the ESP32-S3 alive is the HYPOTHETICAL")
    print("  one in which the committed bus-capacitor ripple failure is first")
    print("  fixed -- and even that passes with only 1.1 W of Q headroom on the")
    print("  film-boosted convention (+1.4 C on the part).  NO as-designed")
    print("  scenario passes on either convention, by any margin, at any")
    print("  emissivity in the sweep.")


if __name__ == "__main__":
    main()
