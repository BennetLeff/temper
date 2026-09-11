#!/usr/bin/env python3
"""
Regenerate firmware/main/fault_list_generated.h from
firmware/test/traces/manifest.json and firmware/tools/fault_list_supplemental.yaml.

Usage:
    python3 firmware/tools/gen_fault_list.py

The script is idempotent — it only overwrites fault_list_generated.h when the
generated content differs from the current file.
"""

import json
import re
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader


# Label overrides for manifest entries whose mechanically-derived label
# would differ from the existing hand-maintained strings in state_machine.h.
# These preserve backward compatibility with test assertions and EEPROM logs.
LABEL_OVERRIDES = {
    "FAULT_OVER_TEMP": "OVER TEMP",
    "FAULT_OVER_CURRENT": "OVER CURRENT",
    "FAULT_FAN_FAILURE": "FAN FAILED",
    "FAULT_PROBE_OPEN": "PROBE OPEN",
    "FAULT_PROBE_SHORT": "PROBE SHORT",
    "FAULT_THERMAL_RUNAWAY": "THERMAL RUNAWAY",
    "FAULT_COOLDOWN_OVERHEAT": "COOLDOWN FAULT",
    "FAULT_IGBT_SHORT": "IGBT SHORT",
    "FAULT_ADC_STUCK": "ADC STUCK",
    # FAULT_SELF_TEST_FAILED graduated out of fault_list_supplemental.yaml
    # on 2026-08-07 (plan 031/U1); preserve its pre-existing display label
    # rather than mechanically deriving one from the new manifest scenario
    # name ("SIL: Self-Test Failure (INIT)"), which doesn't end in the
    # " Fault" suffix derive_label() strips.
    "FAULT_SELF_TEST_FAILED": "SELF TEST FAIL",
}


def derive_label(name, fault_code):
    """Derive a display label from the manifest `name` field.

    The label override dict takes priority (preserving backward compatibility).
    Otherwise, strips "SIL: " prefix and " Fault" suffix from the name,
    keeping any parenthetical qualifier like "(hard short detection)".
    """
    if fault_code in LABEL_OVERRIDES:
        return LABEL_OVERRIDES[fault_code]

    label = name
    # Strip "SIL: " prefix
    if label.startswith("SIL: "):
        label = label[len("SIL: "):]
    # Strip trailing " Fault" (with optional parenthetical suffix)
    label = re.sub(r'\s+Fault(\s*\([^)]*\))?$', '', label)
    return label.upper()


def extract_manifest_faults(manifest_path):
    """Extract unique fault codes and derived labels from manifest.json."""
    with open(manifest_path) as f:
        manifest = json.load(f)

    entries = []
    seen = set()
    for scenario in manifest:
        expected = scenario.get("expected", {})
        fault_code = expected.get("fault_code")
        if not fault_code:
            print(f"ERROR: manifest entry '{scenario.get('name', '?')}' "
                  f"missing expected.fault_code", file=sys.stderr)
            sys.exit(1)
        if fault_code in seen:
            continue
        seen.add(fault_code)

        # FAULT_NONE is a legitimate expected outcome for non-fault SIL
        # scenarios (plan 2026-08-02-031/U3 timing scenarios asserting a
        # timeout resolves to a non-fault state e.g. PAN_TIMEOUT -> IDLE;
        # and demonstrated-gap scenarios that intentionally assert the
        # absence of a fault). It is already defined once, canonically, by
        # fault_list_supplemental.yaml -- skip re-deriving/re-emitting it
        # here so it doesn't collide with that entry in check_collisions().
        if fault_code == "FAULT_NONE":
            continue

        name = scenario.get("name", fault_code)
        label = derive_label(name, fault_code)
        if not label:
            print(f"ERROR: could not derive label for {fault_code} "
                  f"from name '{name}'", file=sys.stderr)
            sys.exit(1)
        entries.append({"name": fault_code, "label": label})

    # Sort alphabetically by fault code name
    entries.sort(key=lambda e: e["name"])
    return entries


def extract_supplemental_faults(supplemental_path):
    """Extract supplemental fault entries from YAML."""
    with open(supplemental_path) as f:
        data = yaml.safe_load(f)

    entries = data.get("entries", [])
    for entry in entries:
        if not entry.get("name") or not entry.get("label"):
            print(f"ERROR: supplemental entry missing name or label: {entry}",
                  file=sys.stderr)
            sys.exit(1)
    return entries


def check_collisions(manifest_entries, supplemental_entries):
    """Check for collisions between manifest and supplemental entries."""
    manifest_names = {e["name"] for e in manifest_entries}
    for entry in supplemental_entries:
        if entry["name"] in manifest_names:
            print(f"ERROR: supplemental entry {entry['name']} duplicates "
                  f"manifest entry", file=sys.stderr)
            sys.exit(1)


def main():
    repo_root = Path(__file__).resolve().parent.parent
    manifest_path = repo_root / "test" / "traces" / "manifest.json"
    supplemental_path = Path(__file__).resolve().parent / "fault_list_supplemental.yaml"
    template_path = Path(__file__).resolve().parent / "fault_list.h.j2"
    output_path = repo_root / "main" / "fault_list_generated.h"

    if not manifest_path.exists():
        print(f"ERROR: manifest not found at {manifest_path}", file=sys.stderr)
        sys.exit(1)

    manifest_entries = extract_manifest_faults(manifest_path)
    supplemental_entries = extract_supplemental_faults(supplemental_path)
    check_collisions(manifest_entries, supplemental_entries)

    env = Environment(loader=FileSystemLoader(template_path.parent))
    template = env.get_template(template_path.name)
    rendered = template.render(
        manifest_entries=manifest_entries,
        supplemental_entries=supplemental_entries,
    )

    # Ensure trailing newline
    if not rendered.endswith("\n"):
        rendered += "\n"

    tmp_path = output_path.with_suffix(".h.tmp")
    with open(tmp_path, "w") as f:
        f.write(rendered)

    if output_path.exists():
        with open(output_path) as f:
            existing = f.read()
        if existing == rendered:
            tmp_path.unlink()
            print("fault_list_generated.h up to date")
            return

    tmp_path.rename(output_path)
    print("fault_list_generated.h regenerated")


if __name__ == "__main__":
    main()
