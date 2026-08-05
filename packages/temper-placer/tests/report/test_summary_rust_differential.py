"""Differential test: report/summary.py compute (temper-io-types) vs the
pinned Python oracle.

Wave 4, Phase 5 — the report surface migration. The Rust migration
(reproducing ``temper_placer/report/summary.py`` bit-identically in the
``temper-io-types`` crate) is driven through the delegation shim
``temper_placer.report.summary``; the pre-migration implementation is
pinned verbatim as the oracle (``_summary_py_oracle.py``).

Output is compared byte-identical; floats via ``float.hex()``; the
`Board Size` line pins int-vs-float rendering of the placement dims.
"""

from __future__ import annotations

import random

import temper_io_types as _rust

import tests.report._summary_py_oracle as _oracle
from temper_placer.report.summary import _extract_key_metrics, generate_summary
from temper_placer.validation.drc_result import (
    CheckResult,
    Issue,
    RunResult,
    Severity,
)
from temper_placer.validation.drc_types import Placement

# Module-scope RED arm.
assert hasattr(_rust, "report_generate_summary")


def _make_result(rng: random.Random) -> RunResult:
    checks = []
    for _ in range(rng.randint(0, 6)):
        issues = []
        for _ in range(rng.randint(0, 4)):
            issues.append(
                Issue(
                    severity=rng.choice(
                        [Severity.CRITICAL, Severity.ERROR, Severity.WARNING, Severity.INFO]
                    ),
                    code=f"C{rng.randint(1, 50)}",
                    message="msg",
                    category=rng.choice(["clearance", "creepage", "erc", "thermal"]),
                    check_name="c",
                    affected_items=[],
                )
            )
        metrics = {}
        for key in ["min_clearance_mm", "overlap_count", "max_loop_area_mm2",
                    "ground_discontinuities", "floating_pins", "other"]:
            if rng.random() < 0.4:
                metrics[key] = rng.choice([rng.uniform(0.0, 50.0), rng.randint(0, 5), 0.0])
        checks.append(
            CheckResult(
                check_name=f"chk{rng.randint(1, 8)}",
                passed=rng.random() < 0.6,
                issues=issues,
                elapsed_ms=rng.uniform(0.0, 3000.0),
                metrics=metrics,
            )
        )
    return RunResult(check_results=checks, total_elapsed_ms=rng.uniform(0.0, 60000.0))


def _make_placement(rng: random.Random) -> Placement:
    from temper_placer.validation.drc_types import ComponentPlacement

    comps = {
        f"R{i}": ComponentPlacement(
            ref=f"R{i}", footprint="fp", x=rng.uniform(0, 100), y=rng.uniform(0, 100),
            rotation=0.0, layer="F.Cu", width=1.0, height=1.0,
        )
        for i in range(rng.randint(0, 8))
    }
    p = Placement(components=comps)
    p.nets = {f"n{i}": ["R0"] for i in range(rng.randint(0, 6))}
    p.zones = {f"z{i}": (0.0, 0.0, 1.0, 1.0) for i in range(rng.randint(0, 3))}
    p.board_width = rng.choice([100.0, 100, 63.5, 80.0])
    p.board_height = rng.choice([80.0, 80, 50.25, 60])
    return p


def _fixtures() -> list[tuple[RunResult, Placement]]:
    rng = random.Random(0xBEEF)
    out = [(_make_result(rng), _make_placement(rng)) for _ in range(25)]
    # Edge: empty everything.
    from temper_placer.validation.drc_types import ComponentPlacement

    out.append((RunResult(check_results=[], total_elapsed_ms=0.0),
                Placement(components={
                    "X": ComponentPlacement(ref="X", footprint="fp", x=0.0, y=0.0,
                                            rotation=0.0, layer="F.Cu", width=1.0, height=1.0)})))
    return out


def test_summary_byte_identical():
    for result, placement in _fixtures():
        assert generate_summary(result, placement, None) == _oracle.generate_summary(
            result, placement, None
        )


def test_extract_key_metrics_identical():
    for result, _ in _fixtures():
        ours = _extract_key_metrics(result)
        theirs = _oracle._extract_key_metrics(result)
        assert [(name, _metric_key(v)) for name, v in ours] == [
            (name, _metric_key(v)) for name, v in theirs
        ]


def _metric_key(v):
    if isinstance(v, bool):
        return ("bool", v)
    if isinstance(v, int):
        return ("int", v)
    if isinstance(v, float):
        return ("float", v.hex())
    return ("str", v)


def _comp(ref: str):
    from temper_placer.validation.drc_types import ComponentPlacement

    return ComponentPlacement(
        ref=ref, footprint="fp", x=0.0, y=0.0, rotation=0.0,
        layer="F.Cu", width=1.0, height=1.0,
    )


def test_board_size_rendering_pins():
    """int vs float board dims render differently ('100mm' vs '100.0mm')."""
    result = RunResult(check_results=[], total_elapsed_ms=0.0)
    for width, height, expected_sub in [
        (100, 80, "Board Size: 100mm × 80mm"),
        (100.0, 80.0, "Board Size: 100.0mm × 80.0mm"),
        (63.5, 50.25, "Board Size: 63.5mm × 50.25mm"),
    ]:
        p = Placement(components={"X": _comp("X")})
        p.board_width, p.board_height = width, height
        text = generate_summary(result, p, None)
        assert expected_sub in text
        assert text == _oracle.generate_summary(result, p, None)


def test_category_sorting_pinned():
    """Categories render sorted ascending, uppercased."""
    from temper_placer.validation.drc_types import ComponentPlacement

    result = RunResult(
        check_results=[
            CheckResult(
                check_name="a",
                passed=False,
                issues=[
                    Issue(severity=Severity.ERROR, code="1", message="m",
                          category="thermal", check_name="a"),
                    Issue(severity=Severity.WARNING, code="2", message="m",
                          category="clearance", check_name="a"),
                    Issue(severity=Severity.ERROR, code="3", message="m",
                          category="clearance", check_name="a"),
                ],
            )
        ],
        total_elapsed_ms=1.0,
    )
    p = Placement(components={"X": _comp("X")})
    text = generate_summary(result, p, None)
    assert "CLEARANCE: 2" in text
    assert "THERMAL: 1" in text
    assert text.index("CLEARANCE: 2") < text.index("THERMAL: 1")
    assert text == _oracle.generate_summary(result, p, None)
