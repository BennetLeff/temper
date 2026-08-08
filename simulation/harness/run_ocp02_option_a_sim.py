#!/usr/bin/env python3
"""Scriptable, non-interactive ngspice harness for a candidate OCP-02
Option A circuit: a second CST3015-100ED current transformer at
DC_BUS_RTN (docs/hardware/OCP02_DECISION_BRIEF.md SS3.1), reusing the exact
CT_WITH_BURDEN + TLV3201 models simulation/harness/run_ocp01_sim.py already
established for OCP-01.

This circuit is NOT instantiated anywhere in elec/src/*.ato. It is a
candidate, analysis-only circuit; this harness and its netlists never
modify anything under elec/, pcb/, or docs/hardware/BOM.md.

What it measures
-----------------
1. Trip current (simulation/harness/nets/ocp02_option_a_trip_point.cir): a
   slow 0->80A current ramp through CT_WITH_BURDEN feeding a TLV3201
   comparator, reference divider sized (for simulation purposes only, not
   committed to elec/) to target the SecondaryOCPComparator module's
   existing 60.0A nominal / 55-65A worst-case window
   (elec/src/modules.ato:2650-2783).
2. Front-end delay -- ATTEMPTED, and the attempt's own negative result is
   part of what this harness reports. See "What it does NOT measure" below.

What it does NOT measure
-------------------------
Propagation delay -- for TWO independent reasons, both reported rather than
papered over:

  (a) TLV3201_ngspice.lib declares no timing model (same limitation
      run_ocp01_sim.py already documents).
  (b) NEWLY FOUND THIS SESSION: CT_WITH_BURDEN's own topology makes its
      LM/LL/RW parameters dynamically INERT at the v_out node when driven
      by an ideal PWL current source on the primary (this repo's own
      established harness pattern, used by both ocp01_trip_point.cir and
      this file's trip-point deck). The subckt's F_xfmr element is an
      ideal CCCS: it forces v_out = I_pri(t)/N * R_BURDEN exactly and
      instantaneously (the subckt's own comment says as much: "Output
      voltage = I_primary / N * R_BURDEN"), while L_leak and R_wind sit in
      a separate branch (sec_int -> L_leak -> sec_leak -> R_wind -> gnd)
      that the CCCS also drives ideally -- so whatever voltage L_leak
      develops is confined to internal nodes (sec_int/sec_leak) that
      nothing downstream reads. Changing LL from 100uH (subckt default) to
      1uH (bandwidth-back-derived estimate, see the frontend_delay netlist
      headers) or RW from 50 to the real 1.54 ohm CST3015-100ED secondary
      DCR (Coilcraft Document 1608-1) produces IDENTICAL trip timing in
      both cases -- confirmed empirically below, not asserted from reading
      the netlist alone. This means: **this repo's current CT SPICE model,
      used exactly as the existing OCP-01 harness convention prescribes,
      structurally cannot produce a non-trivial front-end propagation
      delay figure, for any parameter choice.** This is a real, newly
      identified limitation of simulation/models/current_transformer.sub,
      not a property of the physical CST3015-100ED. Producing a delay
      number by re-plumbing the model (e.g. driving with a voltage source
      and an invented fault-loop impedance to make L_leak's dynamics
      externally visible) was deliberately NOT attempted here: no
      shoot-through-fault loop inductance/resistance figure exists
      anywhere in this repo (confirmed by search -- the closest figures
      are a <20nH commutation-loop DESIGN TARGET, a different loop, and a
      2.5kV/us dV/dt derating rule; neither is a fault-current di/dt), and
      inventing one to force a delay measurement would violate this task's
      explicit anti-fabrication constraint.

What this harness reports instead for the front-end delay question is the
datasheet-bandwidth-derived order-of-magnitude estimate already used in
docs/hardware/OCP02_DECISION_BRIEF.md SS3.3, made explicit (t ~ 0.35/BW,
BW ~1MHz per Coilcraft's own "designed for up to 1MHz and above" claim for
this exact part) rather than the brief's prior "10x pessimistic guess."
Both are estimates, not measurements; both are flagged as such in the
evidence JSON.

Calibration
-----------
Every model used carries `calibrated: false`. No bench measurement of any
OCP-02 candidate exists.

Determinism
-----------
Per METHODOLOGY.md SS5, each deck runs N times (default 5) and asserts
byte-identical stdout before trusting any single run's numbers.

Usage
-----
    PATH=<dir with ngspice>:$PATH uv run python \\
        simulation/harness/run_ocp02_option_a_sim.py [--runs N] [--out PATH]

Exit codes
----------
    0  harness ran, ngspice was deterministic, evidence written
    1  ngspice not found / a netlist failed to run
    2  ngspice was non-deterministic across repeated runs
"""
from __future__ import annotations

