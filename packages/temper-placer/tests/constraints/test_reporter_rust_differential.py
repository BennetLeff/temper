"""Differential test: ConstraintReporter / ConstraintReport compute
(temper-constraint-compiler) vs the pinned Python oracle.

Wave 4, Phase 4 — the constraints surface migration. The Rust migration
(reproducing ``temper_placer/constraints/reporter.py`` bit-identically in the
``temper-constraint-compiler`` crate) is driven through the delegation shim
``temper_placer.constraints.reporter``; the pre-migration implementation is
pinned verbatim as the oracle (``_reporter_py_oracle.py``, commit aece7c372).

Every assertion drives IDENTICAL inputs through both sides and compares
bit-exactly: floats via ``float.hex()``, messages and text/JSON output as
byte-identical strings, result lists canonicalised with concrete types.

The module-scope reference to ``_rust.check_constraints`` is the RED arm:
before the Rust surface lands this file fails to collect (AttributeError).
"""

from __future__ import annotations

import json
import random

import pytest
import temper_constraint_compiler as _rust

import tests.constraints._reporter_py_oracle as _oracle

from temper_placer._constraint_types import (
    ComponentGroup,
    ComponentSpacingRule,
    EscapeClearance,
    PlacementConstraints,
    ProximityRule,
    RoutingCorridor,
    ThermalConstraint,
)
from temper_placer.constraints.reporter import (
    ConstraintReport,
    ConstraintReporter,
    ConstraintResult,
    ConstraintStatus,
)

# Module-scope RED arm.
assert hasattr(_rust, "check_constraints")
assert hasattr(_rust, "report_to_text")
assert hasattr(_rust, "report_to_json_data")


# ---------------------------------------------------------------------------
# Canonicalization (bit-exact floats, concrete types).
# ---------------------------------------------------------------------------


def _f(value):
    """Bit-exact float key: None stays None, else float.hex()."""
    return None if value is None else float(value).hex()


def _result_key(r: ConstraintResult):
    return (
        r.constraint_type,
        r.status.value,
        r.tier,
        tuple(r.components),
        r.message,
        _f(r.actual_value),
        _f(r.expected_value),
        tuple(sorted(r.details.items())),
    )


def _random_constraints(rng: random.Random) -> PlacementConstraints:
    r = random.Random(rng.randint(0, 2**31))
    refs = ["A", "B", "C", "D", "E", "U1", "U2", "Q1", "Q2", "R5"]
    spacing = [
        ComponentSpacingRule(
            component_a=r.choice(refs),
            component_b=r.choice(refs),
            min_separation_mm=r.uniform(1.0, 40.0),
            tier=r.choice(["hard", "soft"]),
            weight=r.uniform(0.1, 5.0),
        )
        for _ in range(r.randint(0, 4))
    ]
    groups = []
    for _ in range(r.randint(0, 3)):
        comps = r.sample(refs, r.randint(2, 3))
        prox = [
            ProximityRule(
                component_a=a,
                component_b=b,
                max_distance_mm=r.uniform(5.0, 50.0),
                tier=r.choice(["hard", "soft"]),
            )
            for a, b in (r.sample(comps, 2) for _ in range(r.randint(0, 2)))
        ]
        groups.append(
            ComponentGroup(
                name=f"g{r.randint(1, 99)}",
                components=comps,
                max_spread_mm=r.uniform(10.0, 60.0),
                proximity_rules=prox,
            )
        )
    escapes = [
        EscapeClearance(
            component=r.choice(refs),
            clearance_mm=r.choice([None, r.uniform(2.0, 15.0)]),
            tier=r.choice(["hard", "soft"]),
        )
        for _ in range(r.randint(0, 3))
    ]
    corridors = [
        RoutingCorridor(
            name=f"c{i}",
            from_component=r.choice(refs),
            to_component=r.choice(refs),
            width_mm=r.uniform(1.0, 10.0),
            keep_clear=r.choice([True, False]),
            tier=r.choice(["hard", "soft"]),
        )
        for i in range(r.randint(0, 2))
    ]
    thermals = [
        ThermalConstraint(
            components=r.sample(refs, r.randint(1, 2)),
            prefer_edge=r.choice([True, False]),
            max_distance_from_edge_mm=r.uniform(5.0, 30.0),
        )
        for _ in range(r.randint(0, 2))
    ]
    return PlacementConstraints(
        board_width_mm=100.0,
        board_height_mm=80.0,
        component_spacing_rules=spacing,
        component_groups=groups,
        escape_clearances=escapes,
        routing_corridors=corridors,
        thermal_constraints=thermals,
    )


