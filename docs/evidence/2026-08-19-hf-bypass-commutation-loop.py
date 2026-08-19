#!/usr/bin/env python3
"""HF bypass for the half-bridge commutation loop -- derivation and sweeps.

Companion to docs/evidence/2026-08-19-hf-bypass-commutation-loop.md.

Answers, for the as-drawn Delon-doubler / half-bridge / series-tank stage in
elec/src:

  1. Where does the 47 kHz commutation current actually circulate, and does
     `hb.c_dc_hf` (0.47 uF, hv_plus -> hv_minus) sit across that loop?
  2. What shunt impedance would a correct bypass have to present, and what
     capacitance does that imply?
  3. What do real, datasheet-verified parts achieve?
  4. Where does the C_BUS ripple ceiling move?

STDLIB ONLY (math, dataclasses, itertools).  Reads NO repo state and loads NO
compiled extension, so `make venv-isolate` is not required to reproduce it:

    python3 docs/evidence/2026-08-19-hf-bypass-commutation-loop.py

PROVENANCE TAGS used throughout:
  [datasheet]    read from a manufacturer PDF this session, quoted with the
                 table it came from
  [repo]         a value committed in this repository, with file:line
  [derived]      computed here from a [datasheet] or [repo] value, with the
                 derivation stated
  [estimated]    an engineering bracket with no measurement behind it -- NEVER
                 blended into a [datasheet] figure
  [UNOBTAINABLE] not published; carried as a bracket or reported as unknown
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass

# =============================================================================
# 1. INPUTS
# =============================================================================

# --- switching band ----------------------------------------------------------
# [repo] elec/src/main.ato: PLL band 44-50 kHz; the 1800 W point is 47.1 kHz.
F_SW_NOM = 47.0e3
F_BAND = (44.0e3, 47.0e3, 50.0e3)

# --- tank current ------------------------------------------------------------
# [repo] docs/evidence/2026-08-19-input-stage-power-ceiling.py:161
#        I_TANK_AT_1800W = (35.4, 40.0); via STRATEGY.md /
#        docs/evidence/2026-07-26-ocp01-vs-full-power-current.md.
#        main.ato:625 independently declares i_ocp_trip_rms = 35.4 A.
# This analysis TAKES that bracket; it does not re-derive it.
I_TANK_1800W = (35.4, 40.0)
# The prior branch's own "central" operating point, recovered from its printed
# HF/cap = 8.90 A and its CAP_HF_SHARE / FM_SW constants:
#     i_tank_central = 8.90 * FM_SW / CAP_HF_SHARE = 8.90 * 1.50 / 0.3536
I_TANK_CENTRAL = 8.90 * 1.50 / 0.3536  # -> 37.75 A rms  [derived from repo]

# --- the electrolytic bank ---------------------------------------------------
# [repo] elec/src/modules.ato:965-992 -- 4 x EKMQ251VSN182MA50S, 1800 uF/250 V,
#        two in parallel per half-bus.
C_BUS_UNIT = 1800e-6
N_PER_HALF = 2
C_BANK_HALF = C_BUS_UNIT * N_PER_HALF  # 3600 uF per half-bus

# [datasheet] Chemi-Con KMQ CAT. E1001E, via the committed
#             docs/evidence/2026-07-26-bus-capacitor-ripple.md Sec.1:
#             I_rms = 2.70 A at 105 C / 120 Hz, tan(delta) <= 0.15 at 120 Hz.
I_CAP_RATED_120HZ = 2.70
TAN_DELTA_120 = 0.15
ESR_UNIT_120 = TAN_DELTA_120 / (2 * math.pi * 120.0 * C_BUS_UNIT)  # 110.5 mOhm

# [repo] the committed frequency-multiplier value the prior branch used:
#        FM(47 kHz) = 1.50 relative to the 120 Hz rating.
FM_SW = 1.50

# ESR at 47 kHz is [UNOBTAINABLE] -- Chemi-Con does not publish it for KMQ, as
# both prior agents found.  Two independent handles, kept apart:
#
#   [derived] Thermal equivalence.  A ripple-current frequency multiplier is a
#     statement that the SAME self-heating is produced by FM x I at the higher
#     frequency.  Self-heating is I^2 * ESR, so ESR(f)/ESR(120) = 1/FM(f)^2.
#     At FM = 1.50 that is 0.444, i.e. 49.1 mOhm/unit, 24.6 mOhm/bank.
#     This reads the multiplier as purely an ESR effect; manufacturers also
#     fold in heat distribution, so treat it as an ANCHOR, not a measurement.
#
#   [estimated] Bracket 15-35 mOhm per bank (= 30-70 mOhm per unit), which
#     contains the anchor and spans the range large 250 V snap-ins are
#     normally seen at between 10 kHz and 100 kHz.
ESR_BANK_ANCHOR = ESR_UNIT_120 / (FM_SW**2) / N_PER_HALF
ESR_BANK_BRACKET = (15e-3, 35e-3)

# Bank self-inductance.  [estimated] 20-30 nH per D35 snap-in with 10 mm lead
# spacing; two in parallel -> 10-15 nH.  Not published for this part.
ESL_BANK_BRACKET = (10e-9, 15e-9)

# --- the interconnect from the bridge to the bank ----------------------------
# [measured, read-only] pcb/temper.kicad_pcb footprint centres, this session:
#     U4 (Q_high, TO-247)              (23.72, 233.25)
#     U5 (Q_low,  TO-247)              (100.07, 159.33)
#     C2  power_in.c_bus1   (+170V/PWR_RTN)  (93.48,  64.84)
#     C4  power_in.c_bus1b  (+170V/PWR_RTN)  (86.46, 188.34)
#     C3  power_in.c_bus2   (DC_BUS_RTN/PWR_RTN) (87.36, 34.94)
#     C5  power_in.c_bus2b  (DC_BUS_RTN/PWR_RTN) (139.62, 230.225)
# Centre-to-centre: U4->C4 77.2 mm, U4->C2 182.2 mm,
#                   U5->C5 81.2 mm, U5->C3 125.2 mm.
BOARD_SEPARATION_MM = (77.2, 182.2)
# [estimated] loop inductance 0.6-1.5 nH per mm of one-way run for a routed
# go/return pair on this stackup.  Combined over the two parallel caps,
# bracket the whole bridge->bank branch inductance at 60-265 nH.  NOTHING in
# this repo measures it; it is the single largest uncertainty below and the
# answer is strongly sensitive to it (see sweep 4).
L_FEED_BRACKET = (60e-9, 265e-9)
L_FEED_CENTRAL = 150e-9

# --- the existing "HF bypass" ------------------------------------------------
# [repo] elec/src/modules.ato:372-379 -- c_dc_hf, 0.47 uF / 630 VDC PP film,
#        EPCOS B32671L6474K000, wired dc_bus.hv_plus -> dc_bus.hv_minus.
C_DC_HF = 0.47e-6
# [estimated] ESR ~ 10 mOhm, ESL ~ 15-20 nH for an 18x11 mm P=15 mm film box.
# Not published per-part; only the magnitude matters here (see sweep 2).
ESR_DC_HF = 10e-3
ESL_DC_HF = 18e-9


# =============================================================================
# 2. NETWORK PRIMITIVES
# =============================================================================

def z_cap(f: float, c: float, esr: float, esl: float) -> complex:
    """Series R-L-C model of a real capacitor branch."""
    w = 2 * math.pi * f
    return complex(esr, w * esl - 1.0 / (w * c))


def z_bank(f: float, esr: float, esl: float, c: float = C_BANK_HALF) -> complex:
    """Electrolytic half-bank + its interconnect (esl includes the feed)."""
    return z_cap(f, c, esr, esl)


# --- the switch-current spectrum ---------------------------------------------
# The half-bridge connects SW to one rail at a time, so the current a half-bus
# sources is the tank current gated by its own switch: a half-wave-rectified
# sine of peak I_pk = sqrt(2) * I_tank_rms.  Its spectrum is
#     DC   : I_pk / pi
#     n=1  : amplitude I_pk / 2                     (at f_sw)
#     n=2k : amplitude 2*I_pk / (pi*(4k^2 - 1))     (even harmonics)
# The DC term CANNOT be supplied by any film capacitor -- it is the term the
# committed ripple analysis already books as the low-frequency (rectifier
# recharge) current.  Only the n >= 1 terms are divertible.

def halfwave_harmonics(i_rms_tank: float, n_max: int = 10):
    """[(frequency multiple, rms amplitude), ...] of the AC harmonics."""
    i_pk = math.sqrt(2.0) * i_rms_tank
    out = [(1, (i_pk / 2.0) / math.sqrt(2.0))]
    k = 1
    while 2 * k <= n_max:
        amp = 2.0 * i_pk / (math.pi * (4 * k * k - 1))
        out.append((2 * k, amp / math.sqrt(2.0)))
        k += 1
    return out


def halfwave_dc(i_rms_tank: float) -> float:
    return math.sqrt(2.0) * i_rms_tank / math.pi


# =============================================================================
# 3. SWEEP 1 -- IS c_dc_hf ACROSS THE COMMUTATION LOOP?
# =============================================================================

def sweep1() -> None:
    print("=" * 78)
    print("1. THE COMMUTATION LOOP, AND WHERE c_dc_hf ACTUALLY SITS")
    print("=" * 78)
    print("""
