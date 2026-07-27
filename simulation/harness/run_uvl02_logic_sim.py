#!/usr/bin/env python3
"""Scriptable, non-interactive ngspice harness for the UVL-02 trip AND
recovery transient (simulation/harness/nets/uvl02_logic_uvlo_trip_point.cir).

Same template as run_thm02_sim.py, applied to LogicUVLOComparator
(elec/src/modules.ato) instead of CoilThermalComparator. UVL-02 (logic-rail
3.3V UVLO, FUNCTIONAL_TEST_CRITERIA.md SS2.4: trip <2.9V falling, recover
>3.0V rising) had NO CONFIRMED IMPLEMENTING CIRCUIT until 2026-07-26 -- two
candidates existed (TPS3823-33's fixed-silicon VDD supervisor, and
RTDSensing.rail_monitor, which measures a different rail) and neither
qualified. See docs/hardware/UVL02_DESIGN.md for the full ambiguity
resolution and satisfiability analysis.

What it measures
-----------------
A VCC ramp (3.3V -> 2.0V over 300us, THEN BACK UP to 3.4V over the next
300us) drives LogicUVLOComparator's TPS3700-based divider + positive
feedback network directly (simulation/models/TPS3700_ngspice.lib). This
script and its netlist never modify anything under elec/.

The down-then-up ramp lets ONE transient run capture both the TRIP (falling,
undervoltage-detected) threshold and the RECOVERY (rising, released)
threshold -- the recovery threshold only exists once OUTA has actually
latched low via r_hyst positive feedback.

It reports the trip and recovery voltages against:
  - UVL-02's declared <2.9V trip / >3.0V recovery requirement
    (docs/FUNCTIONAL_TEST_CRITERIA.md SS2.4).
  - LogicUVLOComparator's own inline hand-derivation (2.715V trip, 3.222V
    recovery, nominal).

What it does NOT measure
-------------------------
- Response time / propagation delay: TPS3700_ngspice.lib declares no timing
  model.
- Worst-case tolerance stackup: the model uses a single fixed VIT_A=394.5mV
  constant with no min/max spread, so this harness measures the NOMINAL
  design point only. The worst-case analysis (+/-1% resistors combined with
  the real TPS3700 datasheet's VIT- range of 387-400mV, 16-corner sweep) is
  a separate analytic calculation, reported in the verdict below and in
  docs/hardware/UVL02_DESIGN.md, NOT derived from this ngspice run.
- Real regulator/board dynamics: the VCC rail here is an idealized PWL
  voltage source, not a simulation of the actual buck-converter output
  under a real brownout event.

Calibration
-----------
Every model used carries `calibrated: false`. TPS3700_ngspice.lib's
VIT_A=394.5mV is a vendor-provenance macro default (TI's own PSpice
transient model plus datasheet), not a bench measurement of this board.

Determinism
-----------
Per METHODOLOGY.md SS5, this script runs the deck N times (default 5) and
asserts byte-identical stdout before trusting any single run's numbers.

Usage
-----
    uv run python simulation/harness/run_uvl02_logic_sim.py [--runs N] [--out PATH]

Exit codes
----------
    0  harness ran, ngspice was deterministic, evidence written
    1  ngspice not found / netlist failed to run
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
NETLIST = HARNESS_DIR / "nets" / "uvl02_logic_uvlo_trip_point.cir"

# Component values below are copied read-only from
# elec/src/modules.ato :: LogicUVLOComparator (added 2026-07-26).
VCC_NOM_V = 3.3
R_DIV_TOP_OHM = 698_000
R_DIV_BOT_OHM = 100_000
R_HYST_OHM = 3_740_000
R_OUTA_PULLUP_OHM = 10_000

# TPS3700_ngspice.lib model default (simulation/models/TPS3700_ngspice.lib
# header: "typical 394.5 mV INA threshold ... from TI's unencrypted TPS3700
# PSpice transient model (SBVM552B) and datasheet"). Used for the
# simulated/nominal cross-check.
VIT_A_MODEL_V = 0.3945

# Real TPS3700 datasheet (SBVS187G, TI, Feb 2019 rev) VIT- electrical spec,
# full VDD/temp range: min 387mV, typ 394.5mV, max 400mV. Used ONLY for the
# analytic worst-case corner sweep below -- NOT simulated, since
# TPS3700_ngspice.lib has no min/max parameterization.
VIT_A_DATASHEET_MIN_V = 0.387
VIT_A_DATASHEET_MAX_V = 0.400

RESISTOR_TOLERANCE = 0.01  # +/-1%, E96 parts per elec/src/modules.ato

UVL02_SPEC_TRIP_CEILING_V = 2.9
UVL02_SPEC_RECOVER_FLOOR_V = 3.0
DOCSTRING_CLAIM_TRIP_V = 2.715
DOCSTRING_CLAIM_RECOVER_V = 3.222
SPEC_MATCH_TOLERANCE_V = 0.05

T_TRIP_RE = re.compile(r"^t_trip\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE)
T_RELEASE_RE = re.compile(r"^t_release\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE)
V_VCC_TRIP_RE = re.compile(r"^v_vcc_at_trip\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE)
V_VCC_RELEASE_RE = re.compile(
    r"^v_vcc_at_release\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE
)
V_INA_TRIP_RE = re.compile(r"^v_ina_p_at_trip\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE)
V_INA_RELEASE_RE = re.compile(
    r"^v_ina_p_at_release\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE
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
        "v_vcc_at_trip_v": V_VCC_TRIP_RE.search(stdout),
        "v_vcc_at_release_v": V_VCC_RELEASE_RE.search(stdout),
        "v_ina_p_at_trip_v": V_INA_TRIP_RE.search(stdout),
        "v_ina_p_at_release_v": V_INA_RELEASE_RE.search(stdout),
    }
    missing = [k for k, v in matches.items() if v is None]
    if missing:
        raise HarnessError(
            f"could not parse {missing} from ngspice stdout -- the "
            "comparator may never have tripped and/or recovered within the "
            f"600us ramp window.\n--- stdout ---\n{stdout}"
        )
    return {k: float(v.group(1)) for k, v in matches.items()}


def trip_recover_from_dividers(
    r_top: float, r_bot: float, r_hyst: float, vit_a: float
) -> tuple[float, float]:
    """VCC_trip / VCC_recover from the divider + positive-feedback network.
    See LogicUVLOComparator's docstring for the derivation."""
    g_top = 1.0 / r_top
    g_bot = 1.0 / r_bot
    g_hyst = 1.0 / r_hyst
    trip = vit_a * (g_top + g_bot + g_hyst) / (g_top + g_hyst)
    recover = vit_a * (g_top + g_bot + g_hyst) / g_top
    return trip, recover


