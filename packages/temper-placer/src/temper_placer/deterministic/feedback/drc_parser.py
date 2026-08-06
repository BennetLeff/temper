from __future__ import annotations

import json

import temper_design_bundle_python as _tdb

from .violation_mapper import DRCViolation

_DH = _tdb.deterministic_hubs


def parse_kicad_drc(file_path: str) -> list[DRCViolation]:
    """
    Parse a KiCad DRC report in JSON format.

    Args:
        file_path: Path to the .json DRC report.

    Returns:
        List of DRCViolation objects.

    Wave 4, **Phase 5** (deterministic hubs slice): the JSON file read stays
    Python (``json.load`` — library semantics not reimplemented); the dict
    traversal, items/pos extraction and clearance-regex compute of
    ``_process_raw_violation`` run in Rust
    (``temper_design_bundle_python.deterministic_hubs.process_drc_violation``).
    """
    with open(file_path) as f:
        data = json.load(f)

    violations = []

    # KiCad JSON format has violations and unconnected_items
    raw_violations = data.get("violations", [])
    for v in raw_violations:
        violations.append(_process_raw_violation(v))

    unconnected = data.get("unconnected_items", [])
    for v in unconnected:
        violations.append(_process_raw_violation(v))

    return violations


def _process_raw_violation(v: dict) -> DRCViolation:
    """Helper to convert raw dict to DRCViolation (Rust-backed)."""
    drc_type, items, severity, description, pos, required, actual = _DH.process_drc_violation(v)
    return DRCViolation(
        type=drc_type, items=items, severity=severity, description=description, pos=pos,
        required=required, actual=actual,
    )