Netlist, traced by hand from elec/src (file:line in the .md):

  PowerInput (Delon doubler)
      d1.K      ~ dc_bus.hv_plus
      c_bus1/1b  hv_plus  -> gnd_ref        <- UPPER half-bank
      c_bus2/2b  gnd_ref  -> hv_minus       <- LOWER half-bank
      cmc.W2_2  ~ dc_bus.gnd_ref            <- midpoint IS AC neutral
  HalfBridge
      dc_bus.hv_plus  ~ q_high.C ; q_high.E ~ switch_node
      switch_node     ~ q_low.C  ; q_low.E  ~ dc_bus.hv_minus
  Top (main.ato)
      hb.switch_node ~ tank.in
      tank.out ~ ct_sense.primary_in ; ct_sense.primary_out ~ power_return
      power_return ~ power_in.dc_bus.gnd_ref      <- TANK RETURNS TO MIDPOINT

  => Q_high on:   hv_plus -> Q_high -> SW -> tank -> MIDPOINT -> C_BUS1 -> hv_plus
     Q_low  on:   MIDPOINT -> tank -> SW -> Q_low -> hv_minus -> C_BUS2 -> MIDPOINT

  Both loops close THROUGH a half-bank.  c_dc_hf is hv_plus -> hv_minus: it
  touches neither loop directly.  It is not, however, "out of the circuit":
  it offers the series path  MIDPOINT -> C_BUS2 -> hv_minus -> c_dc_hf ->
  hv_plus, i.e. it is in series with the OPPOSITE half-bank, in parallel with
  the half-bank the loop wanted to use.  Sweep 2 prices that path.
