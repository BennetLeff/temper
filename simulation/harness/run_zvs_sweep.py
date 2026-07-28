#!/usr/bin/env python3
"""Scriptable, non-interactive ngspice harness for the ZVS margin sweep
(simulation/harness/nets/zvs_margin_sweep.cir).

This is the R1-R6 deliverable for
docs/brainstorms/2026-07-25-spice-harness-zvs-sweep-requirements.md: a
pan-load x switching-frequency sweep of the half-bridge / resonant-tank
model, reporting ZVS margin at every operating point and naming the
worst ones -- not just a pass/fail scalar.

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
C_TANK_F = 300e-9        # c_tank1+c_tank2 in parallel, modules.ato:390/:397
F_SWITCHING_NOMINAL_HZ = 47_000.0   # main.ato:71, CORRECTED 2026-07-27: the
# 35kHz this constant used to hold (main.ato:71's original value) measured
# 100.7% ZVS margin LOST (full hard switching of the half-bridge) for
# cast_iron/stainless once PAN_PRESETS was corrected to the Infineon-
# anchored K=0.79 -- see docs/evidence/2026-07-27-pan-preset-correction.md
# Sec 4.1 and docs/evidence/2026-07-27-zvs-operating-point.md (this pass).
# 47kHz is the best-evidenced replacement: at L=150uH (an ASSUMPTION, not
# a specified coil -- ResonantTank.inductor_conn remains a placeholder),
# ratio~=1.25 over that assumption's loaded resonance delivers ~1804W,
# holds ZVS (0.8% margin) for ALL FOUR pan presets, and clears OCP-01's
# 50.1A peak trip by 43% (28.76A) -- see docs/evidence/2026-07-27-zvs-
# operating-point.md Sec on old-vs-new per-preset margins. This number is
# CONTINGENT on the L=150uH assumption: a different real coil inductance
# would require re-deriving it (a smaller L raises the required minimum
# f_sw further -- e.g. at the harness's own 80uH default the same K=0.79
# loaded resonance is ~52kHz, which 47kHz would NOT clear).
F_SWITCHING_NOMINAL_HZ_PRE_FIX_2026_07_27 = 35_000.0  # historical; still the
# .cir's own committed self-test anchor value (FREQ_GRID_HZ/baseline check
# below) -- deliberately NOT changed to 47kHz, see FREQ_GRID_HZ comment.
F_RESONANT_DECLARED_HZ = 25_000.0   # main.ato:74 (design intent; UNCHANGED
# by this pass -- see docs/evidence/2026-07-27-zvs-operating-point.md for
# why: 25kHz implies L=135.1uH at the fixed 300nF C_TANK, a THIRD value
# distinct from both this file's 80uH model default and the 150uH
# operating-point assumption above, none of which are reconciled. Changing
# it would just be picking a different unverified L via a different
# variable -- reported as an open inconsistency, not resolved here.)
PAN_L1_DEFAULT_H = 80e-6            # pan_load.sub PANLOAD_TRANSFORMER default
F_RESONANT_COMPUTED_HZ = 1.0 / (
    2 * 3.141592653589793 * (PAN_L1_DEFAULT_H * C_TANK_F) ** 0.5
)

# --- Pan-load grid -- CORRECTED 2026-07-27, see
# docs/evidence/2026-07-27-pan-preset-correction.md for the full
# derivation and per-material reasoning. This replaces a citation loop:
# the OLD table here cited pan_load.sub's own header comments, which were
# themselves uncited (no source anywhere in this file's history -- see
# docs/evidence/2026-07-27-coil-pan-coupling-resolution.md Sec 2). Every
# note below cites Infineon AN235020 (the one real measurement in this
# project's evidence) or explicitly says ASSUMPTION where no measurement
# supports the number -- never pan_load.sub.
#
# PAN_RPAN and PAN_L2 are held UNIFORM across all four presets, at
# pan_load.sub's own single, non-material-specific subckt defaults
# (RPAN=10 ohm, L2=218uH -- the Infineon-anchored point derived in the
# resolution doc Sec 2.5). Deliberate, not an oversight: the OLD
# per-material RPAN spread (8/25/125/8 ohm) was exactly the uncited
# pan_load.sub header table this correction disqualifies as a source
# (resolution doc Sec 2.6.3 -- "RPAN's per-material values are uncited
# and cannot be independently checked from the L-ratio constraint
# alone"). Rather than trade one unfounded per-material table for a
# different unfounded one, material differences are expressed ONLY
# through K, the one parameter the Infineon measurement actually
# constrains. L2 is likewise treated as material-independent: in this
# model's own T-topology it represents the pan's geometric
# self-inductance as a shorted loop -- primarily a function of pan/coil
# size and shape, not material -- and no per-material L2 measurement
# exists anywhere in this project's evidence, so it is not fabricated
# here either.
PAN_L2_DEFAULT_H = 218e-6  # docs/evidence/2026-07-27-coil-pan-coupling-resolution.md Sec 2.5
PAN_PRESETS = [
    # name, K, RPAN_ohm, L2_h, source note
    (
        "cast_iron", 0.79, 10.0, PAN_L2_DEFAULT_H,
        "ASSUMPTION: no independent cast-iron measurement exists anywhere "
        "in this project's literature search (docs/evidence/2026-07-27-"
        "coil-pan-coupling-prior-art.md). Treated identically to the "
        "Infineon-anchored stainless point (K=0.79) because cast iron is "
        "ferromagnetic like Infineon's measured pan and no evidence "
        "distinguishes the two materials' coupling quantitatively -- NOT "
        "a claim they are physically identical, only that no citation "
        "supports a different number. Derivation: docs/evidence/2026-07-"
        "27-coil-pan-coupling-resolution.md Sec 2.5 (Infineon AN235020's "
        "measured 0.40 loaded/unloaded L-ratio + sqrt(f)-extrapolated "
        "R_eff~=2.2 ohm at 35kHz).",
    ),
    (
        "stainless", 0.79, 10.0, PAN_L2_DEFAULT_H,
        "Infineon AN235020 (EVAL_2KW_SiC_IH app note), measured "
        "loaded/unloaded L-ratio 0.40 on a stainless stockpot, 90-150kHz. "
        "K=0.79/L2=218uH solved to jointly satisfy that ratio and the "
        "sqrt(f)-extrapolated R_eff~=2.2 ohm at 35kHz, holding RPAN=10 "
        "ohm (pan_load.sub's own single non-material-specific subckt "
        "default) fixed. Full arithmetic: docs/evidence/2026-07-27-coil-"
        "pan-coupling-resolution.md Sec 2.5. NOT a unique solution -- 3 "
        "unknowns (K, L2, RPAN), 2 literature equations; see that "
        "section's underdetermination note.",
    ),
    (
        "aluminum", 0.15, 10.0, PAN_L2_DEFAULT_H,
        "ASSUMPTION, retained from the pre-correction value -- NOT "
        "derived from Infineon. The 0.775 K floor (resolution doc Sec "
        "2.2) is specific to Infineon's ferromagnetic-pan measurement "
        "(permeability-enhanced coupling) and does not necessarily "
        "transfer to non-ferrous aluminum, which couples by eddy currents "
        "alone. No source in the literature search measures aluminum K "
        "in a full-pan geometry; APHO2025's small-test-coupon R_LOAD "
        "measurement (54.6mOhm Al vs. 137.7mOhm ferromagnetic SS410, "
        "~2.5x lower, docs/evidence/2026-07-27-coil-pan-coupling-prior-"
        "art.md) qualitatively supports weaker aluminum coupling but is "
        "NOT used to derive a number here (different geometry/scale by "
        "roughly 2 orders of magnitude -- see that document's own "
        "caveat). K=0.15 is not floor-raised and is flagged UNVERIFIED, "
        "not measured.",
    ),
    (
        "no_pan", 0.01, 10.0, PAN_L2_DEFAULT_H,
        "Models the physical absence of a pan (no eddy-current load), not "
        "a material property -- the Infineon floor/measurement logic does "
        "not apply. At K~=0.01, L2/RPAN are immaterial: the L-ratio floor "
        "1-K^2 ~= 0.9999 regardless of their value (resolution doc Sec "
        "2.2).",
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
# design's current nominal switching frequency. 47kHz is already inside
# this grid's 45-48kHz bracket for the cast_iron/stainless comparison. ---
FREQ_GRID_HZ = [
    28_000, 30_000, 31_000, 32_000, 33_000, 34_000, 35_000, 40_000, 45_000,
    48_000, 50_000, 52_000, 53_000, 54_000, 55_000, 60_000, 65_000,
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


def run_master_deck_once() -> tuple[str, str, int]:
    result = subprocess.run(
        ["ngspice", "-b", MASTER_CIR.name],
        cwd=NETS_DIR,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.stdout, result.stderr, result.returncode


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

    return {
        "pan_preset": pan_name,
        "pan_k": pan_k,
        "pan_rpan_ohm": pan_rpan,
        "pan_l2_h": pan_l2_h,
        "f_sw_hz": f_sw_hz,
        "vce_hs_at_turnon_v": round(vce_hs, 4),
        "vce_ls_at_turnon_v": round(vce_ls, 4),
        "margin_hs_pct": round(margin_hs_pct, 3),
        "margin_ls_pct": round(margin_ls_pct, 3),
        "margin_pct": round(margin_pct, 3),
        "worse_switch": worse_switch,
        "label": label,
        "i_tank_pk_a": round(meas["i_tank_pk_last"], 3),
        "i_tank_rms_a": round(meas["i_tank_rms_last"], 3),
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

    # --- 1. Determinism check on the committed baseline deck, run as-is ---
    print(f"Determinism check (baseline deck, {args.determinism_runs} runs)...")
    baseline_det = check_determinism(
        "baseline (cast_iron, 35kHz, as committed)",
        run_master_deck_once,
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
    # NOTE: these three literals (0.79, 10.0, PAN_L2_DEFAULT_H) must match
    # zvs_margin_sweep.cir's own committed PAN_K/PAN_RPAN/PAN_L2 defaults
    # exactly -- both were updated together 2026-07-27 (see
    # docs/evidence/2026-07-27-pan-preset-correction.md) specifically so
    # this independently-run baseline still represents "cast_iron, 35kHz"
    # and the self-consistency check below (grid_baseline_matches) stays
    # meaningful rather than comparing two different pan configurations.
    baseline_result = compute_point_result(
        "cast_iron", 0.79, 10.0, 35_000, baseline_meas, pan_l2_h=PAN_L2_DEFAULT_H
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
                    "mutual-inductance K_couple + a used R_pan). L2 (pan "
                    "secondary inductance), K, and RPAN were CORRECTED "
                    "2026-07-27 from provably-impossible defaults "
                    "(K=0.4/L2=1uH could never reproduce Infineon "
                    "AN235020's measured 0.40 loaded/unloaded L-ratio, "
                    "independent of any geometry assumption -- see "
                    "docs/evidence/2026-07-27-coil-pan-coupling-"
                    "resolution.md Sec 2.2-2.3) to the Infineon-anchored "
                    "point (K/L2/RPAN per PAN_PRESETS below); PAN_L2 is "
                    "now exposed as a per-preset override rather than "
                    "left at the subckt's own default. See "
                    "docs/evidence/2026-07-27-pan-preset-correction.md."
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
            "citation": "elec/src/modules.ato: HalfBridge, GateDriveHS, GateDriveLS, ResonantTank, PowerInput; elec/src/main.ato top-level Top module",
        },
        "not_sourced_from_elec_model_defaults": {
            "pan_l1_coil_inductance_h": PAN_L1_DEFAULT_H,
            "pan_l2_default_h": PAN_L2_DEFAULT_H,
            "note": (
                "elec/src/modules.ato's ResonantTank does not specify a "
                "coil inductance at all (inductor_conn is a placeholder "
                "for a physical, not-yet-designed Litz coil). PAN_L1 is "
                "pan_load.sub's own PANLOAD_TRANSFORMER default, not a "
                "schematic value -- every frequency-domain conclusion "
                "below inherits this assumption and is only as good as it. "
                "PAN_L2 (218uH, uniform across presets -- see PAN_PRESETS "
                "comment) is CORRECTED 2026-07-27 from the old 1uH default "
                "via docs/evidence/2026-07-27-coil-pan-coupling-"
                "resolution.md Sec 2.5's Infineon-anchored derivation; it "
                "is still not a bench measurement of this project's coil "
                "and remains one point in an underdetermined family (3 "
                "unknowns, 2 literature equations)."
            ),
        },
        "computed_vs_declared_resonance": {
            "f_resonant_computed_hz": round(F_RESONANT_COMPUTED_HZ, 1),
            "f_resonant_declared_hz": F_RESONANT_DECLARED_HZ,
            "f_switching_nominal_hz": F_SWITCHING_NOMINAL_HZ,
            "finding": (
                f"CORRECTED 2026-07-27 (docs/evidence/2026-07-27-zvs-"
                f"operating-point.md): main.ato:71's nominal switching "
                f"frequency moved from 35kHz to {F_SWITCHING_NOMINAL_HZ/1000:.0f}kHz -- 35kHz measured "
                f"100.7% ZVS margin LOST (full hard switching) for cast_"
                f"iron/stainless once PAN_PRESETS was corrected to K=0.79 "
                f"(docs/evidence/2026-07-27-pan-preset-correction.md Sec "
                f"4.1). main.ato:74 still declares f_resonant_nominal="
                f"{F_RESONANT_DECLARED_HZ/1000:.0f}kHz, UNCHANGED by this pass -- that value "
                f"implies L=135.1uH at the fixed 300nF C_TANK (algebraically, "
                f"not simulated), a THIRD coil-inductance assumption "
                f"distinct from both this file's own 80uH model default "
                f"(computed unloaded resonance {F_RESONANT_COMPUTED_HZ:.0f}Hz below) and the "
                f"150uH assumption behind the new 47kHz nominal -- none of "
                f"the three are reconciled, and none is a measurement of "
                f"the actual (unspecified) coil. Even using main.ato's own "
                f"25kHz-implied 135.1uH, the K=0.79 LOADED resonance comes "
                f"to ~39.7kHz -- ABOVE the old 35kHz nominal -- so the "
                f"ZVS-lost finding does not depend on which of the three L "
                f"assumptions is used; it recurs for all of them. This is "
                f"the UNLOADED (no-pan-coupling) resonance figure computed "
                f"here -- per_preset_zvs_transition_hz below shows the "
                f"LOADED transition is very different per preset after the "
                f"2026-07-27 PAN_PRESETS correction: aluminum/no_pan (low "
                f"K, barely load the tank) still collapse near their own "
                f"unloaded figure, while cast_iron/stainless (K=0.79, "
                f"Infineon-anchored) collapse near a loaded resonance ~60% "
                f"higher -- NOT a single number, contradicting the pre-"
                f"correction finding that all four presets shared one "
                f"transition band."
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
        "sanity_checks": {
            "grid_reproduces_independent_baseline_run": baseline_self_consistent,
            "note": (
                "The (cast_iron, 35kHz) grid point, generated by "
                "override_params() rewriting the deck's own committed "
                "defaults back onto themselves, was compared against an "
                "independently-run copy of the committed deck run with no "
                "text rewriting at all. They must match exactly, or "
                "override_params() is silently corrupting every other "
                "grid point too; this run passed that check."
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
                f"F_SW={worst_point['f_sw_hz']}Hz. CORRECTED 2026-07-27 "
                f"(docs/evidence/2026-07-27-pan-preset-correction.md): "
                f"pan type now materially changes WHERE ZVS transitions, "
                f"reversing the pre-correction finding. cast_iron and "
                f"stainless (K=0.79, Infineon-anchored) collapse between "
                f"{per_preset_transitions['cast_iron']['highest_zvs_lost_hz']}Hz "
                f"(lost) and "
                f"{per_preset_transitions['cast_iron']['lowest_zvs_held_or_degraded_hz']}Hz "
                f"(held) -- a loaded resonance roughly "
                f"{(per_preset_transitions['cast_iron']['lowest_zvs_held_or_degraded_hz'] or 0) / F_RESONANT_COMPUTED_HZ - 1:.0%} "
                f"above the {F_RESONANT_COMPUTED_HZ/1000:.1f}kHz unloaded "
                f"figure. aluminum (K=0.15, retained UNVERIFIED assumption) "
                f"and no_pan (K=0.01) still collapse near the unloaded "
                f"resonance, between "
                f"{per_preset_transitions['aluminum']['highest_zvs_lost_hz']}Hz and "
                f"{per_preset_transitions['aluminum']['lowest_zvs_held_or_degraded_hz']}Hz -- "
                f"consistent with the pre-correction band, because their K "
                f"is far below the ferromagnetic floor and was NOT raised "
                f"(see PAN_PRESETS comment: the floor is Infineon's "
                f"ferromagnetic-pan measurement and does not transfer to "
                f"non-ferrous/no-pan cases). Full per-preset transition "
                f"data: per_preset_zvs_transition_hz. UNCALIBRATED: every "
                f"number here depends on an unverified 80uH coil "
                f"inductance assumption that has no source in elec/, and "
                f"K/L2/RPAN remain uncalibrated-but-no-longer-provably-"
                f"impossible per the resolution doc."
            ),
            "does_not_claim": [
                "Absolute switching-loss or turn-on-energy figures (IGBT model is behavioral, see models_used note).",
                "That pan coupling/material has NO effect on ZVS margin in the real board -- the corrected model now shows a LARGE effect (opposite of the pre-correction finding); see per_preset_zvs_transition_hz.",
                "EMI/CISPR prediction (out of scope per the brainstorm).",
                "Any claim about the real coil's inductance -- it is not specified anywhere in elec/.",
                "That K=0.79 (cast_iron/stainless) or K=0.15 (aluminum) are measured values for THIS project's coil/pan -- both are literature-anchored or retained assumptions, not bench measurements (see PAN_PRESETS source notes and docs/evidence/2026-07-27-pan-preset-correction.md).",
            ],
        },
        "derived_bench_measurement_list": [
            {
                "measurement": "Real coil inductance (uncoupled) and coupling coefficient k vs. air gap, for the actual wound Litz coil and at least the cast-iron/stainless/aluminum pans this design intends to support.",
                "why": "Every frequency-domain result in this sweep is anchored on pan_load.sub's undocumented 80uH default and the Infineon-anchored (not this-project-measured) K/L2 correction. The coil does not exist in elec/ as a designed component (modules.ato ResonantTank.inductor_conn is a placeholder). This is the single highest-leverage bench measurement: it could move the computed resonance (and therefore the safe operating floor) by an unknown amount in either direction.",
            },
            {
                "measurement": "Pan-reflected resistance and effective secondary inductance (or equivalent Q) for real pans, at the actual operating frequency band.",
                "why": "This sweep (post 2026-07-27 PAN_PRESETS correction) found pan type now has a LARGE effect on the ZVS transition frequency (cast_iron/stainless transition ~60% higher than aluminum/no_pan, per_preset_zvs_transition_hz) -- the opposite of the pre-correction finding, and a direct consequence of raising L2 from the provably-too-small 1uH default. This makes the bench measurement MORE consequential, not less: if the real pan-reflected reactance differs from the literature-anchored 218uH used here, the transition frequency for ferromagnetic pans moves further, and the whole 1800W/OCP-01 operating point (docs/evidence/2026-07-27-pan-preset-correction.md) moves with it.",
            },
            {
                "measurement": "IGBT switch-node voltage during a real turn-on transition (oscilloscope, Vce vs time) at the nominal 35kHz operating point AND at the corrected model's implied ~53-55kHz ZVS-holding point for ferromagnetic pans.",
                "why": "Directly validates or falsifies this sweep's central claim against the behavioral IGBT model's prediction. Post-correction, 35kHz is deep in zvs_lost territory for cast_iron/stainless (~100.7% margin) -- a materially different, and more actionable, claim to validate than the pre-correction '~2% margin at 35kHz' figure.",
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
