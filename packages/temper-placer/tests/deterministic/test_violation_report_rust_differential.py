"""Differential test: Phase-A U9 typed DRC-feedback wire types in Rust
(temper_drc_rs.Violation / temper_drc_rs.DrcReport) vs the pinned Python
dataclass/list wire (Wave-4 discipline contract G1/G2).

The wire-format types being migrated are:

  | Python wire type                 | File                        | Rust target    |
  |----------------------------------|-----------------------------|----------------|
  | ``DRCViolation`` dataclass       | feedback/violation_mapper.py | ``Violation``  |
  | ``list[DRCViolation]`` (report)  | feedback/drc_parser.py       | ``DrcReport``  |

``Violation`` reproduces the mutable dataclass's full field surface
(``type``/``severity``/``description`` pass through with concrete types --
including non-str values and int-typed ``pos`` coordinates, matching the
kernel's pass-through contract; ``items`` is the ordered description list;
``required``/``actual`` are the clearance floats). ``DrcReport`` is the
typed container returned by ``parse_kicad_drc`` with list-compatible
``__len__``/``__bool__``/``__iter__`` semantics.

The ``_oracle_*`` blocks below are VERBATIM copies of the pre-migration
implementations (feedback/violation_mapper.py's ``DRCViolation`` dataclass
and feedback/drc_parser.py's ``_process_raw_violation`` / ``parse_kicad_drc``
as committed at the dispatch base, origin/main). Do NOT edit them -- they
are the reference.

The Rust symbols ``_tdrc.Violation`` / ``_tdrc.DrcReport`` do not exist yet
(RED); this file fails to collect until the Phase-A U9 Rust implementation
lands (G1 test-before-code).

Comparison convention: type-carrying ``canon`` (bit-exact, never tolerance);
floats via ``float.hex()``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import temper_drc_rs as _tdrc
from tests.core._contract_canon import canon

# Rust symbols under test -- must exist or this file fails to collect (RED).
ORACLE_VIOLATION = _tdrc.Violation
ORACLE_REPORT = _tdrc.DrcReport

from temper_placer.deterministic.feedback.drc_parser import (  # noqa: E402
    _process_raw_violation,
    parse_kicad_drc,
)


# ---------------------------------------------------------------------------
# Oracle 1 — DRCViolation dataclass (violation_mapper.py, verbatim)
# ---------------------------------------------------------------------------

@dataclass
class _OracleDRCViolation:
    """Raw DRC violation data from KiCad."""

    type: str
    items: list[str] = field(default_factory=list)
    severity: str = "error"
    description: str = ""
    pos: tuple[float, float] | None = None
    required: float | None = None
    actual: float | None = None


# ---------------------------------------------------------------------------
# Oracle 2 — _process_raw_violation / parse_kicad_drc (drc_parser.py, verbatim)
# ---------------------------------------------------------------------------

def _oracle_process_raw_violation(v):
    """Pre-migration ``_process_raw_violation``, verbatim (drc_parser.py)."""
    drc_type = v.get("type", "unknown")
    severity = v.get("severity", "error")
    description = v.get("description", "")

    items = []
    pos = None

    for item in v.get("items", []):
        desc = item.get("description", "")
        items.append(desc)

        # Take first valid position found in items
        if pos is None and "pos" in item:
            pos = (item["pos"]["x"], item["pos"]["y"])

    drc_v = _OracleDRCViolation(
        type=drc_type, items=items, severity=severity, description=description, pos=pos
    )

    # Try to extract clearance values from description
    # "clearance 0.2000 mm; actual 0.1958 mm"
    match = re.search(r"clearance ([\d\.]+) mm; actual ([\d\.]+) mm", description)
    if match:
        drc_v.required = float(match.group(1))
        drc_v.actual = float(match.group(2))
    else:
        # TDD format: "Clearance violation (0.15mm < 0.20mm required)"
        match = re.search(r"([\d\.]+)mm < ([\d\.]+)mm required", description)
        if match:
            drc_v.actual = float(match.group(1))
            drc_v.required = float(match.group(2))

    return drc_v


def _oracle_parse_kicad_drc(data):
    """Pre-migration ``parse_kicad_drc`` body, verbatim (drc_parser.py) --
    takes the already-loaded report dict (the file read is library
    semantics, pinned on the shim side)."""
    violations = []

    # KiCad JSON format has violations and unconnected_items
    raw_violations = data.get("violations", [])
    for v in raw_violations:
        violations.append(_oracle_process_raw_violation(v))

    unconnected = data.get("unconnected_items", [])
    for v in unconnected:
        violations.append(_oracle_process_raw_violation(v))

    return violations


# ---------------------------------------------------------------------------
# Field-surface helpers
# ---------------------------------------------------------------------------

def _violation_fields(v):
    """The wire field surface both sides expose, canonicalized."""
    return (
        canon(v.type),
        tuple(canon(i) for i in v.items),
        canon(v.severity),
        canon(v.description),
        canon(v.pos),
        canon(v.required),
        canon(v.actual),
    )


# ---------------------------------------------------------------------------
# Violation — typed constructor vs the dataclass
# ---------------------------------------------------------------------------

def test_violation_constructor_defaults_match_dataclass():
    got = ORACLE_VIOLATION(type="clearance")
    oracle = _OracleDRCViolation(type="clearance")
    assert _violation_fields(got) == _violation_fields(oracle)


def test_violation_constructor_full_surface_matches_dataclass():
    got = ORACLE_VIOLATION(
        type="clearance",
        items=["Pad Q2-D on F.Cu", "Track on F.Cu at (10.0, 20.0)"],
        severity="error",
        description="clearance 0.2000 mm; actual 0.1958 mm",
        pos=(10.0, 20.0),
        required=0.2,
        actual=0.1958,
    )
    oracle = _OracleDRCViolation(
        type="clearance",
        items=["Pad Q2-D on F.Cu", "Track on F.Cu at (10.0, 20.0)"],
        severity="error",
        description="clearance 0.2000 mm; actual 0.1958 mm",
        pos=(10.0, 20.0),
        required=0.2,
        actual=0.1958,
    )
    assert _violation_fields(got) == _violation_fields(oracle)


def test_violation_int_pos_preserved_through_pyclass():
    """int-typed pos coordinates must NOT be coerced to float (the oracle's
    pass-through contract; canon distinguishes int from float)."""
    got = ORACLE_VIOLATION(type="clearance", pos=(0, 5))
    oracle = _OracleDRCViolation(type="clearance", pos=(0, 5))
    assert _violation_fields(got) == _violation_fields(oracle)
    assert isinstance(got.pos[0], int)


def test_violation_non_str_fields_pass_through():
    """type/severity pass through with their concrete type (duck-typed
    dataclass parity -- the parse kernel's documented non-str contract)."""
    got = ORACLE_VIOLATION(type=5, severity=7)
    oracle = _OracleDRCViolation(type=5, severity=7)
    assert _violation_fields(got) == _violation_fields(oracle)


def test_violation_is_mutable_like_dataclass():
    """The dataclass was mutable (``drc_v.required = ...`` after
    construction); the pyclass keeps the set attributes."""
    got = ORACLE_VIOLATION(type="clearance")
    got.required = 0.2
    got.actual = 0.15
    assert got.required == 0.2
    assert got.actual == 0.15


# ---------------------------------------------------------------------------
# Shim _process_raw_violation — typed Violation vs the pinned oracle
# ---------------------------------------------------------------------------

def _assert_parse_parity(payload):
    shim = _process_raw_violation(payload)
    oracle = _oracle_process_raw_violation(payload)
    assert isinstance(shim, ORACLE_VIOLATION)
    assert _violation_fields(shim) == _violation_fields(oracle)


def test_process_raw_violation_missing_keys_defaults():
    _assert_parse_parity({})


def test_process_raw_violation_all_fields_present():
    _assert_parse_parity(
        {
            "type": "clearance",
            "severity": "error",
            "description": "clearance 0.2000 mm; actual 0.1958 mm",
            "items": [
                {"description": "Pad Q2-D on F.Cu", "pos": {"x": 10.0, "y": 20.0}},
                {"description": "Track on F.Cu"},
            ],
        }
    )


def test_process_raw_violation_non_str_pass_through():
    _assert_parse_parity({"type": 5, "severity": 7})


def test_process_raw_violation_int_pos_preserved():
    _assert_parse_parity({"items": [{"description": "x", "pos": {"x": 0, "y": 5}}]})


def test_process_raw_violation_tdd_clearance_format():
    _assert_parse_parity(
        {"description": "Clearance violation (0.15mm < 0.20mm required)"}
    )


# ---------------------------------------------------------------------------
# DrcReport — the typed container returned by parse_kicad_drc
# ---------------------------------------------------------------------------

def _assert_report_parity(data):
    report = ORACLE_REPORT(
        violations=[
            _process_raw_violation(v)
            for v in (data.get("violations", []) + data.get("unconnected_items", []))
        ]
    )
    oracle = _oracle_parse_kicad_drc(data)
    assert isinstance(report, ORACLE_REPORT)
    assert len(report) == len(oracle)
    assert bool(report) == bool(oracle)
    assert [len(v.items) for v in report] == [len(v.items) for v in oracle]
    for rv, ov in zip(report, oracle):
        assert _violation_fields(rv) == _violation_fields(ov)


def test_drc_report_merges_violations_then_unconnected():
    data = {
        "violations": [
            {"type": "clearance", "description": "clearance 0.2 mm; actual 0.1 mm"}
        ],
        "unconnected_items": [
            {"type": "unconnected_items", "items": [{"description": "Net X"}]}
        ],
    }
    _assert_report_parity(data)


def test_drc_report_empty_report():
    data = {}
    report = ORACLE_REPORT()
    assert len(report) == 0
    assert not report
    assert list(report) == []
    assert report.violations == []
    assert _oracle_parse_kicad_drc(data) == []


def test_parse_kicad_drc_returns_typed_report(tmp_path):
    data = {
        "violations": [
            {"type": "clearance", "description": "clearance 0.2 mm; actual 0.1 mm"},
            {"type": "shorting_items", "items": [{"description": "Pad Q2-D on F.Cu"}]},
        ],
        "unconnected_items": [{"type": "unconnected_items", "items": [{"description": "N1"}]}],
    }
    path = tmp_path / "drc.json"
    path.write_text(json.dumps(data))

    report = parse_kicad_drc(str(path))
    assert isinstance(report, ORACLE_REPORT)
    assert len(report) == 3
    for rv, ov in zip(report, _oracle_parse_kicad_drc(data)):
        assert _violation_fields(rv) == _violation_fields(ov)


def test_parse_kicad_drc_report_iteration_feeds_mapper(tmp_path):
    """The orchestrator maps every raw violation: iteration yields Violation
    pyclasses whose field surface the mapper reads."""
    data = {
        "violations": [
            {
                "type": "clearance",
                "items": [{"description": "of Q2", "pos": {"x": 10.0, "y": 5.0}}],
            }
        ]
    }
    path = tmp_path / "drc.json"
    path.write_text(json.dumps(data))
    report = parse_kicad_drc(path)
    for v in report:
        assert isinstance(v, ORACLE_VIOLATION)
        assert v.type == "clearance"
        assert v.pos == (10.0, 5.0)
        assert v.required is None
