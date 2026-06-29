from __future__ import annotations

import json
import re

from .violation_mapper import DRCViolation


def parse_kicad_drc(file_path: str) -> list[DRCViolation]:
    """
    Parse a KiCad DRC report in JSON format.

    Args:
        file_path: Path to the .json DRC report.

    Returns:
        List of DRCViolation objects.
    """
    with open(file_path) as f:
        data = json.load(f)

    violations = []

    # KiCad JSON format has violations and unconnected_items
    raw_violations = data.get('violations', [])
    for v in raw_violations:
        violations.append(_process_raw_violation(v))

    unconnected = data.get('unconnected_items', [])
    for v in unconnected:
        violations.append(_process_raw_violation(v))

    return violations

def _process_raw_violation(v: dict) -> DRCViolation:
    """Helper to convert raw dict to DRCViolation."""
    drc_type = v.get('type', 'unknown')
    severity = v.get('severity', 'error')
    description = v.get('description', '')

    items = []
    pos = None

    for item in v.get('items', []):
        desc = item.get('description', '')
        items.append(desc)

        # Take first valid position found in items
        if pos is None and 'pos' in item:
            pos = (item['pos']['x'], item['pos']['y'])

    drc_v = DRCViolation(
        type=drc_type,
        items=items,
        severity=severity,
        description=description,
        pos=pos
    )

    # Try to extract clearance values from description
    # "clearance 0.2000 mm; actual 0.1958 mm"
    match = re.search(r'clearance ([\d\.]+) mm; actual ([\d\.]+) mm', description)
    if match:
        drc_v.required = float(match.group(1))
        drc_v.actual = float(match.group(2))
    else:
        # TDD format: "Clearance violation (0.15mm < 0.20mm required)"
        match = re.search(r'([\d\.]+)mm < ([\d\.]+)mm required', description)
        if match:
            drc_v.actual = float(match.group(1))
            drc_v.required = float(match.group(2))

    return drc_v