def worst_case_corners(
    r_top: float,
    r_bot: float,
    r_hyst: float,
    tol: float,
    vit_lo: float,
    vit_hi: float,
) -> dict[str, float]:
    """Exhaustive 16-corner sweep: each resistor independently at +/-tol,
    VIT_A at its datasheet min/max. Returns the worst (max) trip and worst
    (min) recovery across all corners -- the two directions that matter for
    clearing the UVL-02 window."""
    worst_trip = float("-inf")
    worst_recover = float("inf")
    best_trip = float("inf")
    best_recover = float("-inf")
    for rt_mult, rb_mult, rh_mult, vit in itertools.product(
        (1 - tol, 1 + tol), (1 - tol, 1 + tol), (1 - tol, 1 + tol), (vit_lo, vit_hi)
    ):
        trip, recover = trip_recover_from_dividers(
            r_top * rt_mult, r_bot * rb_mult, r_hyst * rh_mult, vit
        )
        worst_trip = max(worst_trip, trip)
        worst_recover = min(worst_recover, recover)
        best_trip = min(best_trip, trip)
        best_recover = max(best_recover, recover)
    return {
        "worst_case_trip_v": worst_trip,
        "worst_case_recovery_v": worst_recover,
        "best_case_trip_v": best_trip,
        "best_case_recovery_v": best_recover,
    }


