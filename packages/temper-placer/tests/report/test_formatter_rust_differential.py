"""Differential test: report/formatter.py compute (temper-io-types) vs the
pinned Python oracle.

Wave 4, Phase 5 — the report surface migration. The Rust migration
(reproducing ``temper_placer/report/formatter.py`` bit-identically in the
``temper-io-types`` crate) is driven through the delegation shim
``temper_placer.report.formatter``; the pre-migration implementation is
pinned verbatim as the oracle (``_formatter_py_oracle.py``).

Every assertion drives IDENTICAL inputs through both sides and compares
bit-exactly: text/HTML output as byte-identical strings, JSON via
``json.loads`` re-serialised with the same ``json.dumps`` the shim uses
(so int-vs-float leaf types and key order are both pinned), floats via
``float.hex()``.

The module-scope references to ``_rust.format_text`` etc. are the RED arm:
before the Rust surface lands this file fails to collect (AttributeError).
"""

from __future__ import annotations

import json
import random

import temper_io_types as _rust

import tests.report._formatter_py_oracle as _oracle
from temper_placer.report.formatter import format_html, format_json, format_text
from temper_placer.validation.drc_result import (
    CheckResult,
    Issue,
    Location,
    RunResult,
    Severity,
)

# Module-scope RED arm.
assert hasattr(_rust, "report_format_text")
assert hasattr(_rust, "report_format_json_data")
assert hasattr(_rust, "report_format_html")


def _make_result(rng: random.Random) -> RunResult:
    severities = [Severity.CRITICAL, Severity.ERROR, Severity.WARNING, Severity.INFO]
    checks = []
    for _ in range(rng.randint(0, 5)):
        issues = []
        for _ in range(rng.randint(0, 4)):
            loc = None
            if rng.random() < 0.7:
                loc = Location(
                    x=rng.uniform(-100, 100),
                    y=rng.uniform(-100, 100),
                    layer=rng.choice(["F.Cu", "B.Cu", "Edge.Cuts", None]),
                )
            details = {}
            if rng.random() < 0.5:
                details = {f"k{i}": rng.choice([1, 2.5, "s", True, None]) for i in range(rng.randint(0, 3))}
            issues.append(
                Issue(
                    severity=rng.choice(severities),
                    code=f"CODE_{rng.randint(1, 99)}",
                    message=rng.choice(
                        ["spacing violation", "min clearance 0.2mm", "ø drill", "é unicode 中文"]
                    ),
                    category=rng.choice(["clearance", "creepage", "erc", ""]),
                    check_name="c",
                    affected_items=rng.sample(
                        ["C1", "R2", "U3", "Q4", "L5"], rng.randint(0, 3)
                    ),
                    location=loc,
                    details=details,
                )
            )
        metrics = {}
        if rng.random() < 0.6:
            metrics = {
                "min_clearance_mm": rng.uniform(0.1, 10.0),
                "overlap_count": rng.randint(0, 9),
                "density": rng.uniform(0, 1),
            }
        checks.append(
            CheckResult(
                check_name=f"check_{rng.randint(1, 9)}",
                passed=rng.random() < 0.6,
                issues=issues,
                elapsed_ms=rng.uniform(0.0, 5000.0),
                metrics=metrics,
            )
        )
    return RunResult(check_results=checks, total_elapsed_ms=rng.uniform(0.0, 60000.0))


def _fixtures() -> list[RunResult]:
    rng = random.Random(0xC0FFEE)
    results = [_make_result(rng) for _ in range(30)]
    # Hand-built edge cases.
    empty = RunResult(check_results=[], total_elapsed_ms=0.0)
    single = RunResult(
        check_results=[
            CheckResult(
                check_name="only",
                passed=True,
                issues=[
                    Issue(
                        severity=Severity.ERROR,
                        code="E1",
                        message="m",
                        category="c",
                        check_name="only",
                        affected_items=["R1"],
                        location=Location(x=1.25, y=-2.75, layer="F.Cu"),
                        details={"a": 1},
                    )
                ],
                elapsed_ms=0.1,
            )
        ],
        total_elapsed_ms=0.1,
    )
    results.extend([empty, single])
    return results


def _run_json_key(data) -> tuple:
    """Canonicalise a parsed JSON structure with concrete leaf types."""
    if isinstance(data, dict):
        return tuple((k, _run_json_key(v)) for k, v in data.items())
    if isinstance(data, list):
        return tuple(_run_json_key(v) for v in data)
    if isinstance(data, bool):
        return ("bool", data)
    if isinstance(data, int):
        return ("int", data)
    if isinstance(data, float):
        return ("float", data.hex())
    return ("str", data)


def test_text_byte_identical():
    for result in _fixtures():
        assert format_text(result) == _oracle.format_text(result)


def test_json_byte_identical():
    for result in _fixtures():
        assert format_json(result) == _oracle.format_json(result)


def test_json_shape_and_leaf_types_identical():
    for result in _fixtures():
        ours = json.loads(format_json(result))
        theirs = json.loads(_oracle.format_json(result))
        assert _run_json_key(ours) == _run_json_key(theirs)


def test_html_byte_identical():
    for result in _fixtures():
        for name in ["", "main", "placement é", "a<b>&\"c"]:
            assert format_html(result, name, None) == _oracle.format_html(result, name, None)


def test_text_layout_pins():
    """Structural pins on the text form: header band, status, check lines."""
    rng = random.Random(7)
    result = _make_result(rng)
    text = format_text(result)
    assert text.startswith("=" * 80 + "\ntemper-drc Check Report\n" + "=" * 80)
    assert "\nStatus: " in text
    assert "\nRuntime: " in text
    # Every check line renders one ✓/✗.
    assert text.count("✓") == sum(1 for c in result.check_results if c.passed)
    assert text.count("✗") == sum(1 for c in result.check_results if not c.passed)


def test_json_key_order_pinned():
    """Insertion order of the JSON dicts is pinned, not sorted."""
    result = RunResult(
        check_results=[
            CheckResult(
                check_name="b",
                passed=True,
                issues=[],
                elapsed_ms=1.0,
                metrics={"z": 1.0, "a": 2},
            )
        ],
        total_elapsed_ms=3.0,
    )
    ours = json.loads(format_json(result))
    theirs = json.loads(_oracle.format_json(result))
    assert list(ours.keys()) == list(theirs.keys())
    assert list(ours["checks"][0].keys()) == list(theirs["checks"][0].keys())
    assert list(ours["checks"][0]["metrics"].keys()) == ["z", "a"]
