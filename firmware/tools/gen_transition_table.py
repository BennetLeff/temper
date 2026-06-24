#!/usr/bin/env python3
"""
Regenerate firmware/main/transition_table.h from firmware/transition_table.yaml.

Usage:
    python3 firmware/tools/gen_transition_table.py

The script is idempotent — it only overwrites transition_table.h when the
generated content differs from the current file.
"""

import re
import sys
import os
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader


def parse_state_machine_header(header_path):
    """Extract STATE_*, EVENT_*, and FAULT_* members from state_machine.h."""
    header_path = Path(header_path)
    with open(header_path, 'r') as f:
        content = f.read()

    state_names = []
    event_names = []
    fault_names = set()

    # Parse STATE_LIST X-macro entries
    m = re.search(
        r'#define\s+STATE_LIST\(X\)(.*?)(?:#define\s+EXPAND_STATE_ENUM|\Z)',
        content, re.DOTALL)
    if m:
        for sym, name in re.findall(r'X\((\w+),\s*"([^"]+)"\)', m.group(1)):
            state_names.append((sym, name))

    # Parse EVENT_LIST X-macro entries
    m = re.search(
        r'#define\s+EVENT_LIST\(X\)(.*?)(?:#define\s+EXPAND_EVENT_ENUM|\Z)',
        content, re.DOTALL)
    if m:
        for sym, name in re.findall(r'X\((\w+),\s*"([^"]+)"\)', m.group(1)):
            event_names.append((sym, name))

    # Parse FAULT_LIST X-macro entries from generated file
    fault_list_path = header_path.parent / "fault_list_generated.h"
    if fault_list_path.exists():
        with open(fault_list_path, 'r') as ff:
            fault_content = ff.read()
        m = re.search(
            r'#define\s+FAULT_LIST\(X\)(.*?)(?:/\*|\Z)',
            fault_content, re.DOTALL)
    else:
        # Fallback: parse from state_machine.h for backward compatibility
        m = re.search(
            r'#define\s+FAULT_LIST\(X\)(.*?)(?:#define\s+EXPAND_FAULT_ENUM|\Z)',
            content, re.DOTALL)
    if m:
        for sym, _ in re.findall(r'X\((\w+),\s*"([^"]+)"\)', m.group(1)):
            fault_names.add(sym)

    return state_names, event_names, fault_names


def validate_transitions(transitions, state_names, event_names, fault_names):
    """Validate all transition rows have valid from/to/event/fault values."""
    state_set = {s for s, _ in state_names}
    event_set = {e for e, _ in event_names}
    errors = []

    for i, row in enumerate(transitions):
        from_s = row.get('from', '')
        to_s = row.get('to', '')
        event = row.get('event', '')
        fault = row.get('fault')

        if from_s not in state_set:
            errors.append(
                f"ERROR row {i}: 'from' value '{from_s}' not in STATE_LIST")
        if to_s not in state_set:
            errors.append(
                f"ERROR row {i}: 'to' value '{to_s}' not in STATE_LIST")
        if event not in event_set:
            errors.append(
                f"ERROR row {i}: 'event' value '{event}' not in EVENT_LIST")
        if fault and fault not in fault_names:
            errors.append(
                f"ERROR row {i}: 'fault' value '{fault}' not in FAULT_LIST")

    return errors


def check_no_duplicates(transitions):
    """Check no duplicate (from, event) pairs exist."""
    lookup = {}
    errors = []
    for i, row in enumerate(transitions):
        key = (row['from'], row['event'])
        if key in lookup:
            errors.append(
                f"ERROR: ({key[0]}, {key[1]}) has duplicate transition rows "
                f"(rows {lookup[key]} and {i})")
        lookup[key] = i
    return errors

def check_state_coverage(transitions, state_names, event_names):
    """Check every state has at least one transition row defined.
    Returns errors for states with zero rows (catches new states without
    manifest updates)."""
    states_with_rows = {row['from'] for row in transitions}
    errors = []
    for s_enum, s_name in state_names:
        if s_enum not in states_with_rows:
            errors.append(
                f"ERROR: state {s_enum} has no transition rows in manifest")
    return errors


def main():
    repo_root = Path(__file__).resolve().parent.parent
    manifest_path = repo_root / "transition_table.yaml"
    header_path = repo_root / "main" / "state_machine.h"
    template_path = Path(__file__).resolve().parent / "transition_table.h.j2"
    output_path = repo_root / "main" / "transition_table.h"

    if not manifest_path.exists():
        print(f"ERROR: manifest not found at {manifest_path}", file=sys.stderr)
        sys.exit(1)

    if not header_path.exists():
        print(f"ERROR: header not found at {header_path}", file=sys.stderr)
        sys.exit(1)

    # Parse header
    state_names, event_names, fault_names = parse_state_machine_header(
        str(header_path))

    if not state_names:
        print("ERROR: could not parse STATE_LIST from state_machine.h",
              file=sys.stderr)
        sys.exit(1)
    if not event_names:
        print("ERROR: could not parse EVENT_LIST from state_machine.h",
              file=sys.stderr)
        sys.exit(1)

    # Load manifest
    with open(manifest_path) as f:
        manifest = yaml.safe_load(f)

    transitions = manifest.get('transitions', [])

    # Validate row values
    val_errors = validate_transitions(
        transitions, state_names, event_names, fault_names)
    if val_errors:
        for e in val_errors:
            print(e, file=sys.stderr)
        sys.exit(1)

    # Check for duplicate (from, event) pairs
    dup_errors = check_no_duplicates(transitions)
    if dup_errors:
        for e in dup_errors:
            print(e, file=sys.stderr)
        sys.exit(1)

    # Check every state has at least one transition row
    cov_errors = check_state_coverage(transitions, state_names, event_names)
    if cov_errors:
        for e in cov_errors:
            print(e, file=sys.stderr)
        sys.exit(1)

    # Build cell data for Jinja2 template
    transition_cells = {}
    fault_cells = {}
    for row in transitions:
        key = (row['from'], row['event'])
        transition_cells[key] = row['to']
        fault = row.get('fault')
        if fault:
            fault_cells[key] = fault

    # Render template
    env = Environment(loader=FileSystemLoader(template_path.parent))
    template = env.get_template(template_path.name)
    rendered = template.render(
        state_names=state_names,
        event_names=event_names,
        transition_cells=transition_cells,
        fault_cells=fault_cells,
    )

    # Ensure trailing newline
    if not rendered.endswith("\n"):
        rendered += "\n"

    # Idempotent write
    tmp_path = output_path.with_suffix(".h.tmp")
    with open(tmp_path, "w") as f:
        f.write(rendered)

    if output_path.exists():
        with open(output_path) as f:
            existing = f.read()
        if existing == rendered:
            tmp_path.unlink()
            print("transition_table.h up to date")
            return

    tmp_path.rename(output_path)
    print("transition_table.h regenerated")


if __name__ == "__main__":
    main()
