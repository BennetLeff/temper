#!/usr/bin/env python3
"""
CI cross-check: verify manifest.json fault codes are a subset of the
generated FAULT_LIST, and no supplemental entry duplicates a manifest entry.

Usage:
    python3 scripts/check_fault_list_consistency.py

Exit 0 on pass, non-zero on failure.
"""

import json
import re
import sys
from pathlib import Path

import yaml


def main():
    repo_root = Path(__file__).resolve().parent.parent
    manifest_path = repo_root / "firmware" / "test" / "traces" / "manifest.json"
    generated_path = repo_root / "firmware" / "main" / "fault_list_generated.h"
    supplemental_path = repo_root / "firmware" / "tools" / "fault_list_supplemental.yaml"

    errors = []

    # 1. Extract fault codes from manifest.json
    if not manifest_path.exists():
        errors.append(f"manifest.json not found: {manifest_path}")
    else:
        with open(manifest_path) as f:
            manifest = json.load(f)
        manifest_codes = set()
        for scenario in manifest:
            fc = scenario.get("expected", {}).get("fault_code")
            if fc:
                manifest_codes.add(fc)
        if not manifest_codes:
            errors.append("no fault codes found in manifest.json")

    # 2. Extract fault codes from generated header
    if not generated_path.exists():
        errors.append(f"fault_list_generated.h not found: {generated_path}")
    else:
        with open(generated_path) as f:
            generated_content = f.read()
        generated_codes = set(
            re.findall(r'X\((\w+),\s*"[^"]*"\)', generated_content)
        )
        if not generated_codes:
            errors.append("no fault codes found in fault_list_generated.h")

    # 3. Cross-check: manifest ⊆ generated
    if manifest_codes and generated_codes:
        missing = manifest_codes - generated_codes
        if missing:
            for code in sorted(missing):
                errors.append(
                    f"manifest fault code '{code}' missing from "
                    f"fault_list_generated.h"
                )

    # 4. Check supplemental doesn't duplicate manifest.
    # FAULT_NONE is excluded: it's the sentinel "no fault occurred" outcome
    # for non-fault SIL scenarios (plan 2026-08-02-031/U3 timing scenarios,
    # demonstrated-gap scenarios), not a fault class being claimed by the
    # manifest -- it legitimately appears in both manifest.json (as an
    # expected outcome) and fault_list_supplemental.yaml (as the canonical
    # definition), same exclusion as firmware/tools/gen_fault_list.py.
    if supplemental_path.exists():
        with open(supplemental_path) as f:
            supplemental = yaml.safe_load(f)
        supplemental_names = {e["name"] for e in supplemental.get("entries", [])}
        if manifest_codes and supplemental_names:
            collisions = (manifest_codes - {"FAULT_NONE"}) & supplemental_names
            if collisions:
                for code in sorted(collisions):
                    errors.append(
                        f"supplemental entry '{code}' duplicates manifest entry"
                    )

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)

    print("fault list consistency check passed")
    print(f"  manifest codes: {len(manifest_codes)}")
    print(f"  generated codes: {len(generated_codes)}")
    print(f"  supplemental codes: {len(supplemental_names) if supplemental_path.exists() else 0}")


if __name__ == "__main__":
    main()
