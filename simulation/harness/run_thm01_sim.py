#!/usr/bin/env python3
"""Scriptable, non-interactive ngspice harness for the THM-01 trip-temperature
transient (simulation/harness/nets/thm01_trip_point.cir).

Same template as run_ocp01_sim.py / run_ovp01_sim.py, applied to
ThermalComparator (elec/src/modules.ato) -- the sole thermal-protection
comparator instantiated on this board (see the "only one ThermalComparator
exists" finding recorded in this evidence file's `implementation_scope`
section: there is no second instance for a coil NTC, so THM-02 cannot be
measured by this or any other harness -- there is no circuit for it).

What it measures
-----------------
A "temperature" ramp (25 degC -> 130 degC over 300 us, represented as an
independent voltage source in kelvin -- this is a proxy driver, not a
thermal-electrical simulation; see the netlist header) drives an NTC
modeled by its own Beta (B-parameter) equation, R25=100k / B=4190K, sourced
read-only from elec/src/modules.ato::ThermalComparator's inline comment
citing the committed NTCALUG01A104GA part. The NTC divider and reference
divider (with the r_hyst positive-feedback network, present on THIS
comparator only) feed a TLV3201 comparator model
(simulation/models/TLV3201_ngspice.lib). This script and its netlist never
modify anything under elec/.

It reports the temperature at which the comparator output crosses the
logic threshold ("trip temperature"), and compares it against:
  - THM-01's declared 85 degC trip spec (docs/FUNCTIONAL_TEST_CRITERIA.md SS2.3).
  - ThermalComparator's own docstring claim ("85C threshold").
  - The module's own inline comment estimate (~96 degC, computed WITHOUT
    accounting for the r_hyst loading on the pre-trip reference divider).
  - This harness's own more careful hand derivation (~99.4 degC, accounting
    for r_hyst || r_ref_bot pre-trip).

What it does NOT measure
-------------------------
- Response time / propagation delay: TLV3201_ngspice.lib declares no
  timing model.
- Hysteresis band width in degC: r_hyst's effect on the RESET temperature
  (comp.OUT high -> INP pulled toward VCC through r_hyst, changing the
  reference) is a real, simulatable second trip point, but is out of scope
  for this harness; only the initial (trip/SET) threshold is measured.
- Actual thermal time-constant / mounting: the "temperature ramp" here is
  an idealized proxy signal, not a simulation of heatsink thermal mass or
  the NTC's own thermal time constant.

Calibration
-----------
Every model used carries `calibrated: false`. Additionally, no
Steinhart-Hart table for NTCALUG01A104GA is committed anywhere in this
repo; the Beta-equation R25/B values are the sourced approximation the
module's own comment relies on, so this harness is unusually far from
calibrated even relative to OCP-01/OVP-01 (see `models_used` note).

Determinism
-----------
Per METHODOLOGY.md SS5, this script runs the deck N times (default 5) and
asserts byte-identical stdout before trusting any single run's numbers.

Usage
-----
    uv run python simulation/harness/run_thm01_sim.py [--runs N] [--out PATH]

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
NETLIST = HARNESS_DIR / "nets" / "thm01_trip_point.cir"

# Component / thermistor values below are copied read-only from
# elec/src/modules.ato :: ThermalComparator.
VCC_V = 3.3
R_NTC_FIXED_OHM = 10_000
R_REF_TOP_OHM = 9_530
R_REF_BOT_OHM = 10_000
R_HYST_OHM = 100_000
NTC_R25_OHM = 100_000
NTC_BETA_K = 4190.0
T25_K = 298.15

THM01_SPEC_TRIP_C = 85.0
THM01_SPEC_RECOVER_C = 70.0
DOCSTRING_CLAIM_C = 85.0
DESIGN_COMMENT_UNLOADED_ESTIMATE_C = 96.0  # module's own comment, ignores r_hyst loading

T_TRIP_RE = re.compile(r"^t_trip\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE)
V_NTC_RE = re.compile(r"^v_ntc_sense_at_trip\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE)
TEMP_K_RE = re.compile(r"^temp_k_at_trip\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE)


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
    t_trip_match = T_TRIP_RE.search(stdout)
    v_ntc_match = V_NTC_RE.search(stdout)
    temp_k_match = TEMP_K_RE.search(stdout)
    if t_trip_match is None or v_ntc_match is None or temp_k_match is None:
        raise HarnessError(
            "could not parse t_trip / v_ntc_sense_at_trip / temp_k_at_trip "
            "from ngspice stdout -- the comparator may never have tripped "
            f"within the 300us ramp window.\n--- stdout ---\n{stdout}"
        )
    return {
        "t_trip_s": float(t_trip_match.group(1)),
        "v_ntc_sense_at_trip_v": float(v_ntc_match.group(1)),
        "temp_k_at_trip": float(temp_k_match.group(1)),
    }


def r_ntc_from_beta(temp_k: float) -> float:
    return NTC_R25_OHM * math.exp(NTC_BETA_K * (1.0 / temp_k - 1.0 / T25_K))


def derive_trip_temperature(measurements: dict[str, float]) -> dict[str, float]:
    """Independent derivations of the trip temperature from the same run."""
    t_start_k = 298.15
    t_end_k = 403.15
    ramp_time_s = 300e-6
    temp_from_ramp_time_k = t_start_k + (t_end_k - t_start_k) * (
        measurements["t_trip_s"] / ramp_time_s
    )
    temp_from_meas_node_k = measurements["temp_k_at_trip"]

    # Independently solve for R_ntc at trip from the measured divider
    # voltage (not from the temp_k probe node), then invert the Beta
    # equation to get a THIRD, fully independent temperature estimate.
    v_ntc = measurements["v_ntc_sense_at_trip_v"]
    r_ntc_trip_ohm = v_ntc * R_NTC_FIXED_OHM / (VCC_V - v_ntc)
    temp_from_divider_voltage_k = 1.0 / (
        1.0 / T25_K + math.log(r_ntc_trip_ohm / NTC_R25_OHM) / NTC_BETA_K
    )

    return {
        "temp_trip_from_ramp_time_k": temp_from_ramp_time_k,
        "temp_trip_from_probe_node_k": temp_from_meas_node_k,
        "temp_trip_from_divider_voltage_k": temp_from_divider_voltage_k,
        "r_ntc_at_trip_ohm": r_ntc_trip_ohm,
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
    agreement_k = max(
        abs(derived["temp_trip_from_ramp_time_k"] - derived["temp_trip_from_probe_node_k"]),
        abs(derived["temp_trip_from_probe_node_k"] - derived["temp_trip_from_divider_voltage_k"]),
    )
    within_spec = temp_trip_c <= THM01_SPEC_TRIP_C

    return {
        "schema_version": 1,
        "measurement_date": _dt.date.today().isoformat(),
        "invocation": invocation,
        "harness": "simulation/harness/run_thm01_sim.py",
        "netlist": "simulation/harness/nets/thm01_trip_point.cir",
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
                "file": "simulation/harness/nets/thm01_trip_point.cir (inline B-source)",
                "subckt": "NTC Beta-equation behavioral model",
                "calibrated": False,
                "note": (
                    "R25=100k, B=4190K sourced read-only from "
                    "elec/src/modules.ato ThermalComparator's inline "
                    "comment (citing NTCALUG01A104GA). No Steinhart-Hart "
                    "table for this part is committed anywhere in this "
                    "repo; the Beta-equation approximation is the design's "
                    "own basis, not an independent addition by this "
                    "harness. 'Temperature' is an idealized ramped proxy "
                    "signal, not a thermal-mass or thermal-time-constant "
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
            "citation": "elec/src/modules.ato: ThermalComparator",
        },
        "implementation_scope": {
            "instances_of_ThermalComparator_in_modules_ato": 1,
            "instantiated_as": "SafetyInterlock.thermal (elec/src/modules.ato ~line 1790)",
            "physical_mounting_per_comment": "lug-mount on heatsink (NTCALUG01A104GA)",
            "coil_ntc_circuit_exists": False,
            "note": (
                "Only one ThermalComparator is instantiated anywhere in "
                "elec/src/modules.ato. There is no second thermal-sense "
                "circuit for a coil NTC. THM-02 (coil NTC, 120 degC) has "
                "no implementing circuit to simulate -- this is a separate, "
                "reported finding, not a simulation result for THM-02."
            ),
        },
        "measurements": measurements,
        "derived": derived,
        "internal_consistency_check_k": agreement_k,
        "verdict": {
            "calibrated": False,
            "measured_trip_temp_c": round(temp_trip_c, 2),
            "measured_trip_temp_k": round(temp_trip_k, 2),
            "thm01_spec_trip_c": THM01_SPEC_TRIP_C,
            "thm01_spec_recover_c": THM01_SPEC_RECOVER_C,
            "within_thm01_spec": within_spec,
            "docstring_claim_c": DOCSTRING_CLAIM_C,
            "matches_docstring_claim": abs(temp_trip_c - DOCSTRING_CLAIM_C) < 2.0,
            "design_comment_unloaded_estimate_c": DESIGN_COMMENT_UNLOADED_ESTIMATE_C,
            "matches_design_comment_estimate": abs(
                temp_trip_c - DESIGN_COMMENT_UNLOADED_ESTIMATE_C
            ) < 5.0,
            "response_time_measured": False,
            "response_time_reason": (
                "TLV3201_ngspice.lib declares no timing model; the ramped "
                "'temperature' driver is an idealized proxy, not a thermal "
                "time-constant simulation."
            ),
            "summary": (
                f"Simulated THM-01 (heatsink NTC) trip temperature is "
                f"{temp_trip_c:.2f} degC (uncalibrated). This EXCEEDS the "
                f"THM-01 85 degC trip spec -- the divider as committed "
                f"lets the heatsink reach ~{temp_trip_c:.0f} degC before "
                f"shutdown, {temp_trip_c - THM01_SPEC_TRIP_C:.1f} degC "
                f"past the declared limit. It does NOT match the "
                f"ThermalComparator module's own docstring claim of an "
                f"'85C threshold'; it is close to (but slightly above, "
                f"after correctly accounting for r_hyst loading the "
                f"pre-trip reference) the module's own inline comment "
                f"estimate of ~96 degC. This is a mis-valued divider, not "
                f"an unreachable target: unlike OCP-01's 50A (which is "
                f"physically unreachable from a 3.3V rail with a 1:100 "
                f"CT), an 85 degC trip IS reachable with this NTC/divider "
                f"topology by changing r_ref_top/r_ref_bot -- this harness "
                f"reports the discrepancy, it does not propose or apply a "
                f"fix."
                if not within_spec
                else f"Simulated THM-01 trip temperature is {temp_trip_c:.2f} "
                f"degC (uncalibrated), within the THM-01 85 degC spec."
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
    derived = derive_trip_temperature(measurements)

    invocation = "uv run python simulation/harness/run_thm01_sim.py --runs " + str(
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
        out_path = REPO_ROOT / "docs" / "evidence" / f"{date_str}-thm01-trip-point-sim.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(evidence, indent=2) + "\n")

    print(f"Deterministic across {len(stdout_runs)} runs: {deterministic}")
    print(json.dumps(evidence["verdict"], indent=2))
    print(f"Evidence written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
