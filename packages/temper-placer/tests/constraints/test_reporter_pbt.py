"""Property-based + metamorphic tests for the migrated ConstraintReporter.

Wave 4, Phase 4 (R1c/R1d). The Rust-migrated ``temper_placer.constraints.reporter``
must satisfy these properties; bit-identical parity against the pinned
pre-migration Python is asserted separately by
``test_reporter_rust_differential.py``.

Five properties (non-vacuously guarded):

- P1. Result-count decomposition: ``check()`` emits exactly one result per
  spacing rule + proximity rule + thermal constraint + group (spread) + one
  or more per escape clearance + one or more per corridor, in that order.
- P2. Status domain: every result status is a member of ConstraintStatus and
  its ``value`` is one of the four canonical strings.
- P3. Spacing agreement: a spacing result is SATISFIED iff the measured
  distance >= threshold (bit-exact on the actual_value vs expected_value), and
  VIOLATED iff strictly below; SKIPPED iff a component is unplaced.
- P4. Violation == hard & violated: ``is_violation()`` is true exactly for
  tier == "hard" AND status == VIOLATED (the reporter's own definition), and
  the report's ``violations`` property is exactly those.
- P5. JSON round-trip: ``to_json()`` parses and its ``summary`` counts match
  the report's actual result list.

Four metamorphic relations (honestly bounded):

- MR1. Moving a placed component across a spacing threshold flips SATISFIED ->
  VIOLATED (with the exact values reported), and the non-involved results are
  unchanged.
- MR2. Unplaced-component removal: removing an unplaced component's entry from
  the placements dict leaves every result identical (SKIPPED results do not
  depend on dict presence of the missing ref).
- MR3. Placement-dict order independence (bounded): reordering the placements
  dict leaves results identical for constraint sets with no escape/corridor
  violations (those iterate placements; multi-violation order follows it).
- MR4. Placing a previously-skipped component converts the SKIPPED result into
  a real check (SATISFIED or VIOLATED) and fills in actual/expected values.
"""

from __future__ import annotations

import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

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
    ConstraintStatus,
)

MAX_EXAMPLES = 100

_REFS = ["A", "B", "C", "Z", "U1", "U2", "Q1", "Q2", "R5", "J1"]
_REF = st.sampled_from(_REFS)
# Placement coordinates are millimeters; subnormals excluded (see compiler PBT).
_COORD = st.floats(
    min_value=-100.0,
    max_value=100.0,
    allow_nan=False,
    allow_infinity=False,
    allow_subnormal=False,
)
_POINT = st.tuples(_COORD, _COORD)
_TIER = st.sampled_from(["hard", "soft"])


def _mk(**kw) -> PlacementConstraints:
    return PlacementConstraints(**kw)


def _spacing_constraints(tier: str = "hard", min_sep: float = 10.0) -> PlacementConstraints:
    return _mk(
        component_spacing_rules=[
            ComponentSpacingRule(component_a="A", component_b="B", min_separation_mm=min_sep, tier=tier)
        ]
    )


# ---------------------------------------------------------------------------
# P1 — result-count decomposition
# ---------------------------------------------------------------------------


def test_p1_result_count_decomposition():
    constraints = _mk(
        component_spacing_rules=[
            ComponentSpacingRule(component_a="A", component_b="B", min_separation_mm=10.0, tier="hard"),
            ComponentSpacingRule(component_a="C", component_b="D", min_separation_mm=10.0, tier="soft"),
        ],
        component_groups=[
            ComponentGroup(
                name="g",
                components=["E", "F"],
                proximity_rules=[ProximityRule(component_a="E", component_b="F", max_distance_mm=20.0, tier="soft")],
            )
        ],
        thermal_constraints=[ThermalConstraint(components=["Q1"], prefer_edge=True, max_distance_from_edge_mm=10.0)],
        escape_clearances=[
            EscapeClearance(component="U1", clearance_mm=8.0, tier="hard"),
            EscapeClearance(component="U2", clearance_mm=None, tier="soft"),
        ],
        routing_corridors=[
            RoutingCorridor(name="c", from_component="J1", to_component="R5", width_mm=6.0, tier="hard")
        ],
    )
    reporter = ConstraintReporter(constraints, (0.0, 0.0, 100.0, 100.0))
    report = reporter.check(
        {
            "A": (50.0, 0.0),
            "B": (60.0, 0.0),
            "C": (50.0, 20.0),
            "D": (55.0, 20.0),
            "E": (50.0, 50.0),
            "F": (60.0, 50.0),
            "Q1": (5.0, 50.0),
            "U1": (80.0, 80.0),
            "U2": (90.0, 90.0),
            "J1": (0.0, 0.0),
            "R5": (20.0, 0.0),
        }
    )
    # 2 spacing + 1 proximity + 1 thermal + 1 group + 1 escape (U1) + 1 escape
    # skipped-clearance (U2) + 1 corridor = 8 results, in rule order.
    types = [r.constraint_type for r in report.results]
    assert types == [
        "ComponentSpacing",
        "ComponentSpacing",
        "Proximity",
        "Thermal",
        "GroupSpread",
        "EscapeClearance",
        "EscapeClearance",
        "RoutingCorridor",
    ]


