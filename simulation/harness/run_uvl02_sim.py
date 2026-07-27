#!/usr/bin/env python3
"""Scriptable, non-interactive ngspice harness for a UVL-02 CANDIDATE
circuit: the TPS3700 rail_monitor divider inside RTDSensing
(elec/src/modules.ato), simulated in
simulation/harness/nets/uvl02_rtd_avdd_monitor_trip_point.cir.

IMPORTANT SCOPE CAVEAT -- read before trusting this as "the" UVL-02 answer
---------------------------------------------------------------------------
UVL-02 is defined in docs/FUNCTIONAL_TEST_CRITERIA.md SS2.4 as "Logic (3.3V)
rail, trip < 2.9V falling, recover > 3.0V rising." A grep of
elec/src/modules.ato and elec/src/main.ato for UVLO / undervoltage /
brownout circuitry turns up exactly two candidates, NEITHER of which is
labelled anywhere as "the" system logic UVLO:

  1. TPS3823-33 (Watchdog module, elec/src/modules.ato). Per
     docs/hardware/SAFETY_INTERLOCK_DESIGN.md SS "Voltage Supervision" table
     and prose: "The TPS3823-33 also monitors VDD and asserts RESET if
     voltage drops below 2.93V (typical)." This is the far more literal
     candidate (whole-board VDD supervisor, threshold in the same 2.9-3.0V
     ballpark as the UVL-02 spec) -- but it is a FIXED SILICON THRESHOLD set
     by the "-33" part suffix, not a resistor divider read from elec/, and
     simulation/models/ has NO TPS3823 SPICE model. This candidate is
     UNMEASURED by any harness; see the evidence JSON's `unmeasured_
     candidate` section. TI's published TPS3823-33 VIT tolerance band
     (min/typ/max, quoted secondhand via the design doc, NOT independently
     verified against a primary datasheet by this harness) already brackets
     the 2.9V spec line, which is itself worth flagging but is not a SPICE
     measurement.

  2. TPS3700 rail_monitor (RTDSensing module, elec/src/modules.ato) -- THIS
     harness's subject. It IS a resistor-divider circuit with committed
     elec/ values and a model in simulation/models/TPS3700_ngspice.lib, so
     it is genuinely simulatable. But its own component docstring
     (elec/src/components.ato: "Dual window supervisor; OUTA is low on
     RTD_AVDD undervoltage") and its own module comment scope it to the
     RTD analog front-end's local rail (RTD_AVDD, post-ferrite-bead), not
     to the board's general logic supply. It IS wired into the shared
     SafetyInterlock fault-OR tree (rtd_hw_fault -> fault_any_or), so a
     live trip here does reach the overall hardware fault latch -- but
     reporting this number AS UVL-02 would be asserting a mapping the
     source does not itself state. This harness reports the number as
     "UVL-02 candidate," not as a confirmed UVL-02 PASS/FAIL.

What it measures
-----------------
power_3v3 (which also directly powers rail_monitor.VDD, pre-ferrite) is
ramped down 3.3V -> 0V over 330us, modeling a board-wide brownout. The
divider on INA_P (619 kohm / 100 kohm -- corrected 2026-07-27 from the
fabricated 616 kohm/ERA-3AEB6163V, see
docs/evidence/2026-07-27-era-resistor-resolution.md -- post the 120-ohm "ferrite bead"
placeholder resistor -- elec/src/modules.ato's own comment: "Using
Resistor component as generic placeholder for Ferrite Bead") feeds the
TPS3700 behavioral model's fixed INA threshold (394.5 mV, sourced from the
model file's own header, itself citing TI's TPS3700 PSpice model and
datasheet -- NOT an elec/ value, since TPS3700 has no external
threshold-setting pins). OUTA is externally pulled up (10 kohm, committed
r_rail_ok_pullup) and its falling edge marks the trip.

What it does NOT measure
-------------------------
- The TPS3823-33 candidate described above (no model, no divider -- see
  scope caveat).
- Propagation delay: TPS3700_ngspice.lib is a static behavioral model with
  no timing information.
- The rising RECOVER threshold's hysteresis (the model header shows no
  separate rising/falling thresholds; VIT_A is used both ways in this
  model, unlike a real TPS3700 which likely has some finite hysteresis
  band the datasheet quantifies and this behavioral port does not).

Calibration
-----------
Every model used carries `calibrated: false`.

Determinism
-----------
Per METHODOLOGY.md SS5, this script runs the deck N times (default 5) and
asserts byte-identical stdout before trusting any single run's numbers.

Usage
-----
    uv run python simulation/harness/run_uvl02_sim.py [--runs N] [--out PATH]

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
NETLIST = HARNESS_DIR / "nets" / "uvl02_rtd_avdd_monitor_trip_point.cir"

# Component values below are copied read-only from elec/src/modules.ato ::
# RTDSensing.rail_monitor. The 394.5mV VIT_A threshold is NOT an elec/
# value -- it is the TPS3700 behavioral model's own fixed parameter
# (simulation/models/TPS3700_ngspice.lib header), since TPS3700 has no
# external threshold-setting pins.
VCC_V = 3.3
R_FB_OHM = 120
R_AVDD_TOP_OHM = 619_000  # corrected 2026-07-27, was 616_000 (fabricated)
R_AVDD_BOT_OHM = 100_000
R_PULLUP_OHM = 10_000
TPS3700_VIT_A_V = 0.3945

# Computed, not hand-copied, so this can never drift from the constants
# above the way the previous hardcoded 2.8250 literal did after the 2026-07-27
# r_avdd_top correction (616k -> 619k).
HAND_DERIVED_TRIP_V_VCC_V = round(
    TPS3700_VIT_A_V * (R_AVDD_TOP_OHM + R_AVDD_BOT_OHM) / R_AVDD_BOT_OHM, 4
)

UVL02_SPEC_TRIP_MAX_V = 2.9  # "trip < 2.9V falling"
UVL02_SPEC_RECOVER_MIN_V = 3.0

T_TRIP_RE = re.compile(r"^t_trip\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE)
V_INA_RE = re.compile(r"^v_ina_p_at_trip\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE)
V_VCC_RE = re.compile(r"^v_vcc_at_trip\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE)
V_AVDD_RE = re.compile(r"^v_avdd_post_fb_at_trip\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE)


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
        "v_ina_p_at_trip_v": V_INA_RE.search(stdout),
        "v_vcc_at_trip_v": V_VCC_RE.search(stdout),
        "v_avdd_post_fb_at_trip_v": V_AVDD_RE.search(stdout),
    }
    if any(m is None for m in matches.values()):
        raise HarnessError(
            "could not parse all measurements from ngspice stdout -- the "
            f"comparator may never have tripped.\n--- stdout ---\n{stdout}"
        )
    return {k: float(m.group(1)) for k, m in matches.items()}


def derive_trip_voltage(measurements: dict[str, float]) -> dict[str, float]:
    ramp_time_s = 330e-6
    v_start = 3.3
    v_end = 0.0
    v_vcc_from_ramp_time = v_start + (v_end - v_start) * (
        measurements["t_trip_s"] / ramp_time_s
    )
    ferrite_drop_at_trip_v = (
        measurements["v_vcc_at_trip_v"] - measurements["v_avdd_post_fb_at_trip_v"]
    )
    return {
        "v_vcc_trip_from_ramp_time_v": v_vcc_from_ramp_time,
        "v_vcc_trip_from_node_voltage_v": measurements["v_vcc_at_trip_v"],
        "ferrite_bead_drop_at_trip_v": ferrite_drop_at_trip_v,
    }


def build_evidence(
    measurements: dict[str, float],
    derived: dict[str, float],
    invocation: str,
    determinism_runs: int,
    deterministic: bool,
) -> dict:
    v_trip = derived["v_vcc_trip_from_node_voltage_v"]
    agreement_v = abs(
        derived["v_vcc_trip_from_ramp_time_v"] - derived["v_vcc_trip_from_node_voltage_v"]
    )
    below_uvl02_ceiling = v_trip < UVL02_SPEC_TRIP_MAX_V

    return {
        "schema_version": 1,
        "measurement_date": _dt.date.today().isoformat(),
        "invocation": invocation,
        "harness": "simulation/harness/run_uvl02_sim.py",
        "netlist": "simulation/harness/nets/uvl02_rtd_avdd_monitor_trip_point.cir",
        "gate_scope_caveat": (
            "This measures a CANDIDATE circuit (RTDSensing.rail_monitor / "
            "TPS3700), not a source-confirmed implementation of UVL-02. "
            "See this script's module docstring for the two candidates "
            "found and why neither is unambiguous. The literal whole-board "
            "logic-supply supervisor is TPS3823-33 (Watchdog module), "
            "which has no SPICE model and a fixed silicon threshold -- "
            "reported UNMEASURED, not simulated here."
        ),
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
                "file": "simulation/models/TPS3700_ngspice.lib",
                "subckt": "TPS3700_NGSPICE",
                "calibrated": False,
                "note": (
                    "VIT_A=394.5mV is the model's own header default, "
                    "sourced from TI's TPS3700 PSpice transient model "
                    "(SBVM552B) and datasheet -- not read from elec/, since "
                    "TPS3700 has no external threshold-setting pins."
                ),
            },
        ],
        "sourced_from_elec_read_only": {
            "power_3v3_v": VCC_V,
            "r_fb_ohm": R_FB_OHM,
            "r_avdd_top_ohm": R_AVDD_TOP_OHM,
            "r_avdd_bot_ohm": R_AVDD_BOT_OHM,
            "r_pullup_ohm": R_PULLUP_OHM,
            "citation": "elec/src/modules.ato: RTDSensing (rail_monitor, fb_power, r_avdd_top, r_avdd_bottom, r_rail_ok_pullup)",
        },
        "measurements": measurements,
        "derived": derived,
        "internal_consistency_check_v": agreement_v,
        "unmeasured_candidate": {
            "circuit": "TPS3823-33 (Watchdog module, elec/src/modules.ato)",
            "reason_unmeasured": (
                "No SPICE model exists in simulation/models/ for TPS3823. "
                "Its VDD-brownout threshold (2.93V typical, per "
                "docs/hardware/SAFETY_INTERLOCK_DESIGN.md, itself citing "
                "the TI datasheet secondhand) is a fixed silicon parameter "
                "set by the '-33' part suffix, not a resistor divider read "
                "from elec/ -- there is no board-level circuit topology to "
                "build a .cir against."
            ),
            "measured": False,
        },
        "verdict": {
            "calibrated": False,
            "measured_trip_v_vcc_v": round(v_trip, 4),
            "hand_derived_trip_v_vcc_v": HAND_DERIVED_TRIP_V_VCC_V,
            "hand_sim_agreement_v": round(abs(v_trip - HAND_DERIVED_TRIP_V_VCC_V), 4),
            "uvl02_spec_trip_ceiling_v": UVL02_SPEC_TRIP_MAX_V,
            "uvl02_spec_recover_floor_v": UVL02_SPEC_RECOVER_MIN_V,
            "candidate_below_uvl02_trip_ceiling": below_uvl02_ceiling,
            "gate_confirmed_as_uvl02": False,
            "summary": (
                f"The TPS3700 rail_monitor CANDIDATE circuit trips at "
                f"V(power_3v3)={v_trip:.3f} V (uncalibrated), matching the "
                f"hand-derived {HAND_DERIVED_TRIP_V_VCC_V:.4f} V to within "
                f"{abs(v_trip - HAND_DERIVED_TRIP_V_VCC_V):.4f} V. That number sits BELOW the "
                f"UVL-02 spec's 2.9V trip ceiling, i.e. on the conservative "
                f"side: IF this circuit were confirmed as UVL-02, it would "
                f"trip at {HAND_DERIVED_TRIP_V_VCC_V:.4f}V, before the rail falls all the way to the "
                f"2.9V line the spec treats as the last safe point -- "
                f"earlier/more conservative than the spec requires, not a "
                f"failure to trip in time. But this circuit monitors RTD_AVDD, a "
                f"downstream RTD-subsystem rail, per its own component "
                f"docstring -- it is not source-confirmed as the general "
                f"'Logic (3.3V) UVLO' gate. The more literal candidate "
                f"(TPS3823-33 whole-board VDD supervisor, 2.93V typical) "
                f"is UNMEASURED: no SPICE model exists for it."
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

    invocation = "uv run python simulation/harness/run_uvl02_sim.py --runs " + str(
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
        out_path = (
            REPO_ROOT
            / "docs"
            / "evidence"
            / f"{date_str}-uvl02-rtd-avdd-monitor-candidate-sim.json"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(evidence, indent=2) + "\n")

    print(f"Deterministic across {len(stdout_runs)} runs: {deterministic}")
    print(json.dumps(evidence["verdict"], indent=2))
    print(f"Evidence written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