def build_evidence(
    measurements: dict[str, float],
    invocation: str,
    determinism_runs: int,
    deterministic: bool,
) -> dict:
    trip_v = measurements["v_vcc_at_trip_v"]
    recover_v = measurements["v_vcc_at_release_v"]
    hysteresis_v = recover_v - trip_v

    hand_trip_v, hand_recover_v = trip_recover_from_dividers(
        R_DIV_TOP_OHM, R_DIV_BOT_OHM, R_HYST_OHM, VIT_A_MODEL_V
    )
    trip_agreement_v = abs(trip_v - hand_trip_v)
    recover_agreement_v = abs(recover_v - hand_recover_v)

    worst_case = worst_case_corners(
        R_DIV_TOP_OHM,
        R_DIV_BOT_OHM,
        R_HYST_OHM,
        RESISTOR_TOLERANCE,
        VIT_A_DATASHEET_MIN_V,
        VIT_A_DATASHEET_MAX_V,
    )

    trip_within_spec = trip_v < UVL02_SPEC_TRIP_CEILING_V
    recovery_within_spec = recover_v > UVL02_SPEC_RECOVER_FLOOR_V
    worst_case_trip_within_spec = (
        worst_case["worst_case_trip_v"] < UVL02_SPEC_TRIP_CEILING_V
    )
    worst_case_recovery_within_spec = (
        worst_case["worst_case_recovery_v"] > UVL02_SPEC_RECOVER_FLOOR_V
    )
    within_spec_nominal = trip_within_spec and recovery_within_spec
    within_spec_worst_case = (
        worst_case_trip_within_spec and worst_case_recovery_within_spec
    )

    return {
        "schema_version": 1,
        "measurement_date": _dt.date.today().isoformat(),
        "invocation": invocation,
        "harness": "simulation/harness/run_uvl02_logic_sim.py",
        "netlist": "simulation/harness/nets/uvl02_logic_uvlo_trip_point.cir",
        "gate_scope": (
            "This measures LogicUVLOComparator (elec/src/modules.ato), a NEW "
            "circuit directly monitoring power_3v3 (the board logic rail). "
            "It is the first circuit in this repository confirmed as UVL-02. "
            "Two prior candidates were rejected: TPS3823-33 (Watchdog "
            "module's fixed-silicon VDD supervisor -- verified against TI's "
            "datasheet to fail UVL-02 in both directions even at nominal, no "
            "SPICE model exists, UNMEASURED) and RTDSensing.rail_monitor "
            "(TPS3700 monitoring RTD_AVDD, a different rail, with no "
            "hysteresis resistor -- see "
            "docs/evidence/2026-07-25-uvl02-rtd-avdd-monitor-candidate-sim.json). "
            "This circuit's fault output is NOT wired into the interlock's "
            "fault_or/fault_any_or tree -- see 'implementation_scope' and "
            "'verdict.fault_wired_into_interlock' below. See "
            "docs/hardware/UVL02_DESIGN.md for the full resolution."
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
                    "(SBVM552B) and datasheet SBVS187G. Single fixed "
                    "threshold, no min/max spread, no internal hysteresis, "
                    "no timing model -- all hysteresis in this circuit "
                    "comes from the external r_hyst network."
                ),
            }
        ],
        "sourced_from_elec_read_only": {
            "power_3v3_nominal_v": VCC_NOM_V,
            "r_div_top_ohm": R_DIV_TOP_OHM,
            "r_div_bot_ohm": R_DIV_BOT_OHM,
            "r_hyst_ohm": R_HYST_OHM,
            "r_outa_pullup_ohm": R_OUTA_PULLUP_OHM,
            "resistor_tolerance": RESISTOR_TOLERANCE,
            "citation": "elec/src/modules.ato: LogicUVLOComparator",
        },
        "datasheet_values_not_in_elec": {
            "vit_a_datasheet_min_v": VIT_A_DATASHEET_MIN_V,
            "vit_a_datasheet_typ_v": VIT_A_MODEL_V,
            "vit_a_datasheet_max_v": VIT_A_DATASHEET_MAX_V,
            "citation": (
                "TI TPS3700 datasheet SBVS187G (Feb 2012, rev Feb 2019), "
                "SS6.5 Electrical Characteristics, VIT- row, VDD=1.8V to "
                "18V: min 387mV, typ 394.5mV, max 400mV. Verified directly "
                "from the datasheet PDF, not secondhand."
            ),
        },
        "implementation_scope": {
            "instances_of_LogicUVLOComparator_in_modules_ato": 1,
            "instantiated_as": "SafetyInterlock.uvlo_logic (elec/src/modules.ato)",
            "circuit_existed_before_2026_07_26": False,
            "fault_wiring": (
                "NOT wired into fault_or/fault_any_or. uvlo_logic.fault.line "
                "is instead brought to a test point "
                "(SafetyInterlock.tp_uvlo2_fault). An earlier pass of this "
                "survey, done against a stale worktree, found "
                "fault_any_or.C1 grounded and concluded it was a free SET-path "
                "input -- wrong: on the current tree, THM-02 "
                "(coil_thermal.fault.line) already owns fault_any_or.C1 "
                "(added in commit d99c88e2, before this circuit was "
                "designed). Re-surveyed against the current tree: fault_or "
                "gate 3 (Y3) drives nothing downstream; fault_any_or.C2 sits "
                "on the reset-qualifier path (wiring a fault there blocks "
                "reset without ever tripping the latch); fault_any_or gate 3 "
                "(A3/B3/C3/Y3) is entirely unreferenced, but its Y3 has no "
                "path into the SET aggregation without a further OR stage. "
                "No genuine spare SET-path input exists for UVL-02 -- the "
                "same conclusion already reached for OCP-02 on this same "
                "fault-tree. See docs/hardware/UVL02_DESIGN.md SS7."
            ),
        },
        "measurements": measurements,
        "derived": {
            "hand_derived_trip_v_nominal": hand_trip_v,
            "hand_derived_recover_v_nominal": hand_recover_v,
            "trip_hand_sim_agreement_v": trip_agreement_v,
            "recover_hand_sim_agreement_v": recover_agreement_v,
        },
        "internal_consistency_check_trip_v": trip_agreement_v,
        "internal_consistency_check_recover_v": recover_agreement_v,
        "worst_case_analysis": {
            "method": (
                "Analytic 16-corner sweep (NOT simulated in ngspice -- the "
                "behavioral model has no min/max spread): each of "
                "r_div_top/r_div_bot/r_hyst independently at +/-1% (E96 "
                "part tolerance per elec/src/modules.ato), VIT_A at the "
                "real TPS3700 datasheet's 387mV/400mV min/max. "
                "2^3 x 2 = 16 combinations; worst (max) trip and worst "
                "(min) recovery reported."
            ),
            **worst_case,
            "worst_case_trip_margin_v": (
                UVL02_SPEC_TRIP_CEILING_V - worst_case["worst_case_trip_v"]
            ),
            "worst_case_recovery_margin_v": (
                worst_case["worst_case_recovery_v"] - UVL02_SPEC_RECOVER_FLOOR_V
            ),
            "worst_case_trip_within_spec": worst_case_trip_within_spec,
            "worst_case_recovery_within_spec": worst_case_recovery_within_spec,
            "within_spec_worst_case": within_spec_worst_case,
        },
        "verdict": {
            "calibrated": False,
            "measured_trip_v": round(trip_v, 4),
            "measured_recovery_v": round(recover_v, 4),
            "measured_hysteresis_v": round(hysteresis_v, 4),
            "uvl02_spec_trip_ceiling_v": UVL02_SPEC_TRIP_CEILING_V,
            "uvl02_spec_recover_floor_v": UVL02_SPEC_RECOVER_FLOOR_V,
            "trip_within_uvl02_spec_nominal": trip_within_spec,
            "recovery_within_uvl02_spec_nominal": recovery_within_spec,
            "within_uvl02_spec_nominal": within_spec_nominal,
            "worst_case_trip_v": round(worst_case["worst_case_trip_v"], 4),
            "worst_case_recovery_v": round(worst_case["worst_case_recovery_v"], 4),
            "within_uvl02_spec_worst_case": within_spec_worst_case,
            "docstring_claim_trip_v": DOCSTRING_CLAIM_TRIP_V,
            "matches_docstring_claim_trip": (
                abs(trip_v - DOCSTRING_CLAIM_TRIP_V) < SPEC_MATCH_TOLERANCE_V
            ),
            "docstring_claim_recover_v": DOCSTRING_CLAIM_RECOVER_V,
            "matches_docstring_claim_recover": (
                abs(recover_v - DOCSTRING_CLAIM_RECOVER_V) < SPEC_MATCH_TOLERANCE_V
            ),
            "response_time_measured": False,
            "response_time_reason": (
                "TPS3700_ngspice.lib declares no timing model; the ramped "
                "VCC driver is an idealized PWL stimulus, not a real "
                "regulator brownout transient."
            ),
            "fault_wired_into_interlock": False,
            "fault_wiring_reason": (
                "No genuine spare SET-path input exists in fault_or/"
                "fault_any_or -- THM-02 (coil_thermal) already took the last "
                "one (fault_any_or.C1) before this circuit was designed. "
                "fault.line is brought to a test point "
                "(SafetyInterlock.tp_uvlo2_fault) instead of being wired "
                "into a colliding or dead-end input. See "
                "'implementation_scope.fault_wiring' above and "
                "docs/hardware/UVL02_DESIGN.md SS7."
            ),
            "gate_confirmed_as_uvl02": True,
            "gate_confirmed_as_uvl02_caveat": (
                "This circuit is confirmed as UVL-02's monitor -- it "
                "measures the logic rail directly and meets the trip/"
                "recovery spec with margin -- but it is NOT YET part of the "
                "hardware shutdown path (fault_wired_into_interlock is "
                "False). A live UVL-02 trip today reaches a test point, not "
                "GATE_DISABLE."
            ),
            "summary": (
                f"Simulated UVL-02 (LogicUVLOComparator) trip voltage is "
                f"{trip_v:.4f} V and recovery voltage is {recover_v:.4f} V "
                f"(uncalibrated, nominal component values), giving "
                f"{hysteresis_v:.4f} V of hysteresis. This is "
                f"{'WITHIN' if within_spec_nominal else 'OUTSIDE'} the "
                f"UVL-02 <2.9V trip / >3.0V recovery requirement at nominal, "
                f"matching LogicUVLOComparator's own inline hand-derivation "
                f"({DOCSTRING_CLAIM_TRIP_V}V trip, {DOCSTRING_CLAIM_RECOVER_V}V "
                f"recover) to within {trip_agreement_v:.4f}V / "
                f"{recover_agreement_v:.4f}V. Worst-case analytic corner "
                f"sweep (+/-1% resistors, full datasheet VIT_A range) gives "
                f"trip <= {worst_case['worst_case_trip_v']:.4f} V and "
                f"recovery >= {worst_case['worst_case_recovery_v']:.4f} V, "
                f"which is {'STILL WITHIN' if within_spec_worst_case else 'OUTSIDE'} "
                f"spec with "
                f"{UVL02_SPEC_TRIP_CEILING_V - worst_case['worst_case_trip_v']:.4f}V "
                f"/ "
                f"{worst_case['worst_case_recovery_v'] - UVL02_SPEC_RECOVER_FLOOR_V:.4f}V "
                f"margin respectively. NOT wired into the fault interlock: "
                f"fault_any_or.C1, the only spare SET-path input, was taken "
                f"by THM-02 before this circuit existed; no other spare "
                f"exists (same conclusion as OCP-02 on this fault-tree). "
                f"fault.line terminates at a test point pending a "
                f"fault-aggregation redesign."
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

    invocation = "uv run python simulation/harness/run_uvl02_logic_sim.py --runs " + str(
        max(2, args.runs)
    )
    evidence = build_evidence(
        measurements=measurements,
        invocation=invocation,
        determinism_runs=len(stdout_runs),
        deterministic=deterministic,
    )

    out_path = args.out
    if out_path is None:
        date_str = _dt.date.today().isoformat()
        out_path = (
            REPO_ROOT / "docs" / "evidence" / f"{date_str}-uvl02-logic-uvlo-sim.json"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(evidence, indent=2) + "\n")

    print(f"Deterministic across {len(stdout_runs)} runs: {deterministic}")
    print(json.dumps(evidence["verdict"], indent=2))
    print(f"Evidence written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
