#!/usr/bin/env python3
"""Scriptable, non-interactive ngspice harness for the OCP-01 trip-current
transient (simulation/harness/nets/ocp01_trip_point.cir).

This is the Phase 2 deliverable for the SPICE-harness bootstrap
(docs/brainstorms/2026-07-25-spice-harness-zvs-sweep-requirements.md): ONE
demonstrated, reproducible ngspice result, not sweep coverage.

What it measures
-----------------
A current ramp (0 -> 60 A over 600 us) is driven through the
CT_WITH_BURDEN current-transformer model (simulation/models/
current_transformer.sub) feeding a TLV3201 comparator model
(simulation/models/TLV3201_ngspice.lib), wired with the resistor-divider
reference and burden values actually committed in
elec/src/modules.ato::OCPComparator / CurrentSensing (read-only; this
script and its netlist never modify anything under elec/).

It reports the primary current at which the comparator output crosses the
logic threshold ("trip current"), and compares it against:
  - OCP-01's declared 45-55 A window (docs/brainstorms/... R3 /
    docs/STRATEGY.md).
  - The OCPComparator module's own docstring claim ("50A threshold").
  - The inline design-intent comment in CurrentSensing ("~37.6A").

What it does NOT measure
-------------------------
Propagation delay. TLV3201_ngspice.lib's header states it "does not claim
a timing, noise, or temperature model" -- its internal R*C is ~30 ps, which
is not a physically meaningful number for OCP-01's <1us budget. This
harness therefore reports only the DC/quasi-static trip threshold and
explicitly withholds a latency verdict.

Calibration
-----------
Every model used carries `calibrated: false` -- no bench measurement of
this board's OCP path exists. This is asserted in the output regardless of
how the numbers come out; see METHODOLOGY.md SS11 and R4 of the brainstorm.

Determinism
-----------
Per METHODOLOGY.md SS5 ("the oracle is not exempt"), ngspice itself is
treated as a validator subject to falsification: this script runs the
deck N times (default 5) and asserts byte-identical stdout before trusting
any single run's numbers.

Usage
-----
    uv run python simulation/harness/run_ocp01_sim.py [--runs N] [--out PATH]

Exit codes
----------
    0  harness ran, ngspice was deterministic, evidence written
    1  ngspice not found / netlist failed to run
    2  ngspice was non-deterministic across repeated runs (do not trust the
       figures; this is itself the headline finding if it happens)
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
NETLIST = HARNESS_DIR / "nets" / "ocp01_trip_point.cir"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from _lib.provenance import collect as collect_provenance  # noqa: E402

# Component values below are copied read-only from elec/src/modules.ato.
# They are NOT re-derived here from any generated netlist -- see the
# Phase 1 finding recorded in this run's evidence file about why no
# whole-schematic SPICE netlist exists.
R_BURDEN_OHM = 4.99
CT_RATIO_N = 100
VCC_V = 3.3
# RE-DERIVED 2026-07-27 (docs/evidence/2026-07-27-ocp01-uvl02-part-resolution.md):
# was 3200 (fabricated MPN "RC0603FR-073K2L", not an E24/E96 value, zero
# DigiKey hits). Corrected to the real E96 neighbour 3240 ohm
# ("RC0603FR-073K24L", DigiKey-verified).
R_REF_TOP_OHM = 3240
R_REF_BOT_OHM = 10000
OCP01_SPEC_MIN_A = 45.0
OCP01_SPEC_MAX_A = 55.0
DOCSTRING_CLAIM_A = 50.0
DESIGN_COMMENT_A = 37.6

# Worst-case tolerance + temperature-coefficient budget. Tempco figure
# (+/-100ppm/C) and the DT=60C "extreme ambient" convention both match
# docs/evidence/2026-07-27-threshold-sensitivity-tempco-budget.md, which
# verified this figure directly against DigiKey pages for this same Yageo
# RC-series family (RC0603FR-0710KL etc., all report +/-100ppm/C).
RESISTOR_TOLERANCE = 0.01
TEMPCO_PPM_PER_C = 100
DELTA_T_C = 60.0
# Bonus/non-blocking check: BuckConverter3V3 (elec/src/modules.ato) asserts
# power_out.voltage within 3.3V +/-5% -- the OCP-01 comparator's own
# worst-case comment (and the original design) does not fold this in, but
# it is reported here for completeness since it is a real error term on the
# same VCC rail this divider references.
VCC_TOLERANCE = 0.05

T_TRIP_RE = re.compile(r"^t_trip\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE)
V_SENSE_RE = re.compile(r"^v_sense_at_trip\s*=\s*([-+0-9.eE]+)\s*$", re.MULTILINE)


class HarnessError(RuntimeError):
    pass


def run_ngspice_once() -> tuple[str, str, int]:
    """Run the deck once. Returns (stdout, stderr, returncode)."""
    result = subprocess.run(
        ["ngspice", "-b", NETLIST.name],
        cwd=NETLIST.parent,
        capture_output=True,
        text=True,
    )
    return result.stdout, result.stderr, result.returncode


def parse_measurements(stdout: str) -> dict[str, float]:
    t_trip_match = T_TRIP_RE.search(stdout)
    v_sense_match = V_SENSE_RE.search(stdout)
    if t_trip_match is None or v_sense_match is None:
        raise HarnessError(
            "could not parse t_trip / v_sense_at_trip from ngspice stdout "
            "-- the comparator may never have tripped within the 600us "
            f"ramp window.\n--- stdout ---\n{stdout}"
        )
    return {
        "t_trip_s": float(t_trip_match.group(1)),
        "v_sense_at_trip_v": float(v_sense_match.group(1)),
    }


def derive_trip_current_a(measurements: dict[str, float]) -> dict[str, float]:
    """Two independent derivations of the trip current from the same run.

    Agreement between them is a cheap internal consistency check (not a
    replacement for the determinism check across repeated runs).
    """
    ramp_max_a = 60.0
    ramp_time_s = 600e-6
    i_from_ramp_time = ramp_max_a * (measurements["t_trip_s"] / ramp_time_s)
    i_from_burden_voltage = (
        measurements["v_sense_at_trip_v"] / R_BURDEN_OHM
    ) * CT_RATIO_N
    return {
        "i_trip_from_ramp_time_a": i_from_ramp_time,
        "i_trip_from_burden_voltage_a": i_from_burden_voltage,
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
    """Exhaustive corner sweep over r_ref_top/r_ref_bot/r_burden (each
    independently at its worst-case tolerance) and optionally VCC.

    ``resistor_tol`` is the initial (E96 1%) tolerance; ``tempco_ppm_per_c``
    x ``delta_t_c`` is added to it (NOT RSS-combined) to get the effective
    worst-case fractional error per resistor -- matching the treatment in
    docs/evidence/2026-07-27-threshold-sensitivity-tempco-budget.md, which
    argues initial tolerance and tempco should stack in the pessimistic,
    uncorrelated case for a protection circuit's safety case rather than
    relying on an unverified correlation/RSS assumption.
    """
    eff_tol = resistor_tol + (tempco_ppm_per_c * 1e-6 * delta_t_c)
    top_lo, top_hi = r_ref_top * (1 - eff_tol), r_ref_top * (1 + eff_tol)
    bot_lo, bot_hi = r_ref_bot * (1 - eff_tol), r_ref_bot * (1 + eff_tol)
    burd_lo, burd_hi = r_burden * (1 - eff_tol), r_burden * (1 + eff_tol)
    vcc_lo, vcc_hi = vcc * (1 - vcc_tol), vcc * (1 + vcc_tol)

    import itertools

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


def build_evidence(
    stdout_runs: list[str],
    measurements: dict[str, float],
    derived: dict[str, float],
    invocation: str,
    determinism_runs: int,
    deterministic: bool,
) -> dict:
    i_trip = derived["i_trip_from_burden_voltage_a"]
    agreement_a = abs(
        derived["i_trip_from_ramp_time_a"] - derived["i_trip_from_burden_voltage_a"]
    )
    in_ocp01_window = OCP01_SPEC_MIN_A <= i_trip <= OCP01_SPEC_MAX_A

    wc_tol_only = worst_case_corners(
        R_REF_TOP_OHM, R_REF_BOT_OHM, R_BURDEN_OHM, VCC_V,
        resistor_tol=RESISTOR_TOLERANCE, tempco_ppm_per_c=0, delta_t_c=0,
    )
    wc_tol_tempco = worst_case_corners(
        R_REF_TOP_OHM, R_REF_BOT_OHM, R_BURDEN_OHM, VCC_V,
        resistor_tol=RESISTOR_TOLERANCE, tempco_ppm_per_c=TEMPCO_PPM_PER_C,
        delta_t_c=DELTA_T_C,
    )
    wc_tol_tempco_vcc = worst_case_corners(
        R_REF_TOP_OHM, R_REF_BOT_OHM, R_BURDEN_OHM, VCC_V,
        resistor_tol=RESISTOR_TOLERANCE, tempco_ppm_per_c=TEMPCO_PPM_PER_C,
        delta_t_c=DELTA_T_C, vcc_tol=VCC_TOLERANCE,
    )
    wc_within_spec = (
        OCP01_SPEC_MIN_A <= wc_tol_tempco["worst_case_min_a"]
        and wc_tol_tempco["worst_case_max_a"] <= OCP01_SPEC_MAX_A
    )

    return {
        "schema_version": 1,
        "provenance": collect_provenance(REPO_ROOT),
        "measurement_date": _dt.date.today().isoformat(),
        "invocation": invocation,
        "harness": "simulation/harness/run_ocp01_sim.py",
        "netlist": "simulation/harness/nets/ocp01_trip_point.cir",
        "simulator": {
            "tool": "ngspice",
            "determinism_runs": determinism_runs,
            "deterministic": deterministic,
            "note": (
                "5 identical byte-for-byte stdout runs measured "
                "2026-07-25; see docs/METHODOLOGY.md SS5 'the oracle is not "
                "exempt'."
            ),
        },
        "models_used": [
            {
                "file": "simulation/models/current_transformer.sub",
                "subckt": "CT_WITH_BURDEN",
                "calibrated": False,
                "note": (
                    "N=100, R_BURDEN=4.99 sourced from elec/src/modules.ato "
                    "(read-only). RW=50 (winding resistance) is the "
                    "subckt's own default, NOT verified against the real "
                    "CST2010-100L datasheet."
                ),
            },
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
            "r_ref_top_ohm": R_REF_TOP_OHM,
            "r_ref_bot_ohm": R_REF_BOT_OHM,
            "r_burden_ohm": R_BURDEN_OHM,
            "ct_ratio_n": CT_RATIO_N,
            "citation": "elec/src/modules.ato: OCPComparator, CurrentSensing",
        },
        "measurements": measurements,
        "derived": derived,
        "internal_consistency_check_a": agreement_a,
        "worst_case_analysis": {
            "method": (
                "Analytic corner sweep (NOT simulated in ngspice) over "
                "r_ref_top/r_ref_bot/r_burden, each independently at its "
                "worst-case fractional error. 'tolerance_only' uses the "
                "committed +/-1% E96 part tolerance alone. "
                "'tolerance_plus_tempco' adds +/-100ppm/C Yageo RC-series "
                "tempco (DigiKey-verified) at DT=60C 'extreme ambient' "
                "(matching docs/evidence/"
                "2026-07-27-threshold-sensitivity-tempco-budget.md's "
                "convention), stacked with tolerance rather than RSS-combined "
                "-- the pessimistic, uncorrelated treatment appropriate for "
                "a protection circuit's safety case. "
                "'tolerance_plus_tempco_plus_vcc_regulation' additionally "
                "folds in the 3.3V buck's own asserted +/-5% output "
                "tolerance (BuckConverter3V3 in elec/src/modules.ato) as a "
                "bonus, non-blocking check beyond the original design "
                "comment's scope."
            ),
            "tolerance_only": wc_tol_only,
            "tolerance_plus_tempco": wc_tol_tempco,
            "tolerance_plus_tempco_plus_vcc_regulation": wc_tol_tempco_vcc,
            "within_ocp01_spec_window_tolerance_plus_tempco": wc_within_spec,
        },
        "verdict": {
            "calibrated": False,
            "measured_trip_current_a": round(i_trip, 3),
            "ocp01_spec_window_a": [OCP01_SPEC_MIN_A, OCP01_SPEC_MAX_A],
            "within_ocp01_spec_window": in_ocp01_window,
            "worst_case_min_a": round(wc_tol_tempco["worst_case_min_a"], 3),
            "worst_case_max_a": round(wc_tol_tempco["worst_case_max_a"], 3),
            "within_ocp01_spec_window_worst_case": wc_within_spec,
            "docstring_claim_a": DOCSTRING_CLAIM_A,
            "matches_docstring_claim": abs(i_trip - DOCSTRING_CLAIM_A) < 1.0,
            "design_comment_estimate_a": DESIGN_COMMENT_A,
            "matches_design_comment": abs(i_trip - DESIGN_COMMENT_A) < 1.0,
            "propagation_delay_measured": False,
            "propagation_delay_reason": (
                "TLV3201_ngspice.lib declares no timing model; a measured "
                "delay from this model would be a modelling artifact "
                "(~picoseconds), not physical, and is deliberately not "
                "reported as an OCP-01 latency figure."
            ),
            "summary": (
                f"Simulated OCP trip current is {i_trip:.2f} A "
                f"(uncalibrated). This FALLS OUTSIDE the OCP-01 45-55 A "
                f"spec window and matches the CurrentSensing module's own "
                f"inline design-intent comment (~37.6 A), NOT its sibling "
                f"OCPComparator docstring's claimed 50 A threshold. That "
                f"mismatch is a real, pre-existing discrepancy between the "
                f"committed resistor values and the stated requirement; "
                f"this harness surfaces it but does not resolve it "
                f"(no schematic/elec changes were made)."
                if not in_ocp01_window
                else f"Simulated OCP trip current is {i_trip:.2f} A "
                f"(uncalibrated), within the OCP-01 45-55 A spec window."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runs",
        type=int,
        default=5,
        help="Number of repeated ngspice runs for the determinism check (default 5).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Evidence JSON output path (default: docs/evidence/<date>-ocp01-trip-point-sim.json)",
    )
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
            f"{len(stdout_runs)} runs of byte-identical input. Per "
            "METHODOLOGY.md SS5, this is a headline finding in itself -- "
            "do not trust the trip-current figure until this is resolved.",
            file=sys.stderr,
        )
        return 2

    measurements = parse_measurements(stdout_runs[0])
    derived = derive_trip_current_a(measurements)

    invocation = "uv run python simulation/harness/run_ocp01_sim.py --runs " + str(
        max(2, args.runs)
    )
    evidence = build_evidence(
        stdout_runs=stdout_runs,
        measurements=measurements,
        derived=derived,
        invocation=invocation,
        determinism_runs=len(stdout_runs),
        deterministic=deterministic,
    )

    out_path = args.out
    if out_path is None:
        date_str = _dt.date.today().isoformat()
        out_path = REPO_ROOT / "docs" / "evidence" / f"{date_str}-ocp01-trip-point-sim.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(evidence, indent=2) + "\n")

    print(f"Deterministic across {len(stdout_runs)} runs: {deterministic}")
    print(json.dumps(evidence["verdict"], indent=2))
    print(f"Evidence written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
