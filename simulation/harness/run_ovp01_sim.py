#!/usr/bin/env python3
"""Scriptable, non-interactive ngspice harness for the OVP-01 trip AND
release-voltage transient (simulation/harness/nets/ovp01_trip_point.cir).

Same template as run_ocp01_sim.py, applied to OVPComparator
(elec/src/modules.ato) instead of OCPComparator.

What it measures
-----------------
A bus-voltage ramp (0 -> 500 V over 250us, THEN BACK DOWN to 0 V over the
next 250us) is driven onto the `v_bus.line` node exactly as OVPComparator's
resistor divider is wired (3x 430 kohm top / 10 kohm bottom -> comp.INP;
1.1 kohm / 10 kohm off the 3.3 V rail -> comp.INN; a NEW 287 kohm
hysteresis resistor from comp.INP back to comp.OUT), feeding a TLV3201
comparator model (simulation/models/TLV3201_ngspice.lib). All resistor
values are copied read-only from elec/src/modules.ato::OVPComparator, as
of the 2026-07-26 hysteresis fix; this script and its netlist never
modify anything under elec/.

The up-then-down ramp lets ONE transient run capture both the TRIP
threshold, on the way up, and the RELEASE threshold, on the way down --
the release threshold only exists once the comparator output has actually
latched high via r_hyst positive feedback on the bus-sense node (INP),
not the reference node (INN, unlike ThermalComparator).

It reports the v_bus.line voltage at which the comparator trips and
releases, and compares them against:
  - The hand-derived divider trip/release points (399.8 V trip, 385.0 V
    release, from OVPComparator's own inline comment).
  - OVP-01's declared 390-410 V trip window and 10-20V hysteresis window
    (docs/FUNCTIONAL_TEST_CRITERIA.md SS2.2).

What "v_bus.line" physically is
--------------------------------
main.ato wires `safety.dc_bus.line ~ dc_bus.line`, the FULL DC bus
(resolved 2026-07-26 -- an earlier revision of this harness carried a
stale "half-bus doubling" narrative from when the source was ambiguous;
see docs/hardware/PROTECTION_CHAIN_REVIEW.md for the resolution history).
This harness measures the divider circuit as wired: the trip/release
points at the v_bus.line node, which is what the comparator actually
sees, with no doubling assumption needed.

What it does NOT measure
-------------------------
Propagation delay. TLV3201_ngspice.lib declares no timing model.

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
# OVPComparator, as of the 2026-07-26 hysteresis fix.
VCC_V = 3.3
R_DIV_TOP_OHM = 430_000 * 3
R_DIV_BOT_OHM = 10_000
R_REF_TOP_OHM = 1_100  # CHANGED from 732 ohm
R_REF_BOT_OHM = 10_000
R_HYST_OHM = 287_000  # NEW -- comp.INP (bus-sense node) to comp.OUT

# Hand-derived, from the divider values above (see netlist header for the
# full node-equation derivation):
#   V(INN) = 3.3 * 10000/(1100+10000) = 2.97297 V
#   Pre-trip (comp.OUT ~ 0V):  V_bus_trip = 399.85 V
#   Post-trip (comp.OUT ~ VCC): V_bus_release = 385.02 V
HAND_DERIVED_TRIP_V_BUS_NODE_V = 399.85
HAND_DERIVED_RELEASE_V_BUS_NODE_V = 385.02

# Ramp shape, mirrored from the netlist's .param block (read-only copy for
# the independent ramp-time cross-check derivation).
RAMP_MAX_V = 500.0
T_UP_S = 250e-6
T_DOWN_S = 250e-6

OVP01_SPEC_MIN_V = 390.0
OVP01_SPEC_MAX_V = 410.0
OVP01_HYST_MIN_V = 10.0
OVP01_HYST_MAX_V = 20.0

T_TRIP_RE = re.compile(r"^t_trip\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE)
T_RELEASE_RE = re.compile(r"^t_release\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE)
V_BUS_TRIP_RE = re.compile(r"^v_bus_at_trip\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE)
V_BUS_RELEASE_RE = re.compile(
    r"^v_bus_at_release\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE
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
        "v_bus_at_trip_v": V_BUS_TRIP_RE.search(stdout),
        "v_bus_at_release_v": V_BUS_RELEASE_RE.search(stdout),
    }
    missing = [k for k, v in matches.items() if v is None]
    if missing:
        raise HarnessError(
            f"could not parse {missing} from ngspice stdout -- the "
            "comparator may never have tripped and/or released within the "
            f"500us up/down ramp window.\n--- stdout ---\n{stdout}"
        )
    return {k: float(v.group(1)) for k, v in matches.items()}


def temp_from_ramp_time_v(t_s: float) -> float:
    """Independent ramp-time cross-check, valid on either leg of the
    up-then-down ramp (mirrors the netlist's PWL breakpoints)."""
    if t_s <= T_UP_S:
        return RAMP_MAX_V * (t_s / T_UP_S)
    t_down = t_s - T_UP_S
    return RAMP_MAX_V - RAMP_MAX_V * (t_down / T_DOWN_S)


def derive_trip_and_release(measurements: dict[str, float]) -> dict[str, float]:
    """Two independent derivations of the trip and release voltage from
    the same run."""
    v_trip_from_ramp_time = temp_from_ramp_time_v(measurements["t_trip_s"])
    v_release_from_ramp_time = temp_from_ramp_time_v(measurements["t_release_s"])
    return {
        "v_bus_trip_from_ramp_time_v": v_trip_from_ramp_time,
        "v_bus_trip_from_node_voltage_v": measurements["v_bus_at_trip_v"],
        "v_bus_release_from_ramp_time_v": v_release_from_ramp_time,
        "v_bus_release_from_node_voltage_v": measurements["v_bus_at_release_v"],
    }


def build_evidence(
    measurements: dict[str, float],
    derived: dict[str, float],
    invocation: str,
    determinism_runs: int,
    deterministic: bool,
) -> dict:
    v_bus_trip = derived["v_bus_trip_from_node_voltage_v"]
    v_bus_release = derived["v_bus_release_from_node_voltage_v"]
    hysteresis_v = v_bus_trip - v_bus_release

    trip_agreement_v = abs(
        derived["v_bus_trip_from_ramp_time_v"]
        - derived["v_bus_trip_from_node_voltage_v"]
    )
    release_agreement_v = abs(
        derived["v_bus_release_from_ramp_time_v"]
        - derived["v_bus_release_from_node_voltage_v"]
    )

    in_trip_window = OVP01_SPEC_MIN_V <= v_bus_trip <= OVP01_SPEC_MAX_V
    in_hyst_window = OVP01_HYST_MIN_V <= hysteresis_v <= OVP01_HYST_MAX_V
    within_spec = in_trip_window and in_hyst_window

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
            "r_hyst_ohm": R_HYST_OHM,
            "citation": "elec/src/modules.ato: OVPComparator",
        },
        "v_bus_line_node_identity": {
            "wired_to": "dc_bus.line, the FULL DC bus (elec/src/main.ato: safety.dc_bus.line ~ dc_bus.line)",
            "resolution_note": (
                "RESOLVED 2026-07-26: the divider senses the full bus, not "
                "a half-bus requiring a x2 doubling assumption. An earlier "
                "revision of this harness carried a stale half-bus/doubling "
                "narrative left over from when main.ato's own comments "
                "contradicted each other; see "
                "docs/hardware/PROTECTION_CHAIN_REVIEW.md for the "
                "resolution history."
            ),
        },
        "measurements": measurements,
        "derived": derived,
        "internal_consistency_check_trip_v": trip_agreement_v,
        "internal_consistency_check_release_v": release_agreement_v,
        "verdict": {
            "calibrated": False,
            "measured_trip_v_bus_line_v": round(v_bus_trip, 3),
            "measured_release_v_bus_line_v": round(v_bus_release, 3),
            "measured_hysteresis_v": round(hysteresis_v, 3),
            "hand_derived_trip_v_bus_line_v": HAND_DERIVED_TRIP_V_BUS_NODE_V,
            "hand_derived_release_v_bus_line_v": HAND_DERIVED_RELEASE_V_BUS_NODE_V,
            "hand_sim_trip_agreement_v": round(
                abs(v_bus_trip - HAND_DERIVED_TRIP_V_BUS_NODE_V), 4
            ),
            "hand_sim_release_agreement_v": round(
                abs(v_bus_release - HAND_DERIVED_RELEASE_V_BUS_NODE_V), 4
            ),
            "ovp01_spec_trip_window_v": [OVP01_SPEC_MIN_V, OVP01_SPEC_MAX_V],
            "ovp01_spec_hysteresis_window_v": [OVP01_HYST_MIN_V, OVP01_HYST_MAX_V],
            "within_ovp01_trip_window": in_trip_window,
            "within_ovp01_hysteresis_window": in_hyst_window,
            "within_ovp01_spec": within_spec,
            "propagation_delay_measured": False,
            "propagation_delay_reason": (
                "TLV3201_ngspice.lib declares no timing model; a measured "
                "delay from this model would be a modelling artifact, not "
                "physical."
            ),
            "summary": (
                f"Simulated OVP-01 trip point at the v_bus.line node is "
                f"{v_bus_trip:.2f} V and release point is "
                f"{v_bus_release:.2f} V (uncalibrated), giving "
                f"{hysteresis_v:.2f} V of hysteresis. This is "
                f"{'WITHIN' if within_spec else 'OUTSIDE'} the OVP-01 "
                f"390-410V trip / 10-20V hysteresis requirement "
                f"(FUNCTIONAL_TEST_CRITERIA.md SS2.2), matching the "
                f"OVPComparator module's own inline hand-derivation "
                f"(399.8V trip, 385.0V release) to within "
                f"{abs(v_bus_trip - HAND_DERIVED_TRIP_V_BUS_NODE_V):.2f} V / "
                f"{abs(v_bus_release - HAND_DERIVED_RELEASE_V_BUS_NODE_V):.2f} V."
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
