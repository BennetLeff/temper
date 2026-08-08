#!/usr/bin/env python3
"""
SIL fault-injection coverage check (plan 2026-08-02-031, U1/KTD4).

Coverage is a matrix over (fault class, origin state): for every safety
fault class with a manifest-defined path, the machine must be injected from
*every* state that path is designed to be reachable from -- not just one
origin trajectory.

"Designed" pairs come from two sources, because the firmware itself expresses
fault paths two different ways:

  1. firmware/transition_table.yaml -- event-dispatched rows with a `fault:`
     field. This is the single source of truth for FAULT_SELF_TEST_FAILED,
     FAULT_OVER_TEMP, FAULT_OVER_CURRENT, FAULT_FAN_FAILURE,
     FAULT_PROBE_OPEN, FAULT_PROBE_SHORT, FAULT_THERMAL_RUNAWAY and
     FAULT_COOLDOWN_OVERHEAT.

  2. SUPPLEMENTAL_PAIRS below -- fault classes the firmware raises directly
     from C (bypassing the event table), so they have no transition_table.yaml
     row at all:
       - FAULT_IGBT_SHORT and FAULT_ADC_STUCK: raised by
         check_safety_interlocks() in firmware/main/state_machine.c, called
         only from state_preheat_update() and state_heating_update() in
         firmware/main/state_handlers.c.
       - FAULT_RUNAWAY_BOUNDARY: raised by check_runaway_boundary() in
         firmware/main/state_machine.c, called unconditionally at the top of
         state_machine_update() every tick regardless of state ("any-state"
         reach). Representative coverage is required from at least two
         operational states (HEATING, PREHEAT) rather than every state the
         interlock technically runs in, to keep the matrix finite; see
         REPRESENTATIVE_ANY_STATE_ORIGINS.

This script is intentionally standalone (no CMake/pytest wiring) so it can
run identically from a developer shell or a CI step:

    python3 firmware/test/test_sil_coverage.py [--gate]

Without --gate it always exits 0 and just prints the matrix (useful for
`git diff`-style before/after comparisons). With --gate it exits 1 if any
designed pair is uncovered, matching the plan's Verification Contract.
"""

from __future__ import annotations

import argparse
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
TRANSITION_TABLE_PATH = REPO_ROOT / "firmware" / "transition_table.yaml"

# Fault classes raised directly from C, with no transition_table.yaml row.
# (fault_code, origin_state) pairs, each with the call site that makes it
# "designed" rather than incidental.
SUPPLEMENTAL_PAIRS = {
    ("FAULT_IGBT_SHORT", "PREHEAT"):
        "check_safety_interlocks() <- state_preheat_update() (state_handlers.c)",
    ("FAULT_IGBT_SHORT", "HEATING"):
        "check_safety_interlocks() <- state_heating_update() (state_handlers.c)",
    ("FAULT_ADC_STUCK", "PREHEAT"):
        "check_safety_interlocks() <- state_preheat_update() (state_handlers.c)",
    ("FAULT_ADC_STUCK", "HEATING"):
        "check_safety_interlocks() <- state_heating_update() (state_handlers.c)",
    ("FAULT_RUNAWAY_BOUNDARY", "HEATING"):
        "check_runaway_boundary() <- state_machine_update(), any state (state_machine.c); "
        "representative sample",
    ("FAULT_RUNAWAY_BOUNDARY", "PREHEAT"):
        "check_runaway_boundary() <- state_machine_update(), any state (state_machine.c); "
        "representative sample",
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


def load_designed_pairs():
    """Return {(fault_code, origin_state): source_description}."""
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
    return pairs


def load_covered_pairs():
    """Return {(fault_code, origin_state): [scenario names]} from manifest.json.

    Only scenarios whose `expected.fault_code` is non-FAULT_NONE and whose
    `origin_state` is set are counted -- the demonstrated-gap scenario
    (FAULT_NONE expected) is intentionally excluded, it documents an
    *undesigned* gap, not a covered designed pair.
    """
    covered = {}
    if not MANIFEST_PATH.exists():
        return covered
    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)
    for scenario in manifest:
        fault = scenario.get("expected", {}).get("fault_code")
        origin = scenario.get("origin_state")
        if not fault or fault == "FAULT_NONE" or not origin:
            continue
        covered.setdefault((fault, origin), []).append(scenario.get("name", "<unnamed>"))
    return covered


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


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gate", action="store_true",
                         help="Exit 1 if any designed pair is uncovered")
    args = parser.parse_args()

    designed = load_designed_pairs()
    covered = load_covered_pairs()

    missing = sorted(set(designed) - set(covered))
    extra_designed_not_in_manifest_faults = set()

    print("=== SIL fault-class x origin-state coverage ===")
    print(f"Manifest:          {MANIFEST_PATH.relative_to(REPO_ROOT)}")
    print(f"Transition table:  {TRANSITION_TABLE_PATH.relative_to(REPO_ROOT)}")
    print()
    print(render_matrix(designed, covered))
    print()
    print(f"Designed pairs: {len(designed)}")
    print(f"Covered pairs:  {len(designed) - len(missing)}")
    print(f"Missing pairs:  {len(missing)}")
    if missing:
        print()
        print("Uncovered (fault class, origin state) pairs:")
        for fc, origin in missing:
            print(f"  - {fc} from {origin}  [{designed[(fc, origin)]}]")
    if NO_MANIFEST_PATH:
        print()
        print("Fault classes with no manifest path (excluded from matrix, not missed):")
        for fc, why in sorted(NO_MANIFEST_PATH.items()):
            print(f"  - {fc}: {why}")

    if args.gate and missing:
        print()
        print(f"FAIL: {len(missing)} uncovered designed pair(s)", file=sys.stderr)
        sys.exit(1)

    print()
    print("PASS" if not missing else "PASS (matrix printed; --gate not set, not failing)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