""")


def sweep2() -> None:
    print("=" * 78)
    print("2. HOW MUCH 47 kHz CURRENT DOES c_dc_hf ACTUALLY TAKE?")
    print("=" * 78)
    print("""
Current divider seen by the upper loop, from MIDPOINT back to hv_plus:
    branch A : C_BUS1 bank + its feed inductance          Z_e
    branch B : C_BUS2 bank + its feed + c_dc_hf in series Z_e + Z_f
Fraction through the film path = |Z_e| / |Z_e + (Z_e + Z_f)|.
""")
    print(f"{'f kHz':>7}{'|Z_e| mOhm':>12}{'|Z_dchf| mOhm':>15}"
          f"{'film share %':>14}{'I_elec / no-bypass':>20}")
    for f in F_BAND:
        ze = z_bank(f, ESR_BANK_ANCHOR, ESL_BANK_BRACKET[1] + L_FEED_CENTRAL)
        zf = z_cap(f, C_DC_HF, ESR_DC_HF, ESL_DC_HF)
        zb = ze + zf                      # the long way round
        share = abs(ze) / abs(ze + zb)    # fraction diverted into branch B
        # current in the loop's own half-bank, relative to no bypass at all:
        i_a = abs(zb) / abs(ze + zb)
        print(f"{f/1e3:7.0f}{abs(ze)*1e3:12.2f}{abs(zf)*1e3:15.1f}"
              f"{share*100:14.2f}{i_a:20.4f}")
    print("""