# ---------------------------------------------------------------------------
# P2 — status domain
# ---------------------------------------------------------------------------


@given(
    min_sep=st.floats(min_value=1.0, max_value=30.0),
    pa=_POINT,
    pb=_POINT,
)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p2_status_domain_and_value(min_sep, pa, pb):
    reporter = ConstraintReporter(_spacing_constraints("hard", min_sep))
    report = reporter.check({"A": pa, "B": pb})
    assert len(report.results) == 1
    r = report.results[0]
    assert isinstance(r.status, ConstraintStatus)
    assert r.status.value in ("satisfied", "violated", "warning", "skipped")


# ---------------------------------------------------------------------------
# P3 — spacing agreement (SATISFIED iff dist >= threshold)
# ---------------------------------------------------------------------------


@given(
    min_sep=st.floats(min_value=1.0, max_value=30.0),
    pa=_POINT,
    pb=_POINT,
)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p3_spacing_satisfied_iff_distance_ge_threshold(min_sep, pa, pb):
    reporter = ConstraintReporter(_spacing_constraints("hard", min_sep))
    r = reporter.check({"A": pa, "B": pb}).results[0]
    if r.status == ConstraintStatus.SKIPPED:
        # both placed -> cannot be skipped; guard for hypothesis edge
        return
    dist = ((pa[0] - pb[0]) ** 2 + (pa[1] - pb[1]) ** 2) ** 0.5
    if dist >= min_sep:
        assert r.status == ConstraintStatus.SATISFIED
        assert r.actual_value >= r.expected_value
    else:
        assert r.status == ConstraintStatus.VIOLATED
        assert r.actual_value < r.expected_value
    # bit-exact actual value
    assert r.actual_value.hex() == dist.hex()


def test_p3_spacing_skipped_when_unplaced():
    reporter = ConstraintReporter(_spacing_constraints("hard", 10.0))
    r = reporter.check({"A": (0.0, 0.0)}).results[0]
    assert r.status == ConstraintStatus.SKIPPED
    assert r.actual_value is None
    assert r.expected_value is None


# ---------------------------------------------------------------------------
# P4 — violation == hard & violated
# ---------------------------------------------------------------------------


@given(
    min_sep=st.floats(min_value=1.0, max_value=30.0),
    pa=_POINT,
    pb=_POINT,
)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p4_is_violation_iff_hard_and_violated(min_sep, pa, pb):
    reporter = ConstraintReporter(_spacing_constraints("hard", min_sep))
    report = reporter.check({"A": pa, "B": pb})
    r = report.results[0]
    expected = r.tier == "hard" and r.status == ConstraintStatus.VIOLATED
    assert r.is_violation() == expected
    assert (r in report.violations) == expected


def test_p4_warning_is_soft_violation():
    reporter = ConstraintReporter(_spacing_constraints("soft", 10.0))
    r = reporter.check({"A": (0.0, 0.0), "B": (5.0, 0.0)}).results[0]
    assert r.is_warning() is True
    assert r in reporter.check({"A": (0.0, 0.0), "B": (5.0, 0.0)}).warnings


# ---------------------------------------------------------------------------
# P5 — JSON round-trip summary matches
# ---------------------------------------------------------------------------


def test_p5_json_summary_matches_report():
    constraints = _mk(
        component_spacing_rules=[
            ComponentSpacingRule(component_a="A", component_b="B", min_separation_mm=10.0, tier="hard"),
            ComponentSpacingRule(component_a="C", component_b="D", min_separation_mm=10.0, tier="soft"),
        ]
    )
    reporter = ConstraintReporter(constraints)
    report = reporter.check({"A": (0.0, 0.0), "B": (5.0, 0.0), "C": (0.0, 0.0), "D": (15.0, 0.0)})
    data = json.loads(report.to_json())
    assert data["summary"]["total_constraints"] == len(report.results)
    assert data["summary"]["violations"] == len(report.violations)
    assert data["summary"]["warnings"] == len(report.warnings)
    assert data["summary"]["hard_total"] == len(report.hard_results)
    assert data["summary"]["soft_total"] == len(report.soft_results)
    assert len(data["all_results"]) == len(report.results)


# ---------------------------------------------------------------------------
# MR1 — crossing a spacing threshold flips the status
# ---------------------------------------------------------------------------


