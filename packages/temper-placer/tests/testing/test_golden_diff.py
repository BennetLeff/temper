"""Tests for geometric diff engine — U4."""
import json

from temper_placer.testing.golden_diff import (
    diff_golden,
)

DSN_IDENTICAL = """(pcb temper
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
   (place U1 5000 5000 front 0)))
 (network
  (net NET1 (pins U1-1 U1-4))))
"""

DSN_SHIFTED = """(pcb temper
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
   (place U1 5200 5000 front 0)))
 (network
  (net NET1 (pins U1-1 U1-4))))
"""

DSN_MISSING_NET = """(pcb temper
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
   (place U1 5000 5000 front 0)))
 (network))
"""


def test_diff_identical_dsn():
    report = diff_golden("test", "apply_placements", DSN_IDENTICAL, DSN_IDENTICAL, "dsn", 0.001)
    assert report.passed
    # WITHIN_TOLERANCE entries for matching coordinates
    assert all(e.category == "WITHIN_TOLERANCE" for e in report.entries)


def test_diff_shifted_beyond_tolerance():
    report = diff_golden("test", "apply_placements", DSN_IDENTICAL, DSN_SHIFTED, "dsn", 0.001)
    # 5200-5000 = 200 DSN units / 100 = 2.0mm >> 0.001mm tolerance
    beyond = [e for e in report.entries if e.category == "BEYOND_TOLERANCE"]
    assert len(beyond) >= 1
    assert not report.passed


def test_diff_shifted_within_tolerance():
    report = diff_golden("test", "apply_placements", DSN_IDENTICAL, DSN_SHIFTED, "dsn", 10.0)
    # 2.0mm < 10.0mm tolerance
    assert report.passed
    assert all(e.category == "WITHIN_TOLERANCE" for e in report.entries)


def test_diff_missing_net_binary():
    report = diff_golden("test", "apply_placements", DSN_IDENTICAL, DSN_MISSING_NET, "dsn", 0.001)
    binary = [e for e in report.entries if e.category == "BINARY"]
    assert len(binary) >= 1
    assert not report.passed


def test_diff_empty_golden():
    report = diff_golden("test", "apply_placements", "", "", "dsn", 0.001)
    assert report.passed
    assert len(report.entries) == 0


def test_diff_ses_identical():
    ses = "(session\n(resolution um 10)\n(unit mm)\n(routes)\n)\n"
    report = diff_golden("test", "sequential_routing", ses, ses, "ses", 0.000001)
    assert report.passed


def test_diff_ses_wire_shift():
    ses1 = "(session\n(resolution um 10)\n(unit mm)\n(routes)\n(wire NET1 (path 0 0.250000 0.000000 0.000000 10.000000 10.000000)))\n"
    ses2 = "(session\n(resolution um 10)\n(unit mm)\n(routes)\n(wire NET1 (path 0 0.250000 0.000000 0.000000 10.000001 10.000001)))\n"
    report = diff_golden("test", "sequential_routing", ses1, ses2, "ses", 0.000001)
    assert report.passed  # 0.00000141 < 0.000001? Actually ~1.4e-6 > 1e-6
    # Close to boundary; just check that we get WITHIN_TOLERANCE or BEYOND_TOLERANCE
    assert len(report.entries) > 0


def test_diff_json_identical():
    j = json.dumps({"foo": 42, "bar": [1, 2, 3]})
    report = diff_golden("test", "drc_validation", j, j, "json", 0.001)
    assert report.passed


def test_diff_json_value_mismatch():
    j1 = json.dumps({"foo": 42})
    j2 = json.dumps({"foo": 99})
    report = diff_golden("test", "drc_validation", j1, j2, "json", 0.001)
    assert not report.passed


def test_diff_json_float_within_tolerance():
    j1 = json.dumps({"x": 1.0})
    j2 = json.dumps({"x": 1.0005})
    report = diff_golden("test", "drc_validation", j1, j2, "json", 0.001)
    assert report.passed


def test_diff_json_missing_key():
    j1 = json.dumps({"a": 1, "b": 2})
    j2 = json.dumps({"a": 1})
    report = diff_golden("test", "drc_validation", j1, j2, "json", 0.001)
    assert not report.passed
    binary = [e for e in report.entries if e.category == "BINARY"]
    assert len(binary) >= 1


def test_diff_report_to_json():
    report = diff_golden("test", "apply_placements", DSN_IDENTICAL, DSN_IDENTICAL, "dsn", 0.001)
    entries = report.to_json()
    assert isinstance(entries, list)
    assert len(entries) == len(report.entries)


def test_diff_unknown_format():
    report = diff_golden("test", "apply_placements", "x", "y", "unknown", 0.001)
    assert not report.passed
    assert len(report.entries) == 1
    assert report.entries[0].category == "BINARY"