def _placements(rng: random.Random, refs: list[str]) -> dict:
    out = {}
    for ref in refs:
        if rng.random() < 0.6:
            out[ref] = (rng.uniform(-20.0, 120.0), rng.uniform(-20.0, 100.0))
    return out


def _both(constraints, board_bounds=None):
    o = _oracle.ConstraintReporter(constraints, board_bounds)
    s = ConstraintReporter(constraints, board_bounds)
    return o, s


# ---------------------------------------------------------------------------
# R1a — behavioural A/B: check() result lists, bit-identical.
# ---------------------------------------------------------------------------


class TestCheckDifferential:
    def test_empty_constraints_empty_report(self):
        o, s = _both(PlacementConstraints())
        or_, sr = o.check({}), s.check({})
        assert [_result_key(r) for r in or_.results] == [_result_key(r) for r in sr.results]
        assert len(sr.results) == 0  # empty-input semantics asserted, not assumed

    def test_empty_constraints_with_placements(self):
        o, s = _both(PlacementConstraints())
        placements = {"A": (1.0, 2.0), "B": (3.0, 4.0)}
        or_, sr = o.check(placements), s.check(placements)
        assert [_result_key(r) for r in or_.results] == [_result_key(r) for r in sr.results]

    def test_random_differential(self):
        rng = random.Random(0x3E3F0E)
        refs = ["A", "B", "C", "D", "E", "U1", "U2", "Q1", "Q2", "R5"]
        for case in range(120):
            constraints = _random_constraints(rng)
            bounds = None if case % 3 == 0 else (0.0, 0.0, 100.0, 80.0)
            o, s = _both(constraints, bounds)
            placements = _placements(rng, refs)
            or_, sr = o.check(placements), s.check(placements)
            assert [_result_key(r) for r in or_.results] == [
                _result_key(r) for r in sr.results
            ], f"check mismatch case={case}"
            # Result ORDER is part of the contract (rule order + placements iteration).
            assert [r.constraint_type for r in or_.results] == [
                r.constraint_type for r in sr.results
            ]

    def test_escape_corridor_violation_order_follows_placements(self):
        """Multi-violation results follow placements dict insertion order on BOTH sides."""
        constraints = PlacementConstraints(
            escape_clearances=[EscapeClearance(component="U1", clearance_mm=10.0, tier="hard")],
            routing_corridors=[
                RoutingCorridor(
                    name="path", from_component="A", to_component="B", width_mm=6.0, tier="hard"
                )
            ],
        )
        o, s = _both(constraints)
        placements = {
            "U1": (50.0, 50.0),
            "X1": (55.0, 50.0),
            "X2": (50.0, 58.0),
            "A": (0.0, 0.0),
            "B": (20.0, 0.0),
            "Y1": (10.0, 2.0),
            "Y2": (10.0, -2.0),
        }
        or_, sr = o.check(placements), s.check(placements)
        assert [_result_key(r) for r in or_.results] == [_result_key(r) for r in sr.results]
        # The multi-violation paths are actually exercised (not vacuous).
        assert any(r.constraint_type == "EscapeClearance" and r.status == ConstraintStatus.VIOLATED for r in sr.results)
        assert any(r.constraint_type == "RoutingCorridor" and r.status == ConstraintStatus.VIOLATED for r in sr.results)