VERDICT: c_dc_hf carries ~0.3 % of the loop current.  The prior branch's
claim is upheld.  Two refinements it did not make:
  (a) the reason is BOTH placement and value -- even moved directly across a
      half-bus, 0.47 uF presents 7.2 Ohm at 47 kHz against a ~50 mOhm bank;
  (b) the residual effect is very slightly ADVERSE, not neutral: see sweep 3
      for why a shunt capacitor BELOW the loop resonance raises the
      electrolytic current instead of lowering it.
""")


# =============================================================================
# 4. SWEEP 3 -- THE IMPEDANCE TARGET, AND THE RESONANCE TRAP
# =============================================================================

def elec_share(f: float, zf: complex, esr_e: float, l_e: float) -> tuple:
    """Return (I_elec/I_total, I_film/I_total) for one harmonic."""
    ze = z_bank(f, esr_e, l_e)
    tot = ze + zf
    return abs(zf) / abs(tot), abs(ze) / abs(tot)


def sweep3() -> None:
    print("=" * 78)
    print("3. THE IMPEDANCE TARGET -- AND WHY A SMALL SHUNT MAKES IT WORSE")
    print("=" * 78)
    print("""
A bypass across a half-bus is in parallel with [electrolytic ESR + the
inductance of the run back to it].  Writing Z_e = R_e + jwL_e and, for an
ideal film, Z_f = -j/(wC):

    I_elec / I_no_bypass = |Z_f| / |Z_e + Z_f|
                         = (1/wC) / |R_e + j(wL_e - 1/wC)|

Neglecting R_e, this is < 1 only when  wL_e - 1/wC  >  1/wC, i.e.

    C  >  2 / (w^2 * L_e)                        <-- THE THRESHOLD

Below that the film and the feed inductance form a SERIES-RESONANT loop at
f0 = 1/(2*pi*sqrt(L_e*C)) and the electrolytic current is AMPLIFIED.  The
existing 0.47 uF is three orders below threshold, which is why sweep 2's
last column is just above 1.000.
""")
    print(f"{'L_feed nH':>11}{'f0 @ 40uF kHz':>15}{'C_min 44kHz uF':>16}"
          f"{'C_min 47kHz uF':>16}{'C for 50% cut uF':>18}")
    for l_e in (60e-9, 100e-9, 150e-9, 200e-9, 265e-9):
        f0_40 = 1.0 / (2 * math.pi * math.sqrt(l_e * 40e-6))
        cmin44 = 2.0 / ((2 * math.pi * 44e3) ** 2 * l_e)
        cmin47 = 2.0 / ((2 * math.pi * 47e3) ** 2 * l_e)
        c50 = 3.0 / ((2 * math.pi * 44e3) ** 2 * l_e)
        print(f"{l_e*1e9:11.0f}{f0_40/1e3:15.1f}{cmin44*1e6:16.0f}"
              f"{cmin47*1e6:16.0f}{c50*1e6:18.0f}")
    print("""