def test_mr1_crossing_threshold_flips_status():
    constraints = _mk(
        component_spacing_rules=[
            ComponentSpacingRule(component_a="A", component_b="B", min_separation_mm=10.0, tier="hard"),
            ComponentSpacingRule(component_a="C", component_b="D", min_separation_mm=5.0, tier="soft"),
        ]
    )
    reporter = ConstraintReporter(constraints)
    close = reporter.check({"A": (0.0, 0.0), "B": (5.0, 0.0), "C": (0.0, 0.0), "D": (3.0, 0.0)})
    far = reporter.check({"A": (0.0, 0.0), "B": (15.0, 0.0), "C": (0.0, 0.0), "D": (3.0, 0.0)})
    close_a = next(r for r in close.results if r.components == ["A", "B"])
    far_a = next(r for r in far.results if r.components == ["A", "B"])
    assert close_a.status == ConstraintStatus.VIOLATED
    assert far_a.status == ConstraintStatus.SATISFIED
    assert close_a.actual_value == 5.0
    assert far_a.actual_value == 15.0
    # The non-involved pair (C, D) results are identical across the two checks
    # (only A and B moved).
    close_c = next(r for r in close.results if r.components == ["C", "D"])
    far_c = next(r for r in far.results if r.components == ["C", "D"])
    assert close_c.status == far_c.status == ConstraintStatus.VIOLATED
    assert close_c.actual_value == far_c.actual_value == 3.0


# ---------------------------------------------------------------------------
# MR2 — removing an unplaced component's entry is inert
# ---------------------------------------------------------------------------


def test_mr2_unplaced_entry_removal_inert():
    constraints = _mk(
        component_spacing_rules=[
            ComponentSpacingRule(component_a="A", component_b="B", min_separation_mm=10.0, tier="hard")
        ]
    )
    reporter = ConstraintReporter(constraints)
    full = reporter.check({"A": (0.0, 0.0), "B": (15.0, 0.0), "GHOST": (50.0, 50.0)})
    trimmed = reporter.check({"A": (0.0, 0.0), "B": (15.0, 0.0)})
    assert len(full.results) == len(trimmed.results)
    for rf, rt in zip(full.results, trimmed.results):
        assert (rf.status, rf.actual_value, rf.expected_value, rf.message) == (
            rt.status,
            rt.actual_value,
            rt.expected_value,
            rt.message,
        )


# ---------------------------------------------------------------------------
# MR3 — placements-dict order independence (bounded: no escape/corridor
# violations, since those iterate placements for multi-violation order)
# ---------------------------------------------------------------------------


def test_mr3_placements_order_independence_bounded():
    constraints = _mk(
        component_spacing_rules=[
            ComponentSpacingRule(component_a="A", component_b="B", min_separation_mm=10.0, tier="hard")
        ],
        component_groups=[
            ComponentGroup(name="g", components=["C", "D"], proximity_rules=[])
        ],
        thermal_constraints=[
            ThermalConstraint(components=["Q1"], prefer_edge=True, max_distance_from_edge_mm=10.0)
        ],
    )
    reporter = ConstraintReporter(constraints, (0.0, 0.0, 100.0, 100.0))
    ordered = {"A": (0.0, 0.0), "B": (5.0, 0.0), "C": (50.0, 50.0), "D": (60.0, 50.0), "Q1": (5.0, 50.0)}
    shuffled = {k: ordered[k] for k in ["Q1", "D", "A", "C", "B"]}
    r1 = reporter.check(ordered)
    r2 = reporter.check(shuffled)
    assert [(r.constraint_type, r.status, r.actual_value, r.message) for r in r1.results] == [
        (r.constraint_type, r.status, r.actual_value, r.message) for r in r2.results
    ]


# ---------------------------------------------------------------------------
# MR4 — placing a skipped component converts SKIPPED into a real check
# ---------------------------------------------------------------------------


def test_mr4_placing_skipped_component_activates_check():
    constraints = _mk(
        component_spacing_rules=[
            ComponentSpacingRule(component_a="A", component_b="B", min_separation_mm=10.0, tier="hard")
        ]
    )
    reporter = ConstraintReporter(constraints)
    skipped = reporter.check({"A": (0.0, 0.0)}).results[0]
    assert skipped.status == ConstraintStatus.SKIPPED
    assert skipped.actual_value is None
    placed = reporter.check({"A": (0.0, 0.0), "B": (15.0, 0.0)}).results[0]
    assert placed.status in (ConstraintStatus.SATISFIED, ConstraintStatus.VIOLATED)
    assert placed.actual_value is not None
    assert placed.expected_value is not None
    # The two checks are the same rule; only placement state changed.
    assert skipped.constraint_type == placed.constraint_type == "ComponentSpacing"
    assert skipped.components == placed.components == ["A", "B"]