class TestReportTextAndJsonDifferential:
    def test_empty_report_text(self):
        """Empty-input semantics for to_text: header + blank line + bare SUMMARY."""
        o, s = ConstraintReport(), ConstraintReport()
        assert o.to_text() == s.to_text()
        assert s.to_text() == "=== Constraint Satisfaction Report ===\n\nSUMMARY:"

    def test_empty_report_json(self):
        o, s = ConstraintReport(), ConstraintReport()
        assert o.to_json() == s.to_json()
        assert json.loads(s.to_json())["summary"]["total_constraints"] == 0

    def test_text_json_identical_on_random_checks(self):
        rng = random.Random(0xA11CE)
        refs = ["A", "B", "C", "D", "E", "U1", "U2", "Q1", "Q2", "R5"]
        for case in range(60):
            constraints = _random_constraints(rng)
            bounds = None if case % 2 == 0 else (0.0, 0.0, 100.0, 80.0)
            o, s = _both(constraints, bounds)
            placements = _placements(rng, refs)
            or_, sr = o.check(placements), s.check(placements)
            assert or_.to_text() == sr.to_text(), f"to_text mismatch case={case}"
            assert or_.to_json() == sr.to_json(), f"to_json mismatch case={case}"

    def test_hand_built_report_with_details(self):
        """Reports built by hand (not via check) with details must round-trip."""
        o = ConstraintReport(
            results=[
                ConstraintResult(
                    "ComponentSpacing",
                    ConstraintStatus.VIOLATED,
                    "hard",
                    ["A", "B"],
                    "Test violation",
                    actual_value=5.0,
                    expected_value=10.0,
                    details={"side": "left"},
                ),
                ConstraintResult(
                    "Proximity",
                    ConstraintStatus.SATISFIED,
                    "soft",
                    ["C", "D"],
                    "OK",
                ),
            ]
        )
        s = ConstraintReport(
            results=[
                ConstraintResult(
                    "ComponentSpacing",
                    ConstraintStatus.VIOLATED,
                    "hard",
                    ["A", "B"],
                    "Test violation",
                    actual_value=5.0,
                    expected_value=10.0,
                    details={"side": "left"},
                ),
                ConstraintResult(
                    "Proximity",
                    ConstraintStatus.SATISFIED,
                    "soft",
                    ["C", "D"],
                    "OK",
                ),
            ]
        )
        assert o.to_text() == s.to_text()
        assert o.to_json() == s.to_json()
        data = json.loads(s.to_json())
        assert data["violations"][0]["details"] == {"side": "left"}

    def test_summary_counts(self):
        """Summary counts reflect hard/soft/satisfied splits exactly."""
        s = ConstraintReport(
            results=[
                ConstraintResult("A", ConstraintStatus.VIOLATED, "hard", ["X"], "m1"),
                ConstraintResult("B", ConstraintStatus.SATISFIED, "hard", ["X"], "m2"),
                ConstraintResult("C", ConstraintStatus.VIOLATED, "soft", ["X"], "m3"),
                ConstraintResult("D", ConstraintStatus.WARNING, "soft", ["X"], "m4"),
                ConstraintResult("E", ConstraintStatus.SKIPPED, "soft", ["X"], "m5"),
            ]
        )
        data = json.loads(s.to_json())
        assert data["summary"] == {
            "total_constraints": 5,
            "hard_satisfied": 1,
            "hard_total": 2,
            "soft_satisfied": 0,
            "soft_total": 3,
            "violations": 1,
            "warnings": 1,
        }
        text = s.to_text()
        assert "Hard: 1/2 satisfied" in text
        assert "Soft: 0/3 satisfied" in text
        assert "VIOLATIONS: 1" in text


class TestReportPropertiesDifferential:
    def test_properties_parity(self):
        """violations/warnings/satisfied/hard/soft filters match the oracle."""
        constraints = PlacementConstraints(
            component_spacing_rules=[
                ComponentSpacingRule(component_a="A", component_b="B", min_separation_mm=10.0, tier="hard"),
                ComponentSpacingRule(component_a="C", component_b="D", min_separation_mm=10.0, tier="soft"),
            ],
            component_groups=[
                ComponentGroup(name="g", components=["E", "F"], proximity_rules=[])
            ],
        )
        o, s = _both(constraints)
        placements = {"A": (0.0, 0.0), "B": (5.0, 0.0), "C": (0.0, 0.0), "D": (5.0, 0.0)}
        or_, sr = o.check(placements), s.check(placements)
        for prop in ["violations", "warnings", "satisfied", "hard_results", "soft_results"]:
            assert [_result_key(r) for r in getattr(or_, prop)] == [
                _result_key(r) for r in getattr(sr, prop)
            ], prop
        assert or_.has_violations() == sr.has_violations()
