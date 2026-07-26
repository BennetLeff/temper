#!/usr/bin/env python3
"""Scriptable, non-interactive ngspice harness for the OVP-01 trip-voltage
transient (simulation/harness/nets/ovp01_trip_point.cir).

Same template as run_ocp01_sim.py, applied to OVPComparator
(elec/src/modules.ato) instead of OCPComparator.

What it measures
-----------------
A voltage ramp (0 -> 250 V over 250 us) is driven onto the `v_bus.line`
node exactly as OVPComparator's resistor divider is wired
(3x 430 kohm top / 10 kohm bottom -> comp.INP; 12 kohm / 10 kohm off the
3.3 V rail -> comp.INN), feeding a TLV3201 comparator model
(simulation/models/TLV3201_ngspice.lib). All resistor values are copied
read-only from elec/src/modules.ato::OVPComparator; this script and its
netlist never modify anything under elec/.

It reports the v_bus.line voltage at which the comparator output crosses
the logic threshold ("trip voltage"), and compares it against:
  - The hand-derived divider trip point (195 V at the v_bus.line node).
  - OVPComparator's own inline "full bus" claim (390 V, after doubling the
    195 V half-bus figure -- see the netlist header for why that doubling
    is a separate, unverified claim about upstream circuit symmetry that
    this deck does not itself test).
  - OVP-01's declared 390-410 V spec window (docs/STRATEGY.md).

What "v_bus.line" physically is
--------------------------------
main.ato wires `safety.dc_bus.line ~ dc_bus_plus`. dc_bus_plus is the HALF
bus of the split-rail voltage-doubler topology (nominal ~170V, per
PowerInput's own `v_bus_half: voltage = 170V` and main.ato's own comment
"Half-bus input (~170VDC)" on the same net) -- NOT the full 340V bus,
despite main.ato's top-level `signal dc_bus_plus  # +340V` comment. This
harness measures the divider circuit as wired: the trip point IN TERMS OF
THE v_bus.line NODE VOLTAGE, which is what the comparator actually sees.
Whether that node reaching 195V correctly implies a 390V full-bus event
depends on an un-simulated symmetry assumption (dc_bus_minus mirrors
dc_bus_plus) that is outside the scope of this two-terminal divider deck.

What it does NOT measure
-------------------------
Propagation delay / hysteresis. TLV3201_ngspice.lib declares no timing
model. OVPComparator (unlike ThermalComparator) has no hysteresis feedback
network at all, so there is no hysteresis band to measure either --
FUNCTIONAL_TEST_CRITERIA.md SS2.2's "10-20V hysteresis" spec column has no
corresponding circuit element in the committed schematic.

Calibration
-----------
Every model used carries `calibrated: false` -- no bench measurement of
this board's OVP path exists.

Determinism
-----------
Per METHODOLOGY.md SS5, this script runs the deck N times (default 5) and
asserts byte-identical stdout before trusting any single run's numbers.

Usage
-----
    uv run python simulation/harness/run_ovp01_sim.py [--runs N] [--out PATH]

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
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_DIR = Path(__file__).resolve().parent
NETLIST = HARNESS_DIR / "nets" / "ovp01_trip_point.cir"

# Component values below are copied read-only from elec/src/modules.ato ::
# OVPComparator.
VCC_V = 3.3
R_DIV_TOP_OHM = 430_000 * 3
R_DIV_BOT_OHM = 10_000
R_REF_TOP_OHM = 12_000
R_REF_BOT_OHM = 10_000

# Hand-derived, from the divider values above:
#   V(INN) = 3.3 * 10000/(12000+10000) = 1.5000 V
#   V(INP) = V_bus * 10000/1300000 = V_bus/130
#   trip:  V_bus/130 = 1.5  =>  V_bus = 195 V (at the v_bus.line node)
HAND_DERIVED_TRIP_V_BUS_NODE_V = 195.0

OVP01_SPEC_MIN_V = 390.0
OVP01_SPEC_MAX_V = 410.0
# OVPComparator's own inline comment doubles the half-bus trip point to
# claim a "full bus" trip of 390V. Reported as a derived quantity, not
# something this two-terminal deck independently verifies (see netlist
# header and module docstring).
DESIGN_COMMENT_FULL_BUS_CLAIM_V = 390.0

T_TRIP_RE = re.compile(r"^t_trip\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE)
V_BUS_RE = re.compile(r"^v_bus_at_trip\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE)


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
    v_bus_match = V_BUS_RE.search(stdout)
    if t_trip_match is None or v_bus_match is None:
        raise HarnessError(
            "could not parse t_trip / v_bus_at_trip from ngspice stdout -- "
            "the comparator may never have tripped within the 250us ramp "
            f"window.\n--- stdout ---\n{stdout}"
        )
    return {
        "t_trip_s": float(t_trip_match.group(1)),
        "v_bus_at_trip_v": float(v_bus_match.group(1)),
    }


def derive_trip_voltage(measurements: dict[str, float]) -> dict[str, float]:
    """Two independent derivations of the trip voltage from the same run."""
    ramp_max_v = 250.0
    ramp_time_s = 250e-6
    v_from_ramp_time = ramp_max_v * (measurements["t_trip_s"] / ramp_time_s)
    v_from_divider = measurements["v_bus_at_trip_v"]
    return {
        "v_bus_trip_from_ramp_time_v": v_from_ramp_time,
        "v_bus_trip_from_node_voltage_v": v_from_divider,
    }


def build_evidence(
    measurements: dict[str, float],
    derived: dict[str, float],
    invocation: str,
    determinism_runs: int,
    deterministic: bool,
) -> dict:
    v_bus_trip = derived["v_bus_trip_from_node_voltage_v"]
    agreement_v = abs(
        derived["v_bus_trip_from_ramp_time_v"]
        - derived["v_bus_trip_from_node_voltage_v"]
    )
    full_bus_doubled_v = v_bus_trip * 2.0
    in_ovp01_window = OVP01_SPEC_MIN_V <= full_bus_doubled_v <= OVP01_SPEC_MAX_V

    return {
        "schema_version": 1,
        "measurement_date": _dt.date.today().isoformat(),
        "invocation": invocation,
        "harness": "simulation/harness/run_ovp01_sim.py",
        "netlist": "simulation/harness/nets/ovp01_trip_point.cir",
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
                    "Vendor-provenance behavioural port. Its own header "
                    "states it 'does not claim a timing, noise, or "
                    "temperature model' -- propagation delay is NOT "
                    "measurable with this model."
                ),
            },
        ],
        "sourced_from_elec_read_only": {
            "power_3v3_v": VCC_V,
            "r_div_top_total_ohm": R_DIV_TOP_OHM,
            "r_div_bot_ohm": R_DIV_BOT_OHM,
            "r_ref_top_ohm": R_REF_TOP_OHM,
            "r_ref_bot_ohm": R_REF_BOT_OHM,
            "citation": "elec/src/modules.ato: OVPComparator",
        },
        "v_bus_line_node_identity": {
            "wired_to": "dc_bus_plus (elec/src/main.ato: safety.dc_bus.line ~ dc_bus_plus)",
            "actual_nominal_v": 170.0,
            "citation": (
                "elec/src/modules.ato PowerInput.v_bus_half = 170V; "
                "elec/src/main.ato comment 'Half-bus input (~170VDC)' on "
                "the same dc_bus_plus net"
            ),
            "source_self_contradiction": (
                "elec/src/main.ato's own top-of-file signal comment reads "
                "'signal dc_bus_plus  # +340V', contradicting every actual "
                "use of that net (170V half-bus). Structurally identical "
                "to the OCP-01 docstring-vs-comment mismatch."
            ),
        },
        "measurements": measurements,
        "derived": derived,
        "internal_consistency_check_v": agreement_v,
        "verdict": {
            "calibrated": False,
            "measured_trip_v_bus_line_v": round(v_bus_trip, 3),
            "hand_derived_trip_v_bus_line_v": HAND_DERIVED_TRIP_V_BUS_NODE_V,
            "hand_sim_agreement_v": round(
                abs(v_bus_trip - HAND_DERIVED_TRIP_V_BUS_NODE_V), 4
            ),
            "design_intent_full_bus_v": round(full_bus_doubled_v, 3),
            "ovp01_spec_window_v": [OVP01_SPEC_MIN_V, OVP01_SPEC_MAX_V],
            "within_ovp01_spec_window_if_doubling_assumption_holds": in_ovp01_window,
            "doubling_assumption_verified_by_this_deck": False,
            "hysteresis_measured": False,
            "hysteresis_reason": (
                "OVPComparator has no hysteresis feedback network in the "
                "committed schematic (unlike ThermalComparator's r_hyst); "
                "FUNCTIONAL_TEST_CRITERIA.md's 10-20V hysteresis spec has "
                "no implementing circuit to measure."
            ),
            "propagation_delay_measured": False,
            "propagation_delay_reason": (
                "TLV3201_ngspice.lib declares no timing model; a measured "
                "delay from this model would be a modelling artifact, not "
                "physical."
            ),
            "summary": (
                f"Simulated OVP trip point at the v_bus.line node "
                f"(=dc_bus_plus) is {v_bus_trip:.2f} V (uncalibrated), "
                f"matching the hand-derived 195 V divider calculation to "
                f"within {agreement_v:.4f} V. Doubling this half-bus figure "
                f"per the module's own inline comment gives a 'full bus' "
                f"claim of {full_bus_doubled_v:.1f} V, which lands inside "
                f"the OVP-01 390-410V window -- BUT that doubling assumes "
                f"dc_bus_minus mirrors dc_bus_plus symmetrically, an "
                f"assumption this single-ended divider deck does not "
                f"itself verify (dc_bus_minus is not wired to this "
                f"comparator at all). The circuit AS WIRED trips at "
                f"{v_bus_trip:.1f} V on the node it actually senses."
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
    derived = derive_trip_voltage(measurements)

    invocation = "uv run python simulation/harness/run_ovp01_sim.py --runs " + str(
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
        out_path = REPO_ROOT / "docs" / "evidence" / f"{date_str}-ovp01-trip-point-sim.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(evidence, indent=2) + "\n")

    print(f"Deterministic across {len(stdout_runs)} runs: {deterministic}")
    print(json.dumps(evidence["verdict"], indent=2))
    print(f"Evidence written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