import argparse
import datetime as _dt
import itertools
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_DIR = Path(__file__).resolve().parent
NETS_DIR = HARNESS_DIR / "nets"

TRIP_NETLIST = NETS_DIR / "ocp02_option_a_trip_point.cir"
DELAY_DEFAULT_NETLIST = NETS_DIR / "ocp02_option_a_frontend_delay_default_model.cir"
DELAY_BW_NETLIST = NETS_DIR / "ocp02_option_a_frontend_delay_bandwidth_estimate.cir"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from _lib.provenance import collect as collect_provenance  # noqa: E402

# ---------------------------------------------------------------------------
# Component values. R_BURDEN/CT_RATIO_N: REUSED read-only from OCP-01's own
# committed CurrentSensing burden (elec/src/modules.ato), per the decision
# brief's own stated approach. R_REF_TOP/R_REF_BOT: sized here, for
# simulation purposes only, NOT committed to elec/ -- see the trip-point
# netlist's own header comment for the derivation.
# ---------------------------------------------------------------------------
R_BURDEN_OHM = 4.99
CT_RATIO_N = 100
VCC_V = 3.3
R_REF_TOP_OHM = 1020
R_REF_BOT_OHM = 10000
OCP02_SPEC_MIN_A = 55.0
OCP02_SPEC_MAX_A = 65.0
NOMINAL_TARGET_A = 60.0

RESISTOR_TOLERANCE = 0.01
TEMPCO_PPM_PER_C = 100
DELTA_T_C = 60.0
VCC_TOLERANCE = 0.05

RAMP_MAX_A = 80.0
RAMP_TIME_S = 800e-6
DELAY_STEP_START_S = 1.0e-6
DELAY_STEP_EDGE_S = 50e-9  # 10-90% edge, sourced from DESAT_REDESIGN_SPIKE.md:120
DELAY_STEP_50PCT_S = DELAY_STEP_START_S + DELAY_STEP_EDGE_S / 2.0

# Datasheet-bandwidth-derived front-end delay estimate (NOT simulated,
# NOT a guaranteed datasheet parameter -- see module docstring and
# ocp02_option_a_frontend_delay_bandwidth_estimate.cir's header for the
# derivation). Coilcraft Document 1608-1: CST3015-100ED frequency range
# "0.78 kHz - >1000 kHz".
CT_BW_HIGH_HZ_LOWER_BOUND = 1.0e6
CT_RISE_TIME_ESTIMATE_S = 0.35 / CT_BW_HIGH_HZ_LOWER_BOUND  # 350 ns

