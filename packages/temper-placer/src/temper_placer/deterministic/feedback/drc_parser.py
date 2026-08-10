from __future__ import annotations

import json

import temper_design_bundle_python as _tdb
import temper_drc_rs as _tdrc

_DH = _tdb.deterministic_hubs


def parse_kicad_drc(file_path: str) -> _tdrc.DrcReport:
    """
    Parse a KiCad DRC report in JSON format.

    Args:
        file_path: Path to the .json DRC report.

    Returns:
        DrcReport -- the typed report container (list-compatible
        ``__len__``/``__bool__``/``__iter__`` over ``Violation`` objects).

    Wave 4, **Phase 5** (deterministic hubs slice): the JSON file read stays
    Python (``json.load`` -- library semantics not reimplemented); the dict
    traversal, items/pos extraction and clearance-regex compute of
    ``_process_raw_violation`` run in Rust
    (``temper_design_bundle_python.deterministic_hubs.process_drc_violation``).
    Phase-A **U9** (rust-orchestration-engine plan): the wire types are now
    typed -- ``temper_drc_rs.Violation`` for the raw violation and
    ``temper_drc_rs.DrcReport`` for the parsed report (replacing the
    ``DRCViolation`` dataclass / ``list[DRCViolation]``).
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

    return _tdrc.DrcReport(violations=violations)


def _process_raw_violation(v: dict) -> _tdrc.Violation:
    """Helper to convert raw dict to a typed Violation (Rust-backed)."""
    drc_type, items, severity, description, pos, required, actual = _DH.process_drc_violation(v)
    return _tdrc.Violation(
        type=drc_type, items=items, severity=severity, description=description, pos=pos,
        required=required, actual=actual,
    )
