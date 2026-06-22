#!/usr/bin/env python3
"""
Fault-table coverage checker.

Cross-references FAULT_xxx enum values from firmware/main/state_machine.h
against tools/sil/faults.yaml and reports any fault codes with missing
coverage.  Missing coverage is a warning only (exit code 0).

Usage:
    python3 tools/sil/check_coverage.py
"""

import re
import sys
import yaml

STATE_MACHINE_H = "firmware/main/state_machine.h"
FAULTS_YAML = "tools/sil/faults.yaml"

# Fault codes that are explicitly deferred from SIL coverage
DEFERRED_FAULTS = {
    "FAULT_NONE",
    "FAULT_WATCHDOG_RESET",    # requires MCU reset, not applicable to SIL
    "FAULT_COOLDOWN_OVERHEAT", # deferred per origin open question
    "FAULT_PAN_DETECT_HW",     # deferred, requires hardware-specific mock
}


def parse_fault_enum(path: str):
    """Parse fault_code_t enum values from state_machine.h."""
    codes = {}
    with open(path, "r") as f:
        content = f.read()

    # Match enum block: fault_code_t { ... }
    match = re.search(
        r'typedef\s+enum\s*\{([^}]+)\}\s*fault_code_t;', content, re.DOTALL)
    if not match:
        print(f"ERROR: could not find fault_code_t enum in {path}", file=sys.stderr)
        sys.exit(1)

    body = match.group(1)
    # Extract entries: FAULT_XXX, FAULT_XXX = N
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("//") or line.startswith("/*"):
            continue
        m = re.match(r'(FAULT_\w+)', line)
        if m:
            codes[m.group(1)] = line

    return codes


def parse_fault_table(path: str):
    """Parse expected.fault_code values from faults.yaml."""
    covered = set()
    with open(path, "r") as f:
        data = yaml.safe_load(f)

    for fault in data.get("faults", []):
        expected = fault.get("expected", {})
        fc = expected.get("fault_code", "")
        if fc:
            covered.add(fc)
    return covered


def main() -> None:
    enum_codes = parse_fault_enum(STATE_MACHINE_H)
    covered_codes = parse_fault_table(FAULTS_YAML)

    missing = []
    for code in sorted(enum_codes):
        if code in DEFERRED_FAULTS:
            continue
        if code not in covered_codes:
            missing.append(code)

    if missing:
        print("WARNING: Fault codes without SIL coverage:", file=sys.stderr)
        for code in missing:
            print(f"  - {code}", file=sys.stderr)
    else:
        print("All non-deferred fault codes have SIL coverage.")

    total = len([c for c in enum_codes if c not in DEFERRED_FAULTS])
    covered = total - len(missing)
    print(f"Coverage: {covered}/{total} fault codes covered")

    # Exit 0 always (warning, not failure)
    sys.exit(0)


if __name__ == "__main__":
    main()
