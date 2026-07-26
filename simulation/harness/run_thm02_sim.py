#!/usr/bin/env python3
"""Scriptable, non-interactive ngspice harness for the THM-02 trip AND
recovery transient (simulation/harness/nets/thm02_trip_point.cir).

Same template as run_thm01_sim.py, applied to CoilThermalComparator
(elec/src/modules.ato) instead of ThermalComparator. THM-02 (coil NTC,
120C) had NO IMPLEMENTING CIRCUIT AT ALL until 2026-07-26 -- see
docs/hardware/PROTECTION_CHAIN_REVIEW.md's "OCP-02, THM-02 -- no circuit
exists" finding -- so there was previously nothing for any harness to
simulate. This is the first THM-02 simulation.

What it measures
-----------------
A "temperature" ramp (25 degC -> 200 degC over 300us, THEN BACK DOWN to
25 degC over the next 300us) drives an NTC modeled by its own Beta
(B-parameter) equation, R25=100k / B=4190K -- the same part family as the
heatsink sensor, per elec/src/modules.ato::CoilThermalComparator's inline
comment. The NTC divider and reference divider (with the r_hyst
positive-feedback network) feed a TLV3201 comparator model
(simulation/models/TLV3201_ngspice.lib). This script and its netlist
never modify anything under elec/.

The up-then-down ramp lets ONE transient run capture both the TRIP (SET)
threshold, on the way up, and the RECOVERY (RESET) threshold, on the way
down -- the recovery threshold only exists once the comparator output has
actually latched high via r_hyst positive feedback.

It reports the trip and recovery temperatures against:
  - THM-02's declared 120 degC trip / 100 degC recovery spec
    (docs/FUNCTIONAL_TEST_CRITERIA.md SS2.3).
  - CoilThermalComparator's own inline comment estimates (120.0 degC trip,
    100.1 degC recovery).

What it does NOT measure
-------------------------
- Response time / propagation delay: TLV3201_ngspice.lib declares no
  timing model.
- Actual thermal time-constant / mounting: the "temperature ramp" here is
  an idealized proxy signal, not a simulation of coil thermal mass or the
  NTC's own thermal time constant.
- The module's own SENSOR RATING CAVEAT: NTCALUG01A104GA is specified to
  +125C and this gate trips at ~120C, within 5C of the sensor's own rated
  maximum. That is a part-selection concern the module flags explicitly;
  this harness reports the electrical trip/recovery point only.

Calibration
-----------
Every model used carries `calibrated: false`. No Steinhart-Hart table for
NTCALUG01A104GA is committed anywhere in this repo; the Beta-equation
R25/B values are the sourced approximation the module's own comment
relies on.

Determinism
-----------
Per METHODOLOGY.md SS5, this script runs the deck N times (default 5) and
asserts byte-identical stdout before trusting any single run's numbers.

Usage
-----
    uv run python simulation/harness/run_thm02_sim.py [--runs N] [--out PATH]

Exit codes
----------
    0  harness ran, ngspice was deterministic, evidence written
    1  ngspice not found / netlist failed to run
    2  ngspice was non-deterministic across repeated runs
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_DIR = Path(__file__).resolve().parent
NETLIST = HARNESS_DIR / "nets" / "thm02_trip_point.cir"

# Component / thermistor values below are copied read-only from
# elec/src/modules.ato :: CoilThermalComparator (added 2026-07-26).
VCC_V = 3.3
R_NTC_FIXED_OHM = 3_320
R_REF_TOP_OHM = 3_160
R_REF_BOT_OHM = 4_420
R_HYST_OHM = 11_500
NTC_R25_OHM = 100_000
NTC_BETA_K = 4190.0
T25_K = 298.15

# Ramp shape, mirrored from the netlist's .param block (read-only copy for
# the independent ramp-time cross-check derivation).
T_START_K = 298.15
T_PEAK_K = 473.15
T_UP_S = 300e-6
T_DOWN_S = 300e-6

THM02_SPEC_TRIP_C = 120.0
THM02_SPEC_RECOVER_C = 100.0
DOCSTRING_CLAIM_TRIP_C = 120.0
DOCSTRING_CLAIM_RECOVER_C = 100.1  # module's own hand-derivation
SPEC_MATCH_TOLERANCE_C = 2.0

# Module's own SENSOR RATING CAVEAT: NTCALUG01A104GA is rated to +125C.
NTC_MAX_RATED_TEMP_C = 125.0

T_TRIP_RE = re.compile(r"^t_trip\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE)
T_RELEASE_RE = re.compile(r"^t_release\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE)
V_NTC_TRIP_RE = re.compile(
    r"^v_ntc_sense_at_trip\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE
)
V_NTC_RELEASE_RE = re.compile(
    r"^v_ntc_sense_at_release\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE
)
TEMP_K_TRIP_RE = re.compile(r"^temp_k_at_trip\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE)
TEMP_K_RELEASE_RE = re.compile(
    r"^temp_k_at_release\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE
)


class HarnessError(RuntimeError):
    pass


def run_ngspice_once() -> tuple[str, str, int]:
    result = subprocess.run(
        ["ngspice", "-b", NETLIST.name],
        cwd=NETLIST.parent,
        capture_output=True,
        text=True,
    )
    return result.stdout, result.stderr, result.returncode


def parse_measurements(stdout: str) -> dict[str, float]:
    matches = {
        "t_trip_s": T_TRIP_RE.search(stdout),
        "t_release_s": T_RELEASE_RE.search(stdout),
        "v_ntc_sense_at_trip_v": V_NTC_TRIP_RE.search(stdout),
        "v_ntc_sense_at_release_v": V_NTC_RELEASE_RE.search(stdout),
        "temp_k_at_trip": TEMP_K_TRIP_RE.search(stdout),
        "temp_k_at_release": TEMP_K_RELEASE_RE.search(stdout),
    }
    missing = [k for k, v in matches.items() if v is None]
    if missing:
        raise HarnessError(
            f"could not parse {missing} from ngspice stdout -- the "
            "comparator may never have tripped and/or released within the "
            f"600us up/down ramp window.\n--- stdout ---\n{stdout}"
        )
    return {k: float(v.group(1)) for k, v in matches.items()}


def temp_from_r_ntc(r_ntc_ohm: float) -> float:
    return 1.0 / (1.0 / T25_K + math.log(r_ntc_ohm / NTC_R25_OHM) / NTC_BETA_K)


def temp_from_ramp_time_k(t_s: float) -> float:
    """Independent ramp-time cross-check, valid on either leg of the
    up-then-down ramp (mirrors the netlist's PWL breakpoints)."""
    if t_s <= T_UP_S:
        return T_START_K + (T_PEAK_K - T_START_K) * (t_s / T_UP_S)
    t_down = t_s - T_UP_S
    return T_PEAK_K - (T_PEAK_K - T_START_K) * (t_down / T_DOWN_S)


def derive_trip_and_release(measurements: dict[str, float]) -> dict[str, float]:
    """Independent derivations of the trip and release temperatures from
    the same run: ramp-time interpolation, the probe node, and inverting
    the NTC divider voltage through the Beta equation."""
    temp_trip_from_ramp_time_k = temp_from_ramp_time_k(measurements["t_trip_s"])
    temp_release_from_ramp_time_k = temp_from_ramp_time_k(measurements["t_release_s"])

    temp_trip_from_probe_node_k = measurements["temp_k_at_trip"]
    temp_release_from_probe_node_k = measurements["temp_k_at_release"]

    v_ntc_trip = measurements["v_ntc_sense_at_trip_v"]
    r_ntc_trip_ohm = v_ntc_trip * R_NTC_FIXED_OHM / (VCC_V - v_ntc_trip)
    temp_trip_from_divider_voltage_k = temp_from_r_ntc(r_ntc_trip_ohm)

    v_ntc_release = measurements["v_ntc_sense_at_release_v"]
    r_ntc_release_ohm = v_ntc_release * R_NTC_FIXED_OHM / (VCC_V - v_ntc_release)
    temp_release_from_divider_voltage_k = temp_from_r_ntc(r_ntc_release_ohm)

    return {
        "temp_trip_from_ramp_time_k": temp_trip_from_ramp_time_k,
        "temp_trip_from_probe_node_k": temp_trip_from_probe_node_k,
        "temp_trip_from_divider_voltage_k": temp_trip_from_divider_voltage_k,
        "r_ntc_at_trip_ohm": r_ntc_trip_ohm,
        "temp_release_from_ramp_time_k": temp_release_from_ramp_time_k,
        "temp_release_from_probe_node_k": temp_release_from_probe_node_k,
        "temp_release_from_divider_voltage_k": temp_release_from_divider_voltage_k,
        "r_ntc_at_release_ohm": r_ntc_release_ohm,
    }


def build_evidence(
    measurements: dict[str, float],
    derived: dict[str, float],
    invocation: str,
    determinism_runs: int,
    deterministic: bool,
) -> dict:
    temp_trip_k = derived["temp_trip_from_divider_voltage_k"]
    temp_trip_c = temp_trip_k - 273.15
    temp_release_k = derived["temp_release_from_divider_voltage_k"]
    temp_release_c = temp_release_k - 273.15
    hysteresis_c = temp_trip_c - temp_release_c

    trip_agreement_k = max(
        abs(derived["temp_trip_from_ramp_time_k"] - derived["temp_trip_from_probe_node_k"]),
        abs(
            derived["temp_trip_from_probe_node_k"]
            - derived["temp_trip_from_divider_voltage_k"]
        ),
    )
    release_agreement_k = max(
        abs(
            derived["temp_release_from_ramp_time_k"]
            - derived["temp_release_from_probe_node_k"]
        ),
        abs(
            derived["temp_release_from_probe_node_k"]
            - derived["temp_release_from_divider_voltage_k"]
        ),
    )

    trip_within_spec = abs(temp_trip_c - THM02_SPEC_TRIP_C) <= SPEC_MATCH_TOLERANCE_C
    recovery_within_spec = (
        abs(temp_release_c - THM02_SPEC_RECOVER_C) <= SPEC_MATCH_TOLERANCE_C
    )
    within_spec = trip_within_spec and recovery_within_spec
    within_sensor_rating = temp_trip_c < NTC_MAX_RATED_TEMP_C

    return {
        "schema_version": 1,
        "measurement_date": _dt.date.today().isoformat(),
        "invocation": invocation,
        "harness": "simulation/harness/run_thm02_sim.py",
        "netlist": "simulation/harness/nets/thm02_trip_point.cir",
        "simulator": {
            "tool": "ngspice",
            "determinism_runs": determinism_runs,
            "deterministic": deterministic,
            "note": (
                f"{determinism_runs} identical byte-for-byte stdout runs; "
                "see docs/METHODOLOGY.md SS5 'the oracle is not exempt'."
            ),
        },
        "models_used": [
            {
                "file": "simulation/models/TLV3201_ngspice.lib",
                "subckt": "TLV3201_NGSPICE",
                "calibrated": False,
                "note": (
                    "Vendor-provenance behavioural port; declares no "
                    "timing model."
                ),
            },
            {
                "file": "simulation/harness/nets/thm02_trip_point.cir (inline B-source)",
                "subckt": "NTC Beta-equation behavioral model",
                "calibrated": False,
                "note": (
                    "R25=100k, B=4190K sourced read-only from "
                    "elec/src/modules.ato CoilThermalComparator's inline "
                    "comment (same NTCALUG01A104GA part family as the "
                    "heatsink sensor). No Steinhart-Hart table for this "
                    "part is committed anywhere in this repo. "
                    "'Temperature' is an idealized ramped proxy signal, "
                    "not a thermal-mass or thermal-time-constant "
                    "simulation."
                ),
            },
        ],
        "sourced_from_elec_read_only": {
            "power_3v3_v": VCC_V,
            "r_ntc_fixed_ohm": R_NTC_FIXED_OHM,
            "r_ref_top_ohm": R_REF_TOP_OHM,
            "r_ref_bot_ohm": R_REF_BOT_OHM,
            "r_hyst_ohm": R_HYST_OHM,
            "ntc_r25_ohm": NTC_R25_OHM,
            "ntc_beta_k": NTC_BETA_K,
            "ntc_mpn": "NTCALUG01A104GA",
            "ntc_max_rated_temp_c": NTC_MAX_RATED_TEMP_C,
            "citation": "elec/src/modules.ato: CoilThermalComparator",
        },
        "implementation_scope": {
            "instances_of_CoilThermalComparator_in_modules_ato": 1,
            "instantiated_as": "SafetyInterlock.coil_thermal (elec/src/modules.ato)",
            "circuit_existed_before_2026_07_26": False,
            "note": (
                "THM-02 previously had NO implementing circuit at all "
                "(docs/hardware/PROTECTION_CHAIN_REVIEW.md: 'OCP-02, "
                "THM-02 -- no circuit exists'). This is the first "
                "simulation of THM-02."
            ),
        },
        "measurements": measurements,
        "derived": derived,
        "internal_consistency_check_trip_k": trip_agreement_k,
        "internal_consistency_check_release_k": release_agreement_k,
        "verdict": {
            "calibrated": False,
            "measured_trip_temp_c": round(temp_trip_c, 2),
            "measured_trip_temp_k": round(temp_trip_k, 2),
            "measured_recovery_temp_c": round(temp_release_c, 2),
            "measured_recovery_temp_k": round(temp_release_k, 2),
            "measured_hysteresis_c": round(hysteresis_c, 2),
            "thm02_spec_trip_c": THM02_SPEC_TRIP_C,
            "thm02_spec_recover_c": THM02_SPEC_RECOVER_C,
            "spec_match_tolerance_c": SPEC_MATCH_TOLERANCE_C,
            "trip_within_thm02_spec": trip_within_spec,
            "recovery_within_thm02_spec": recovery_within_spec,
            "within_thm02_spec": within_spec,
            "docstring_claim_trip_c": DOCSTRING_CLAIM_TRIP_C,
            "matches_docstring_claim_trip": abs(temp_trip_c - DOCSTRING_CLAIM_TRIP_C) < 1.0,
            "docstring_claim_recover_c": DOCSTRING_CLAIM_RECOVER_C,
            "matches_docstring_claim_recover": (
                abs(temp_release_c - DOCSTRING_CLAIM_RECOVER_C) < 1.0
            ),
            "within_ntc_sensor_rating": within_sensor_rating,
            "ntc_sensor_rating_margin_c": round(NTC_MAX_RATED_TEMP_C - temp_trip_c, 2),
            "sensor_rating_caveat": (
                "NTCALUG01A104GA is specified to +125C; the simulated trip "
                f"temperature ({temp_trip_c:.1f}C) is within "
                f"{NTC_MAX_RATED_TEMP_C - temp_trip_c:.1f}C of that rated "
                "maximum. Flagged per the module's own comment, not "
                "resolved by this harness."
            ),
            "response_time_measured": False,
            "response_time_reason": (
                "TLV3201_ngspice.lib declares no timing model; the ramped "
                "'temperature' driver is an idealized proxy, not a thermal "
                "time-constant simulation."
            ),
            "summary": (
                f"Simulated THM-02 (coil NTC) trip temperature is "
                f"{temp_trip_c:.2f} degC and recovery temperature is "
                f"{temp_release_c:.2f} degC (uncalibrated), giving "
                f"{hysteresis_c:.2f} degC of hysteresis. This is "
                f"{'WITHIN' if within_spec else 'OUTSIDE'} the THM-02 120C "
                f"trip / 100C recovery requirement "
                f"(FUNCTIONAL_TEST_CRITERIA.md SS2.3), matching "
                f"CoilThermalComparator's own inline hand-derivation "
                f"(120.0C trip, 100.1C recovery) to within "
                f"{abs(temp_trip_c - DOCSTRING_CLAIM_TRIP_C):.2f} degC / "
                f"{abs(temp_release_c - DOCSTRING_CLAIM_RECOVER_C):.2f} degC. "
                f"The trip point sits {NTC_MAX_RATED_TEMP_C - temp_trip_c:.1f} "
                f"degC below the NTC's own +125C rated maximum -- close "
                f"enough that the module itself flags it as a caveat."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    if shutil.which("ngspice") is None:
        print("ERROR: ngspice not found on PATH.", file=sys.stderr)
        return 1

    if not NETLIST.exists():
        print(f"ERROR: netlist not found: {NETLIST}", file=sys.stderr)
        return 1

    stdout_runs: list[str] = []
    for i in range(max(2, args.runs)):
        stdout, stderr, code = run_ngspice_once()
        if code != 0:
            print(
                f"ERROR: ngspice exited {code} on run {i + 1}\n"
                f"--- stderr ---\n{stderr}\n--- stdout ---\n{stdout}",
                file=sys.stderr,
            )
            return 1
        stdout_runs.append(stdout)

    deterministic = all(s == stdout_runs[0] for s in stdout_runs)
    if not deterministic:
        print(
            "ERROR: ngspice produced non-identical stdout across "
            f"{len(stdout_runs)} runs of byte-identical input.",
            file=sys.stderr,
        )
        return 2

    measurements = parse_measurements(stdout_runs[0])
    derived = derive_trip_and_release(measurements)

    invocation = "uv run python simulation/harness/run_thm02_sim.py --runs " + str(
        max(2, args.runs)
    )
    evidence = build_evidence(
        measurements=measurements,
        derived=derived,
        invocation=invocation,
        determinism_runs=len(stdout_runs),
        deterministic=deterministic,
    )

    out_path = args.out
    if out_path is None:
        date_str = _dt.date.today().isoformat()
        out_path = REPO_ROOT / "docs" / "evidence" / f"{date_str}-thm02-trip-point-sim.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(evidence, indent=2) + "\n")

    print(f"Deterministic across {len(stdout_runs)} runs: {deterministic}")
    print(json.dumps(evidence["verdict"], indent=2))
    print(f"Evidence written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