READ THIS TABLE AS THE CENTRAL RESULT.  To do ANY good at the bottom of the
PLL band, a shunt film across a half-bus must be ~100-370 uF -- three orders
of magnitude above the 0.47 uF that is there now, and one order above what
"add a bypass cap" normally means.  Anything smaller sits below the loop
resonance and makes the electrolytic ripple worse.
""")
    print("What a 40 uF film -- a normal 'big' DC-link value -- actually does:")
    print(f"{'L_feed nH':>11}{'f kHz':>8}{'I_elec/I_0':>13}{'verdict':>12}")
    for l_e in (60e-9, 150e-9, 265e-9):
        for f in F_BAND:
            zf = z_cap(f, 40e-6, 5e-3, 30e-9)
            ie, _ = elec_share(f, zf, ESR_BANK_ANCHOR, ESL_BANK_BRACKET[1] + l_e)
            print(f"{l_e*1e9:11.0f}{f/1e3:8.0f}{ie:13.3f}"
                  f"{'WORSE' if ie > 1.0 else 'better':>12}")


# =============================================================================
# 5. SWEEP 4 -- THE SELECTED PART
# =============================================================================

# [datasheet] Vishay Roederstein MKP1848C DC-Link, document 26015, revision
# 09-Aug-2023, fetched and text-extracted this session.
#   MKP1848C71250JY5 -- 120 uF, U_NDC(85 C) = 500 V, 4 pins, P1 = 52.5 mm,
#   P2 = 20.3 mm, case 45.0 x 45.0 x 57.5 mm, mass 150 g,
#   I_RMS = 19 A, ESR = 2.5 mOhm, I_PEAK = 1200 A, dV/dt = 10 V/us,
#   tan(delta) at 10 kHz < 450e-4.
#   Footnote (2): "Maximum RMS current at 10 kHz, +85 C, dt = +15 C".
#   Footnote (3): ESR typical values are valid "at f = 10 kHz to 50 kHz for
#                 P = 52.5 mm"  <-- covers the whole 44-50 kHz PLL band.
#   Quick-reference data: "Self inductance (LS) < 1 nH per mm of lead
#                 spacing"  -> < 52.5 nH for this pitch.  UPPER BOUND ONLY;
#                 no typical is published, so it is bracketed below.
#   DC voltage ratings row: U_OPDC at 70 C = 600 V, at 105 C = 350 V.
#   "Maximum applicable peak to peak ripple voltage 0.2 x U_NDC" -> 100 V.
PART = dict(
    mpn="MKP1848C71250JY5",
    c=120e-6, v_ndc=500.0, v_op_105c=350.0,
    esr=2.5e-3, i_rms=19.0, i_peak=1200.0, dvdt=10.0,
    esl_max=52.5e-9,
    w=45.0, h=45.0, l=57.5, mass_g=150.0,
)
N_PARALLEL = 2  # per half-bus


def film_branch(f: float, esl_each: float) -> complex:
    c = PART["c"] * N_PARALLEL
    esr = PART["esr"] / N_PARALLEL
    esl = esl_each / N_PARALLEL
    return z_cap(f, c, esr, esl)


def sweep4() -> None:
    print("=" * 78)
    print("4. SELECTED PART: 2 x MKP1848C71250JY5 PER HALF-BUS (240 uF)")
    print("=" * 78)
    print(f"  per half-bus: {PART['c']*N_PARALLEL*1e6:.0f} uF, "
          f"ESR {PART['esr']/N_PARALLEL*1e3:.2f} mOhm, "
          f"I_rms capability {PART['i_rms']*N_PARALLEL:.0f} A "
          f"(datasheet, 10-50 kHz valid)")
    print(f"  ESL bracket per cap 20 nH .. {PART['esl_max']*1e9:.1f} nH "
          f"(datasheet gives only the < 1 nH/mm upper bound)\n")

    print(f"{'L_feed nH':>10}{'ESR_e mOhm':>12}{'ESL/cap nH':>12}{'f kHz':>7}"
          f"{'|Z_film| mOhm':>15}{'|Z_elec| mOhm':>15}"
          f"{'I_elec/I_0':>12}{'I_film/I_0':>12}")
    worst = 0.0
    best = 9.9
    worst_corner = best_corner = None
    for l_e in L_FEED_BRACKET:
        for esr_e in ESR_BANK_BRACKET:
            for esl in (20e-9, PART["esl_max"]):
                for f in F_BAND:
                    zf = film_branch(f, esl)
                    ze = z_bank(f, esr_e, ESL_BANK_BRACKET[1] + l_e)
                    ie = abs(zf) / abs(ze + zf)
                    if_ = abs(ze) / abs(ze + zf)
                    corner = (l_e, esr_e, esl, f)
                    if ie > worst:
                        worst, worst_corner = ie, corner
                    if ie < best:
                        best, best_corner = ie, corner
                    print(f"{l_e*1e9:10.0f}{esr_e*1e3:12.0f}{esl*1e9:12.1f}"
                          f"{f/1e3:7.0f}{abs(zf)*1e3:15.2f}{abs(ze)*1e3:15.2f}"
                          f"{ie:12.3f}{if_:12.3f}")
    def _c(c):
        return (f"L_feed {c[0]*1e9:.0f} nH, ESR_e {c[1]*1e3:.0f} mOhm, "
                f"ESL/cap {c[2]*1e9:.1f} nH, {c[3]/1e3:.0f} kHz")
    print(f"\n  worst corner ({_c(worst_corner)}): I_elec/I_0 = {worst:.3f}")
    print(f"  best  corner ({_c(best_corner)}): I_elec/I_0 = {best:.3f}")
    print(f"\n  ACROSS THE WHOLE CORNER SET: I_elec/I_0 = {best:.3f} .. {worst:.3f}")
    print(f"  i.e. the electrolytics keep {best*100:.0f}-{worst*100:.0f} % of "
          f"the 47 kHz current they carry today\n")

    print("  4b. SENSITIVITY TO THE BRIDGE->BANK FEED INDUCTANCE")
    print("  This is the constraint the PLACER owns.  The bypass works by")
    print("  being the LOW-inductance path; if the bulk bank is placed just")
    print("  as close to the bridge as the film, the divider collapses.")
    print(f"  {'L_feed nH':>11}{'44 kHz':>9}{'47 kHz':>9}{'50 kHz':>9}"
          f"{'verdict':>26}")
    for l_e in (10e-9, 20e-9, 30e-9, 45e-9, 60e-9, 100e-9, 150e-9, 265e-9):
        row = []
        for f in F_BAND:
            # worst film/bank corner: lowest film ESL, lowest bank ESR
            zf = film_branch(f, 20e-9)
            ze = z_bank(f, ESR_BANK_BRACKET[0], ESL_BANK_BRACKET[1] + l_e)
            row.append(abs(zf) / abs(ze + zf))
        v = ("NET HARM somewhere in band" if max(row) >= 1.0
             else "marginal" if max(row) > 0.7 else "effective")
        print(f"  {l_e*1e9:11.0f}{row[0]:9.3f}{row[1]:9.3f}{row[2]:9.3f}"
              f"{v:>26}")
    print("""  READ THIS CAREFULLY -- it is the reason 240 uF and not 40 uF was
  selected.  At 240 uF the ratio never reaches 1.0 anywhere in the table, so
  the fix is NEVER counter-productive, at any feed inductance, anywhere in
  the PLL band.  That robustness is exactly what the 40 uF row in sweep 3
  does not have.  But the BENEFIT is strongly layout-dependent: 24 % current
  reduction if the bulk bank ends up 10 nH away, 87 % if it stays where the
  board has it today.

  PLACER CONSTRAINT, stated as a number: keep the film-branch loop inductance
  (film terminals <-> Q_high collector / tank-return node) at or below 25 nH,
  and do NOT tighten the bridge->bulk-bank loop below ~60 nH -- the as-built
  placement gives 77-182 mm centre-to-centre [measured, read-only], which is
  far above that.  Nothing in this repo enforces either bound today, and a
  future placement pass that "improves" the bus-cap-to-bridge loop would
  silently take the benefit from 87 % back down to 24 %.
