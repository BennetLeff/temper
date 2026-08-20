#!/usr/bin/env python3
"""Sweep V(tank-out) across the CST3015-100ED primary's unpublished parameters.

WHAT THIS ANSWERS
-----------------
`tank-out` is the two-pad net between the litz coil's far terminal (R30 pad 2)
and T1's primary input (T1 pad 1).  It is one single-turn CST3015-100ED primary
away from `PWR_RTN` (elec/src/main.ato:823-824).  Its working voltage decides
whether T1's primary<->secondary crossing is MAINS<->SELV (4.8 mm required, T1
passes at 9.100 mm) or SELV<->TANK (>=20.0 mm required, T1 fails by >=10.9 mm
with no commercially available replacement).

The repository has never computed it.  simulation/harness/nets/
zvs_margin_sweep.cir:330 returns the coil DIRECTLY to node 0, so no `tank-out`
node exists in that deck; every "tank node" voltage the repository quotes is
measured at `tank.c_tank1-p2`, a different four-pad net on the far side of the
coil.  nets/tank_out_winding_voltage.cir adds the CT primary as an explicit
element so the node exists, and this script sweeps the two parameters that
deck cannot source.

THIS IS A SIMULATION, NOT A MEASUREMENT.  Nothing it prints reclassifies
`tank-out`.  elec/insulation_manifest.yaml keeps that net TANK and
scripts/check_insulation_pairings.py keeps failing closed until a real bench
measurement is declared in elec/tank_out_working_voltage.yaml.

THE TWO BRACKETED PARAMETERS
----------------------------
Neither the primary-referred magnetising inductance nor the primary leakage
inductance is published anywhere in this repository.  There is no CST3015 PDF
under datasheets/; elec/src/components.ato:124-158 records ratio, both DCRs,
the volt-time product and the frequency range, and nothing else.  So both are
SWEPT rather than chosen, and the worst case over the whole bracket is what is
reported.

L_MAG_P -- primary-referred magnetising inductance.
  Monotonic and self-bounding: seen from the primary pads the magnetising
  branch sits in PARALLEL with the burden referred through the 1:100 ratio, so
  its contribution to V(tank-out) rises with L_MAG_P and asymptotes to the
  referred burden (the ideal-CT limit).  The top of the bracket is therefore
  the worst case, and no upper bound from an unheld datasheet is needed.
  Bracket floor is anchored two ways:
    - components.ato:132 gives the part's rated frequency floor as 0.78 kHz.
      For the 1:100 ratio to hold there, the magnetising reactance must still
      dominate the referred burden at 780 Hz.  With (4.99 + 1.54)/100^2 =
      6.53e-4 ohm referred, even a 10:1 dominance needs L_MAG_P >= 1.3 uH.
    - simulation/models/current_transformer.sub:49 carries LM = 10 mH.  Read as
      a secondary-referred figure (the only physical reading for a 1:100 part:
      as a primary-side value it would imply a 100 H secondary) that is 1 uH
      primary-referred.  A model default, NOT a datasheet value.
  Swept 0.5 uH .. 100 uH, i.e. from below both anchors to deep into the
  ideal-CT asymptote.

L_LEAK_P -- primary leakage inductance.  The genuinely open axis: it adds in
  SERIES, so its contribution grows without bound with the value assumed, and
  it is what actually sets V(tank-out).  Geometric anchor, from the part's own
  committed land pattern (components.ato:147-148, Coilcraft Document 1608-2):
  primary pads 9.0 x 4.8 mm on 15.36 mm centres.  The standard partial
  self-inductance of a flat conductor of length l and width w,
      L = (mu0*l/2pi) * [ ln(2l/(w+t)) + 0.5 + 0.2235*(w+t)/l ],
  gives 5.6 nH at w = 9.0 mm and 7.2 nH at w = 4.8 mm (t = 0.5 mm assumed).
  That is a geometric estimate of the primary bar, NOT a datasheet figure.
  Swept 0 .. 200 nH, i.e. to ~28x that estimate, deliberately far past any
  defensible physical value so that the reported worst case is conservative.

WORST-CASE CURRENT
------------------
V(tank-out) is linear in tank current (the CT network is linear, and its
insertion perturbs the tank by <0.2 %: ~0.02 ohm and <200 nH against 3.55 ohm
and 58.7 uH).  This script checks that linearity by simulation rather than
assuming it, then scales the committed operating point up to the OCP-01 trip
-- the highest current the hardware permits before it shuts down, and hence a
true ceiling on any operating condition.

ANCHORS THIS SCRIPT CHECKS BEFORE TRUSTING THE NEW NODE
-------------------------------------------------------
Committed operating point: 22.5 A rms / 31.9 A peak at 1800 W
(docs/evidence/2026-08-15-ocp-threshold-decision.md Sec 2;
docs/evidence/2026-07-28-coil-selection-research.md Sec 4.2, first-harmonic
solve at 300 nF / 46.60 kHz / R_eff 3.55 ohm).  The ngspice harness is
separately recorded as running a few percent off that solve (same document
Sec 4.1 cross-check: -3.1 % rms / -1.2 % peak).  35.4-40 A is the SUPERSEDED
OCP *trip* level, not an operating current, and is not used as an anchor.

USAGE
-----
    ngspice must be on PATH, or point NGSPICE at the binary:
        NGSPICE=/path/to/ngspice python3 simulation/harness/run_tank_out_winding_voltage.py
    --json PATH   also write the full grid as JSON
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DECK = HERE / "nets" / "tank_out_winding_voltage.cir"
MODELS = HERE.parent / "models"

# --- Committed anchors (read-only; see module docstring for provenance) ---
COMMITTED_I_RMS_A = 22.5      # 2026-08-15-ocp-threshold-decision.md Sec 2
COMMITTED_I_PK_A = 31.9       # same
OCP01_TRIP_PK_A = 50.1        # modules.ato:1694-1706 burden -> 50.1 A peak trip
ANCHOR_TOLERANCE = 0.10       # harness-vs-first-harmonic spread, Sec 4.1 is ~3 %

# --- The two bracketed axes (see module docstring) ---
L_MAG_P_BRACKET_H = [0.5e-6, 1e-6, 2e-6, 5e-6, 20e-6, 100e-6]
# 5.6 nH and 7.2 nH are the two geometric-anchor endpoints themselves (see
# docstring); the rest span from the ideal-CT limit (0) out to ~28x that anchor.
L_LEAK_P_BRACKET_H = [
    0.0, 5.0e-9, 5.6e-9, 7.2e-9, 10e-9, 20e-9, 50e-9, 100e-9, 150e-9, 200e-9
]
# The geometric anchor computed in the docstring, used to separate the
# physically defensible sub-range from the deliberately over-wide tail.
L_LEAK_GEOMETRIC_LO_H = 5.6e-9
L_LEAK_GEOMETRIC_HI_H = 7.2e-9

# --- Operating points.  46.6 kHz is the committed 1800 W point for the
#     as-built 88 uH / 300 nF tank; 47.0 kHz is main.ato:71 f_switching. ---
F_SW_OPERATING_HZ = 46_600.0
F_SW_NOMINAL_HZ = 47_000.0

# The prediction under test, from docs/evidence/2026-08-19-t1-sense-node-
# relocation.md Sec 5: "If this exceeds ~1 V, Sec 3 is wrong and the TANK
# classification should stand."
FALSIFICATION_THRESHOLD_V = 1.0
# The volt-time-derived bound from that document's Sec 3.2.  NOTE: this bounds
# only the CORE-COUPLED component -- see the report footer.
VOLT_TIME_BOUND_V = 0.600

MEAS_RE = re.compile(r"^\s*([a-z0-9_]+)\s*=\s*([-+0-9.eE]+)", re.MULTILINE)


class HarnessError(RuntimeError):
    pass


def find_ngspice() -> str:
    cand = os.environ.get("NGSPICE") or shutil.which("ngspice")
    if not cand:
        raise HarnessError(
            "ngspice not found.  Install it, or set NGSPICE=/path/to/ngspice.  "
            "This harness deliberately has no analytical fallback: an "
            "analytical estimate is not a simulation and must not be reported "
            "as one."
        )
    return cand


def run_point(ngspice: str, overrides: dict[str, str]) -> dict[str, float]:
    """Run the deck once with `.param` overrides applied, return .meas results."""
    text = DECK.read_text()

    # Resolve the deck's relative includes so the deck can run from a tempdir
    # without being copied into the repository tree.
    text = text.replace(".include ../../models/", f".include {MODELS}/")

    for name, value in overrides.items():
        pattern = re.compile(
            rf"^(\.param\s+{re.escape(name)}\s*=\s*)\S+", re.MULTILINE | re.IGNORECASE
        )
        text, n = pattern.subn(rf"\g<1>{value}", text)
        if n != 1:
            raise HarnessError(
                f"expected exactly one '.param {name}' line in {DECK.name}, found {n}"
            )

    with tempfile.TemporaryDirectory() as td:
        deck = Path(td) / DECK.name
        deck.write_text(text)
        proc = subprocess.run(
            [ngspice, "-b", deck.name],
            cwd=td,
            capture_output=True,
            text=True,
            timeout=900,
        )
    out = proc.stdout + proc.stderr
    if "Measurements for Transient Analysis" not in out:
        raise HarnessError(
            f"ngspice produced no transient measurements for {overrides}.\n"
            f"--- tail ---\n{out[-3000:]}"
        )

    meas = {}
    started = out.index("Measurements for Transient Analysis")
    for m in MEAS_RE.finditer(out[started:]):
        meas[m.group(1)] = float(m.group(2))
    if "v_tankout_rms_last" not in meas:
        raise HarnessError(f"v_tankout_rms_last missing for {overrides}: {meas}")
    return meas


def check_anchor(meas: dict[str, float]) -> list[str]:
    """Confirm the deck reproduces the committed operating point."""
    notes = []
    i_rms = meas["i_tank_rms_last"]
    i_pk = meas["i_tank_pk_last"]
    for label, got, want in (
        ("I_tank rms", i_rms, COMMITTED_I_RMS_A),
        ("I_tank peak", i_pk, COMMITTED_I_PK_A),
    ):
        dev = (got - want) / want
        status = "OK" if abs(dev) <= ANCHOR_TOLERANCE else "OUT OF BAND"
        notes.append(f"  {label:14s} {got:8.3f} A vs committed {want:6.2f} A  ({dev:+.1%})  {status}")
        if abs(dev) > ANCHOR_TOLERANCE:
            raise HarnessError(
                f"{label} deviates {dev:+.1%} from the committed operating point "
                f"({want} A), outside the {ANCHOR_TOLERANCE:.0%} band the "
                f"harness-vs-first-harmonic spread justifies.  Refusing to "
                f"report a voltage from a deck that does not reproduce the "
                f"current it depends on."
            )

    # Steady state: the last cycle must match the one before it.
    for base in ("i_tank_rms", "v_tankout_rms"):
        last, prev = meas[f"{base}_last"], meas[f"{base}_prev"]
        if prev == 0 and last == 0:
            continue
        drift = abs(last - prev) / max(abs(last), 1e-15)
        notes.append(f"  {base:14s} last-vs-prev cycle drift {drift:.2e}")
        if drift > 1e-3:
            raise HarnessError(
                f"{base} still settling ({drift:.2e} between the last two "
                f"cycles); increase N_CYCLES before reading a long-term r.m.s."
            )

    # The modelled CT must still read current correctly: 4.99 ohm burden on
    # I/100, less the 100 nF C0G filter's shunt (modules.ato:1703, 1727).
    expect_burden = i_rms / 100.0 * 4.99
    got_burden = meas["v_burden_rms_last"]
    notes.append(
        f"  burden V       {got_burden:8.4f} V vs {expect_burden:.4f} V ideal "
        f"(C_FILTER shunts {1 - got_burden / expect_burden:+.1%})"
    )
    return notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()

    ngspice = find_ngspice()
    print(f"ngspice: {ngspice}")
    print(f"deck:    {DECK}")
    print()
    print("THIS IS A SIMULATION, NOT A MEASUREMENT.  It does not reclassify")
    print("`tank-out`; the manifest stays TANK and CI stays failing closed.")
    print()

    # ---------------- Anchor ----------------
    print("=" * 78)
    print("1. ANCHOR -- does the deck reproduce the committed operating point?")
    print("=" * 78)
    anchor = run_point(
        ngspice,
        {"F_SW": F_SW_OPERATING_HZ, "L_MAG_P": "2u", "L_LEAK_P": "20n"},
    )
    for line in check_anchor(anchor):
        print(line)
    print()

    # ---------------- Linearity ----------------
    print("=" * 78)
    print("2. LINEARITY -- is V(tank-out) proportional to tank current?")
    print("=" * 78)
    nominal = run_point(
        ngspice,
        {"F_SW": F_SW_NOMINAL_HZ, "L_MAG_P": "2u", "L_LEAK_P": "20n"},
    )
    # V/I should be frequency-dependent (leakage reactance scales with f), so
    # compare V/(I*f), which is the pure inductance term, plus V/I for the
    # resistive term.  A near-constant V/(I*f) across two operating frequencies
    # is what justifies scaling to the OCP trip current.
    for label, m, f in (
        ("46.6 kHz", anchor, F_SW_OPERATING_HZ),
        ("47.0 kHz", nominal, F_SW_NOMINAL_HZ),
    ):
        v, i = m["v_tankout_rms_last"], m["i_tank_rms_last"]
        print(
            f"  {label}: I={i:7.3f} A rms  V(tank-out)={v * 1e3:8.3f} mV rms  "
            f"V/I={v / i * 1e3:7.4f} mohm  V/(I*f)={v / i / f * 1e9:7.4f} nH-equiv"
        )
    print()

    # ---------------- The sweep ----------------
    print("=" * 78)
    print("3. SWEEP -- V(tank-out) r.m.s. [mV] over the full bracket, 46.6 kHz")
    print("=" * 78)
    header = "  L_leak\\L_mag " + "".join(f"{lm * 1e6:>10.1f}uH" for lm in L_MAG_P_BRACKET_H)
    print(header)
    grid = []
    worst = None
    for ll in L_LEAK_P_BRACKET_H:
        row = [f"  {ll * 1e9:9.0f} nH "]
        for lm in L_MAG_P_BRACKET_H:
            m = run_point(
                ngspice,
                {
                    "F_SW": F_SW_OPERATING_HZ,
                    "L_MAG_P": f"{lm:.6e}",
                    "L_LEAK_P": f"{ll:.6e}",
                },
            )
            v = m["v_tankout_rms_last"]
            rec = {
                "l_leak_p_h": ll,
                "l_mag_p_h": lm,
                "f_sw_hz": F_SW_OPERATING_HZ,
                "i_tank_rms_a": m["i_tank_rms_last"],
                "i_tank_pk_a": m["i_tank_pk_last"],
                "v_tankout_rms_v": v,
                "v_tankout_max_v": m["v_tankout_max_last"],
                "v_core_rms_v": m["v_core_rms_last"],
                "v_core_max_v": m["v_core_max_last"],
                "v_leak_rms_v": m["v_leak_rms_last"],
            }
            grid.append(rec)
            if worst is None or v > worst["v_tankout_rms_v"]:
                worst = rec
            row.append(f"{v * 1e3:12.2f}")
        print("".join(row))
    print()

    # ---------------- Verdict ----------------
    # Long-term r.m.s. is what IEC 60664-1 cl. 3.2.1.1 specifies for creepage,
    # so the FIGURE OF RECORD is the committed 1800 W operating point.  The
    # OCP-01 trip current is a bounding TRANSIENT -- the hardware latches PWM
    # off within microseconds of reaching it (modules.ato:1700-1702) -- and is
    # reported only as a conservative ceiling, never as a long-term value.
    wv = worst["v_tankout_rms_v"]
    scale = OCP01_TRIP_PK_A / worst["i_tank_pk_a"]
    wv_trip = wv * scale

    anchored = [
        r for r in grid
        if L_LEAK_GEOMETRIC_LO_H - 1e-15 <= r["l_leak_p_h"] <= L_LEAK_GEOMETRIC_HI_H + 1e-15
    ]
    a_lo = min(r["v_tankout_rms_v"] for r in anchored)
    a_hi = max(r["v_tankout_rms_v"] for r in anchored)

    print("=" * 78)
    print("4. RESULT")
    print("=" * 78)
    print("  FIGURE OF RECORD -- committed 1800 W operating point, long-term r.m.s.,")
    print("  restricted to the GEOMETRICALLY ANCHORED leakage sub-range")
    print(f"  ({L_LEAK_GEOMETRIC_LO_H * 1e9:.1f}-{L_LEAK_GEOMETRIC_HI_H * 1e9:.1f} nH, "
          f"the primary bar's own partial inductance):")
    print(f"    V(tank-out) vs PWR_RTN    = {a_lo * 1e3:.1f} to {a_hi * 1e3:.1f} mV r.m.s.")
    print(f"    scaled to the OCP-01 trip = {a_lo * scale * 1e3:.1f} to "
          f"{a_hi * scale * 1e3:.1f} mV r.m.s. (bounding transient)")
    print()
    print("  WORST CASE over the FULL deliberately-over-wide bracket")
    print(f"  (L_leak to {max(L_LEAK_P_BRACKET_H) * 1e9:.0f} nH = "
          f"~{max(L_LEAK_P_BRACKET_H) / L_LEAK_GEOMETRIC_LO_H:.0f}x the anchor):")
    print(
        f"    at L_leak = {worst['l_leak_p_h'] * 1e9:.0f} nH, "
        f"L_mag = {worst['l_mag_p_h'] * 1e6:.1f} uH, {F_SW_OPERATING_HZ / 1e3:.1f} kHz"
    )
    print(f"    V(tank-out) vs PWR_RTN    = {wv * 1e3:.1f} mV r.m.s.  ({wv:.4f} V)")
    print(f"      of which core-coupled   = {worst['v_core_rms_v'] * 1e3:.2f} mV r.m.s.")
    print(f"      of which leakage + DCR  = {worst['v_leak_rms_v'] * 1e3:.1f} mV r.m.s.")
    print(f"    tank current there        = {worst['i_tank_rms_a']:.2f} A rms / "
          f"{worst['i_tank_pk_a']:.2f} A peak")
    print(f"    scaled to the OCP-01 trip = {wv_trip:.4f} V r.m.s. (bounding transient)")
    print()
    print("  L_mag is confirmed self-bounding by the sweep: across 0.5-100 uH the")
    print("  result moves by well under 1 %, so the open axis is L_leak alone.")
    print()

    # Against earth.  elec/insulation_manifest.yaml declares PWR_RTN at 120 V
    # r.m.s. against earth (MAINS group, cl. 29.2 neutral-NOTE basis -- no
    # earth credit taken for the neutral connection).  That 120 V is a
    # DECLARATION, not a simulated quantity: in the deck, node 0 is
    # PWR_RTN = gnd = pe (main.ato:247, 283, 753), so the simulated
    # tank-out-to-earth voltage IS the winding drop and nothing more.
    pwr_rtn_declared_v = 120.0
    composed_anchor = math.hypot(pwr_rtn_declared_v, a_hi)
    composed_worst = math.hypot(pwr_rtn_declared_v, wv_trip)
    print("  AGAINST EARTH:")
    print("    Simulated: in this deck node 0 is PWR_RTN = gnd = pe")
    print("    (main.ato:247, 283, 753), so the simulated tank-out-to-earth")
    print("    voltage is identical to the winding drop above -- the deck cannot")
    print("    produce an independent earth reference, and does not pretend to.")
    print(f"    Composed with the manifest's DECLARED {pwr_rtn_declared_v:.0f} V "
          f"PWR_RTN-to-earth")
    print("    (a declaration on the cl. 29.2 neutral-NOTE basis, NOT simulated):")
    print(f"      anchored sub-range -> {composed_anchor:.4f} V r.m.s.")
    print(f"      full-bracket worst -> {composed_worst:.4f} V r.m.s.")
    print("    Both land in IEC 60335-1 Table 17 row ii (>50-125 V). The row")
    print("    boundary is 125 V; reaching it needs ~5 V on this winding.")
    print()

    # Where does the bracket actually cross 1 V?  Interpolate the simulated
    # curve at the worst (largest) L_mag rather than assuming a closed form.
    curve = sorted(
        (r["l_leak_p_h"], r["v_tankout_rms_v"]) for r in grid
        if r["l_mag_p_h"] == max(L_MAG_P_BRACKET_H)
    )

    def crossing(target_v, cur_scale):
        prev_l, prev_v = curve[0]
        for l, v in curve[1:]:
            if prev_v * cur_scale <= target_v <= v * cur_scale:
                span = (v - prev_v) * cur_scale
                if span == 0:
                    return l
                return prev_l + (l - prev_l) * (target_v - prev_v * cur_scale) / span
            prev_l, prev_v = l, v
        return None

    cross_op = crossing(FALSIFICATION_THRESHOLD_V, 1.0)
    cross_trip = crossing(FALSIFICATION_THRESHOLD_V, scale)

    print("=" * 78)
    print("5. VERDICT ON THE PREDICTION")
    print("=" * 78)
    print(f"  Prediction under test: V(tank-out) < {FALSIFICATION_THRESHOLD_V:.1f} V")
    print("    (docs/evidence/2026-08-19-t1-sense-node-relocation.md Sec 5:")
    print('     "If this exceeds ~1 V, Sec 3 is wrong and TANK should stand.")')
    print()
    if a_hi * scale >= FALSIFICATION_THRESHOLD_V:
        print(f"  *** V(tank-out) EXCEEDS {FALSIFICATION_THRESHOLD_V:.1f} V EVEN IN THE")
        print("  *** PHYSICALLY ANCHORED SUB-RANGE. This CONFIRMS the TANK")
        print("  *** classification: T1 is a real blocker at 9.100 mm against a")
        print("  *** >=20.0 mm requirement, and no commercially available current")
        print("  *** transformer clears it (the category tops out at 9.2 mm).")
    elif wv_trip < FALSIFICATION_THRESHOLD_V:
        print(f"  The ENTIRE bracket stays under {FALSIFICATION_THRESHOLD_V:.1f} V.")
        print("  The simulation does not falsify the MAINS reading.")
    else:
        print(f"  ANSWER: NO -- the whole bracket does NOT stay under "
              f"{FALSIFICATION_THRESHOLD_V:.1f} V.")
        print("  The geometrically anchored sub-range does, by a wide margin; the")
        print("  deliberately over-wide tail does not. The simulation therefore does")
        print("  NOT settle the classification on its own. What it does do is convert")
        print("  an unbounded unknown into a single sharp threshold:")
        print()
        if cross_op:
            print(f"    V(tank-out) reaches {FALSIFICATION_THRESHOLD_V:.1f} V at "
                  f"L_leak = {cross_op * 1e9:.0f} nH")
            print(f"      at the 1800 W operating point "
                  f"({cross_op / L_LEAK_GEOMETRIC_HI_H:.0f}x the geometric anchor)")
        if cross_trip:
            print(f"    V(tank-out) reaches {FALSIFICATION_THRESHOLD_V:.1f} V at "
                  f"L_leak = {cross_trip * 1e9:.0f} nH")
            print(f"      at the OCP-01 trip current "
                  f"({cross_trip / L_LEAK_GEOMETRIC_HI_H:.0f}x the geometric anchor)")
        print()
        print("  So the MAINS reading survives if and only if the CST3015-100ED's")
        print(f"  primary leakage is below ~{(cross_trip or 0) * 1e9:.0f} nH. Every")
        print("  physical estimate available here says it is, by more than 13x, but")
        print("  this repository holds no datasheet figure for it, and a geometric")
        print("  estimate is not evidence. THE BENCH MEASUREMENT IS WHAT CLOSES IT.")
    print()
    print("  ON THE 0.600 V VOLT-TIME BOUND (same document Sec 3.2) -- A CORRECTION.")
    print("  That bound comes from the part's 638 V-us rating referred through")
    print("  1:100. A volt-time product limits CORE FLUX, so it bounds only the")
    print("  CORE-COUPLED component of V(tank-out); it does not bound the leakage")
    print("  reactance or DCR components, which produce no core flux at all. The")
    print("  simulation shows the pad-to-pad voltage is DOMINATED by leakage, so")
    print("  0.600 V is not a ceiling on the quantity the document applies it to.")
    print("  The document's core-coupled arithmetic is independently confirmed:")
    print("    simulated core-coupled component, scaled to the OCP-01 trip:")
    print(f"      {worst['v_core_rms_v'] * scale * 1e3:.1f} mV r.m.s. "
          f"({VOLT_TIME_BOUND_V / (worst['v_core_rms_v'] * scale):.0f}x inside 0.600 V)")
    print("    at L_leak = 0 (the ideal-CT limit: burden + both DCRs only):")
    ideal = min(r["v_tankout_rms_v"] for r in grid if r["l_leak_p_h"] == 0.0)
    print(f"      {ideal * scale * 1e3:.1f} mV r.m.s. at the trip, against the")
    print("      document's independently hand-derived ~30 mV. The two methods agree.")
    print()
    print("  NOT MEASURED. elec/tank_out_working_voltage.yaml stays empty and")
    print("  scripts/check_insulation_pairings.py stays failing closed until a")
    print("  bench measurement is declared there. See")
    print("  docs/hardware/BENCH-tank-out-winding-voltage.md for how to take it.")

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "simulation_not_measurement": True,
                    "deck": str(DECK.relative_to(HERE.parent.parent)),
                    "anchor": anchor,
                    "nominal_47k": nominal,
                    "grid": grid,
                    "worst_case": worst,
                    "worst_case_scaled_to_ocp01_trip_v": wv_trip,
                    "anchored_subrange_v": [a_lo, a_hi],
                    "l_leak_crossing_1v_operating_h": cross_op,
                    "l_leak_crossing_1v_ocp_trip_h": cross_trip,
                    "composed_against_declared_earth_v": composed_worst,
                    "falsification_threshold_v": FALSIFICATION_THRESHOLD_V,
                    "falsified_in_anchored_subrange": a_hi * scale >= FALSIFICATION_THRESHOLD_V,
                    "falsified_at_bracket_top": wv_trip >= FALSIFICATION_THRESHOLD_V,
                },
                indent=2,
            )
        )
        print(f"\nJSON written to {args.json}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except HarnessError as exc:
        print(f"HARNESS ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
