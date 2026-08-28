"""Pinned oracle for the Rust golden-diff kernels.

This is retained as the pre-migration Python reference
(``temper_placer/testing/golden_diff.py``, Wave-4 PORT).

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
dataclass renames inside the retained kernels) identifies the verbatim
reference block; the retired binding differential tests are intentionally
omitted.

The former Python public API delegated to ``temper_io_types.golden_diff_dsn`` /
``golden_diff_ses`` / ``golden_diff_json``. Those bindings had no production
callers and were retired; this file remains as a pinned, executable copy of
the pre-migration oracle for Rust-side regression tests.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field


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

# NET1's end point nudged by +0.5 mm in X -- a displacement whose delta is
# EXACTLY the tolerance (0.5, an exactly-representable value, so the
# sqrt(dx^2+dy^2) delta is the exact float 0.5 and the `<=` boundary is
# pinned rather than float-noise-dependent).
_SES_WITHIN = _SES_GOLDEN.replace(
    "(wire NET1 (path 0 0.250000 0.000000 0.000000 10.000000 10.000000))",
    "(wire NET1 (path 0 0.250000 0.000000 0.000000 10.500000 10.000000))",
)

# The same displacement plus one ULP-scale overshoot: strictly beyond 0.5.
_SES_BEYOND = _SES_GOLDEN.replace(
    "(wire NET1 (path 0 0.250000 0.000000 0.000000 10.000000 10.000000))",
    "(wire NET1 (path 0 0.250000 0.000000 0.000000 10.500001 10.000000))",
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
    # A +0.5 mm X-only displacement is EXACTLY at the 0.5 tolerance (the
    # `<=` boundary), so the within fixture passes and the +1e-6 overshoot
    # fails.
    ses_report = _oracle_diff_ses("test", "routing", _SES_GOLDEN, _SES_WITHIN, 0.5)
    assert ses_report.passed
    beyond = _oracle_diff_ses("test", "routing", _SES_GOLDEN, _SES_BEYOND, 0.5)
    assert not beyond.passed