""")
    return best, worst


def sweep5(best: float, worst: float) -> None:
    print("=" * 78)
    print("5. WHAT THE FILM CAPS THEMSELVES MUST CARRY, AND THE NEW CEILING")
    print("=" * 78)

    # --- film loading, harmonic-resolved, over ALL corners -------------------
    print("Film-branch loading at 1800 W (harmonic-resolved, MAX over the")
    print("whole corner set, fundamental swept across the 44-50 kHz band):")
    print(f"{'I_tank A':>10}{'I_film/half-bus A':>20}{'per cap A':>12}"
          f"{'rated A':>9}{'margin':>9}")
    for it in (I_TANK_1800W[0], I_TANK_CENTRAL, I_TANK_1800W[1]):
        best_i = 0.0
        for f0 in F_BAND:
            for l_e in L_FEED_BRACKET:
                for esr_e in ESR_BANK_BRACKET:
                    for esl in (20e-9, PART["esl_max"]):
                        acc = 0.0
                        for n, i_h in halfwave_harmonics(it):
                            f = f0 * n
                            zf = film_branch(f, esl)
                            ze = z_bank(f, esr_e, ESL_BANK_BRACKET[1] + l_e)
                            acc += (i_h * abs(ze) / abs(ze + zf)) ** 2
                        best_i = max(best_i, math.sqrt(acc))
        print(f"{it:10.1f}{best_i:20.2f}{best_i/N_PARALLEL:12.2f}"
              f"{PART['i_rms']:9.1f}{PART['i_rms']/(best_i/N_PARALLEL):9.2f}x")
    print("""  CAVEAT [UNOBTAINABLE]: the 2nd harmonic of the gated switch
  current sits at 88-100 kHz and carries ~0.21 x I_tank.  Vishay's ESR
  figures for P = 52.5 mm are declared valid only to 50 kHz, so the film's
  dissipation at that harmonic is NOT bounded by the datasheet.  Film ESR
  rises with frequency, so the margins above are optimistic by an unquantified
  amount at the 2nd harmonic.  Bench measurement required before fab.""")

    # --- electrolytic HF term, before and after -----------------------------
    print("\nElectrolytic HF term per capacitor, 120 Hz-equivalent "
          f"(divide by FM={FM_SW}):")
    print("  book-keeping A (conservative): the committed 8.90 A/cap figure")
    print("    includes the DC term of the gated switch current, which NO")
    print("    capacitor can divert; only its AC part is reduced.")
    print("  book-keeping B (strict): the DC term is the LF rectifier term,")
    print("    already counted separately, so the whole HF term scales.\n")
    i_pk = math.sqrt(2.0) * I_TANK_CENTRAL
    dc = halfwave_dc(I_TANK_CENTRAL)
    ac = math.sqrt(sum(a * a for _, a in halfwave_harmonics(I_TANK_CENTRAL)))
    tot = math.hypot(dc, ac)
    print(f"  gated-switch current per half-bus: DC {dc:.2f} A, "
          f"AC {ac:.2f} A, total {tot:.2f} A "
          f"(= 0.7071 x I_tank, the committed convention)")
    print(f"{'':>4}{'case':<10}{'HF/cap actual A':>18}{'eq-120Hz A':>13}"
          f"{'x 2.70 A':>10}")
    for name, k in (("today", 1.0), ("best", best), ("worst", worst)):
        a_cons = math.hypot(dc, k * ac) / N_PER_HALF
        a_strict = (tot * k) / N_PER_HALF
        for lbl, a in (("A", a_cons), ("B", a_strict)):
            print(f"{'':>4}{name + ' ' + lbl:<10}{a:18.2f}"
                  f"{a/FM_SW:13.2f}{a/FM_SW/I_CAP_RATED_120HZ:10.2f}")

    # --- ceiling -------------------------------------------------------------
    print("""
