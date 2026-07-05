"""
U2: Feedback Classifier Tests.

Tests for the feedback-class vocabulary — mapping router_v6 routing
results to CP-SAT constraint deltas across all four feedback classes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pytest

from temper_placer.placer.cp_sat.feedback import (
    ClassificationResult,
    ConstraintDelta,
    FeedbackClassifier,
    UnclassifiedFailure,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@dataclass
class MockRoutingResult:
    completion_rate: float = 0.5
    unrouted_nets: list[str] = field(default_factory=list)
    drc_violations: list[object] = field(default_factory=list)
    congestion_regions: list[object] = field(default_factory=list)


@dataclass
class MockDrcViolation:
    comp_a: str | None = None
    comp_b: str | None = None
    components: list[str] = field(default_factory=list)
    location: tuple[float, float] = (0.0, 0.0)
    message: str = "clearance violation"
    required_mm: float = 6.0


@dataclass
class MockCongestionRegion:
    comp_a: str | None = None
    comp_b: str | None = None
    current_distance_mm: float = 2.0
    bbox: tuple[float, float, float, float] | None = None


@dataclass
class MockPlacement:
    positions: np.ndarray
    placed_refs: list[str]


@pytest.fixture
def classifier():
    return FeedbackClassifier()


@pytest.fixture
def basic_placement():
    positions = np.array([[10.0, 20.0], [30.0, 40.0], [50.0, 60.0]], dtype=np.float32)
    return MockPlacement(positions=positions, placed_refs=["Q1", "Q2", "C_BUS1"])


# ---------------------------------------------------------------------------
# U2.0: ConstraintDelta and ClassificationResult dataclasses
# ---------------------------------------------------------------------------


def test_constraint_delta_creation():
    """ConstraintDelta holds constraint, reason, and priority."""
    delta = ConstraintDelta(
        constraint=None,
        reason="Test reason",
        priority=10,
    )
    assert delta.reason == "Test reason"
    assert delta.priority == 10


def test_classification_result_defaults():
    """ClassificationResult has sensible defaults."""
    result = ClassificationResult()
    assert result.deltas == []
    assert result.unclassified == []
    assert result.round_number == 0


# ---------------------------------------------------------------------------
# U2.1: Clean placement -> no deltas
# ---------------------------------------------------------------------------


def test_clean_placement_produces_no_deltas(classifier, basic_placement):
    """A routing result with 100% completion produces no deltas."""
    rr = MockRoutingResult(completion_rate=1.0)
    result = classifier.classify(rr, basic_placement)
    assert result.deltas == []
    assert result.unclassified == []


# ---------------------------------------------------------------------------
# U2.2: Class 1 — Congestion in corridor
# ---------------------------------------------------------------------------


def test_congestion_produces_separated_constraint(classifier, basic_placement):
    """Congestion between two components produces SeparatedConstraint delta."""
    rr = MockRoutingResult(
        completion_rate=0.8,
        congestion_regions=[
            MockCongestionRegion(
                comp_a="Q1",
                comp_b="Q2",
                current_distance_mm=2.0,
            ),
        ],
    )

    result = classifier.classify(rr, basic_placement)
    assert len(result.deltas) >= 1

    sep_deltas = [d for d in result.deltas if "Congestion" in d.reason]
    assert len(sep_deltas) >= 1
    delta = sep_deltas[0]

    from temper_placer.pcl.constraints import ConstraintType, SeparatedConstraint

    constraint = delta.constraint
    assert isinstance(constraint, SeparatedConstraint)
    assert constraint.a == "Q1"
    assert constraint.b == "Q2"
    assert constraint.min_distance_mm > 2.0  # Increased spacing
    assert delta.priority == 10


def test_congestion_with_bbox_produces_keepout(classifier, basic_placement):
    """Congestion without component refs produces KeepoutConstraint fallback."""
    rr = MockRoutingResult(
        completion_rate=0.8,
        congestion_regions=[
            MockCongestionRegion(bbox=(20, 20, 40, 40)),
        ],
    )

    result = classifier.classify(rr, basic_placement)
    deltas = [d for d in result.deltas if "General congestion" in d.reason]
    assert len(deltas) >= 1
    assert deltas[0].priority == 20


# ---------------------------------------------------------------------------
# U2.3: Class 2 — DRC clearance violation
# ---------------------------------------------------------------------------


def test_clearance_violation_produces_separated_constraint(classifier, basic_placement):
    """DRC clearance violation produces a SeparatedConstraint with required distance."""
    rr = MockRoutingResult(
        completion_rate=0.9,
        drc_violations=[
            MockDrcViolation(
                comp_a="Q1",
                comp_b="Q2",
                required_mm=6.0,
                message="Clearance violation at 5.8mm, required 6.0mm",
            ),
        ],
    )

    result = classifier.classify(rr, basic_placement)
    clearance_deltas = [d for d in result.deltas if "Clearance violation" in d.reason]
    assert len(clearance_deltas) >= 1
    delta = clearance_deltas[0]

    from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint

    assert isinstance(delta.constraint, SeparatedConstraint)
    assert delta.constraint.a == "Q1"
    assert delta.constraint.b == "Q2"
    assert delta.constraint.min_distance_mm == 6.0
    assert delta.constraint.tier == ConstraintTier.HARD
    assert delta.priority == 5  # Highest priority


def test_clearance_violation_from_components_list(classifier, basic_placement):
    """DRC violation can specify involved components as a list."""
    rr = MockRoutingResult(
        completion_rate=0.85,
        drc_violations=[
            MockDrcViolation(components=["C_BUS1", "Q1"], required_mm=5.0),
        ],
    )

    result = classifier.classify(rr, basic_placement)
    clearance_deltas = [d for d in result.deltas if "Clearance violation" in d.reason]
    assert len(clearance_deltas) >= 1
    assert clearance_deltas[0].constraint.min_distance_mm == 5.0


# ---------------------------------------------------------------------------
# U2.4: Class 3 — Unrouted critical pin
# ---------------------------------------------------------------------------


def test_unrouted_critical_pin_produces_anchored_constraint(classifier, basic_placement):
    """Unrouted net on Q1 produces AnchoredConstraint."""
    rr = MockRoutingResult(
        completion_rate=0.7,
        unrouted_nets=["GATE_DRIVE"],
    )

    result = classifier.classify(rr, basic_placement)

    from temper_placer.pcl.constraints import AnchoredConstraint, ConstraintTier

    anchored_deltas = [d for d in result.deltas if isinstance(d.constraint, AnchoredConstraint)]
    assert len(anchored_deltas) >= 1

    delta = anchored_deltas[0]
    assert delta.constraint.component in FeedbackClassifier.CRITICAL_ICS
    assert delta.constraint.tier == ConstraintTier.STRONG


# ---------------------------------------------------------------------------
# U2.5: Class 4 — Persistent high-pin-count IC failure
# ---------------------------------------------------------------------------


def test_persistent_ic_failure_produces_rotation_delta(classifier, basic_placement):
    """After 3+ rounds of failures on a critical IC, rotation coordination fires."""
    previous = [
        UnclassifiedFailure(description="fail 1", components=["Q1"]),
        UnclassifiedFailure(description="fail 2", components=["Q1"]),
        UnclassifiedFailure(description="fail 3", components=["Q1"]),
    ]

    rr = MockRoutingResult(
        completion_rate=0.5,
        unrouted_nets=["SW_NODE"],
    )

    result = classifier.classify(rr, basic_placement, round_number=4, previous_unclassified=previous)

    rotation_deltas = [
        d for d in result.deltas if "Rotation coordination" in d.reason
    ]
    assert len(rotation_deltas) >= 1
    assert rotation_deltas[0].priority == 25


def test_persistent_ic_not_fired_before_threshold(classifier, basic_placement):
    """Rotation coordination does NOT fire before round 3."""
    previous = [
        UnclassifiedFailure(description="fail 1", components=["Q1"]),
        UnclassifiedFailure(description="fail 2", components=["Q1"]),
    ]

    rr = MockRoutingResult(
        completion_rate=0.6,
        unrouted_nets=["SW_NODE"],
    )

    result = classifier.classify(rr, basic_placement, round_number=2, previous_unclassified=previous)

    rotation_deltas = [
        d for d in result.deltas if "Rotation coordination" in d.reason
    ]
    assert len(rotation_deltas) == 0


# ---------------------------------------------------------------------------
# U2.6: Unclassified fallback
# ---------------------------------------------------------------------------


def test_non_critical_unrouted_net_unclassified(classifier, basic_placement):
    """An unrouted net not involving critical ICs is reported as unclassified."""
    rr = MockRoutingResult(
        completion_rate=0.7,
        unrouted_nets=["SOME_UNKNOWN_NET"],
    )

    result = classifier.classify(rr, basic_placement)
    assert len(result.unclassified) >= 1
    failure = result.unclassified[0]
    assert "Unrouted net" in failure.description
    assert "SOME_UNKNOWN_NET" in failure.nets


def test_all_deltas_valid_constraint_types(classifier, basic_placement):
    """All produced deltas are valid PCL constraint types."""
    rr = MockRoutingResult(
        completion_rate=0.5,
        congestion_regions=[
            MockCongestionRegion(comp_a="Q1", comp_b="Q2"),
        ],
        drc_violations=[
            MockDrcViolation(comp_a="Q1", comp_b="Q2", required_mm=6.0),
        ],
        unrouted_nets=["SW_NODE"],
    )

    from temper_placer.pcl.constraints import BaseConstraint

    result = classifier.classify(rr, basic_placement, round_number=4)
    for delta in result.deltas:
        assert isinstance(delta.constraint, BaseConstraint), \
            f"delta {delta} has non-constraint type: {type(delta.constraint)}"


# ---------------------------------------------------------------------------
# U2.7: Delta priority ordering
# ---------------------------------------------------------------------------


def test_deltas_sorted_by_priority(classifier, basic_placement):
    """Deltas are returned sorted by priority (lowest first)."""
    rr = MockRoutingResult(
        completion_rate=0.5,
        drc_violations=[
            MockDrcViolation(comp_a="Q1", comp_b="Q2", required_mm=6.0),
        ],
        congestion_regions=[
            MockCongestionRegion(comp_a="Q1", comp_b="C_BUS1", bbox=(20, 20, 40, 40)),
        ],
        unrouted_nets=["SW_NODE"],
    )

    result = classifier.classify(rr, basic_placement, round_number=4)
    priorities = [d.priority for d in result.deltas]
    assert priorities == sorted(priorities), f"Deltas not sorted: {priorities}"