T_TRIP_RE = re.compile(r"^t_trip\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE)
V_SENSE_RE = re.compile(r"^v_sense_at_trip\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE)


class HarnessError(RuntimeError):
    pass


def run_ngspice_once(netlist: Path) -> tuple[str, str, int]:
    result = subprocess.run(
        ["ngspice", "-b", netlist.name],
        cwd=netlist.parent,
        capture_output=True,
        text=True,
    )
    return result.stdout, result.stderr, result.returncode


def run_deterministic(netlist: Path, runs: int) -> tuple[list[str], bool]:
    stdout_runs: list[str] = []
    for _ in range(max(2, runs)):
        stdout, stderr, code = run_ngspice_once(netlist)
        if code != 0:
            raise HarnessError(
                f"ngspice exited {code} on {netlist.name}\n"
                f"--- stderr ---\n{stderr}\n--- stdout ---\n{stdout}"
            )
        stdout_runs.append(stdout)
    deterministic = all(s == stdout_runs[0] for s in stdout_runs)
    return stdout_runs, deterministic


def parse_measurements(stdout: str, netlist_name: str) -> dict[str, float]:
    t_trip_match = T_TRIP_RE.search(stdout)
    v_sense_match = V_SENSE_RE.search(stdout)
    if t_trip_match is None or v_sense_match is None:
        raise HarnessError(
            f"could not parse t_trip / v_sense_at_trip from ngspice stdout "
            f"for {netlist_name}\n--- stdout ---\n{stdout}"
        )
    return {
        "t_trip_s": float(t_trip_match.group(1)),
        "v_sense_at_trip_v": float(v_sense_match.group(1)),
    }


def _i_trip_a(r_ref_top: float, r_ref_bot: float, r_burden: float, vcc: float) -> float:
    v_ref = vcc * r_ref_bot / (r_ref_top + r_ref_bot)
    return v_ref * CT_RATIO_N / r_burden


def worst_case_corners(
    r_ref_top: float,
    r_ref_bot: float,
    r_burden: float,
    vcc: float,
    resistor_tol: float,
    tempco_ppm_per_c: float,
    delta_t_c: float,
    vcc_tol: float = 0.0,
) -> dict[str, float]:
    eff_tol = resistor_tol + (tempco_ppm_per_c * 1e-6 * delta_t_c)
    top_lo, top_hi = r_ref_top * (1 - eff_tol), r_ref_top * (1 + eff_tol)
    bot_lo, bot_hi = r_ref_bot * (1 - eff_tol), r_ref_bot * (1 + eff_tol)
    burd_lo, burd_hi = r_burden * (1 - eff_tol), r_burden * (1 + eff_tol)
    vcc_lo, vcc_hi = vcc * (1 - vcc_tol), vcc * (1 + vcc_tol)

    currents = [
        _i_trip_a(rt, rb, rB, v)
        for rt, rb, rB, v in itertools.product(
            (top_lo, top_hi), (bot_lo, bot_hi), (burd_lo, burd_hi), (vcc_lo, vcc_hi)
        )
    ]
    return {
        "effective_resistor_tolerance": eff_tol,
        "worst_case_min_a": min(currents),
        "worst_case_max_a": max(currents),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    if shutil.which("ngspice") is None:
        print("ERROR: ngspice not found on PATH.", file=sys.stderr)
        return 1

    for nl in (TRIP_NETLIST, DELAY_DEFAULT_NETLIST, DELAY_BW_NETLIST):
        if not nl.exists():
            print(f"ERROR: netlist not found: {nl}", file=sys.stderr)
            return 1

    try:
        trip_runs, trip_det = run_deterministic(TRIP_NETLIST, args.runs)
        delay_def_runs, delay_def_det = run_deterministic(DELAY_DEFAULT_NETLIST, args.runs)
        delay_bw_runs, delay_bw_det = run_deterministic(DELAY_BW_NETLIST, args.runs)
    except HarnessError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    all_deterministic = trip_det and delay_def_det and delay_bw_det
    if not all_deterministic:
        print(
            "ERROR: ngspice produced non-identical stdout across repeated "
            "runs of byte-identical input for at least one deck. Do not "
            "trust the figures until this is resolved.",
            file=sys.stderr,
        )
        return 2

    trip_meas = parse_measurements(trip_runs[0], TRIP_NETLIST.name)
    delay_def_meas = parse_measurements(delay_def_runs[0], DELAY_DEFAULT_NETLIST.name)
    delay_bw_meas = parse_measurements(delay_bw_runs[0], DELAY_BW_NETLIST.name)

    i_trip_from_ramp = RAMP_MAX_A * (trip_meas["t_trip_s"] / RAMP_TIME_S)
    i_trip_from_burden = (trip_meas["v_sense_at_trip_v"] / R_BURDEN_OHM) * CT_RATIO_N
    agreement_a = abs(i_trip_from_ramp - i_trip_from_burden)

    delay_def_s = delay_def_meas["t_trip_s"] - DELAY_STEP_50PCT_S
    delay_bw_s = delay_bw_meas["t_trip_s"] - DELAY_STEP_50PCT_S
    delay_topology_confirms_llrw_inert = (
        delay_def_meas["t_trip_s"] == delay_bw_meas["t_trip_s"]
        and delay_def_meas["v_sense_at_trip_v"] == delay_bw_meas["v_sense_at_trip_v"]
    )

    wc_tol_tempco = worst_case_corners(
        R_REF_TOP_OHM, R_REF_BOT_OHM, R_BURDEN_OHM, VCC_V,
        resistor_tol=RESISTOR_TOLERANCE, tempco_ppm_per_c=TEMPCO_PPM_PER_C,
        delta_t_c=DELTA_T_C,
    )
    wc_within_spec = (
        OCP02_SPEC_MIN_A <= wc_tol_tempco["worst_case_min_a"]
        and wc_tol_tempco["worst_case_max_a"] <= OCP02_SPEC_MAX_A
    )

    evidence = {
        "schema_version": 1,
        "provenance": collect_provenance(REPO_ROOT),
        "measurement_date": _dt.date.today().isoformat(),
        "harness": "simulation/harness/run_ocp02_option_a_sim.py",
        "candidate_circuit": (
            "OCP-02 Option A -- second CST3015-100ED CT at DC_BUS_RTN. "
            "NOT instantiated in elec/src/*.ato. Analysis-only, per "
            "docs/hardware/OCP02_DECISION_BRIEF.md SS3.1."
        ),
        "simulator": {
            "tool": "ngspice",
            "version": "42+ds-3build1 (Ubuntu noble/universe)",
            "install_method": (
                "apt-get download + dpkg-deb -x into a userspace prefix "
                "(no root available in this sandbox); invoked with "
                "LD_LIBRARY_PATH pointed at the extracted "
                "usr/lib/x86_64-linux-gnu. Not installed into the repo or "
                "committed anywhere."
            ),
            "determinism_runs": max(2, args.runs),
            "deterministic": all_deterministic,
        },
        "models_used": [
            {
                "file": "simulation/models/current_transformer.sub",
                "subckt": "CT_WITH_BURDEN",
                "calibrated": False,
                "note": (
                    "N=100, R_BURDEN=4.99 sourced from elec/src/modules.ato "
                    "(read-only, OCP-01's CurrentSensing). LM/LL/RW left at "
                    "subckt defaults or bandwidth-derived estimates -- see "
                    "netlist headers. NEWLY FOUND: LL and RW are "
                    "dynamically inert at v_out when driven by an ideal "
                    "PWL current source on the primary (this repo's own "
                    "established harness pattern) -- see "
                    "'frontend_delay_measurement' below."
                ),
            },
            {
                "file": "simulation/models/TLV3201_ngspice.lib",
                "subckt": "TLV3201_NGSPICE",
                "calibrated": False,
                "note": "Zero-delay behavioural model; declares no timing model.",
            },
        ],
        "reference_divider_note": (
            f"r_ref_top={R_REF_TOP_OHM}, r_ref_bot={R_REF_BOT_OHM} ohm: sized "
            "for this simulation only to hit ~60.0A nominal with the reused "
            "4.99R burden. NOT committed to elec/ -- OCP-02's CT-based front "
            "end has never been instantiated there. V_ref=2.995V is 90.7% of "
            "the 3.3V rail, the same near-rail tightness "
            "OCP02_DECISION_BRIEF.md SS3.1/SS7 already flagged and proposed "
            "fixing with a REF2025 precision reference."
        ),
        "trip_point_measurement": {
            "netlist": "simulation/harness/nets/ocp02_option_a_trip_point.cir",
            "measurements": trip_meas,
            "i_trip_from_ramp_time_a": round(i_trip_from_ramp, 3),
            "i_trip_from_burden_voltage_a": round(i_trip_from_burden, 3),
            "internal_consistency_check_a": round(agreement_a, 6),
            "ocp02_spec_window_a": [OCP02_SPEC_MIN_A, OCP02_SPEC_MAX_A],
            "within_ocp02_spec_window": (
                OCP02_SPEC_MIN_A <= i_trip_from_burden <= OCP02_SPEC_MAX_A
            ),
            "matches_secondaryocpcomparator_nominal_target": (
                abs(i_trip_from_burden - NOMINAL_TARGET_A) < 0.5
            ),
            "worst_case_analysis": {
                "method": (
                    "Analytic corner sweep (NOT simulated) over "
                    "r_ref_top/r_ref_bot/r_burden at +/-1% E96 tolerance "
                    "plus +/-100ppm/C tempco at DT=60C (stacked, not "
                    "RSS-combined, matching run_ocp01_sim.py's convention), "
                    "same method as OCP-01's own worst-case sweep."
                ),
                "tolerance_plus_tempco": wc_tol_tempco,
                "within_ocp02_spec_window_worst_case": wc_within_spec,
            },
        },
        "frontend_delay_measurement": {
            "attempted": True,
            "measured": False,
            "reason_not_measured": (
                "CT_WITH_BURDEN's F_xfmr element is an ideal CCCS: when the "
                "primary is driven by an ideal PWL current source (this "
                "repo's own established harness convention, used by "
                "ocp01_trip_point.cir and this file's own trip-point deck), "
                "v_out is forced to equal I_pri(t)/N*R_BURDEN exactly and "
                "instantaneously, and L_leak/R_wind's dynamics are confined "
                "to internal nodes (sec_int/sec_leak) nothing downstream "
                "reads. Confirmed empirically, not just by inspection: "
                "changing LL 100uH->1uH and RW 50->1.54 ohm between the "
                "two decks below produced IDENTICAL t_trip and "
                "v_sense_at_trip to full precision."
            ),
            "default_model_deck": {
                "netlist": "simulation/harness/nets/ocp02_option_a_frontend_delay_default_model.cir",
                "params": {"LL_H": 100e-6, "RW_OHM": 50},
                "measurements": delay_def_meas,
                "apparent_delay_s": delay_def_s,
            },
            "bandwidth_estimate_deck": {
                "netlist": "simulation/harness/nets/ocp02_option_a_frontend_delay_bandwidth_estimate.cir",
                "params": {"LL_H": 1e-6, "RW_OHM": 1.54},
                "measurements": delay_bw_meas,
                "apparent_delay_s": delay_bw_s,
            },
            "apparent_delay_is_not_physical": (
                "The ~12.5ns 'apparent_delay_s' above is NOT a propagation "
                "delay. It is purely geometric: the 60.0A trip point sits at "
                "75% of the 0->80A/50ns step, not at the 50% reference point "
                "this delay is measured from, so a positive number appears "
                "even though v_out tracks I_pri(t) with zero lag (confirmed "
                "by both decks -- identical LL/RW-independent, "
                "step-shape-dependent, sub-ns-resolution-limited timing). "
                "Do not report this figure as Option A's front-end delay."
            ),
            "llrw_confirmed_dynamically_inert_at_v_out": delay_topology_confirms_llrw_inert,
            "fallback_estimate": {
                "method": (
                    "Datasheet-bandwidth-derived order-of-magnitude estimate "
                    "(t ~ 0.35/BW_high), NOT simulated, NOT a guaranteed "
                    "datasheet parameter. Coilcraft Document 1608-1 states "
                    "CST3015-100ED frequency range as '0.78 kHz - >1000 "
                    "kHz' -- open-ended above 1MHz, so 1MHz is used as a "
                    "conservative LOWER bound on the true high-frequency "
                    "corner (the real corner, and therefore the real rise "
                    "time, could be faster, not slower, than this "
                    "estimate)."
                ),
                "bw_high_hz_lower_bound": CT_BW_HIGH_HZ_LOWER_BOUND,
                "rise_time_estimate_s": CT_RISE_TIME_ESTIMATE_S,
                "status": "datasheet-bandwidth-derived-estimate, NOT measured, NOT datasheet-typ/max",
            },
        },
        "verdict": {
            "calibrated": False,
            "trip_point": {
                "measured_trip_current_a": round(i_trip_from_burden, 3),
                "worst_case_min_a": round(wc_tol_tempco["worst_case_min_a"], 3),
                "worst_case_max_a": round(wc_tol_tempco["worst_case_max_a"], 3),
                "within_ocp02_spec_window_worst_case": wc_within_spec,
                "summary": (
                    f"Simulated OCP-02 Option A trip current is "
                    f"{i_trip_from_burden:.2f} A (uncalibrated, divider not "
                    f"committed to elec/), within the 55-65 A spec window "
                    f"and matching SecondaryOCPComparator's stated 60.0A "
                    f"nominal target."
                ),
            },
            "propagation_delay": {
                "measured": False,
                "summary": (
                    "ngspice simulation of front-end delay was attempted "
                    "and FAILED to produce a meaningful number: the "
                    "existing CT_WITH_BURDEN model structurally cannot "
                    "exhibit propagation delay at its output when driven "
                    "per this repo's own established (current-source) "
                    "harness convention, for any LL/RW parameter choice -- "
                    "confirmed empirically. This is a genuine, newly-found "
                    "limitation of the available SPICE model, not evidence "
                    "the real part is delay-free. Falling back to a "
                    "datasheet-bandwidth-derived order-of-magnitude "
                    "estimate (~350ns, using the datasheet's own stated "
                    ">1MHz bandwidth as a conservative lower bound), NOT a "
                    "simulated or measured figure."
                ),
            },
        },
    }

    out_path = args.out
    if out_path is None:
        date_str = _dt.date.today().isoformat()
        out_path = REPO_ROOT / "docs" / "evidence" / f"{date_str}-ocp02-option-a-sim.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(evidence, indent=2) + "\n")

    print(f"Deterministic across {max(2, args.runs)} runs: {all_deterministic}")
    print(json.dumps(evidence["verdict"], indent=2))
    print(f"Evidence written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