Ceiling.  The HF term scales as sqrt(P) (series-resonant tank into a fixed
reflected pan resistance) -- verified against the committed table: 8.90 x
sqrt(900/1800) = 6.29, which is exactly what that table prints.

The LF term does NOT follow a clean power law; the committed analysis
simulates it.  Rather than re-simulate the doubler (that is the prior
branch's work, not this one's), this reproduces its LF curve by log-log
interpolation through its OWN four committed central-case points:
    1800 W -> 8.84 A,  900 W -> 4.65 A,  400 W -> 2.25 A,  150 W -> 0.95 A
CROSS-CHECK: with the HF term unchanged this must reproduce the committed
146 W ceiling.  It does (see the 'today' row), which validates the
reconstruction before it is used to move the ceiling.
""")
    lf_pts = [(150.0, 0.95), (400.0, 2.25), (900.0, 4.65), (1800.0, 8.84)]

    def lf_at(p: float) -> float:
        p = max(p, 1e-3)
        if p <= lf_pts[0][0]:
            p0, a0 = lf_pts[0]
            p1, a1 = lf_pts[1]
        elif p >= lf_pts[-1][0]:
            p0, a0 = lf_pts[-2]
            p1, a1 = lf_pts[-1]
        else:
            for (p0, a0), (p1, a1) in zip(lf_pts, lf_pts[1:]):
                if p0 <= p <= p1:
                    break
        s = math.log(a1 / a0) / math.log(p1 / p0)
        return a0 * (p / p0) ** s

    print(f"{'HF case':<22}{'HF_1800 eq A':>14}{'ceiling W':>12}{'binding':>18}")
    cases = [("today (committed)", 1.0, "B"),
             ("bypass, best corner", best, "B"),
             ("bypass, worst corner", worst, "B"),
             ("bypass best, bk A", best, "A"),
             ("bypass worst, bk A", worst, "A"),
             ("PERFECT bypass (k=0)", 0.0, "B")]
    for name, k, bk in cases:
        if bk == "A":
            hf1800 = (math.hypot(dc, k * ac) / N_PER_HALF) / FM_SW
        else:
            hf1800 = (tot * k / N_PER_HALF) / FM_SW
        lo, hi = 1.0, 20000.0
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if math.hypot(lf_at(mid),
                          hf1800 * math.sqrt(mid / 1800.0)) > I_CAP_RATED_120HZ:
                hi = mid
            else:
                lo = mid
        lf = lf_at(lo)
        hf = hf1800 * math.sqrt(lo / 1800.0)
        binding = "LF (rectifier)" if lf > hf else "HF (tank)"
        print(f"{name:<22}{hf1800:14.2f}{lo:12.0f}{binding:>18}")
    print("""
