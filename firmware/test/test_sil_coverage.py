#!/usr/bin/env python3
"""
SIL fault-injection coverage check (plan 2026-08-02-031, U1/KTD4), for both
SIL configurations: the legacy loop (test_sil_fault_injection) and the C1
pan-sensor loop (test_sil_fault_injection_c1, TEMPER_PAN_CONTROL_C1;
output/temper-sensor-r3/firmware/DECISIONS.md D-SIL).

Coverage is a matrix over (fault class, origin state), per mode: for every
safety fault class with a manifest-defined path, the machine must be injected
from *every* state that path is designed to be reachable from -- not just one
origin trajectory. A scenario counts for a mode when its manifest "modes"
list includes that mode (default: both).

"Designed" pairs come from these sources, because the firmware expresses
fault paths in different ways:

  1. firmware/transition_table.yaml -- event-dispatched rows with a `fault:`
     field (both modes). This is the single source of truth for
     FAULT_SELF_TEST_FAILED, FAULT_OVER_TEMP, FAULT_OVER_CURRENT,
     FAULT_FAN_FAILURE, FAULT_PROBE_OPEN, FAULT_PROBE_SHORT,
     FAULT_THERMAL_RUNAWAY and FAULT_COOLDOWN_OVERHEAT.

  2. SUPPLEMENTAL_PAIRS below (both modes) -- fault classes the firmware
     raises directly from C (bypassing the event table):
       - FAULT_IGBT_SHORT: check_safety_interlocks() in
         firmware/main/state_machine.c, called only from
         state_preheat_update() and state_heating_update().
       - FAULT_ADC_STUCK: legacy -- the same interlock's equal-reading
         check; C1 -- rtd_service.c's frozen-code check (the interlock's is
         compiled out), which runs in every state.
       - FAULT_RUNAWAY_BOUNDARY: check_runaway_boundary(), called at the
         top of state_machine_update() every tick regardless of state.
         Representative coverage from two operational states (HEATING,
         PREHEAT); see REPRESENTATIVE_ANY_STATE_ORIGINS.

  3. C1_SUPPLEMENTAL_PAIRS (C1 only) -- the C1 converter service
     (rtd_service.c) reports register-07h, DRDY-stale and frozen-code faults
     from every state, so C1 adds IDLE (a non-power state, where no legacy
     interlock runs) as a representative origin for those classes.

C1 also replaces rules, not only paths, so a second C1 matrix is gated:
C1_MECHANISMS x origin (R1, the absolute 300 degC check, supervisor R2
stages 1/2a/2b, register 07h, DRDY stale, frozen code, the current-sense
checks (a) and (b), and the probe-leakage latch). A scenario covers a
cell through its manifest "c1_mechanism"; the C1 runner checks the attribution
where the firmware exposes it (supervisor latch, reading at the trip, 07h,
service stopped).

Structural rules (gated):
  * C1 designed pairs are a superset of legacy designed pairs, and C1 covers
    at least as many pairs as legacy;
  * a legacy-only scenario names why (legacy_only_reason) and its C1
    replacement(s) (c1_replaced_by), each an existing scenario run in C1;
  * a C1-only scenario says why (c1_only_reason);
  * a C1 latency bound above the legacy one names why
    (c1_later_than_legacy_reason) -- never a silent loosening;
  * every trace file exists, and the generated traces match
    gen_sil_traces.py.

This script is intentionally standalone (no CMake/pytest wiring) so it can
run identically from a developer shell or a CI step:

    python3 firmware/test/test_sil_coverage.py [--gate]

Without --gate it always exits 0 and just prints the matrices (useful for
`git diff`-style before/after comparisons). With --gate it exits 1 on any
uncovered designed pair or mechanism cell, or a structural-rule violation.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("ERROR: pyyaml is required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = REPO_ROOT / "firmware" / "test" / "traces" / "manifest.json"
TRACE_DIR = MANIFEST_PATH.parent
TRANSITION_TABLE_PATH = REPO_ROOT / "firmware" / "transition_table.yaml"
TRACE_GENERATOR = REPO_ROOT / "firmware" / "test" / "gen_sil_traces.py"

MODES = ("legacy", "c1")

REPRESENTATIVE_ANY_STATE_ORIGINS = ("HEATING", "PREHEAT")

# Fault classes raised directly from C, with no transition_table.yaml row.
# (fault_code, origin_state) pairs, each with the call site that makes it
# "designed" rather than incidental. Both modes.
SUPPLEMENTAL_PAIRS = {
    ("FAULT_IGBT_SHORT", "PREHEAT"):
        "check_safety_interlocks() <- state_preheat_update() (state_handlers.c)",
    ("FAULT_IGBT_SHORT", "HEATING"):
        "check_safety_interlocks() <- state_heating_update() (state_handlers.c)",
    ("FAULT_ADC_STUCK", "PREHEAT"):
        "legacy: check_safety_interlocks() <- state_preheat_update(); "
        "C1: rtd_service.c frozen-code check, any state",
    ("FAULT_ADC_STUCK", "HEATING"):
        "legacy: check_safety_interlocks() <- state_heating_update(); "
        "C1: rtd_service.c frozen-code check, any state",
}
for _origin in REPRESENTATIVE_ANY_STATE_ORIGINS:
    SUPPLEMENTAL_PAIRS[("FAULT_RUNAWAY_BOUNDARY", _origin)] = (
        "check_runaway_boundary() <- state_machine_update(), any state "
        "(state_machine.c); representative sample")

_C1_SERVICE = ("rtd_service_control_tick() (C1, every state) -> "
               "state_machine_report_rtd_{device_fault,frozen}(); representative non-power state")
_C1_ISENSE = ("pan_control_step() current-sense checks (components/control/current_sense_check.c, "
              "DECISIONS D-ISENSE) -> state_machine_report_latched_fault(), PREHEAT/HEATING")
_C1_LEAK = ("pan_control_step() Pt100 leak check (components/control/pan_leak_check.c, DECISIONS "
            "D-LEAK) -> state_machine_report_latched_fault(); needs a hot pan, HEATING")
_C1_RIMLIM = ("pan_control_step() setpoint-relative rim limit (components/control/pan_rim_limit.c, "
              "DECISIONS D-RIMLIM) -> state_machine_report_latched_fault(); a VALID rim, PREHEAT/HEATING; "
              "and the cold-soak check (components/control/pan_cold_soak.c, DECISIONS D-SOAK) in the "
              "first PREHEAT period")
C1_SUPPLEMENTAL_PAIRS = {
    ("FAULT_PROBE_OPEN", "IDLE"): _C1_SERVICE,
    ("FAULT_PROBE_SHORT", "IDLE"): _C1_SERVICE,
    ("FAULT_ADC_STUCK", "IDLE"): _C1_SERVICE,
    ("FAULT_CURRENT_SENSE", "PREHEAT"): _C1_ISENSE,
    ("FAULT_CURRENT_SENSE", "HEATING"): _C1_ISENSE,
    ("FAULT_PROBE_LEAKAGE", "HEATING"): _C1_LEAK,
    ("FAULT_PROBE_LEAKAGE", "PREHEAT"): _C1_RIMLIM,
}

# C1 rules x the origins each must be injected from.
C1_MECHANISMS = {
    "R1": (("HEATING", "PREHEAT"),
           "pan_supervisor R1 sustained rise <- check_runaway_boundary(), any state"),
    "absolute-300": (("HEATING", "PREHEAT"),
                     "check_runaway_boundary() absolute limit on the C1 reading"),
    "R2-stage1": (("HEATING",),
                  "supervisor stage 1: over target + 10 K forces the command to 0, no latch"),
    "R2-2a": (("HEATING", "PREHEAT"),
              "supervisor stage 2a: bus current the command cannot explain"),
    "R2-2b": (("HEATING",),
              "supervisor stage 2b: over target, command 0 for 20 s, still rising"),
    "rtd-07h": (("IDLE", "PREHEAT", "HEATING"),
                "MAX31865 threshold fault, register 07h (C1 window)"),
    "rtd-stale": (("IDLE", "HEATING"), "no DRDY for 60 ms"),
    "rtd-frozen": (("IDLE", "PREHEAT", "HEATING"), "250 identical conversions"),
    "isense-run": (("PREHEAT", "HEATING"),
                   "current-sense check (a): >= 300 W commanded, bus current near 0 A for 0.5 s"),
    "isense-pulse": (("PREHEAT",), "current-sense check (b): the start-up pulse shows no current"),
    "xchk-leak": (("HEATING",),
                  "Pt100 leak check: two chained cross-check suspect -> probe-passed cycles"),
    "rim-limit": (("HEATING", "PREHEAT"),
                  "setpoint-relative rim limit: rim over the glass envelope of max(setpoint, t_hat) "
                  "+ 19.1 K, not falling, for 5 s"),
    "cold-soak": (("PREHEAT",),
                  "cold-soak check: soaked >= 30 min, the heatsink NTC over the Pt100 by > 12.9 K "
                  "through the window, before the first power"),
    "cold-soak-pass": (("PREHEAT",), "cold-soak check runs on an intact probe: verdict pass, no latch"),
    "cold-soak-skip": (("PREHEAT",), "cold-soak check skips when not soaked (power-up counts as "
                                     "coil activity): no latch"),
}

# Fault classes with NO manifest path at all (no transition_table.yaml row,
# no C call site) -- legacy codes carried in fault_list_supplemental.yaml.
# Excluded from the coverage matrix per R41's success signal ("every safety
# fault class with a manifest path"), not silently dropped: listed so a
# reader can see they were considered and excluded, not missed.
NO_MANIFEST_PATH = {
    "FAULT_WATCHDOG_RESET": "no transition_table.yaml row or C call site as of this audit "
                             "(2026-08-02-031); legacy fault_list_supplemental.yaml entry",
    "FAULT_PAN_DETECT_HW": "no transition_table.yaml row or C call site as of this audit "
                            "(2026-08-02-031); legacy fault_list_supplemental.yaml entry",
}

STATE_RE = re.compile(r"^STATE_(\w+)$")


def strip_state_prefix(state: str) -> str:
    m = STATE_RE.match(state)
    return m.group(1) if m else state


def scenario_modes(scenario: dict) -> list[str]:
    return list(scenario.get("modes", MODES))


def load_manifest() -> list[dict]:
    if not MANIFEST_PATH.exists():
        return []
    with open(MANIFEST_PATH) as f:
        return json.load(f)


def load_designed_pairs(mode: str = "legacy"):
    """Return {(fault_code, origin_state): source_description} for a mode."""
    pairs = {}
    with open(TRANSITION_TABLE_PATH) as f:
        table = yaml.safe_load(f)
    for row in table.get("transitions", []):
        fault = row.get("fault")
        if not fault:
            continue
        origin = strip_state_prefix(row["from"])
        pairs[(fault, origin)] = (
            f"transition_table.yaml: {row['from']} + {row['event']} -> "
            f"{row['to']} (fault: {fault})"
        )
    for pair, source in SUPPLEMENTAL_PAIRS.items():
        pairs[pair] = source
    if mode == "c1":
        for pair, source in C1_SUPPLEMENTAL_PAIRS.items():
            pairs[pair] = source
    return pairs


def load_covered_pairs(mode: str = "legacy", manifest: list[dict] | None = None):
    """Return {(fault_code, origin_state): [scenario names]} for a mode.

    Only scenarios whose `expected.fault_code` is non-FAULT_NONE and whose
    `origin_state` is set are counted -- the demonstrated-gap scenarios
    (FAULT_NONE expected) are intentionally excluded, they document an
    *undesigned* gap, not a covered designed pair.
    """
    manifest = load_manifest() if manifest is None else manifest
    covered = {}
    for scenario in manifest:
        if mode not in scenario_modes(scenario):
            continue
        fault = scenario.get("expected", {}).get("fault_code")
        origin = scenario.get("origin_state")
        if not fault or fault == "FAULT_NONE" or not origin:
            continue
        covered.setdefault((fault, origin), []).append(scenario.get("name", "<unnamed>"))
    return covered


def load_mechanism_cells(manifest: list[dict]):
    """Return {(mechanism, origin): [scenario names]} for C1 scenarios."""
    cells = {}
    for scenario in manifest:
        mech = scenario.get("c1_mechanism")
        if not mech or "c1" not in scenario_modes(scenario):
            continue
        cells.setdefault((mech, scenario.get("origin_state")), []).append(scenario["name"])
    return cells


def structural_errors(manifest: list[dict]) -> list[str]:
    errors = []
    by_name = {s.get("name"): s for s in manifest}
    for s in manifest:
        name = s.get("name", "<unnamed>")
        modes = scenario_modes(s)
        unknown = set(modes) - set(MODES)
        if unknown or not modes:
            errors.append(f"{name}: bad modes {modes}")
        trace = s.get("trace_file")
        if trace and not (TRACE_DIR / trace).exists():
            errors.append(f"{name}: trace {trace} missing")
        if modes == ["legacy"]:
            if not s.get("legacy_only_reason"):
                errors.append(f"{name}: legacy-only without legacy_only_reason")
            repl = s.get("c1_replaced_by") or []
            if not repl:
                errors.append(f"{name}: legacy-only without c1_replaced_by")
            for r in repl:
                if r not in by_name:
                    errors.append(f"{name}: C1 replacement '{r}' not in the manifest")
                elif "c1" not in scenario_modes(by_name[r]):
                    errors.append(f"{name}: C1 replacement '{r}' does not run in C1")
        if modes == ["c1"] and not s.get("c1_only_reason"):
            errors.append(f"{name}: C1-only without c1_only_reason")
        exp = s.get("expected", {})
        lat, lat_c1 = exp.get("max_latency_ticks"), exp.get("max_latency_ticks_c1")
        if lat_c1 is not None and lat is not None and lat_c1 > lat and \
                not s.get("c1_later_than_legacy_reason"):
            errors.append(f"{name}: C1 bound {lat_c1} > legacy {lat} without "
                          "c1_later_than_legacy_reason")
        mech = s.get("c1_mechanism")
        if mech and mech not in C1_MECHANISMS:
            errors.append(f"{name}: unknown c1_mechanism '{mech}'")
        if mech and "c1" not in modes:
            errors.append(f"{name}: c1_mechanism on a scenario that does not run in C1")
    return errors


def trace_drift() -> list[str]:
    spec = importlib.util.spec_from_file_location("gen_sil_traces", TRACE_GENERATOR)
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    drift = []
    for name, make in gen.TRACES.items():
        path = TRACE_DIR / name
        if not path.exists() or path.read_text() != gen.render(make()):
            drift.append(name)
    return drift


def render_matrix(designed: dict, covered: dict) -> str:
    fault_classes = sorted({f for f, _ in designed})
    origins = sorted({o for _, o in designed})

    col_w = max(len(o) for o in origins) + 2
    header = "fault class".ljust(28) + "".join(o.ljust(col_w) for o in origins)
    lines = [header, "-" * len(header)]
    for fc in fault_classes:
        row = fc.ljust(28)
        for o in origins:
            if (fc, o) not in designed:
                cell = "."
            elif (fc, o) in covered:
                cell = f"OK({len(covered[(fc, o)])})"
            else:
                cell = "MISSING"
            row += cell.ljust(col_w)
        lines.append(row)
    return "\n".join(lines)


def render_mechanisms(cells: dict) -> tuple[str, int, int]:
    origins = ("IDLE", "PREHEAT", "HEATING")
    header = "C1 mechanism".ljust(16) + "".join(o.ljust(11) for o in origins)
    lines = [header, "-" * len(header)]
    required = covered = 0
    for mech, (need, _why) in C1_MECHANISMS.items():
        row = mech.ljust(16)
        for o in origins:
            if o not in need:
                cell = "."
            else:
                required += 1
                if (mech, o) in cells:
                    covered += 1
                    cell = f"OK({len(cells[(mech, o)])})"
                else:
                    cell = "MISSING"
            row += cell.ljust(11)
        lines.append(row)
    return "\n".join(lines), required, covered


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gate", action="store_true",
                        help="Exit 1 on any uncovered pair/mechanism or rule violation")
    args = parser.parse_args()

    manifest = load_manifest()
    failures = []
    summary = {}

    print("=== SIL fault-class x origin-state coverage ===")
    print(f"Manifest:          {MANIFEST_PATH.relative_to(REPO_ROOT)}")
    print(f"Transition table:  {TRANSITION_TABLE_PATH.relative_to(REPO_ROOT)}")
    designed_by_mode = {}
    for mode in MODES:
        designed = load_designed_pairs(mode)
        designed_by_mode[mode] = designed
        covered = load_covered_pairs(mode, manifest)
        missing = sorted(set(designed) - set(covered))
        n_scen = sum(1 for s in manifest if mode in scenario_modes(s))
        print()
        print(f"--- mode: {mode} ({n_scen} scenarios) ---")
        print(render_matrix(designed, covered))
        print()
        print(f"Designed pairs: {len(designed)}")
        print(f"Covered pairs:  {len(designed) - len(missing)}")
        print(f"Missing pairs:  {len(missing)}")
        summary[mode] = (n_scen, len(designed), len(designed) - len(missing))
        if missing:
            print()
            print("Uncovered (fault class, origin state) pairs:")
            for fc, origin in missing:
                print(f"  - {fc} from {origin}  [{designed[(fc, origin)]}]")
            failures.append(f"{mode}: {len(missing)} uncovered designed pair(s)")

    if not set(designed_by_mode["legacy"]) <= set(designed_by_mode["c1"]):
        failures.append("C1 designed pairs are not a superset of legacy designed pairs")
    if summary["c1"][2] < summary["legacy"][2]:
        failures.append("C1 covers fewer designed pairs than legacy")

    print()
    print("--- C1 mechanism x origin ---")
    text, required, covered_cells = render_mechanisms(load_mechanism_cells(manifest))
    print(text)
    print()
    print(f"Required cells: {required}")
    print(f"Covered cells:  {covered_cells}")
    if covered_cells < required:
        failures.append(f"c1: {required - covered_cells} uncovered mechanism cell(s)")

    errors = structural_errors(manifest)
    drift = trace_drift()
    if drift:
        errors.append("generated traces differ from gen_sil_traces.py: " + ", ".join(drift))
    print()
    print("--- structural rules ---")
    legacy_only = [s["name"] for s in manifest if scenario_modes(s) == ["legacy"]]
    c1_only = [s["name"] for s in manifest if scenario_modes(s) == ["c1"]]
    print(f"Legacy-only scenarios: {len(legacy_only)} (each names its C1 replacement)")
    for s in manifest:
        if scenario_modes(s) == ["legacy"]:
            print(f"  - {s['name']}\n      -> " + "\n      -> ".join(s.get("c1_replaced_by", [])))
    print(f"C1-only scenarios:     {len(c1_only)}")
    for e in errors:
        print(f"  ERROR: {e}")
    if errors:
        failures.append(f"{len(errors)} structural rule violation(s)")
    else:
        print("  all rules hold")

    if NO_MANIFEST_PATH:
        print()
        print("Fault classes with no manifest path (excluded from matrix, not missed):")
        for fc, why in sorted(NO_MANIFEST_PATH.items()):
            print(f"  - {fc}: {why}")

    print()
    for mode in MODES:
        n, d, c = summary[mode]
        print(f"SUMMARY {mode}: {n} scenarios, {c}/{d} designed pairs covered")
    print(f"SUMMARY c1 mechanisms: {covered_cells}/{required} cells covered")

    if args.gate and failures:
        print()
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        sys.exit(1)

    print()
    print("PASS" if not failures else "PASS (matrix printed; --gate not set, not failing)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
