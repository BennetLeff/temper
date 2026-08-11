"""Differential tests: Rust golden-diff kernels vs the pre-migration Python
reference (``temper_placer/testing/golden_diff.py``, Wave-4 PORT).

``golden_diff.py`` is the last sizeable Python module with real
parsing/diffing logic: it compares golden outputs (DSN/sexp/JSON) against
candidates with per-boundary geometric tolerance and produces a structured
``DiffReport``. The parsing + tolerance-diff kernels migrated to
``packages/temper-io-types/src/golden_diff.rs`` are pinned bit-exactly
against a VERBATIM copy of the pre-migration implementations (the
``_oracle_*`` block below, ``git show 2426f5cf5:packages/temper-placer/src/
temper_placer/testing/golden_diff.py``):

- ``_oracle_parse_dsn_places`` / ``_oracle_parse_dsn_nets`` — regex
  extraction of ``(place ...)``/``(net ... (pins ...))`` blocks. Every
  behavioural corner the Rust port must reproduce lives here: the
  ``[\\d.]+`` capture class silently skips *negative* coordinates (no minus
  sign in the class), DSN units are divided by 100 then ``round(x, 6)``
  (round-half-even), and a float-conversion failure on any capture (e.g.
  ``..``) makes the WHOLE places parse return ``None``.
- ``_oracle_diff_dsn`` — component-place tolerance comparison (rotation
  deltas wrap modulo 360) + net pin-count comparison.
- ``_oracle_parse_ses_wires`` / ``_oracle_diff_ses`` — ``(wire NET (path
  layer width x1 y1 x2 y2))`` extraction and Euclidean point-distance
  comparison, wires keyed ``{net}_{enumerate-index}``.
- ``_oracle_diff_json`` / ``_oracle_json_diff_recursive`` — the
  tolerance-aware recursive JSON diff (dict key-union in sorted order,
  list length then index recursion, float-vs-float tolerance categories,
  ``type()``-exact name comparison for everything else).

The ``_oracle_`` prefix (and the ``_oracle_DiffEntry``/``_oracle_DiffReport``
dataclass renames inside the kernels) are the only differences from the
committed file.

The public API (`diff_golden` dispatcher, ``DiffEntry``/``DiffReport``
dataclasses, ``GoldenDiffParseError``, ``DiffReport.to_json``) stays in
Python; the shim delegates the three format kernels to
``temper_io_types.golden_diff_dsn`` / ``golden_diff_ses`` /
``golden_diff_json``. The differential therefore asserts BOTH the raw-Rust
kernel against the oracle AND the shim's ``diff_golden`` against the oracle.

RED state (R1f): this module accesses ``temper_io_types.golden_diff_dsn``
at import time, so the whole file fails to collect with ``AttributeError``
before the Rust surface lands.

Also here: PBT properties (P1-P5, each with an in-test vacuity guard) and
metamorphic relations (MR1-MR3) over generated DSN/SES/JSON documents, plus
a real-production parity run over ``power_pcb_dataset/goldens`` DSN files.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import temper_io_types as _rs
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.testing.golden_diff import diff_golden as shim_diff_golden

# ---------------------------------------------------------------------------
# Verbatim pre-migration oracles (copied from golden_diff.py AS COMMITTED at
# origin/main 2426f5cf5 before the migration; do not edit -- they are the
# reference).  Only the ``_oracle_`` name prefix differs from the committed
# file.
# ---------------------------------------------------------------------------


@dataclass
class _oracle_DiffEntry:
    board: str
    stage: str
    category: str  # "BINARY" | "WITHIN_TOLERANCE" | "BEYOND_TOLERANCE"
    entity: str  # e.g., "net 'HV_IN'" or "component 'Q1'"
    field: str  # e.g., "X coordinate" or "pin count"
    golden_value: str
    candidate_value: str
    delta: float | None = None
    tolerance: float | None = None


@dataclass
class _oracle_DiffReport:
    board: str
    stage: str
    passed: bool
    entries: list[_oracle_DiffEntry] = field(default_factory=list)
    summary: str = ""


def _oracle_parse_dsn_places(dsn_text):
    try:
        pattern = re.compile(r"\(\s*place\s+(\S+)\s+([\d.]+)\s+([\d.]+)\s+\S+\s+([\d.]+)")
        places = {}
        for m in pattern.finditer(dsn_text):
            ref = m.group(1)
            x = float(m.group(2)) / 100.0
            y = float(m.group(3)) / 100.0
            rot = float(m.group(4))
            places[ref] = (round(x, 6), round(y, 6), round(rot, 6))
        return places
    except Exception:
        return None


def _oracle_parse_dsn_nets(dsn_text):
    pattern = re.compile(r"\(\s*net\s+(\S+)\s+\(\s*pins\s+(.*?)\)")
    nets = {}
    for m in pattern.finditer(dsn_text):
        name = m.group(1)
        pins = m.group(2).split()
        nets[name] = len(pins)
    return nets


def _oracle_diff_dsn(board, stage, golden, candidate, tolerance):
    entries = []
    golden_places = _oracle_parse_dsn_places(golden)
    candidate_places = _oracle_parse_dsn_places(candidate)

    if golden_places is None or candidate_places is None:
        entries.append(
            _oracle_DiffEntry(
                board=board,
                stage=stage,
                category="BINARY",
                entity="dsn",
                field="parse",
                golden_value="parse_ok" if golden_places else "parse_fail",
                candidate_value="parse_ok" if candidate_places else "parse_fail",
            )
        )
        return _oracle_DiffReport(
            board=board, stage=stage, passed=False, entries=entries, summary="DSN parse failure"
        )

    all_refs = sorted(set(golden_places.keys()) | set(candidate_places.keys()))
    for ref in all_refs:
        gp = golden_places.get(ref)
        cp = candidate_places.get(ref)
        if gp is None:
            entries.append(
                _oracle_DiffEntry(
                    board=board,
                    stage=stage,
                    category="BINARY",
                    entity=f"component {ref}",
                    field="presence",
                    golden_value="missing",
                    candidate_value="present",
                )
            )
            continue
        if cp is None:
            entries.append(
                _oracle_DiffEntry(
                    board=board,
                    stage=stage,
                    category="BINARY",
                    entity=f"component {ref}",
                    field="presence",
                    golden_value="present",
                    candidate_value="missing",
                )
            )
            continue
        for axis, gv, cv in zip(
            ["X", "Y", "rotation"], [gp[0], gp[1], gp[2]], [cp[0], cp[1], cp[2]]
        ):
            if axis == "rotation":
                delta = abs(gv - cv) % 360.0
                delta = min(delta, 360.0 - delta)
            else:
                delta = abs(gv - cv)
            cat = "WITHIN_TOLERANCE" if delta <= tolerance else "BEYOND_TOLERANCE"
            entries.append(
                _oracle_DiffEntry(
                    board=board,
                    stage=stage,
                    category=cat,
                    entity=f"component {ref}",
                    field=f"{axis} coordinate",
                    golden_value=str(gv),
                    candidate_value=str(cv),
                    delta=delta,
                    tolerance=tolerance,
                )
            )

    golden_nets = _oracle_parse_dsn_nets(golden)
    candidate_nets = _oracle_parse_dsn_nets(candidate)
    all_nets = sorted(set(golden_nets) | set(candidate_nets))
    for net in all_nets:
        gn = golden_nets.get(net)
        cn = candidate_nets.get(net)
        if gn is None:
            entries.append(
                _oracle_DiffEntry(
                    board=board,
                    stage=stage,
                    category="BINARY",
                    entity=f"net '{net}'",
                    field="presence",
                    golden_value="missing",
                    candidate_value="present",
                )
            )
        elif cn is None:
            entries.append(
                _oracle_DiffEntry(
                    board=board,
                    stage=stage,
                    category="BINARY",
                    entity=f"net '{net}'",
                    field="presence",
                    golden_value="present",
                    candidate_value="missing",
                )
            )
        elif gn != cn:
            entries.append(
                _oracle_DiffEntry(
                    board=board,
                    stage=stage,
                    category="BINARY",
                    entity=f"net '{net}'",
                    field="pin_count",
                    golden_value=str(gn),
                    candidate_value=str(cn),
                )
            )

    passed = not any(e.category in ("BINARY", "BEYOND_TOLERANCE") for e in entries)
    failures = [e for e in entries if e.category in ("BINARY", "BEYOND_TOLERANCE")]
    summary = f"{board}/{stage}: {'PASS' if passed else 'FAIL'} — {len(failures)} issues"
    return _oracle_DiffReport(board=board, stage=stage, passed=passed, entries=entries, summary=summary)


def _oracle_parse_ses_wires(ses_text):
    try:
        pattern = re.compile(
            r"\(\s*wire\s+(\S+)\s+\(\s*path\s+\S+\s+[\d.]+\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)"
        )
        wires = {}
        for idx, m in enumerate(pattern.finditer(ses_text)):
            net = m.group(1)
            x1, y1 = float(m.group(2)), float(m.group(3))
            x2, y2 = float(m.group(4)), float(m.group(5))
            wires[f"{net}_{idx}"] = [(x1, y1), (x2, y2)]
        return wires
    except Exception:
        return None


def _oracle_diff_ses(board, stage, golden, candidate, tolerance):
    entries = []
    golden_wires = _oracle_parse_ses_wires(golden)
    candidate_wires = _oracle_parse_ses_wires(candidate)

    if golden_wires is None or candidate_wires is None:
        entries.append(
            _oracle_DiffEntry(
                board=board,
                stage=stage,
                category="BINARY",
                entity="ses",
                field="parse",
                golden_value="parse_ok" if golden_wires else "parse_fail",
                candidate_value="parse_ok" if candidate_wires else "parse_fail",
            )
        )
        return _oracle_DiffReport(
            board=board, stage=stage, passed=False, entries=entries, summary="SES parse failure"
        )

    all_keys = sorted(set(golden_wires.keys()) | set(candidate_wires.keys()))
    for key in all_keys:
        gw = golden_wires.get(key)
        cw = candidate_wires.get(key)
        if gw is None:
            entries.append(
                _oracle_DiffEntry(
                    board=board,
                    stage=stage,
                    category="BINARY",
                    entity=f"wire_{key}",
                    field="presence",
                    golden_value="missing",
                    candidate_value="present",
                )
            )
            continue
        if cw is None:
            entries.append(
                _oracle_DiffEntry(
                    board=board,
                    stage=stage,
                    category="BINARY",
                    entity=f"wire_{key}",
                    field="presence",
                    golden_value="present",
                    candidate_value="missing",
                )
            )
            continue
        for i, (gpt, cpt) in enumerate(zip(gw, cw)):
            delta = math.sqrt((gpt[0] - cpt[0]) ** 2 + (gpt[1] - cpt[1]) ** 2)
            cat = "WITHIN_TOLERANCE" if delta <= tolerance else "BEYOND_TOLERANCE"
            entries.append(
                _oracle_DiffEntry(
                    board=board,
                    stage=stage,
                    category=cat,
                    entity=f"wire_{key}",
                    field=f"point_{i}",
                    golden_value=str(gpt),
                    candidate_value=str(cpt),
                    delta=delta,
                    tolerance=tolerance,
                )
            )

    passed = not any(e.category in ("BINARY", "BEYOND_TOLERANCE") for e in entries)
    failures = [e for e in entries if e.category in ("BINARY", "BEYOND_TOLERANCE")]
    summary = f"{board}/{stage}: {'PASS' if passed else 'FAIL'} — {len(failures)} issues"
    return _oracle_DiffReport(board=board, stage=stage, passed=passed, entries=entries, summary=summary)


def _oracle_diff_json(board, stage, golden, candidate, tolerance):
    entries = []
    try:
        gj = json.loads(golden)
    except json.JSONDecodeError:
        entries.append(
            _oracle_DiffEntry(
                board=board,
                stage=stage,
                category="BINARY",
                entity="json",
                field="parse",
                golden_value="parse_fail",
                candidate_value="parse_ok",
            )
        )
        return _oracle_DiffReport(
            board=board,
            stage=stage,
            passed=False,
            entries=entries,
            summary="Golden JSON parse failure",
        )
    try:
        cj = json.loads(candidate)
    except json.JSONDecodeError:
        entries.append(
            _oracle_DiffEntry(
                board=board,
                stage=stage,
                category="BINARY",
                entity="json",
                field="parse",
                golden_value="parse_ok",
                candidate_value="parse_fail",
            )
        )
        return _oracle_DiffReport(
            board=board,
            stage=stage,
            passed=False,
            entries=entries,
            summary="Candidate JSON parse failure",
        )

    _oracle_json_diff_recursive(gj, cj, tolerance, board, stage, "", entries)

    passed = not any(e.category in ("BINARY", "BEYOND_TOLERANCE") for e in entries)
    failures = [e for e in entries if e.category in ("BINARY", "BEYOND_TOLERANCE")]
    summary = f"{board}/{stage}: {'PASS' if passed else 'FAIL'} — {len(failures)} issues"
    return _oracle_DiffReport(board=board, stage=stage, passed=passed, entries=entries, summary=summary)


def _oracle_json_diff_recursive(golden_val, candidate_val, tolerance, board, stage, path, entries):
    if type(golden_val) != type(candidate_val):  # noqa: E721
        entries.append(
            _oracle_DiffEntry(
                board=board,
                stage=stage,
                category="BINARY",
                entity=path or "root",
                field="type",
                golden_value=str(type(golden_val).__name__),
                candidate_value=str(type(candidate_val).__name__),
            )
        )
        return

    if isinstance(golden_val, dict):
        all_keys = sorted(set(golden_val.keys()) | set(candidate_val.keys()))
        for k in all_keys:
            new_path = f"{path}.{k}" if path else k
            if k not in golden_val:
                entries.append(
                    _oracle_DiffEntry(
                        board=board,
                        stage=stage,
                        category="BINARY",
                        entity=new_path,
                        field="presence",
                        golden_value="missing",
                        candidate_value="present",
                    )
                )
            elif k not in candidate_val:
                entries.append(
                    _oracle_DiffEntry(
                        board=board,
                        stage=stage,
                        category="BINARY",
                        entity=new_path,
                        field="presence",
                        golden_value="present",
                        candidate_value="missing",
                    )
                )
            else:
                _oracle_json_diff_recursive(
                    golden_val[k], candidate_val[k], tolerance, board, stage, new_path, entries
                )
    elif isinstance(golden_val, list):
        if len(golden_val) != len(candidate_val):
            entries.append(
                _oracle_DiffEntry(
                    board=board,
                    stage=stage,
                    category="BINARY",
                    entity=path or "root",
                    field="length",
                    golden_value=str(len(golden_val)),
                    candidate_value=str(len(candidate_val)),
                )
            )
        else:
            for i, (gv, cv) in enumerate(zip(golden_val, candidate_val)):
                _oracle_json_diff_recursive(gv, cv, tolerance, board, stage, f"{path}[{i}]", entries)
    elif isinstance(golden_val, (int, float)):
        if isinstance(golden_val, float) and isinstance(candidate_val, float):
            delta = abs(golden_val - candidate_val)
            cat = "WITHIN_TOLERANCE" if delta <= tolerance else "BEYOND_TOLERANCE"
            entries.append(
                _oracle_DiffEntry(
                    board=board,
                    stage=stage,
                    category=cat,
                    entity=path or "root",
                    field="value",
                    golden_value=str(golden_val),
                    candidate_value=str(candidate_val),
                    delta=delta,
                    tolerance=tolerance,
                )
            )
        elif golden_val != candidate_val:
            entries.append(
                _oracle_DiffEntry(
                    board=board,
                    stage=stage,
                    category="BINARY",
                    entity=path or "root",
                    field="value",
                    golden_value=str(golden_val),
                    candidate_value=str(candidate_val),
                )
            )
    else:
        if str(golden_val) != str(candidate_val):
            entries.append(
                _oracle_DiffEntry(
                    board=board,
                    stage=stage,
                    category="BINARY",
                    entity=path or "root",
                    field="value",
                    golden_value=str(golden_val),
                    candidate_value=str(candidate_val),
                )
            )


# Accessing the Rust surface at import time is what makes this file fail to
# collect (RED) until golden_diff.rs lands.
_RS_DSN = _rs.golden_diff_dsn
_RS_SES = _rs.golden_diff_ses
_RS_JSON = _rs.golden_diff_json

# ---------------------------------------------------------------------------
# Report-normalisation helpers
# ---------------------------------------------------------------------------


def _entry_dict(e) -> dict:
    return {
        "board": e.board,
        "stage": e.stage,
        "category": e.category,
        "entity": e.entity,
        "field": e.field,
        "golden_value": e.golden_value,
        "candidate_value": e.candidate_value,
        "delta": e.delta,
        "tolerance": e.tolerance,
    }


def _report_dict(r) -> dict:
    return {
        "board": r.board,
        "stage": r.stage,
        "passed": r.passed,
        "summary": r.summary,
        "entries": [_entry_dict(e) for e in r.entries],
    }


def _rust_report(board: str, stage: str, result) -> dict:
    entries, passed, summary = result
    return {
        "board": board,
        "stage": stage,
        "passed": passed,
        "summary": summary,
        "entries": [dict(e) for e in entries],
    }


def _assert_report_parity(rust: dict, oracle: dict, label: str) -> None:
    assert rust["passed"] == oracle["passed"], f"{label}: passed {rust['passed']} != {oracle['passed']}"
    assert rust["summary"] == oracle["summary"], (
        f"{label}: summary {rust['summary']!r} != oracle {oracle['summary']!r}"
    )
    assert rust["entries"] == oracle["entries"], (
        f"{label}: {len(rust['entries'])} entries vs oracle {len(oracle['entries'])}; "
        f"first divergence:\nrust={rust['entries'][:5]!r}\noracle={oracle['entries'][:5]!r}"
    )


def _assert_shim_parity(board, stage, golden, candidate, fmt, tolerance, oracle) -> None:
    report = shim_diff_golden(board, stage, golden, candidate, fmt, tolerance)
    assert _report_dict(report) == _report_dict(oracle), (
        f"shim diff_golden diverged from oracle ({fmt}):\n"
        f"shim={_report_dict(report)!r}\noracle={_report_dict(oracle)!r}"
    )


# ---------------------------------------------------------------------------
# Realistic golden/candidate fixtures
# ---------------------------------------------------------------------------

_DSN_GOLDEN = """(pcb temper
 (parser (string_quote ") (space_in_quoted_tokens on))
 (resolution um 10)
 (unit mm)
 (structure
  (layer F.Cu (type signal) (property (index 0)))
  (layer B.Cu (type signal) (property (index 1)))
  (boundary (rect pcb 0 0 10000 8000)))
 (library
  (image SOIC-8_U1
   (pin PS_RECT_0_500x0_500_ALL 1 200 150)
   (pin PS_RECT_0_500x0_500_ALL 4 -200 -150)))
 (placement
  (component SOIC-8_U1
   (place U1 5000 5000 front 0))
  (component SOIC-8_U1
   (place U2 2500 4000 front 90))
  (component SOIC-8_U1
   (place U3 7500 1000 front 180)))
 (network
  (net NET1 (pins U1-1 U2-1))
  (net NET2 (pins U1-4 U2-4))
  (net NET3 (pins U3-1))))
"""

# U1 shifted by +1 DSN unit (0.01 mm), U3 by +500 DSN units (5 mm).
_DSN_SHIFTED = _DSN_GOLDEN.replace(
    "(place U1 5000 5000 front 0)", "(place U1 5001 5000 front 0)"
).replace("(place U3 7500 1000 front 180)", "(place U3 8000 1000 front 180)")

# U2 rotation wrapped by a full turn (90 -> 450): modulo-360 delta is 0.
_DSN_ROTATION_WRAP = _DSN_GOLDEN.replace(
    "(place U2 2500 4000 front 90)", "(place U2 2500 4000 front 450)"
)

# U2 absent from the candidate.
_DSN_MISSING_COMPONENT = _DSN_GOLDEN.replace(
    "  (component SOIC-8_U1\n   (place U2 2500 4000 front 90))\n", ""
)

# A net with no pins in the candidate.
_DSN_MISSING_NET = _DSN_GOLDEN.replace(
    "  (net NET3 (pins U3-1))", "  (net NET3 (pins))"
)

# Negative coordinates are NOT captured by the [\\d.]+ class on either side
# (shared naive behaviour -- the component is silently skipped).
_DSN_NEGATIVE_COORD = _DSN_GOLDEN.replace(
    "(place U3 7500 1000 front 180)", "(place U3 -7500 1000 front 180)"
)

# Malformed places (float() / parse failure on "..") -> "DSN parse failure".
_DSN_MALFORMED = _DSN_GOLDEN.replace(
    "(place U1 5000 5000 front 0)", "(place U1 .. 5000 front 0)"
)

_SES_GOLDEN = """(session
(resolution um 10)
(unit mm)
(routes)
(wire NET1 (path 0 0.250000 0.000000 0.000000 10.000000 10.000000))
(wire NET2 (path 1 0.200000 1.000000 2.000000 3.000000 4.000000))
)
"""

# NET1's end point nudged by (0.3, 0.4) mm -- exactly a 0.5 mm displacement.
_SES_WITHIN = _SES_GOLDEN.replace(
    "(wire NET1 (path 0 0.250000 0.000000 0.000000 10.000000 10.000000))",
    "(wire NET1 (path 0 0.250000 0.000000 0.000000 10.300000 10.400000))",
)

# NET1's end point nudged beyond a 0.5 mm tolerance.
_SES_BEYOND = _SES_GOLDEN.replace(
    "(wire NET1 (path 0 0.250000 0.000000 0.000000 10.000000 10.000000))",
    "(wire NET1 (path 0 0.250000 0.000000 0.000000 10.300001 10.400000))",
)

# A second NET1 wire on the candidate -> a new wire_NET1_1 key (BINARY).
_SES_EXTRA_WIRE = _SES_GOLDEN + (
    "(wire NET1 (path 0 0.250000 0.000000 0.000000 20.000000 20.000000))\n"
)

# Malformed wire (parse failure on "..") -> "SES parse failure".
_SES_MALFORMED = _SES_GOLDEN.replace(
    "(wire NET1 (path 0 0.250000 0.000000 0.000000 10.000000 10.000000))",
    "(wire NET1 (path 0 0.250000 0.000000 .. 10.000000 10.000000))",
)

_JSON_GOLDEN = {
    "net_count": 12,
    "violations": [
        {"net": "HV_IN", "count": 3.0, "ok": True},
        {"net": "LV_SIG", "count": 1.5, "ok": False},
    ],
    "stats": {"elapsed_ms": 12.5, "placement": {"x": 1.0, "y": 2.0}},
    "meta": None,
    "name": "temper",
}
_JSON_GOLDEN_TEXT = json.dumps(_JSON_GOLDEN)

_JSON_FLOAT_BEYOND = json.dumps(
    {**_JSON_GOLDEN, "stats": {**_JSON_GOLDEN["stats"], "elapsed_ms": 12.75}}
)  # delta 0.25 > tol 0.1

_JSON_FLOAT_AT_TOLERANCE = json.dumps(
    {**_JSON_GOLDEN, "stats": {**_JSON_GOLDEN["stats"], "elapsed_ms": 12.5}}
)  # identical

_JSON_NESTED_VALUE_MISMATCH = json.dumps(
    {**_JSON_GOLDEN, "stats": {**_JSON_GOLDEN["stats"], "placement": {"x": 1.5, "y": 2.0}}}
)

_JSON_MISSING_KEY = json.dumps({k: v for k, v in _JSON_GOLDEN.items() if k != "meta"})

_JSON_EXTRA_KEY = json.dumps({**_JSON_GOLDEN, "extra": 7})

_JSON_LIST_LENGTH = json.dumps(
    {**_JSON_GOLDEN, "violations": _JSON_GOLDEN["violations"] + [{"net": "X", "count": 0.0, "ok": True}]}
)

_JSON_TYPE_MISMATCH = json.dumps({**_JSON_GOLDEN, "net_count": 12.0})

_JSON_BOOL_VS_INT = json.dumps({**_JSON_GOLDEN, "net_count": True})

_JSON_NULL_VS_STRING = json.dumps({**_JSON_GOLDEN, "meta": "present"})

_JSON_MALFORMED_GOLDEN = '{"net_count": 12, "violations": [1, 2'

_JSON_MALFORMED_CANDIDATE = '{"net_count": 12, "violations": [1, 2'


def test_oracle_is_verbatim_semantics() -> None:
    """Pins the oracle's own behaviour on hand cases so a broken verbatim
    copy cannot silently agree with a broken port."""
    places = _oracle_parse_dsn_places(_DSN_GOLDEN)
    assert places == {
        "U1": (50.0, 50.0, 0.0),
        "U2": (25.0, 40.0, 90.0),
        "U3": (75.0, 10.0, 180.0),
    }
    nets = _oracle_parse_dsn_nets(_DSN_GOLDEN)
    assert nets == {"NET1": 2, "NET2": 2, "NET3": 1}
    assert _oracle_parse_dsn_places(_DSN_MALFORMED) is None
    wires = _oracle_parse_ses_wires(_SES_GOLDEN)
    assert wires == {
        "NET1_0": [(0.0, 0.0), (10.0, 10.0)],
        "NET2_1": [(1.0, 2.0), (3.0, 4.0)],
    }
    assert _oracle_parse_ses_wires(_SES_MALFORMED) is None
    # The 3-4-5 triangle: a (0.3, 0.4) displacement is exactly 0.5 mm.
    ses_report = _oracle_diff_ses("test", "routing", _SES_GOLDEN, _SES_WITHIN, 0.5)
    assert ses_report.passed
    beyond = _oracle_diff_ses("test", "routing", _SES_GOLDEN, _SES_BEYOND, 0.5)
    assert not beyond.passed


# ---------------------------------------------------------------------------
# Differential: fixture matrix (raw Rust kernel AND shim vs oracle)
# ---------------------------------------------------------------------------

_BOARD = "temper"
_DSN_STAGE = "apply_placements"
_SES_STAGE = "sequential_routing"
_JSON_STAGE = "drc_validation"


@pytest.mark.parametrize(
    ("label", "golden", "candidate", "tolerance"),
    [
        ("identical", _DSN_GOLDEN, _DSN_GOLDEN, 0.001),
        ("shifted_x_0.01mm", _DSN_GOLDEN, _DSN_SHIFTED, 0.001),
        ("shifted_x_within_tol", _DSN_GOLDEN, _DSN_SHIFTED, 10.0),
        ("rotation_wrap_360", _DSN_GOLDEN, _DSN_ROTATION_WRAP, 0.001),
        ("missing_component", _DSN_GOLDEN, _DSN_MISSING_COMPONENT, 0.001),
        ("missing_net", _DSN_GOLDEN, _DSN_MISSING_NET, 0.001),
        ("negative_coord_skipped_both_sides", _DSN_GOLDEN, _DSN_NEGATIVE_COORD, 0.001),
        ("malformed_golden", _DSN_MALFORMED, _DSN_GOLDEN, 0.001),
        ("malformed_candidate", _DSN_GOLDEN, _DSN_MALFORMED, 0.001),
        ("malformed_both", _DSN_MALFORMED, _DSN_MALFORMED, 0.001),
        ("empty_golden", "", _DSN_GOLDEN, 0.001),
        ("empty_both", "", "", 0.001),
    ],
)
def test_dsn_parity_matrix(label, golden, candidate, tolerance) -> None:
    oracle = _oracle_diff_dsn(_BOARD, _DSN_STAGE, golden, candidate, tolerance)
    _assert_report_parity(
        _rust_report(_BOARD, _DSN_STAGE, _RS_DSN(_BOARD, _DSN_STAGE, golden, candidate, tolerance)),
        _report_dict(oracle),
        f"dsn/{label}",
    )
    _assert_shim_parity(_BOARD, _DSN_STAGE, golden, candidate, "dsn", tolerance, oracle)


@pytest.mark.parametrize(
    ("label", "golden", "candidate", "tolerance"),
    [
        ("identical", _SES_GOLDEN, _SES_GOLDEN, 0.000001),
        ("within_exact_0.5mm", _SES_GOLDEN, _SES_WITHIN, 0.5),
        ("beyond_0.5mm", _SES_GOLDEN, _SES_BEYOND, 0.5),
        ("extra_wire_binary", _SES_GOLDEN, _SES_EXTRA_WIRE, 0.000001),
        ("missing_wire_binary", _SES_EXTRA_WIRE, _SES_GOLDEN, 0.000001),
        ("malformed_golden", _SES_MALFORMED, _SES_GOLDEN, 0.000001),
        ("malformed_candidate", _SES_GOLDEN, _SES_MALFORMED, 0.000001),
        ("empty_golden", "", _SES_GOLDEN, 0.000001),
        ("empty_both", "", "", 0.000001),
    ],
)
def test_ses_parity_matrix(label, golden, candidate, tolerance) -> None:
    oracle = _oracle_diff_ses(_BOARD, _SES_STAGE, golden, candidate, tolerance)
    _assert_report_parity(
        _rust_report(_BOARD, _SES_STAGE, _RS_SES(_BOARD, _SES_STAGE, golden, candidate, tolerance)),
        _report_dict(oracle),
        f"ses/{label}",
    )
    _assert_shim_parity(_BOARD, _SES_STAGE, golden, candidate, "ses", tolerance, oracle)


@pytest.mark.parametrize(
    ("label", "golden", "candidate", "tolerance"),
    [
        ("identical", _JSON_GOLDEN_TEXT, _JSON_GOLDEN_TEXT, 0.1),
        ("float_beyond", _JSON_GOLDEN_TEXT, _JSON_FLOAT_BEYOND, 0.1),
        ("nested_value_mismatch", _JSON_GOLDEN_TEXT, _JSON_NESTED_VALUE_MISMATCH, 0.1),
        ("missing_key", _JSON_GOLDEN_TEXT, _JSON_MISSING_KEY, 0.1),
        ("extra_key", _JSON_GOLDEN_TEXT, _JSON_EXTRA_KEY, 0.1),
        ("list_length", _JSON_GOLDEN_TEXT, _JSON_LIST_LENGTH, 0.1),
        ("type_mismatch_int_float", _JSON_GOLDEN_TEXT, _JSON_TYPE_MISMATCH, 0.1),
        ("bool_vs_int", _JSON_GOLDEN_TEXT, _JSON_BOOL_VS_INT, 0.1),
        ("null_vs_string", _JSON_GOLDEN_TEXT, _JSON_NULL_VS_STRING, 0.1),
        ("malformed_golden", _JSON_MALFORMED_GOLDEN, _JSON_GOLDEN_TEXT, 0.1),
        ("malformed_candidate", _JSON_GOLDEN_TEXT, _JSON_MALFORMED_CANDIDATE, 0.1),
        ("malformed_both", _JSON_MALFORMED_GOLDEN, _JSON_MALFORMED_CANDIDATE, 0.1),
        ("empty_golden", "", _JSON_GOLDEN_TEXT, 0.1),
        ("empty_both", "", "", 0.1),
    ],
)
def test_json_parity_matrix(label, golden, candidate, tolerance) -> None:
    oracle = _oracle_diff_json(_BOARD, _JSON_STAGE, golden, candidate, tolerance)
    _assert_report_parity(
        _rust_report(_BOARD, _JSON_STAGE, _RS_JSON(_BOARD, _JSON_STAGE, golden, candidate, tolerance)),
        _report_dict(oracle),
        f"json/{label}",
    )
    _assert_shim_parity(_BOARD, _JSON_STAGE, golden, candidate, "json", tolerance, oracle)


# Tolerance-edge pins: an exactly-at-tolerance delta is WITHIN_TOLERANCE
# (<=), one ULP-scale above is BEYOND.  A `>=`/`>` or `<=`/`<` slip on
# either side flips these.
def test_json_tolerance_boundary_exact_equality_is_within() -> None:
    golden = json.dumps({"x": 1.0})
    candidate = json.dumps({"x": 1.25})
    oracle = _oracle_diff_json("test", "drc", golden, candidate, 0.25)
    rust = _rust_report("test", "drc", _RS_JSON("test", "drc", golden, candidate, 0.25))
    assert rust == _report_dict(oracle)
    assert rust["passed"]
    assert all(e["category"] == "WITHIN_TOLERANCE" for e in rust["entries"])
    assert rust["entries"][0]["delta"] == 0.25


def test_json_tolerance_boundary_just_above_is_beyond() -> None:
    golden = json.dumps({"x": 1.0})
    candidate = json.dumps({"x": 1.250001})
    oracle = _oracle_diff_json("test", "drc", golden, candidate, 0.25)
    rust = _rust_report("test", "drc", _RS_JSON("test", "drc", golden, candidate, 0.25))
    assert rust == _report_dict(oracle)
    assert not rust["passed"]
    assert rust["entries"][0]["category"] == "BEYOND_TOLERANCE"


def test_summary_string_is_exactly_the_python_fstring() -> None:
    """Pins the summary's exact text (incl. the em-dash) so both sides
    cannot silently drift together."""
    rust = _rust_report(
        _BOARD, _DSN_STAGE, _RS_DSN(_BOARD, _DSN_STAGE, _DSN_GOLDEN, _DSN_SHIFTED, 0.001)
    )
    assert rust["summary"] == "temper/apply_placements: FAIL — 2 issues"
    assert rust["passed"] is False
    assert len(rust["entries"]) == 3 * 3  # 3 components x 3 axes, nets identical
    beyond = [e for e in rust["entries"] if e["category"] == "BEYOND_TOLERANCE"]
    assert len(beyond) == 2  # U1 x (0.01mm) and U3 x (5mm)

    ok = _rust_report(
        _BOARD, _DSN_STAGE, _RS_DSN(_BOARD, _DSN_STAGE, _DSN_GOLDEN, _DSN_GOLDEN, 0.001)
    )
    assert ok["summary"] == "temper/apply_placements: PASS — 0 issues"


# ---------------------------------------------------------------------------
# Real-production DSN parity (the shipped golden corpus)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.parametrize("dsn_name", ["apply_placements", "zone_geometry", "slot_generation"])
def test_real_production_dsn_parity(dsn_name: str) -> None:
    path = _REPO_ROOT / "power_pcb_dataset" / "goldens" / "temper_routable" / f"{dsn_name}.dsn"
    if not path.exists():
        pytest.skip(f"golden corpus missing: {path}")
    golden = path.read_text()
    candidate = re.sub(r"(place (\S+) )(\d+)", lambda m: f"{m.group(1)}{int(m.group(3)) + 1}", golden)
    assert golden != candidate
    tolerance = 0.01
    oracle = _oracle_diff_dsn("temper_routable", dsn_name, golden, candidate, tolerance)
    rust = _rust_report(
        "temper_routable", dsn_name, _RS_DSN("temper_routable", dsn_name, golden, candidate, tolerance)
    )
    _assert_report_parity(rust, _report_dict(oracle), f"real dsn/{dsn_name}")
    _assert_shim_parity(
        "temper_routable", dsn_name, golden, candidate, "dsn", tolerance, oracle
    )
    assert len(rust["entries"]) > 0


# ---------------------------------------------------------------------------
# PBT: generation strategies
# ---------------------------------------------------------------------------

_REF_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"


@st.composite
def dsn_doc(draw):
    n_comp = draw(st.integers(1, 4))
    n_nets = draw(st.integers(1, 4))
    refs = draw(
        st.lists(
            st.text(min_size=1, max_size=6, alphabet=_REF_CHARS),
            min_size=n_comp,
            max_size=n_comp,
            unique=True,
        )
    )
    places = []
    for ref in refs:
        x = draw(st.integers(0, 10000))
        y = draw(st.integers(0, 10000))
        rot = draw(st.integers(0, 720))
        places.append(f"(place {ref} {x} {y} front {rot})")
    nets = []
    for i in range(n_nets):
        pin_refs = draw(st.lists(st.sampled_from(refs), min_size=0, max_size=3))
        pin_names = " ".join(f"{r}-{draw(st.integers(1, 8))}" for r in pin_refs)
        nets.append(f"(net NET{i} (pins {pin_names}))")
    return (
        "(pcb t\n(placement\n  "
        + "\n  ".join(places)
        + "\n)\n(network\n  "
        + "\n  ".join(nets)
        + "\n))\n"
    )


@st.composite
def ses_doc(draw):
    n_wires = draw(st.integers(1, 4))
    lines = []
    for _ in range(n_wires):
        net = draw(st.text(min_size=1, max_size=6, alphabet=_REF_CHARS))
        layer = draw(st.integers(0, 3))
        width = draw(st.integers(1, 1000))
        coords = [draw(st.integers(0, 10000)) for _ in range(4)]
        lines.append(
            "(wire {} (path {} {:.6f} {:.6f} {:.6f} {:.6f} {:.6f}))".format(
                net,
                layer,
                width / 1_000_000.0,
                *(c / 1_000_000.0 for c in coords),
            )
        )
    return "(session\n(resolution um 10)\n(unit mm)\n(routes)\n" + "\n".join(lines) + "\n)\n"


@st.composite
def json_doc(draw):
    return draw(
        st.recursive(
            st.one_of(
                st.none(),
                st.booleans(),
                st.integers(-(10**12), 10**12),
                st.floats(
                    min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False
                ),
                st.text(min_size=0, max_size=12),
            ),
            lambda children: st.one_of(
                st.lists(children, min_size=0, max_size=5),
                st.dictionaries(
                    st.text(min_size=1, max_size=8),
                    children,
                    min_size=0,
                    max_size=5,
                ),
            ),
            max_leaves=30,
        )
    )


def _bump_first_place_x(doc: str, amount: int) -> str:
    def repl(m: re.Match) -> str:
        ref, x, rest = m.group(1), int(m.group(2)), m.group(3)
        return f"(place {ref} {x + amount}{rest}"

    out, n = re.subn(r"\(place (\S+) (\d+)( \d+ front \d+)", repl, doc, count=1)
    assert n == 1, "fixture mutation failed to find a place line"
    return out


# ---------------------------------------------------------------------------
# PBT: properties (each with an in-test vacuity guard)
# ---------------------------------------------------------------------------

_MAX_EXAMPLES = 60


@given(doc=dsn_doc())
@settings(max_examples=_MAX_EXAMPLES)
def test_p1_identical_docs_always_pass(doc: str) -> None:
    """The identity diff is always passed, never BINARY, across all three
    formats -- a structural symmetry the kernels must not break."""
    assert "(place" in doc  # vacuity guard: at least one component
    for fmt, rs_fn, stage, oracle_fn in (
        ("dsn", _RS_DSN, _DSN_STAGE, _oracle_diff_dsn),
        ("ses", _RS_SES, _SES_STAGE, _oracle_diff_ses),
    ):
        rust = _rust_report(_BOARD, stage, rs_fn(_BOARD, stage, doc, doc, 0.001))
        oracle = oracle_fn(_BOARD, stage, doc, doc, 0.001)
        assert rust == _report_dict(oracle)
        assert rust["passed"]
        cats = {e["category"] for e in rust["entries"]}
        assert cats <= {"WITHIN_TOLERANCE"}, f"{fmt}: unexpected categories {cats}"
        assert all(e["delta"] == 0.0 for e in rust["entries"])


@given(doc=json_doc())
@settings(max_examples=_MAX_EXAMPLES)
def test_p1_identical_json_always_pass(doc) -> None:
    text = json.dumps(doc)
    rust = _rust_report(_BOARD, _JSON_STAGE, _RS_JSON(_BOARD, _JSON_STAGE, text, text, 0.001))
    oracle = _oracle_diff_json(_BOARD, _JSON_STAGE, text, text, 0.001)
    assert rust == _report_dict(oracle)
    assert rust["passed"]
    assert all(e["delta"] == 0.0 for e in rust["entries"])


@given(doc=dsn_doc())
@settings(max_examples=_MAX_EXAMPLES)
def test_p2_tolerance_monotone(doc: str) -> None:
    """Raising tolerance can only shrink (or keep) the failing set; passed
    can only go False -> True, never backwards."""
    assert "(place" in doc  # vacuity guard
    candidate = _bump_first_place_x(doc, 500)  # 5 mm shift on the first place
    t_small = 0.001
    t_big = 100.0
    small = _rust_report(_BOARD, _DSN_STAGE, _RS_DSN(_BOARD, _DSN_STAGE, doc, candidate, t_small))
    big = _rust_report(_BOARD, _DSN_STAGE, _RS_DSN(_BOARD, _DSN_STAGE, doc, candidate, t_big))
    small_failing = {e["entity"] for e in small["entries"] if e["category"] != "WITHIN_TOLERANCE"}
    big_failing = {e["entity"] for e in big["entries"] if e["category"] != "WITHIN_TOLERANCE"}
    assert big_failing <= small_failing
    assert bool(big["passed"]) >= bool(small["passed"])
    assert not small["passed"]  # vacuity guard: the 5mm shift IS beyond t_small
    assert big["passed"]


@given(doc=dsn_doc())
@settings(max_examples=_MAX_EXAMPLES)
def test_p3_rotation_wraps_mod_360(doc: str) -> None:
    """Rotating a component by a full turn produces a zero rotation delta --
    the modulo-360 wrap must make r and r+360 indistinguishable."""
    assert "(place" in doc  # vacuity guard
    m = re.search(r"\(place (\S+) (\d+) (\d+) front (\d+)", doc)
    assert m is not None
    ref, x, y, rot = m.group(1), m.group(2), m.group(3), int(m.group(4))
    wrapped = doc.replace(
        f"(place {ref} {x} {y} front {rot})", f"(place {ref} {x} {y} front {rot + 360})"
    )
    rust = _rust_report(_BOARD, _DSN_STAGE, _RS_DSN(_BOARD, _DSN_STAGE, doc, wrapped, 0.001))
    assert rust["passed"]
    rot_entries = [e for e in rust["entries"] if e["field"] == "rotation coordinate"]
    assert rot_entries  # vacuity guard: rotation axes were compared
    assert all(e["delta"] == 0.0 for e in rot_entries)


@given(offset=st.floats(min_value=1.0, max_value=100.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=_MAX_EXAMPLES)
def test_p4_json_tolerance_boundary_flips(offset: float) -> None:
    """A float pair whose delta is exactly the tolerance is WITHIN (<=);
    the same pair widened by one ULP-scale is BEYOND.  This is the `<=`
    vs `<` boundary both sides must agree on."""
    tol = 0.25
    g = 1.0
    at = g + tol  # delta == tol exactly (0.25 is representable)
    assert at - g == tol
    above = at + offset * 1e-12  # tiny, strictly above
    rust_at = _rust_report(
        _BOARD, _JSON_STAGE, _RS_JSON(_BOARD, _JSON_STAGE, json.dumps({"v": g}), json.dumps({"v": at}), tol)
    )
    rust_above = _rust_report(
        _BOARD, _JSON_STAGE, _RS_JSON(_BOARD, _JSON_STAGE, json.dumps({"v": g}), json.dumps({"v": above}), tol)
    )
    oracle_at = _oracle_diff_json(_BOARD, _JSON_STAGE, json.dumps({"v": g}), json.dumps({"v": at}), tol)
    oracle_above = _oracle_diff_json(
        _BOARD, _JSON_STAGE, json.dumps({"v": g}), json.dumps({"v": above}), tol
    )
    assert rust_at == _report_dict(oracle_at)
    assert rust_above == _report_dict(oracle_above)
    assert rust_at["passed"]
    assert rust_above["entries"][0]["category"] == "BEYOND_TOLERANCE"


@given(
    golden=st.dictionaries(st.text(min_size=1, max_size=8), json_doc(), min_size=2, max_size=5)
)
@settings(max_examples=_MAX_EXAMPLES)
def test_p5_missing_or_extra_key_is_binary_and_fails(golden) -> None:
    """A key present in exactly one side is a BINARY presence entry and the
    report does not pass -- the diff must not swallow structural
    differences under tolerance."""
    assert len(golden) >= 2  # vacuity guard: dropping one key leaves a real dict
    text = json.dumps(golden)
    dropped = {k: v for k, v in golden.items() if k != list(golden)[0]}
    rust = _rust_report(
        _BOARD, _JSON_STAGE, _RS_JSON(_BOARD, _JSON_STAGE, text, json.dumps(dropped), 100.0)
    )
    oracle = _oracle_diff_json(
        _BOARD, _JSON_STAGE, text, json.dumps(dropped), 100.0
    )
    assert rust == _report_dict(oracle)
    assert not rust["passed"]
    presence = [e for e in rust["entries"] if e["field"] == "presence"]
    assert presence  # vacuity guard: the dropped key produced an entry
    assert all(e["category"] == "BINARY" for e in presence)


# ---------------------------------------------------------------------------
# Differential over generated documents
# ---------------------------------------------------------------------------


@given(golden=dsn_doc(), candidate=dsn_doc(), tol=st.floats(min_value=0.0001, max_value=10.0))
@settings(max_examples=_MAX_EXAMPLES)
def test_random_dsn_parity(golden, candidate, tol: float) -> None:
    oracle = _oracle_diff_dsn(_BOARD, _DSN_STAGE, golden, candidate, tol)
    rust = _rust_report(
        _BOARD, _DSN_STAGE, _RS_DSN(_BOARD, _DSN_STAGE, golden, candidate, tol)
    )
    _assert_report_parity(rust, _report_dict(oracle), "random dsn")


@given(golden=ses_doc(), candidate=ses_doc(), tol=st.floats(min_value=0.0001, max_value=10.0))
@settings(max_examples=_MAX_EXAMPLES)
def test_random_ses_parity(golden, candidate, tol: float) -> None:
    oracle = _oracle_diff_ses(_BOARD, _SES_STAGE, golden, candidate, tol)
    rust = _rust_report(
        _BOARD, _SES_STAGE, _RS_SES(_BOARD, _SES_STAGE, golden, candidate, tol)
    )
    _assert_report_parity(rust, _report_dict(oracle), "random ses")


@given(
    golden=json_doc(),
    candidate=json_doc(),
    tol=st.floats(min_value=0.0001, max_value=10.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=_MAX_EXAMPLES)
def test_random_json_parity(golden, candidate, tol: float) -> None:
    """The random JSON differential is also the float-str() parity sweep:
    every float leaf's `str(float)` rendering and its tolerance category
    are compared byte-for-byte against CPython's repr over a broad value
    range."""
    gt, ct = json.dumps(golden), json.dumps(candidate)
    oracle = _oracle_diff_json(_BOARD, _JSON_STAGE, gt, ct, tol)
    rust = _rust_report(_BOARD, _JSON_STAGE, _RS_JSON(_BOARD, _JSON_STAGE, gt, ct, tol))
    _assert_report_parity(rust, _report_dict(oracle), "random json")


# ---------------------------------------------------------------------------
# Metamorphic relations (R1d)
# ---------------------------------------------------------------------------


def _mirror_report(report: dict) -> dict:
    mirrored = []
    for e in report["entries"]:
        e = dict(e)
        e["golden_value"], e["candidate_value"] = e["candidate_value"], e["golden_value"]
        mirrored.append(e)
    return {**report, "entries": mirrored}


@given(golden=dsn_doc(), candidate=dsn_doc(), tol=st.floats(min_value=0.0001, max_value=10.0))
@settings(max_examples=_MAX_EXAMPLES)
def test_mr1_diff_is_antisymmetric_under_argument_swap(golden, candidate, tol: float) -> None:
    """diff(g, c) is the mirror of diff(c, g): every entry's two value
    strings swap, deltas/categories/summary are unchanged."""
    ab = _rust_report(_BOARD, _DSN_STAGE, _RS_DSN(_BOARD, _DSN_STAGE, golden, candidate, tol))
    ba = _rust_report(_BOARD, _DSN_STAGE, _RS_DSN(_BOARD, _DSN_STAGE, candidate, golden, tol))
    assert ab == _mirror_report(ba)
    assert ab["passed"] == ba["passed"]
    assert ab["summary"] == ba["summary"]


@given(golden=dsn_doc(), candidate=dsn_doc(), tol=st.floats(min_value=0.0001, max_value=10.0))
@settings(max_examples=_MAX_EXAMPLES)
def test_mr2_common_offset_leaves_deltas_unchanged(golden, candidate, tol: float) -> None:
    """Adding the same offset to EVERY component's X in both documents
    leaves every delta and category unchanged -- the diff is translation
    invariant (only the rendered value strings shift)."""
    assert "(place" in golden  # vacuity guard
    g_shifted = re.sub(r"(\(place \S+ )\d+", lambda m: f"{m.group(1)}9999", golden)
    c_shifted = re.sub(r"(\(place \S+ )\d+", lambda m: f"{m.group(1)}9999", candidate)
    base = _rust_report(_BOARD, _DSN_STAGE, _RS_DSN(_BOARD, _DSN_STAGE, golden, candidate, tol))
    shifted = _rust_report(
        _BOARD, _DSN_STAGE, _RS_DSN(_BOARD, _DSN_STAGE, g_shifted, c_shifted, tol)
    )
    assert len(base["entries"]) == len(shifted["entries"])
    for eb, es in zip(base["entries"], shifted["entries"]):
        assert eb["category"] == es["category"]
        assert eb["delta"] == es["delta"]
        assert eb["tolerance"] == es["tolerance"]
        assert eb["field"] == es["field"]
        assert eb["entity"] == es["entity"]


@given(
    golden=json_doc(),
    candidate=json_doc(),
    tol=st.floats(min_value=0.0001, max_value=10.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=_MAX_EXAMPLES)
def test_mr3_json_key_order_is_irrelevant(golden, candidate, tol: float) -> None:
    """Permuting a JSON object's key order (both sides) yields the
    byte-identical report -- dict keys are diffed in sorted order, so the
    serialization order must never leak into the report."""
    if not isinstance(golden, dict) or not isinstance(candidate, dict):
        return  # vacuity guard below
    if len(golden) < 2 or len(candidate) < 2:
        return  # vacuity guard: need at least two keys to permute
    gt, ct = json.dumps(golden), json.dumps(candidate)
    gp = json.dumps(dict(reversed(list(golden.items()))))
    cp = json.dumps(dict(reversed(list(candidate.items()))))
    assert gp != gt and cp != ct  # vacuity guard: the permutation really reordered
    base = _rust_report(
        _BOARD, _JSON_STAGE, _RS_JSON(_BOARD, _JSON_STAGE, gt, ct, tol)
    )
    perm = _rust_report(
        _BOARD, _JSON_STAGE, _RS_JSON(_BOARD, _JSON_STAGE, gp, cp, tol)
    )
    assert base == perm
    # And the oracle agrees with both arms.
    oracle = _oracle_diff_json(_BOARD, _JSON_STAGE, gt, ct, tol)
    assert base == _report_dict(oracle)
