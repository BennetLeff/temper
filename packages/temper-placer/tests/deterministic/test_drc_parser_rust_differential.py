"""Differential test: deterministic feedback DRC report parsing, Rust vs oracle.

Wave 4, **Phase 5** (deterministic hubs slice). The KiCad DRC report traversal
of ``temper_placer/deterministic/feedback/drc_parser.py``
(``_process_raw_violation``) moves to
``temper_design_bundle_python.deterministic_hubs.process_drc_violation``. The
JSON file read stays Python (``json.load`` — library semantics not
reimplemented); the dict traversal, items/pos extraction and clearance-regex
compute move to Rust. ``DRCViolation`` stays a Python dataclass.

Bit-exactness pins:
- ``type``/``severity``/``description`` defaults on missing keys
  (``"unknown"``/``"error"``/``""``) and pass-through of present values
  (including non-str values, which are returned unchanged — the kernel carries
  the Python object).
- ``pos`` is the FIRST item carrying a ``pos`` key; ``(item["pos"]["x"],
  item["pos"]["y"])`` pass through with their concrete int/float type (the
  type-carrying canon catches a float-coercion drift).
- Clearance regexes tried in the oracle's order (pattern 2 ``clearance X mm;
  actual Y mm`` first, then pattern 1 ``Xmm < Ymm required``), each group
  mapped to the correct field (pattern 2: g1=required g2=actual; pattern 1:
  g1=actual g2=required).
- ``data.get("violations", [])`` and ``data.get("unconnected_items", [])`` are
  both parsed, in that order.
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb
import tests.deterministic._drc_parser_py_oracle as _oracle
from tests.core._contract_canon import canon

# Rust symbols under test — must exist or this file fails to collect (RED).
_DH = _tdb.deterministic_hubs
RS_PROCESS = _DH.process_drc_violation


def _process_rust(v):
    """Run the Rust kernel and rebuild the shim's DRCViolation-equivalent fields."""
    return RS_PROCESS(v)


def _assert_parity(v):
    o = _oracle._process_raw_violation(v)
    fields = _process_rust(v)
    (
        type_obj,
        items,
        severity_obj,
        description_obj,
        pos,
        required,
        actual,
    ) = fields
    shim = (
        type_obj,
        tuple(items),
        severity_obj,
        description_obj,
        pos,
        required,
        actual,
    )
    oracle = (
        o.type,
        tuple(o.items),
        o.severity,
        o.description,
        o.pos,
        o.required,
        o.actual,
    )
    assert canon(shim) == canon(oracle), f"parity divergence: {shim} vs {oracle}"


# ---------------------------------------------------------------------------
# Field pass-through + defaults
# ---------------------------------------------------------------------------


def test_missing_keys_defaults():
    _assert_parity({})


def test_all_fields_present():
    _assert_parity(
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


def test_non_str_values_pass_through():
    # JSON "type" is always str in real reports, but the oracle passes non-str
    # values through untouched; the kernel must too.
    _assert_parity({"type": 5, "severity": 7})


def test_int_pos_preserved():
    # int-typed pos coordinates pass through WITHOUT float coercion.
    _assert_parity(
        {"items": [{"description": "x", "pos": {"x": 0, "y": 5}}]}
    )


# ---------------------------------------------------------------------------
# items / pos traversal
# ---------------------------------------------------------------------------


def test_first_pos_wins():
    _assert_parity(
        {
            "items": [
                {"description": "a", "pos": {"x": 1.0, "y": 2.0}},
                {"description": "b", "pos": {"x": 3.0, "y": 4.0}},
            ]
        }
    )


def test_items_descriptions_only():
    _assert_parity(
        {
            "items": [
                {"description": "Via at (1, 2)"},
                {"description": "PTH pad Q2-1"},
                {},  # empty item -> empty description
            ]
        }
    )


def test_unconnected_items_are_separate_top_level():
    # parse_kicad_drc appends violations THEN unconnected_items; the per-item
    # kernel is identical for both. Pin the traversal order at the file level.
    report = {
        "violations": [{"type": "clearance", "description": "clearance 0.2 mm; actual 0.1 mm"}],
        "unconnected_items": [{"type": "unconnected_items", "items": [{"description": "Net X"}]}],
    }
    _assert_parity(report["violations"][0])
    _assert_parity(report["unconnected_items"][0])


# ---------------------------------------------------------------------------
# Clearance regex extraction (order + group mapping)
# ---------------------------------------------------------------------------


def test_clearance_pattern2_first():
    _assert_parity({"description": "clearance 0.2000 mm; actual 0.1958 mm"})


def test_clearance_pattern1_fallback():
    _assert_parity({"description": "Clearance violation (0.15mm < 0.20mm required)"})


def test_clearance_extra_text_around_pattern2():
    _assert_parity({"description": "Zone clearance 0.3000 mm; actual 0.2900 mm (net X)"})


def test_clearance_extra_text_around_pattern1():
    _assert_parity({"description": "NOTE: Clearance violation (1.0mm < 1.5mm required)!"})


def test_no_clearance_pattern():
    _assert_parity({"description": "something else"})


def test_clearance_pattern_not_regex_overlap():
    # pattern2's regex must not match pattern1's text and vice versa.
    _assert_parity({"description": "clearance 0.2000 mm; actual 0.1958 mm required"})
    _assert_parity({"description": "0.15mm < 0.20mm required, clearance 0.5 mm"})


def test_clearance_both_patterns_present_but_different_values():
    # A description containing BOTH patterns with DIFFERENT values: pattern 2
    # ("clearance X mm; actual Y mm") is tried FIRST, so the oracle takes
    # required=0.1 / actual=0.2 and must NOT fall through to pattern 1
    # (which would yield actual=0.5 / required=0.6). This is the mutant
    # discriminator for the pattern-order pin (M9 in the mutation campaign).
    _assert_parity(
        {"description": "clearance 0.1000 mm; actual 0.2000 mm and 0.5mm < 0.6mm required"}
    )