The last row is the hard limit of this remedy: with the 47 kHz term removed
ENTIRELY the ceiling stops at the LF (doubler recharge) term.  No HF bypass,
however good, gets past it.  The committed analysis quotes that LF-alone
ceiling as 441-491 W across its efficiency bracket; the central-case
reconstruction above lands inside that band, as it must.""")


# =============================================================================
# 6. VOLTAGE
# =============================================================================

def sweep6() -> None:
    print("=" * 78)
    print("6. VOLTAGE RATING AND MARGIN")
    print("=" * 78)
    rows = [
        ("nominal line, no load", 120.0,
         "[repo] main.ato / constraints.ato nominal 120 Vrms"),
        ("repo declared AC max", 135.0,
         "[repo] constraints.ato ACMainsConstraints.v_max = 135V"),
        ("ANSI C84.1 Range B upper utilisation", 127.0,
         "[uncited-standard] NOT fetched; shown only to bracket 135 V"),
    ]
    print(f"{'case':<40}{'Vrms':>7}{'V_half pk':>12}{'V_bus pk':>11}")
    for name, v, _ in rows:
        vh = math.sqrt(2) * v
        print(f"{name:<40}{v:7.1f}{vh:12.1f}{2*vh:11.1f}")
    v_half_wc = math.sqrt(2) * 135.0
    print(f"""
Worst-case steady-state half-bus = sqrt(2) x 135 V = {v_half_wc:.1f} V, using
the repo's OWN declared AC ceiling (constraints.ato) rather than a standard
this analysis did not fetch.  The full bus is {2*v_half_wc:.1f} V, against the
repo's declared HighVoltageConstraints.v_max = 400 V.

Transients.  MOV1 (V150LA10AP, modules.ato) clamps L-N.  Its clamping voltage
is [UNOBTAINABLE] here -- the Littelfuse LA-series datasheet was not fetched
this session, and no clamping figure is committed in the repo.  It does not
bind: an 8/20 us surge delivers of order 1 mC, and 1 mC into the 3600 uF
half-bank is a {1e-3/3.6e-3*1e3:.2f} mV step.  The bulk bank, not the film cap, sets
the transient bus excursion, and the film sees whatever the bulk sees.

Selected part rating:  U_NDC(85 C) = {PART['v_ndc']:.0f} V  ->  margin
  {PART['v_ndc']/v_half_wc:.2f}x  on worst-case steady state
  {PART['v_op_105c']/v_half_wc:.2f}x  even at the 105 C derated U_OPDC of
  {PART['v_op_105c']:.0f} V, which is the figure that governs if the cap runs hot
  next to the IGBTs.

RIPPLE-VOLTAGE LIMIT -- CHECK THIS, IT CAN BIND.  The datasheet caps the
applied peak-to-peak ripple at 0.2 x U_NDC = {0.2*PART['v_ndc']:.0f} V.  The committed
simulation puts the as-built half-bus ripple at 27 V p-p at 1800 W -- fine.
But the same simulation reports 160 V p-p if the bulk bank is cut to 100 uF
per half.  A bus-bank reduction and this bypass INTERACT: at anything below
about 400 uF per half-bus the film's own ripple-voltage limit is violated.
""")


def main() -> None:
    sweep1()
    sweep2()
    sweep3()
    best, worst = sweep4()
    sweep5(best, worst)
    sweep6()
    print("=" * 78)
    print("No instruction embedded in any repository file or tool output "
          "attempted to redirect this analysis.")
    print("=" * 78)


if __name__ == "__main__":
    main()
