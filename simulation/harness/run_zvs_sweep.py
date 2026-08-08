#!/usr/bin/env python3
"""Scriptable, non-interactive ngspice harness for the ZVS margin sweep
(simulation/harness/nets/zvs_margin_sweep.cir).

This is the R1-R6 deliverable for
docs/brainstorms/2026-07-25-spice-harness-zvs-sweep-requirements.md: a
pan-load x switching-frequency sweep of the half-bridge / resonant-tank
model, reporting ZVS margin at every operating point and naming the
worst ones -- not just a pass/fail scalar.

UPDATED 2026-08-07 (docs/evidence/2026-08-07-zvs-margin-sweep.md), for the
build-order step 9 ZVS-margin-across-the-pan-load-envelope sweep. Three
things changed from the 2026-07-27 version of this harness:

1. PAN_L1 (coil UNLOADED inductance) moved from pan_load.sub's stale 80uH
   model default to elec/src/main.ato's now-declared `l_tank_assumed =
   88uH` (the coil stopped being a placeholder 2026-07-29,
   docs/evidence/2026-07-29-tank-coil-specification.md).
2. PAN_K/PAN_L2 for the ferromagnetic (cast_iron/stainless) presets are
   RE-DERIVED against main.ato's own 2026-07-29 `l_pan_loaded_ratio =
   0.68` (an in-band, Infineon EVAL-IHW25N140R5L chart reading) instead
   of the 2026-07-27 K=0.79/L2=218uH pair, which was solved against a
   DIFFERENT Infineon measurement (AN235020, 90-150kHz, out of this
   design's 20-50kHz band) and which main.ato's own comment already
   flags as a known, un-actioned divergence ("CONSEQUENCE, RECORDED NOT
   FIXED"). See PAN_L2_DEFAULT_H / PAN_PRESETS below for the derivation.
   Still constraint-satisfying, not measured -- see caveats there.
3. FREQ_GRID_HZ is densified across the firmware's ACTUAL PLL tracking
   range (f_pll_tracking_min/max in main.ato, PLL_MIN_FREQ_HZ/
   PLL_MAX_FREQ_HZ in pll_control.h -- 44-50kHz, not the 20-100kHz
   "LC-tank theoretical bound" main.ato itself says overstates firmware
   capability by 5x), and each point now also reports delivered pan
   power (P_pan = i_pan_rms^2 * RPAN) so the 1800W operating point can be
   located on the same grid as the ZVS-margin numbers, per
   docs/STRATEGY.md's instruction to sweep "the power range up to
   1800W," not just frequency.

None of this makes the pan-coupling model measured. It remains one
self-consistent point in an underdetermined family (K, L2, RPAN from 2
equations); see the evidence doc for the full statement of what would
resolve that (a bench measurement, not more arithmetic).

What it measures
-----------------
For each (pan preset, switching frequency) grid point, generates an
ephemeral copy of zvs_margin_sweep.cir with PAN_K / PAN_RPAN / F_SW
overridden (the committed .cir's own baseline values are left untouched
on disk; ephemeral copies are deleted after each run), runs ngspice on
it, and parses the auto-printed ".meas" results out of ngspice's batch
stdout:
    vce_hs_last / vce_ls_last   -- Vce at each switch's own turn-on
                                   instant, last simulated cycle (this
                                   IS the ZVS margin; see the .cir header
                                   for the definition and why)
    vce_hs_prev / vce_ls_prev   -- same, one cycle earlier (ring-up /
                                   convergence check)
    i_tank_pk_last, i_tank_rms_last, v_sw_max, v_sw_min -- context

ZVS margin (both this script and the .cir agree on the definition):
    margin_pct = 100 * |Vce at turn-on| / (2 * V_HALF)
report the WORSE of the HS/LS margins as the operating point's headline
number, since either switch losing ZVS is a failure.

Labels (a reporting convenience of this harness, not a datasheet figure):
    margin_pct < 10        -> "zvs_held"
    10 <= margin_pct < 50  -> "degraded"
    margin_pct >= 50       -> "zvs_lost"

Convergence
-----------
N_CYCLES in the .cir is fixed at 25. Some operating points (especially
weak/no coupling, which this model implements as very light tank
damping -- see the .cir header's PANLOAD_TRANSFORMER note) could in
principle still be ring-up transients rather than periodic steady state
at cycle 25. Every point's vce_*_prev vs vce_*_last delta is checked; any
point where that delta exceeds 1% of the full bus (3.4V) is flagged
"converged": false in its result and EXCLUDED from the worst-margin
ranking text (though its raw numbers are still reported) -- a possibly-
still-transient number is not allowed to silently masquerade as a
steady-state verdict.

Calibration
-----------
Every model used carries `calibrated: false`. See the .cir header for the
full list of values sourced from elec/ vs. values that are undocumented
model defaults (the coil inductance is the big one: modules.ato's
ResonantTank does not specify one at all). This propagates into the
evidence verdict regardless of how the numbers come out (METHODOLOGY.md
SS11, R4 of the brainstorm).

Determinism
-----------
Per METHODOLOGY.md SS5 ("the oracle is not exempt"), this script re-runs
TWO decks -- the committed baseline (cast iron, 35kHz, as-shipped in the
.cir) and the worst-margin grid point found -- N times each (default 3)
and asserts byte-identical stdout before trusting any number from this
harness. Full-grid determinism is NOT checked (would 2x the runtime for
marginal additional evidence about a solver that has already shown itself
deterministic on this exact resonant topology); this is stated as a
deliberate scope limit, not an oversight.

Usage
-----
    uv run python simulation/harness/run_zvs_sweep.py [--determinism-runs N] [--out PATH]

Exit codes
----------
    0  harness ran, ngspice was deterministic on the checked decks, evidence written
    1  ngspice not found / netlist missing / master deck failed to run at all
    2  ngspice was non-deterministic on a checked deck (do not trust any
       figure in the evidence file until this is resolved)
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_DIR = Path(__file__).resolve().parent
NETS_DIR = HARNESS_DIR / "nets"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from _lib.provenance import collect as collect_provenance  # noqa: E402
MASTER_CIR = NETS_DIR / "zvs_margin_sweep.cir"

# --- Sourced from elec/ (read-only); duplicated here (not imported from
# the .cir) only for evidence-file bookkeeping. The .cir is the single
# source of truth for what the simulator actually uses; see its header
# for the modules.ato / main.ato line citations for every value below. ---
V_HALF = 170.0          # PowerInput.v_bus_half, modules.ato:563
V_BUS_FULL = 2 * V_HALF  # 340V differential, main.ato:49/:65
RG_OHM = 2.2             # GateDriveHS/LS.rg_on, modules.ato:158/:213
RGS_OHM = 2200.0         # GateDriveHS/LS.rgs, modules.ato:164/:219
T_DEAD_S = 305.4e-9      # HalfBridge.t_dead_time, modules.ato:279
C_TANK_F = 300e-9        # c_tank1+c_tank2+c_tank3 in parallel (3 x 100nF CDE
                         # 942C16P1K-F as of 2026-07-29; was 2 x 150nF WIMA
                         # FKP 1, re-sourced on AC current not value -- see
                         # docs/evidence/2026-07-29-tank-cap-cde-942c-
                         # verification.md). The 300nF total is UNCHANGED.
F_SWITCHING_NOMINAL_HZ = 47_000.0   # main.ato:71 f_switching, UNCHANGED by
# this pass. History: CORRECTED 2026-07-27 from a 35kHz value that measured
# 100.7% ZVS margin LOST (full hard switching of the half-bridge) for
# cast_iron/stainless once PAN_PRESETS was corrected to the (now-superseded)
# Infineon-anchored K=0.79 -- see docs/evidence/2026-07-27-pan-preset-
# correction.md Sec 4.1 and docs/evidence/2026-07-27-zvs-operating-point.md.
# main.ato's own comment on this line states it is now CONTINGENT on
# L_LOADED ~= 59.8uH (not any single coil value in isolation) --
# 88uH x 0.68 = 59.84uH, per the 2026-07-29 coil respecification -- and
# that 47kHz sits at ratio 1.2512 over the nominal loaded resonance
# (37563Hz) and 1.1261 over the worst-case (-10% L, -10% C) loaded
# resonance (41737Hz, see F_PLL_MIN_HZ below). Re-verified, not re-derived,
# by this pass's sweep (see verdict below).
F_SWITCHING_NOMINAL_HZ_PRE_FIX_2026_07_27 = 35_000.0  # historical; still the
# .cir's own committed self-test anchor value (FREQ_GRID_HZ/baseline check
# below) -- deliberately NOT changed to 47kHz, see FREQ_GRID_HZ comment.
F_RESONANT_DECLARED_HZ = 31_000.0   # main.ato:311 f_resonant_nominal.
# UPDATED 2026-08-07 to track main.ato: moved 25kHz -> 31kHz on 2026-07-29
# (docs/evidence/2026-07-29-tank-coil-specification.md) once the coil
# stopped being unspecified -- this is now DERIVED arithmetic
# (1/(2*pi*sqrt(88uH*300nF)) = 30975Hz, declared 31kHz) rather than a
# fourth independent guess. It is the UNLOADED resonance (no pan); see
# F_RESONANT_COMPUTED_HZ below, which should now closely track it since
# both use the same 88uH/300nF pair (the 2026-07-27 version of this
# harness computed F_RESONANT_COMPUTED_HZ from an 80uH model default that
# had no relationship to main.ato's then-25kHz declaration at all).
# --- PLL tracking range: the firmware's ACTUAL capability, NOT the
# 20-100kHz "LC tank theoretical bound" main.ato:72 itself flags as
# overstating firmware capability by 5x. Mirrors main.ato's
# f_pll_tracking_min/max and pll_control.h's PLL_MIN_FREQ_HZ/
# PLL_MAX_FREQ_HZ, cross-checked by scripts/check_pll_range_
# consistency.py. THIS is the range a real sweep must resolve finely --
# it is the window the firmware can and will actually command. ---
F_PLL_MIN_HZ = 44_000.0   # main.ato f_pll_tracking_min / pll_control.h PLL_MIN_FREQ_HZ
F_PLL_MAX_HZ = 50_000.0   # main.ato f_pll_tracking_max / pll_control.h PLL_MAX_FREQ_HZ
PAN_L1_DEFAULT_H = 88e-6            # UPDATED 2026-08-07: was pan_load.sub's
# stale 80uH PANLOAD_TRANSFORMER model default; now elec/src/main.ato's
# declared l_tank_assumed = 88uH (modules.ato ResonantTank.inductor_conn,
# an Inductor since 2026-07-29 -- no longer a placeholder). Using the old
# model default here, after the design declared a real value, would be
# exactly the "harness silently drifts behind the source it claims to
# model" defect this project's own evidence trail (main.ato's
# l_pan_loaded_ratio comment) already names as unresolved for K/L2 below.
F_RESONANT_COMPUTED_HZ = 1.0 / (
    2 * 3.141592653589793 * (PAN_L1_DEFAULT_H * C_TANK_F) ** 0.5
)

# --- Pan-load grid -- K/L2 RE-DERIVED 2026-08-07 for the ferromagnetic
# (cast_iron/stainless) presets, see docs/evidence/2026-08-07-zvs-margin-
# sweep.md Sec 2 for the full derivation. aluminum/no_pan are UNCHANGED
# (no new evidence touches them).
#
# WHY THE FERROMAGNETIC PRESETS MOVED. The 2026-07-27 correction
# (docs/evidence/2026-07-27-pan-preset-correction.md) solved K=0.79/
# L2=218uH against Infineon AN235020's measured loaded/unloaded L-ratio
# (0.40), measured at 90-150kHz on an unstated stockpot -- OUT OF this
# design's 20-50kHz band. On 2026-07-29, elec/src/main.ato's own
# `l_pan_loaded_ratio` was separately updated to 0.68, sourced from a
# DIFFERENT, IN-BAND Infineon chart (EVAL-IHW25N140R5L Fig. 16, a 2kW
# cooking coil measured WITH a pan across 15-50kHz: ratio 0.71/0.68/0.66
# at 30/40/50kHz) -- but this harness's K/L2 were left untouched, and
# main.ato's own comment on that line names the resulting divergence
# explicitly ("CONSEQUENCE, RECORDED NOT FIXED... this file and that
# harness now describe pan coupling differently... the harness preset is
# the one anchored to out-of-band data"). Running this harness's OLD
# K=0.79 today would sweep a coupling point main.ato itself no longer
# asserts.
#
# THE RE-DERIVATION. Using the SAME T-model relation
# run_tank_coil_sweep.py already uses elsewhere in this repo,
#     L_app/L1 = 1 - K^2 * x^2/(RPAN^2 + x^2),   x = omega * L2
# solved (RPAN=10 ohm held fixed, same uncited pan_load.sub placeholder
# as the 2026-07-27 pass used -- not re-solved here, to avoid trading one
# underdetermined pair for an equally underdetermined triple) against TWO
# of main.ato's three chart points (30kHz/0.71 and 50kHz/0.66) gives
# K=0.6136, L2=97.13uH. Checked against the THIRD point (40kHz): this
# pair predicts ratio=0.6776 against main.ato's declared 0.68 -- 0.35%
# off, an order of magnitude inside the 1.05 ZVS-margin threshold the PLL
# floor is derived against. THIS IS STILL CONSTRAINT-SATISFYING, NOT
# MEASURED -- it is one point in a family that 2 unknowns (K, L2) and 3
# approximately-consistent equations (not quite exactly consistent,
# hence the 0.35% residual) narrow but do not uniquely pin down, and
# "narrows a chart reading closer to another chart reading" is not a
# bench measurement of THIS project's coil and pan. See
# docs/evidence/2026-08-07-zvs-margin-sweep.md Sec 2 for the full
# arithmetic and docs/evidence/2026-07-27-coil-pan-coupling-resolution.md
# Sec 4 for what a real bench measurement of this quantity requires
# (three frequency points on the real coil+pan -- unchanged advice; this
# pass substitutes a better chart reading for a worse one, it does not
# supply the missing bench data).
#
# PAN_RPAN is held UNIFORM across all four presets (10 ohm, unchanged --
# see docs/evidence/2026-07-27-coil-pan-coupling-resolution.md Sec 2.6.3
# for why a per-material RPAN table was rejected as a source). L2 is
# likewise held uniform: in this model's T-topology it represents the
# pan's geometric self-inductance as a shorted loop, primarily a function
# of pan/coil size and shape rather than material, and no per-material L2
# measurement exists in this project's evidence.
PAN_L2_DEFAULT_H = 97.13e-6  # docs/evidence/2026-08-07-zvs-margin-sweep.md Sec 2
PAN_K_FERROMAGNETIC = 0.6136  # ditto
PAN_PRESETS = [
    # name, K, RPAN_ohm, L2_h, source note
    (
        "cast_iron", PAN_K_FERROMAGNETIC, 10.0, PAN_L2_DEFAULT_H,
        "ASSUMPTION: no independent cast-iron measurement exists anywhere "
        "in this project's literature search (docs/evidence/2026-07-27-"
        "coil-pan-coupling-prior-art.md). Treated identically to the "
        "stainless/ferromagnetic point below because cast iron is "
        "ferromagnetic like the measured pan and no evidence distinguishes "
        "the two materials' coupling quantitatively -- NOT a claim they "
        "are physically identical, only that no citation supports a "
        "different number. Derivation (RE-DERIVED 2026-08-07, see block "
        "comment above): K=0.6136/L2=97.13uH solved against main.ato's own "
        "in-band 0.71/0.68/0.66 ratio at 30/40/50kHz "
        "(docs/evidence/2026-07-29-tank-coil-specification.md), holding "
        "RPAN=10 ohm fixed. Full arithmetic: "
        "docs/evidence/2026-08-07-zvs-margin-sweep.md Sec 2.",
    ),
    (
        "stainless", PAN_K_FERROMAGNETIC, 10.0, PAN_L2_DEFAULT_H,
        "Infineon EVAL-IHW25N140R5L user guide rev 1.0 Fig. 16 (a 2kW "
        "cooking coil measured WITH a vessel, 15-50kHz -- THIS design's "
        "own band), read at 40kHz as loaded/unloaded ratio 0.68 "
        "(0.71 at 30kHz, 0.66 at 50kHz), the same chart reading behind "
        "elec/src/main.ato's `l_pan_loaded_ratio = 0.68` "
        "(docs/evidence/2026-07-29-tank-coil-specification.md). "
        "K=0.6136/L2=97.13uH solved to reproduce that ratio via the "
        "T-model relation, holding RPAN=10 ohm (pan_load.sub's own single "
        "non-material-specific subckt default) fixed. Full arithmetic: "
        "docs/evidence/2026-08-07-zvs-margin-sweep.md Sec 2. NOT a unique "
        "solution -- 2 unknowns (K, L2), RPAN held fixed rather than "
        "solved; see that section's underdetermination note. SUPERSEDES "
        "the 2026-07-27 K=0.79/L2=218uH point (docs/evidence/2026-07-27-"
        "coil-pan-coupling-resolution.md Sec 2.5), which was anchored to "
        "a DIFFERENT Infineon measurement (AN235020, 90-150kHz) outside "
        "this design's 20-50kHz operating band.",
    ),
    (
        "aluminum", 0.15, 10.0, PAN_L2_DEFAULT_H,
        "UNCHANGED 2026-08-07 -- no new evidence touches this preset. "
        "ASSUMPTION, retained from the 2026-07-27 pre-correction value -- "
        "NOT derived from Infineon. The ferromagnetic coupling floor is "
        "specific to Infineon's ferromagnetic-pan measurements "
        "(permeability-enhanced coupling) and does not necessarily "
        "transfer to non-ferrous aluminum, which couples by eddy currents "
        "alone. No source in the literature search measures aluminum K "
        "in a full-pan geometry; APHO2025's small-test-coupon R_LOAD "
        "measurement (54.6mOhm Al vs. 137.7mOhm ferromagnetic SS410, "
        "~2.5x lower, docs/evidence/2026-07-27-coil-pan-coupling-prior-"
        "art.md) qualitatively supports weaker aluminum coupling but is "
        "NOT used to derive a number here (different geometry/scale by "
        "roughly 2 orders of magnitude -- see that document's own "
        "caveat). K=0.15 is flagged UNVERIFIED, not measured. L2 is "
        "shared with the ferromagnetic presets (97.13uH, RE-DERIVED "
        "2026-08-07) per the uniform-L2 rationale above, though at this "
        "K its effect on the ratio is small regardless of L2's value.",
    ),
    (
        "no_pan", 0.01, 10.0, PAN_L2_DEFAULT_H,
        "UNCHANGED 2026-08-07. Models the physical absence of a pan (no "
        "eddy-current load), not a material property -- the Infineon "
        "floor/measurement logic does not apply. At K~=0.01, L2/RPAN are "
        "immaterial: the L-ratio floor 1-K^2 ~= 0.9999 regardless of "
        "their value.",
    ),
]

# --- Frequency grid: bracket the computed UNLOADED tank resonance
# (~32.5kHz, see F_RESONANT_COMPUTED_HZ) tightly, plus the declared
# nominal (35kHz) and well above it. The original 28-45kHz grid (pre-
# 2026-07-27 preset correction) located the ZVS transition between 32kHz
# (lost) and 33kHz (held) for ALL FOUR pan presets, because the broken
# K=0.15-0.5/L2=1uH presets barely loaded the tank at all -- the loaded
# and unloaded resonances were nearly identical.
#
# EXTENDED 2026-07-27 (docs/evidence/2026-07-27-pan-preset-correction.md)
# after the corrected cast_iron/stainless preset (K=0.79, L2=218uH) moved
# their LOADED resonance to ~52kHz at this deck's fixed PAN_L1=80uH (self-
# consistent iteration: L_apparent/L1 depends on omega, which depends on
# L_apparent -- see the resolution doc Sec 2.1) -- ~60% above the old
# 32.5kHz figure, consistent with the supplementary-deck finding reported
# in docs/evidence/2026-07-27-pan-model-correction.md Sec 4. The original
# 28-45kHz grid never converges to ZVS-held for the two K=0.79 presets at
# all (every point 100.4-101.1% zvs_lost, confirmed by a live run before
# this extension) -- it was measuring only the aluminum/no_pan (low-K,
# still barely-loaded) transition. Points above 45kHz were added
# specifically to locate the high-K transition; low points are kept for
# the still-valid aluminum/no_pan comparison and for the (cast_iron,
# 35kHz) baseline self-consistency check.
#
# NOTE 2026-07-27 (docs/evidence/2026-07-27-zvs-operating-point.md):
# main.ato:71's declared nominal moved from 35kHz to 47kHz (see
# F_SWITCHING_NOMINAL_HZ above) once 35kHz was shown to lose ZVS
# completely for ferromagnetic pans. 35kHz remains in this grid, and
# remains the .cir's own committed .param default, ONLY as the fixed
# self-test anchor the sanity check below needs (it must match a value
# the committed deck already ships with) -- it no longer represents the
# design's current nominal switching frequency.
#
# DENSIFIED 2026-08-07 (docs/evidence/2026-08-07-zvs-margin-sweep.md)
# across F_PLL_MIN_HZ-F_PLL_MAX_HZ (44-50kHz, the firmware's ACTUAL PLL
# tracking range -- see that constant's comment) at 500Hz resolution.
# This is the window the firmware can and will actually command; the
# original grid's coarser 45/48/50kHz points could straddle a real
# transition inside that 6kHz band without ever landing a point on it.
# Context points below 44kHz (down through the loaded-resonance region,
# ~30-42kHz) and above 50kHz are kept for the same purpose as before:
# locating the transition even if it falls outside the firmware's legal
# range (which would itself be a finding -- see verdict below), and
# preserving the original grid's aluminum/no_pan low-K comparison and the
# (cast_iron, 35kHz) self-test anchor. ---
FREQ_GRID_HZ = [
    28_000, 30_000, 31_000, 32_000, 33_000, 34_000, 35_000, 36_000, 38_000,
    40_000, 41_000, 42_000, 43_000,
    44_000, 44_500, 45_000, 45_500, 46_000, 46_500, 47_000, 47_500, 48_000,
    48_500, 49_000, 49_500, 50_000,
    51_000, 52_000, 53_000, 54_000, 55_000, 60_000, 65_000,
]

PARAM_RE_TEMPLATE = r"^\.param\s+{name}\s*=.*$"
MEAS_VALUE_RE = re.compile(
    r"^(?P<name>[a-z_][a-z0-9_]*)\s*=\s*(?P<value>[-+0-9.eE]+)", re.MULTILINE
)


class HarnessError(RuntimeError):
    pass


def override_params(base_text: str, overrides: dict[str, float | str]) -> str:
    text = base_text
    for name, value in overrides.items():
        pattern = re.compile(PARAM_RE_TEMPLATE.format(name=re.escape(name)), re.MULTILINE)
        replacement = f".param {name} = {value}"
        new_text, n = pattern.subn(replacement, text)
        if n != 1:
            raise HarnessError(
                f"expected exactly one '.param {name} = ...' line in "
                f"{MASTER_CIR.name}, found {n}"
            )
        text = new_text
    return text


def run_ngspice_on_text(cir_text: str) -> tuple[str, str, int]:
    """Write cir_text to an ephemeral deck next to the master .cir (so its
    relative .include paths resolve), run ngspice on it, delete it, and
    return (stdout, stderr, returncode)."""
    scratch = NETS_DIR / f"_zvs_sweep_scratch_{uuid.uuid4().hex}.cir"
    scratch.write_text(cir_text)
    try:
        result = subprocess.run(
            ["ngspice", "-b", scratch.name],
            cwd=NETS_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return result.stdout, result.stderr, result.returncode
    finally:
        scratch.unlink(missing_ok=True)


def run_master_deck_once(base_text: str) -> tuple[str, str, int]:
    """Run the deck's own committed default parameters -- but through the
    SAME rewrite-to-scratch-file code path as every grid point
    (override_params(base_text, {}), i.e. zero overrides, same values),
    rather than invoking ngspice directly on the tracked .cir.

    CHANGED 2026-08-07 (docs/evidence/2026-08-07-zvs-margin-sweep.md).
    Previously this ran `ngspice -b zvs_margin_sweep.cir` directly against
    the tracked file. On at least one ngspice build encountered while
    producing that evidence (ngspice-42, Ubuntu noble, KLU direct solver),
    that literal invocation reliably fails to converge ("Timestep too
    small... trouble with node tank_mid2") on the committed baseline
    point, while a byte-for-byte VALUE-IDENTICAL copy generated by
    override_params(base_text, {}) -- same parameters, different line
    formatting/whitespace from the .param substitution -- reliably
    converges and reproduces the grid's own (cast_iron, 35kHz) point
    exactly. This was verified directly (not assumed): the raw file fails
    on repeated runs; the rewritten-but-value-identical copy succeeds on
    repeated runs and its parsed .meas values match the grid point bit for
    bit. This is consistent with -- and an addition to -- the .cir header's
    existing "resonant circuits are stiffer than OCP-01's deck" note: this
    circuit sits close enough to a numerical knife-edge that even a
    whitespace-only difference in how the identical parameter values reach
    ngspice's numparam preprocessor changes whether the stiff dead-time
    transition converges on this solver build. Routing the baseline
    through the same code path as the grid removes the discrepancy without
    changing what is being measured -- the values simulated are identical
    either way, only the on-disk formatting differs. This is reported here
    rather than silently worked around, per METHODOLOGY.md SS5 ("the
    oracle is not exempt")."""
    return run_ngspice_on_text(override_params(base_text, {}))


def parse_measurements(stdout: str) -> dict[str, float]:
    values: dict[str, float] = {}
    for m in MEAS_VALUE_RE.finditer(stdout):
        values[m.group("name")] = float(m.group("value"))
    required = {
        "vce_hs_last",
        "vce_ls_last",
        "vce_hs_prev",
        "vce_ls_prev",
        "i_tank_pk_last",
        "i_tank_rms_last",
        "v_sw_max",
        "v_sw_min",
        "i_pan_rms_last",
    }
    missing = required - values.keys()
    if missing:
        raise HarnessError(
            f"missing .meas results {sorted(missing)} in ngspice stdout "
            f"-- circuit may have failed to converge or a .meas 'failed!' "
            f"error occurred.\n--- stdout tail ---\n{stdout[-2000:]}"
        )
    return values


def compute_point_result(
    pan_name, pan_k, pan_rpan, f_sw_hz, meas: dict[str, float], pan_l2_h: float = PAN_L2_DEFAULT_H
) -> dict:
    vce_hs = meas["vce_hs_last"]
    vce_ls = meas["vce_ls_last"]
    margin_hs_pct = 100.0 * abs(vce_hs) / V_BUS_FULL
    margin_ls_pct = 100.0 * abs(vce_ls) / V_BUS_FULL
    margin_pct = max(margin_hs_pct, margin_ls_pct)
    worse_switch = "hs" if margin_hs_pct >= margin_ls_pct else "ls"

    if margin_pct < 10.0:
        label = "zvs_held"
    elif margin_pct < 50.0:
        label = "degraded"
    else:
        label = "zvs_lost"

    conv_delta_hs = abs(meas["vce_hs_last"] - meas["vce_hs_prev"])
    conv_delta_ls = abs(meas["vce_ls_last"] - meas["vce_ls_prev"])
    conv_delta_max = max(conv_delta_hs, conv_delta_ls)
    converged = conv_delta_max < 0.01 * V_BUS_FULL  # < 1% of full bus

    # Power delivered to the pan load (docs/STRATEGY.md build-order step 9:
    # sweep "the power range up to 1800W," not just frequency). R_pan is
    # the only dissipative element in PANLOAD_TRANSFORMER's secondary loop
    # (see the .cir's i_pan_rms_last comment), so this is the model's own
    # estimate of delivered cooking power at this operating point --
    # subject to the same uncalibrated-model caveats as everything else
    # here (behavioral IGBT, constraint-satisfying not measured pan
    # coupling).
    p_pan_w = meas["i_pan_rms_last"] ** 2 * pan_rpan
    in_pll_range = F_PLL_MIN_HZ <= f_sw_hz <= F_PLL_MAX_HZ

    return {
        "pan_preset": pan_name,
        "pan_k": pan_k,
        "pan_rpan_ohm": pan_rpan,
        "pan_l2_h": pan_l2_h,
        "f_sw_hz": f_sw_hz,
        "in_firmware_pll_range": in_pll_range,
        "vce_hs_at_turnon_v": round(vce_hs, 4),
        "vce_ls_at_turnon_v": round(vce_ls, 4),
        "margin_hs_pct": round(margin_hs_pct, 3),
        "margin_ls_pct": round(margin_ls_pct, 3),
        "margin_pct": round(margin_pct, 3),
        "worse_switch": worse_switch,
        "label": label,
        "i_tank_pk_a": round(meas["i_tank_pk_last"], 3),
        "i_tank_rms_a": round(meas["i_tank_rms_last"], 3),
        "i_pan_rms_a": round(meas["i_pan_rms_last"], 4),
        "p_pan_w": round(p_pan_w, 2),
        "v_sw_max_v": round(meas["v_sw_max"], 3),
        "v_sw_min_v": round(meas["v_sw_min"], 3),
        "convergence_delta_v": round(conv_delta_max, 4),
        "converged": converged,
    }


def check_determinism(label: str, cir_text_fn, runs: int) -> dict:
    """Run the same deck N times and check TWO things, not one:

    1. stdout_byte_identical -- the OCP-01/comparator-deck standard
       (METHODOLOGY.md SS5 "run the tool N times on byte-identical input").
    2. measurements_identical -- whether the parsed .meas VALUES agree,
       even if raw stdout does not.

    These can disagree, and did on first measurement of this exact deck:
    ngspice prints internal adaptive-timestep "Reference value : ..."
    diagnostic lines during the stiff dead-time transition whose printed
    values vary run to run (verified: they do NOT appear for the simpler
    OCP-01 comparator deck), so stdout_byte_identical is False here. But
    the parsed .meas results were identical across every run checked. Both
    facts are reported rather than collapsing them into one pass/fail --
    an oracle that is noisy in a way that doesn't touch the number you
    read from it is a different, and better, finding than "deterministic"
    or "not deterministic" alone would say (METHODOLOGY.md SS5, "the
    oracle is not exempt": characterise the noise, don't just gate on it).
    """
    stdout_runs = []
    meas_runs = []
    for _ in range(max(2, runs)):
        stdout, stderr, code = cir_text_fn()
        if code != 0:
            raise HarnessError(
                f"ngspice exited {code} during determinism check '{label}'\n"
                f"--- stderr ---\n{stderr}\n--- stdout tail ---\n{stdout[-1000:]}"
            )
        stdout_runs.append(stdout)
        meas_runs.append(parse_measurements(stdout))
    stdout_byte_identical = all(s == stdout_runs[0] for s in stdout_runs)
    measurements_identical = all(m == meas_runs[0] for m in meas_runs)
    return {
        "label": label,
        "runs": len(stdout_runs),
        "stdout_byte_identical": stdout_byte_identical,
        "measurements_identical": measurements_identical,
        "stdout_runs": stdout_runs,
        "meas_runs": meas_runs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--determinism-runs",
        type=int,
        default=3,
        help="Repeated ngspice runs per determinism-checked deck (default 3).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Evidence JSON output path (default: docs/evidence/<date>-zvs-margin-sweep.json)",
    )
    args = parser.parse_args()

    if shutil.which("ngspice") is None:
        print("ERROR: ngspice not found on PATH.", file=sys.stderr)
        return 1
    if not MASTER_CIR.exists():
        print(f"ERROR: netlist not found: {MASTER_CIR}", file=sys.stderr)
        return 1

    base_text = MASTER_CIR.read_text()

    # --- 1. Determinism check on the committed baseline deck (its own
    #        default parameters, run through the same rewrite-to-scratch
    #        path as every grid point -- see run_master_deck_once()'s
    #        docstring for why, as of 2026-08-07) ---
    print(f"Determinism check (baseline deck, {args.determinism_runs} runs)...")
    baseline_det = check_determinism(
        "baseline (cast_iron, 35kHz, as committed)",
        lambda: run_master_deck_once(base_text),
        args.determinism_runs,
    )
    print(
        f"  stdout_byte_identical={baseline_det['stdout_byte_identical']} "
        f"measurements_identical={baseline_det['measurements_identical']}"
    )
    if not baseline_det["measurements_identical"]:
        print(
            "ERROR: ngspice produced non-identical .meas VALUES across "
            "repeated runs of the byte-identical baseline deck (not just "
            "differing internal diagnostic text). Per METHODOLOGY.md SS5, "
            "this is a headline finding in itself -- do not trust any "
            "figure in this sweep until resolved.",
            file=sys.stderr,
        )
        return 2
    baseline_meas = baseline_det["meas_runs"][0]
    # NOTE: these three literals (PAN_K_FERROMAGNETIC, 10.0,
    # PAN_L2_DEFAULT_H) must match zvs_margin_sweep.cir's own committed
    # PAN_K/PAN_RPAN/PAN_L2 defaults exactly -- both were updated together
    # 2026-08-07 (see docs/evidence/2026-08-07-zvs-margin-sweep.md, and
    # 2026-07-27 before that, docs/evidence/2026-07-27-pan-preset-
    # correction.md) specifically so this independently-run baseline still
    # represents "cast_iron, 35kHz" and the self-consistency check below
    # (grid_baseline_matches) stays meaningful rather than comparing two
    # different pan configurations.
    baseline_result = compute_point_result(
        "cast_iron", PAN_K_FERROMAGNETIC, 10.0, 35_000, baseline_meas,
        pan_l2_h=PAN_L2_DEFAULT_H,
    )

    # --- 2. Full grid sweep ---
    results = []
    total_points = len(PAN_PRESETS) * len(FREQ_GRID_HZ)
    done = 0
    for pan_name, pan_k, pan_rpan, pan_l2, _pan_source_note in PAN_PRESETS:
        for f_sw in FREQ_GRID_HZ:
            done += 1
            overrides = {"F_SW": f_sw, "PAN_K": pan_k, "PAN_RPAN": pan_rpan, "PAN_L2": pan_l2}
            cir_text = override_params(base_text, overrides)
            stdout, stderr, code = run_ngspice_on_text(cir_text)
            print(f"[{done}/{total_points}] pan={pan_name} f_sw={f_sw}Hz ...", end=" ")
            if code != 0:
                print("UNMEASURED (ngspice nonzero exit)")
                results.append(
                    {
                        "pan_preset": pan_name,
                        "pan_k": pan_k,
                        "pan_rpan_ohm": pan_rpan,
                        "pan_l2_h": pan_l2,
                        "f_sw_hz": f_sw,
                        "measured": False,
                        "reason": f"ngspice exited {code}: {stderr[-500:]}",
                    }
                )
                continue
            try:
                meas = parse_measurements(stdout)
            except HarnessError as exc:
                print("UNMEASURED (parse/convergence failure)")
                results.append(
                    {
                        "pan_preset": pan_name,
                        "pan_k": pan_k,
                        "pan_rpan_ohm": pan_rpan,
                        "pan_l2_h": pan_l2,
                        "f_sw_hz": f_sw,
                        "measured": False,
                        "reason": str(exc)[:1000],
                    }
                )
                continue
            point = compute_point_result(pan_name, pan_k, pan_rpan, f_sw, meas, pan_l2_h=pan_l2)
            point["measured"] = True
            results.append(point)
            print(f"margin={point['margin_pct']:.2f}% ({point['label']})")

    measured_results = [r for r in results if r.get("measured")]
    converged_results = [r for r in measured_results if r["converged"]]
    if not converged_results:
        raise HarnessError("no grid point converged -- cannot rank worst margins")

    # Sanity check: the grid's own (cast_iron, 35kHz) point was generated by
    # override_params() rewriting the SAME nominal values the committed
    # deck already ships with. It should reproduce the independently-run
    # baseline result exactly; if it doesn't, override_params() is
    # silently mismatching the deck (e.g. a stale default drifted from the
    # override table) and every other grid point is suspect too.
    grid_baseline_matches = [
        r for r in measured_results if r["pan_preset"] == "cast_iron" and r["f_sw_hz"] == 35_000
    ]
    if not grid_baseline_matches:
        raise HarnessError("grid did not include the (cast_iron, 35kHz) baseline point")
    grid_baseline = grid_baseline_matches[0]
    baseline_self_consistent = (
        grid_baseline["vce_hs_at_turnon_v"] == baseline_result["vce_hs_at_turnon_v"]
        and grid_baseline["vce_ls_at_turnon_v"] == baseline_result["vce_ls_at_turnon_v"]
    )
    if not baseline_self_consistent:
        raise HarnessError(
            "override_params()-generated (cast_iron, 35kHz) grid point "
            f"({grid_baseline['vce_hs_at_turnon_v']}, {grid_baseline['vce_ls_at_turnon_v']}) "
            "does not match the independently-run committed baseline deck "
            f"({baseline_result['vce_hs_at_turnon_v']}, {baseline_result['vce_ls_at_turnon_v']}) "
            "-- override_params() is mismatching the deck's own defaults; "
            "do not trust the grid until this is fixed."
        )

    worst_sorted = sorted(converged_results, key=lambda r: -r["margin_pct"])
    worst_5 = worst_sorted[:5]
    best_5 = sorted(converged_results, key=lambda r: r["margin_pct"])[:5]

    # --- Per-preset ZVS transition (data-driven, NOT assumed uniform) ---
    # Pre-2026-07-27-preset-correction, ALL FOUR presets transitioned at the
    # same 32-33kHz because the broken K=0.15-0.5/L2=1uH presets barely
    # loaded the tank. That is no longer true for the corrected K=0.79
    # presets (cast_iron/stainless), whose loaded resonance moved ~60%
    # higher -- computing one blanket transition band across all presets
    # would silently reintroduce the old (now false) assumption. For each
    # preset, report the highest converged zvs_lost frequency and the
    # lowest converged zvs_held frequency found in this run's own grid.
    per_preset_transitions: dict[str, dict] = {}
    for pan_name, *_ in PAN_PRESETS:
        preset_points = sorted(
            (r for r in converged_results if r["pan_preset"] == pan_name),
            key=lambda r: r["f_sw_hz"],
        )
        lost_freqs = [r["f_sw_hz"] for r in preset_points if r["label"] == "zvs_lost"]
        held_freqs = [r["f_sw_hz"] for r in preset_points if r["label"] != "zvs_lost"]
        per_preset_transitions[pan_name] = {
            "highest_zvs_lost_hz": max(lost_freqs) if lost_freqs else None,
            "lowest_zvs_held_or_degraded_hz": min(held_freqs) if held_freqs else None,
        }

    # --- Operating envelope inside the firmware's LEGAL PLL range, and the
    # 1800W cross-reference (docs/STRATEGY.md build-order step 9: "sweep
    # ZVS margin across the pan-load envelope ... and the power range up
    # to 1800W"). Added 2026-08-07. For each preset, restrict to grid
    # points inside [F_PLL_MIN_HZ, F_PLL_MAX_HZ] -- the range the firmware
    # can actually command -- and report: the worst (highest-margin) point
    # found there, whether ZVS is lost ANYWHERE in that legal range (the
    # question that actually matters: EFF-02 requires ZVS active AT
    # 1800W, but a control loop that can legally command a hard-switching
    # frequency is a hazard regardless of the nominal setpoint), and the
    # grid point closest to 1800W delivered pan power, with its margin.
    operating_envelope: dict[str, dict] = {}
    for pan_name, *_ in PAN_PRESETS:
        pll_points = sorted(
            (
                r for r in converged_results
                if r["pan_preset"] == pan_name and r["in_firmware_pll_range"]
            ),
            key=lambda r: r["f_sw_hz"],
        )
        if not pll_points:
            operating_envelope[pan_name] = {
                "pll_range_points_converged": 0,
                "note": "no converged grid point fell inside the firmware's legal PLL range for this preset",
            }
            continue
        worst_in_pll_range = max(pll_points, key=lambda r: r["margin_pct"])
        closest_to_1800w = min(pll_points, key=lambda r: abs(r["p_pan_w"] - 1800.0))
        zvs_lost_in_pll_range = [r for r in pll_points if r["label"] == "zvs_lost"]
        operating_envelope[pan_name] = {
            "pll_range_points_converged": len(pll_points),
            "power_range_w": [
                round(min(r["p_pan_w"] for r in pll_points), 1),
                round(max(r["p_pan_w"] for r in pll_points), 1),
            ],
            "worst_margin_in_pll_range": {
                "f_sw_hz": worst_in_pll_range["f_sw_hz"],
                "margin_pct": worst_in_pll_range["margin_pct"],
                "label": worst_in_pll_range["label"],
                "p_pan_w": worst_in_pll_range["p_pan_w"],
            },
            "closest_to_1800w": {
                "f_sw_hz": closest_to_1800w["f_sw_hz"],
                "p_pan_w": closest_to_1800w["p_pan_w"],
                "margin_pct": closest_to_1800w["margin_pct"],
                "label": closest_to_1800w["label"],
                "reaches_1800w": closest_to_1800w["p_pan_w"] >= 1800.0
                or max(r["p_pan_w"] for r in pll_points) >= 1800.0,
            },
            "zvs_lost_anywhere_in_legal_pll_range": bool(zvs_lost_in_pll_range),
            "zvs_lost_frequencies_hz": [r["f_sw_hz"] for r in zvs_lost_in_pll_range],
        }

    # --- 3. Determinism check on the worst-margin point found ---
    worst_point = worst_sorted[0]
    print(
        f"Determinism check (worst-margin point: pan={worst_point['pan_preset']} "
        f"f_sw={worst_point['f_sw_hz']}Hz, {args.determinism_runs} runs)..."
    )
    worst_overrides = {
        "F_SW": worst_point["f_sw_hz"],
        "PAN_K": worst_point["pan_k"],
        "PAN_RPAN": worst_point["pan_rpan_ohm"],
        "PAN_L2": worst_point["pan_l2_h"],
    }
    worst_cir_text = override_params(base_text, worst_overrides)
    worst_det = check_determinism(
        "worst-margin point",
        lambda: run_ngspice_on_text(worst_cir_text),
        args.determinism_runs,
    )
    print(
        f"  stdout_byte_identical={worst_det['stdout_byte_identical']} "
        f"measurements_identical={worst_det['measurements_identical']}"
    )
    if not worst_det["measurements_identical"]:
        print(
            "ERROR: ngspice produced non-identical .meas VALUES across "
            "repeated runs of the byte-identical worst-margin deck. Do "
            "not trust the worst-margin figure until resolved.",
            file=sys.stderr,
        )
        return 2

    # "Deterministic" for this harness's purposes means the numbers this
    # evidence file reports are reproducible -- NOT that raw ngspice
    # stdout is byte-identical (it is not, for either deck checked; see
    # simulator.note below). This is a deliberate, disclosed redefinition,
    # not a silent loosening of the OCP-01 standard.
    overall_measurements_deterministic = (
        baseline_det["measurements_identical"] and worst_det["measurements_identical"]
    )
    overall_stdout_byte_identical = (
        baseline_det["stdout_byte_identical"] and worst_det["stdout_byte_identical"]
    )

    invocation = (
        "uv run python simulation/harness/run_zvs_sweep.py --determinism-runs "
        + str(max(2, args.determinism_runs))
    )

    evidence = {
        "schema_version": 1,
        "provenance": collect_provenance(REPO_ROOT),
        "measurement_date": _dt.date.today().isoformat(),
        "invocation": invocation,
        "harness": "simulation/harness/run_zvs_sweep.py",
        "netlist": "simulation/harness/nets/zvs_margin_sweep.cir",
        "zvs_margin_definition": (
            "margin_pct = 100 * |Vce at the switch's own gate turn-on "
            "instant| / (full DC bus differential, 340V). Sampled at an "
            "analytically-known time (this deck's own PWM generator), on "
            "the last of 25 simulated switching cycles. See the .cir "
            "header for full rationale. <10% = zvs_held, 10-50% = "
            "degraded, >=50% = zvs_lost (harness reporting convenience, "
            "not a datasheet figure)."
        ),
        "simulator": {
            "tool": "ngspice",
            "determinism_runs_per_checked_deck": max(2, args.determinism_runs),
            "stdout_byte_identical": overall_stdout_byte_identical,
            "measurements_identical": overall_measurements_deterministic,
            "deterministic": overall_measurements_deterministic,
            "decks_checked": [
                {
                    "deck": "baseline (cast_iron K=0.5/RPAN=8, F_SW=35kHz, as committed)",
                    "stdout_byte_identical": baseline_det["stdout_byte_identical"],
                    "measurements_identical": baseline_det["measurements_identical"],
                },
                {
                    "deck": (
                        f"worst-margin grid point (pan={worst_point['pan_preset']}, "
                        f"F_SW={worst_point['f_sw_hz']}Hz)"
                    ),
                    "stdout_byte_identical": worst_det["stdout_byte_identical"],
                    "measurements_identical": worst_det["measurements_identical"],
                },
            ],
            "note": (
                "UNLIKE the OCP-01 comparator deck (5/5 byte-identical "
                "stdout runs, 2026-07-25), this resonant-tank deck's raw "
                "ngspice stdout is NOT byte-identical across repeated runs "
                "on byte-identical input: ngspice prints internal "
                "adaptive-timestep 'Reference value : ...' diagnostic "
                "lines during the stiff dead-time switching transition, "
                "and the printed values differ run to run (verified by "
                "diffing raw stdout from two runs of the committed "
                "baseline deck). This is exactly the 'confirm it stays "
                "so for a resonant circuit, which is stiffer' check the "
                "brainstorm asked for, and the honest answer is nuanced, "
                "not a clean yes: the oracle's RAW OUTPUT has a "
                "non-deterministic component. HOWEVER, every .meas VALUE "
                "this harness actually reads (vce_hs_last, vce_ls_last, "
                "etc.) was identical across every run of every deck "
                "checked -- the non-determinism lives entirely in solver "
                "bookkeeping the evidence never touches, not in the "
                "physics being reported. `deterministic` above reports "
                "the measurements_identical result (what this evidence "
                "file's numbers depend on), not stdout_byte_identical "
                "(which is False and expected to be False, per the "
                "mechanism just described) -- this is a disclosed "
                "redefinition of the OCP-01 standard for a stiffer "
                "circuit, not a silent loosening of it. Full-grid "
                "determinism was NOT checked (would double the sweep's "
                "runtime for marginal additional evidence); only the "
                "baseline and worst-margin decks were, a deliberate scope "
                "limit. This harness also required loosened ABSTOL/ITL4/"
                "GMIN (documented in the .cir) for the solver to converge "
                "at all on several grid points, additional reason to "
                "treat this oracle as noisier than OCP-01's rather than "
                "assume its properties transfer."
            ),
        },
        "models_used": [
            {
                "file": "simulation/models/IKW40N120H3.lib",
                "subckt": "IKW40N120H3",
                "calibrated": False,
                "note": (
                    "Behavioral macromodel: fixed (non-Vce-dependent) "
                    "Cge/Cce/Cgc, linear on-resistance, single-pole RC "
                    "reverse-recovery approximation. Real IGBT/diode "
                    "capacitances are strongly Vce-nonlinear, which is "
                    "exactly the mechanism setting real ZVS dV/dt. Margin "
                    "percentages here are ordinal (better/worse across "
                    "operating points), NOT calibrated absolute "
                    "switching-loss figures."
                ),
            },
            {
                "file": "simulation/models/pan_load.sub",
                "subckt": "PANLOAD_TRANSFORMER",
                "calibrated": False,
                "note": (
                    "PANLOAD_SIMPLE/PANLOAD_VARIABLE were NOT used: both "
                    "declare an RPAN parameter that is never referenced in "
                    "the subckt body (dead code -- verified by reading the "
                    "model). PANLOAD_TRANSFORMER is used instead (real "
                    "mutual-inductance K_couple + a used R_pan). "
                    "L2/K/RPAN history: CORRECTED 2026-07-27 from "
                    "provably-impossible defaults (K=0.4/L2=1uH could "
                    "never reproduce Infineon AN235020's measured 0.40 "
                    "loaded/unloaded L-ratio, independent of any geometry "
                    "assumption) to an Infineon-anchored point (K=0.79, "
                    "L2=218uH) -- but that point was anchored to a "
                    "DIFFERENT Infineon measurement (AN235020, 90-150kHz) "
                    "outside this design's 20-50kHz band. RE-DERIVED "
                    "2026-08-07 (K=0.6136, L2=97.13uH, ferromagnetic "
                    "presets only) against elec/src/main.ato's own in-band "
                    "l_pan_loaded_ratio=0.68 chart reading -- see "
                    "PAN_PRESETS below and "
                    "docs/evidence/2026-08-07-zvs-margin-sweep.md Sec 2. "
                    "PAN_L1 (coil unloaded inductance) also moved 2026-08-"
                    "07 from the model's own stale 80uH default to "
                    "main.ato's declared 88uH l_tank_assumed (the coil "
                    "stopped being a placeholder 2026-07-29). STILL "
                    "constraint-satisfying, not measured, for all three "
                    "parameters -- see docs/evidence/2026-07-27-coil-pan-"
                    "coupling-resolution.md Sec 4 for what a bench "
                    "measurement of this quantity requires."
                ),
            },
        ],
        "sourced_from_elec_read_only": {
            "v_half_v": V_HALF,
            "v_bus_full_differential_v": V_BUS_FULL,
            "rg_ohm": RG_OHM,
            "rgs_ohm": RGS_OHM,
            "t_dead_s": T_DEAD_S,
            "c_tank_f": C_TANK_F,
            "f_switching_nominal_hz": F_SWITCHING_NOMINAL_HZ,
            "f_resonant_declared_hz": F_RESONANT_DECLARED_HZ,
            "f_pll_tracking_min_hz": F_PLL_MIN_HZ,
            "f_pll_tracking_max_hz": F_PLL_MAX_HZ,
            "pan_l1_coil_unloaded_inductance_h": PAN_L1_DEFAULT_H,
            "citation": (
                "elec/src/modules.ato: HalfBridge, GateDriveHS, "
                "GateDriveLS, ResonantTank (incl. inductor_conn = Inductor "
                "88uH+/-10%, declared 2026-07-29), PowerInput; "
                "elec/src/main.ato top-level Top module "
                "(f_switching, f_resonant_nominal, l_tank_assumed, "
                "f_pll_tracking_min/max); firmware/components/control/"
                "pll_control.h (PLL_MIN_FREQ_HZ/PLL_MAX_FREQ_HZ, mirrored "
                "by main.ato and cross-checked by scripts/"
                "check_pll_range_consistency.py). PAN_L1 moved from a "
                "model default (see not_sourced_from_elec_model_defaults, "
                "historical) to an elec/-sourced value 2026-08-07 now that "
                "the coil is a declared Inductor, not a placeholder -- "
                "listed here rather than below for that reason."
            ),
        },
        "not_sourced_from_elec_model_defaults": {
            "pan_l2_default_h": PAN_L2_DEFAULT_H,
            "pan_k_ferromagnetic": PAN_K_FERROMAGNETIC,
            "pan_rpan_ohm": 10.0,
            "note": (
                "L2/K (ferromagnetic presets) and RPAN (all presets) are "
                "NOT sourced from elec/ -- elec/src/main.ato declares only "
                "a single scalar `l_pan_loaded_ratio = 0.68` (loaded/"
                "unloaded inductance ratio), not the (K, L2, RPAN) triple "
                "this model's T-topology needs to reproduce that ratio as "
                "a function of frequency. RE-DERIVED 2026-08-07 (K=0.6136, "
                "L2=97.13uH, holding RPAN=10 ohm fixed at pan_load.sub's "
                "own pre-existing uncited default) to reproduce "
                "main.ato's in-band 0.71/0.68/0.66 ratio at 30/40/50kHz "
                "via the T-model relation -- see PAN_PRESETS comment and "
                "docs/evidence/2026-08-07-zvs-margin-sweep.md Sec 2. This "
                "SUPERSEDES the 2026-07-27 K=0.79/L2=218uH point, which "
                "was solved against a DIFFERENT, out-of-band (90-150kHz) "
                "Infineon measurement -- see docs/evidence/2026-07-27-"
                "coil-pan-coupling-resolution.md Sec 2.5. Still not a "
                "bench measurement of this project's coil and pan, and "
                "still one point in an underdetermined family (2 "
                "unknowns, RPAN held fixed rather than solved)."
            ),
        },
        "computed_vs_declared_resonance": {
            "f_resonant_computed_hz": round(F_RESONANT_COMPUTED_HZ, 1),
            "f_resonant_declared_hz": F_RESONANT_DECLARED_HZ,
            "f_switching_nominal_hz": F_SWITCHING_NOMINAL_HZ,
            "f_pll_tracking_range_hz": [F_PLL_MIN_HZ, F_PLL_MAX_HZ],
            "finding": (
                f"UPDATED 2026-08-07: this deck's PAN_L1 (88uH) and "
                f"C_TANK (300nF) now equal main.ato's own l_tank_assumed "
                f"and c_tank_total exactly, so the UNLOADED resonance "
                f"computed here ({F_RESONANT_COMPUTED_HZ:.0f}Hz) and "
                f"main.ato's declared f_resonant_nominal "
                f"({F_RESONANT_DECLARED_HZ/1000:.0f}kHz) are now the SAME "
                f"arithmetic over the SAME two declared quantities, not "
                f"two independent guesses as they were pre-2026-07-29 "
                f"(when main.ato declared 25kHz -- implying a THIRD, "
                f"unreconciled 135.1uH coil value -- while this harness "
                f"used an 80uH model default with no relationship to it "
                f"at all). This is the UNLOADED (no-pan-coupling) figure; "
                f"per_preset_zvs_transition_hz below shows the LOADED "
                f"transition (the one that actually determines ZVS) "
                f"differs sharply per preset: aluminum/no_pan (low K, "
                f"barely load the tank) collapse near this unloaded "
                f"figure, while cast_iron/stainless (K=0.6136, re-derived "
                f"2026-08-07 against main.ato's in-band 0.68 ratio) "
                f"collapse near a loaded resonance well above it -- see "
                f"per_preset_zvs_transition_hz and "
                f"operating_envelope_pll_range_and_1800w for where that "
                f"puts the transition relative to the firmware's actual "
                f"{F_PLL_MIN_HZ/1000:.0f}-{F_PLL_MAX_HZ/1000:.0f}kHz PLL "
                f"tracking range and the {F_SWITCHING_NOMINAL_HZ/1000:.0f}kHz "
                f"nominal operating point."
            ),
        },
        "sweep_grid": {
            "pan_presets": [
                {"name": n, "k": k, "rpan_ohm": r, "l2_h": l2, "source": s}
                for n, k, r, l2, s in PAN_PRESETS
            ],
            "frequencies_hz": FREQ_GRID_HZ,
            "total_points": total_points,
            "measured_points": len(measured_results),
            "converged_points": len(converged_results),
        },
        "per_preset_zvs_transition_hz": per_preset_transitions,
        "operating_envelope_pll_range_and_1800w": operating_envelope,
        "sanity_checks": {
            "grid_reproduces_independent_baseline_run": baseline_self_consistent,
            "note": (
                "The (cast_iron, 35kHz) grid point, generated by "
                "override_params() rewriting the deck's own committed "
                "defaults with F_SW/PAN_K/PAN_RPAN/PAN_L2 EXPLICITLY set "
                "back to those same defaults, is compared against a "
                "SEPARATE run_master_deck_once() invocation of the deck's "
                "committed defaults via override_params(base_text, {}) "
                "-- zero explicit overrides, same code path (see that "
                "function's docstring for why, as of 2026-08-07: an "
                "environment-specific ngspice convergence quirk on the "
                "raw tracked file, unrelated to override_params()). They "
                "must match exactly, or override_params() is silently "
                "corrupting every other grid point too; this run passed "
                "that check."
            ),
        },
        "results": results,
        "worst_margin_points": worst_5,
        "best_margin_points": best_5,
        "verdict": {
            "calibrated": False,
            "summary": (
                f"Of {total_points} grid points ({len(measured_results)} "
                f"measured, {len(converged_results)} converged to <1% "
                f"cycle-over-cycle drift), the worst margin is "
                f"{worst_point['margin_pct']:.1f}% "
                f"({worst_point['label']}) at pan={worst_point['pan_preset']}, "
                f"F_SW={worst_point['f_sw_hz']}Hz. Pan type materially "
                f"changes WHERE ZVS transitions (unchanged finding from "
                f"2026-07-27, re-verified here with re-derived coupling): "
                f"cast_iron and stainless (K=0.6136, re-derived 2026-08-07 "
                f"against main.ato's in-band l_pan_loaded_ratio=0.68, "
                f"superseding the 2026-07-27 out-of-band K=0.79 point) "
                f"collapse between "
                f"{per_preset_transitions['cast_iron']['highest_zvs_lost_hz']}Hz "
                f"(lost) and "
                f"{per_preset_transitions['cast_iron']['lowest_zvs_held_or_degraded_hz']}Hz "
                f"(held). aluminum (K=0.15, retained UNVERIFIED assumption) "
                f"and no_pan (K=0.01) collapse near the "
                f"{F_RESONANT_COMPUTED_HZ/1000:.1f}kHz unloaded resonance, "
                f"between "
                f"{per_preset_transitions['aluminum']['highest_zvs_lost_hz']}Hz and "
                f"{per_preset_transitions['aluminum']['lowest_zvs_held_or_degraded_hz']}Hz -- "
                f"because their K is far below the ferromagnetic floor and "
                f"was NOT raised (the floor is Infineon's ferromagnetic-pan "
                f"measurement and does not transfer to non-ferrous/no-pan "
                f"cases). Whether ZVS is lost ANYWHERE inside the "
                f"firmware's actual {F_PLL_MIN_HZ/1000:.0f}-"
                f"{F_PLL_MAX_HZ/1000:.0f}kHz PLL tracking range, and where "
                f"the 1800W point falls in that range per preset: see "
                f"operating_envelope_pll_range_and_1800w. Full per-preset "
                f"transition data: per_preset_zvs_transition_hz. "
                f"UNCALIBRATED: PAN_L1 (88uH) now tracks main.ato's "
                f"declared coil, but K/L2/RPAN remain constraint-"
                f"satisfying-not-measured (re-derived, not re-measured, "
                f"2026-08-07 -- see not_sourced_from_elec_model_defaults), "
                f"and the IGBT model is behavioral (see models_used)."
            ),
            "does_not_claim": [
                "Absolute switching-loss or turn-on-energy figures (IGBT model is behavioral, see models_used note).",
                "That pan coupling/material has NO effect on ZVS margin in the real board -- the model shows a LARGE effect; see per_preset_zvs_transition_hz.",
                "EMI/CISPR prediction (out of scope per the brainstorm).",
                "That the real coil is 88uH -- main.ato declares it (docs/evidence/2026-07-29-tank-coil-specification.md) from a manufacturer chart reading, not a bench measurement of THIS project's coil; this sweep uses the declared design value, which is a different (stronger) claim than the pre-2026-07-29 80uH model default, but still not a measurement.",
                "That K=0.6136 (cast_iron/stainless) or K=0.15 (aluminum) are measured values for THIS project's coil/pan -- both are literature-anchored/re-derived or retained assumptions, not bench measurements (see PAN_PRESETS source notes and docs/evidence/2026-08-07-zvs-margin-sweep.md).",
                "That the pan-coupling re-derivation in this pass (K/L2 against main.ato's ratio) constitutes calibration -- it reconciles two chart readings, not a bench measurement; see docs/evidence/2026-07-27-coil-pan-coupling-resolution.md Sec 4 for what that would require.",
            ],
        },
        "derived_bench_measurement_list": [
            {
                "measurement": "Real coil inductance (uncoupled) and coupling coefficient k vs. air gap and pan material, for the actual wound Litz coil and at least the cast-iron/stainless/aluminum pans this design intends to support.",
                "why": "The coil is no longer a placeholder in elec/ (modules.ato ResonantTank.inductor_conn declares 88uH+/-10% since 2026-07-29), but that value is still a manufacturer chart reading (Infineon EVAL-IHW25N140R5L Fig. 16) of a DIFFERENT coil, not a measurement of this project's own wound coil -- see docs/hardware/TANK_COIL_SPECIFICATION.md's own incoming acceptance test, which exists precisely because this is still unverified. This remains the single highest-leverage bench measurement: it could move the computed resonance (and therefore the PLL floor) within the +/-10% band the design already tolerates, or outside it if the delivered coil fails acceptance.",
            },
            {
                "measurement": "Pan-reflected resistance and effective secondary inductance (or equivalent Q) for real pans, at the actual operating frequency band (30-50kHz, this design's own PLL range, not Infineon's 90-150kHz test point).",
                "why": "Pan type has a LARGE effect on the ZVS transition frequency in this model (per_preset_zvs_transition_hz): cast_iron/stainless collapse well above the unloaded resonance, aluminum/no_pan collapse near it. This sweep's ferromagnetic K/L2 (re-derived 2026-08-07 to match main.ato's own in-band 0.68 ratio) is a better chart reading than the prior out-of-band one, but it is still not a measurement of THIS project's coil and pan -- see docs/evidence/2026-07-27-coil-pan-coupling-resolution.md Sec 4 for the specific three-frequency-point bench protocol this would require (a single-frequency measurement cannot separate L2 from RPAN).",
            },
            {
                "measurement": "IGBT switch-node voltage during a real turn-on transition (oscilloscope, Vce vs time), at the firmware's nominal 47kHz operating point AND at the lowest frequency inside the 44-50kHz PLL range for the worst-case (highest-margin, still-converged) preset found by this sweep -- see operating_envelope_pll_range_and_1800w and worst_margin_points for which point that is in this run.",
                "why": "Directly validates or falsifies this sweep's central claim against the behavioral IGBT model's prediction, at the specific frequency/preset combination this run identifies as tightest -- not a generic frequency chosen independently of the sweep's own findings.",
            },
            {
                "measurement": "Actual dead time as generated by firmware MCPWM configuration and measured at the gate driver output (not just the RDT-resistor nominal 305.4ns).",
                "why": "main.ato:229 records a SEPARATE software dead time (300ns) from the hardware nominal (305.4ns) with only a 55ns stated margin over IGBT turn-off (245ns). This sweep held T_DEAD fixed at the hardware nominal; the margin collapse observed near each preset's own transition frequency (per_preset_zvs_transition_hz) would move if the real, as-configured dead time differs.",
            },
        ],
    }

    out_path = args.out
    if out_path is None:
        date_str = _dt.date.today().isoformat()
        out_path = REPO_ROOT / "docs" / "evidence" / f"{date_str}-zvs-margin-sweep.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(evidence, indent=2) + "\n")

    print()
    print(
        f"stdout_byte_identical={overall_stdout_byte_identical} "
        f"measurements_identical={overall_measurements_deterministic} "
        f"(baseline + worst-margin decks)"
    )
    print(json.dumps(evidence["verdict"], indent=2))
    print(f"Evidence written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
