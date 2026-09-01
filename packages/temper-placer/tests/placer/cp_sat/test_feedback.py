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


def test_heuristic_position_is_rust_owned():
    """The deterministic unrouted-pin position bias lives in orchestration."""
    import temper_orchestration

    assert temper_orchestration.compute_heuristic_position("Q1", (10.0, 20.0), "GATE") == (
        10.0,
        15.0,
    )
    assert temper_orchestration.compute_heuristic_position("U_MCU", (10.0, 20.0), "SPI") == (
        10.0,
        20.0,
    )
    assert temper_orchestration.compute_heuristic_position("J1", (10.0, 20.0), "OTHER") == (
        10.0,
        25.0,
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

    from temper_placer.pcl.constraints import SeparatedConstraint

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


def test_congestion_classifier_path_does_not_call_python_handler(monkeypatch, basic_placement):
    """The production classifier dispatches congestion directly to Rust.

    Keep the public method as a compatibility adapter, but make a mutated
    callback unable to alter the normal classifier path.  This is the
    migration boundary proof that a Python implementation cannot quietly
    become the computational source of truth again.
    """
    def fail_if_called(self, region, placed_refs):  # noqa: ARG001
        raise AssertionError("production congestion handler must be Rust-owned")

    monkeypatch.setattr(FeedbackClassifier, "_handle_congestion", fail_if_called)
    rr = MockRoutingResult(
        completion_rate=0.8,
        congestion_regions=[
            MockCongestionRegion(comp_a="Q1", comp_b="Q2", current_distance_mm=3.0)
        ],
    )
    result = FeedbackClassifier().classify(rr, basic_placement)
    assert len(result.deltas) == 1
    assert result.deltas[0].constraint.min_distance_mm == 4.5


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

    result = classifier.classify(
        rr, basic_placement, round_number=4, previous_unclassified=previous
    )

    rotation_deltas = [d for d in result.deltas if "Rotation coordination" in d.reason]
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

    result = classifier.classify(
        rr, basic_placement, round_number=2, previous_unclassified=previous
    )

    rotation_deltas = [d for d in result.deltas if "Rotation coordination" in d.reason]
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
        assert isinstance(delta.constraint, BaseConstraint), (
            f"delta {delta} has non-constraint type: {type(delta.constraint)}"
        )


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


# ---------------------------------------------------------------------------
# Class 2, authoritative net classification
#
# ADDED 2026-08-19 (docs/evidence/2026-08-19-is-hv-net-blast-radius.md).
# `_handle_clearance_violation` used to classify the violating nets by NAME
# via `core.net_classification.classify_net_type()`, whose HV keyword set
# ({"AC_L","AC_N","PE","DC_BUS+","DC_BUS-","SW_NODE"}) matches none of the
# spellings this board actually uses for its DC bus, half-bridge return or
# resonant tank. The separation it then injected in response to a DRC
# clearance violation was therefore the unclassified-signal default rather
# than the net's real net-class figure.
# ---------------------------------------------------------------------------


@dataclass
class MockDrcViolationWithNets(MockDrcViolation):
    """A DRC clearance violation that carries the two NET names.

    `_handle_clearance_violation` only consults net classification when the
    violation exposes `net_a`/`net_b`; the base `MockDrcViolation` above
    (and the one in `test_feedback_rust_differential.py`) does not, which is
    why that whole branch was untested.
    """

    net_a: str | None = None
    net_b: str | None = None


def _clearance_distance_for(net_a: str, net_b: str) -> float:
    """Run one clearance violation between *net_a*/*net_b* through the real
    classifier with the real Temper design rules, and return the separation
    it injects."""
    from temper_placer.core.design_rules import create_temper_design_rules

    classifier = FeedbackClassifier(design_rules=create_temper_design_rules())
    placement = MockPlacement(
        positions=np.array([[10.0, 20.0], [30.0, 40.0]]),
        placed_refs=["U_A", "U_B"],
    )
    routing = MockRoutingResult(
        completion_rate=0.9,
        drc_violations=[
            MockDrcViolationWithNets(
                comp_a="U_A", comp_b="U_B", required_mm=0.1, net_a=net_a, net_b=net_b
            )
        ],
    )
    result = classifier.classify(routing, placement, round_number=0)
    deltas = [d for d in result.deltas if "Clearance violation" in d.reason]
    assert len(deltas) == 1, f"expected exactly one clearance delta, got {deltas}"
    return deltas[0].constraint.min_distance_mm


@pytest.mark.parametrize(
    ("net", "min_expected_mm", "why"),
    [
        ("+170V_BUS", 2.0, "rectified 170V DC bus -- netclass HighVoltage"),
        ("DC_BUS_RTN", 2.0, "DC bus return -- netclass HighVoltage"),
        ("hb-gnd", 2.0, "half-bridge low-side return -- netclass HighVoltage"),
        ("tank-out", 2.0, "resonant tank coil node -- netclass HighVoltage"),
        ("tank.c_tank1-p2", 2.0, "resonant tank cap<->coil -- netclass HighVoltageTank"),
        ("ac_l", 6.0, "mains line -- netclass ACMains"),
        ("ac_n", 6.0, "mains neutral -- netclass ACMains"),
    ],
)
def test_clearance_feedback_uses_authoritative_netclass_for_hv_nets(net, min_expected_mm, why):
    """A clearance violation naming a mains/HV conductor must be remediated
    at that conductor's own net-class separation, not at the LV default.

    Pre-fix measurements (same venv, same design rules): ``+170V_BUS``,
    ``DC_BUS_RTN``, ``tank-out`` and ``tank.c_tank1-p2`` all resolved to the
    non-existent "Signal" class and injected 0.15mm; ``hb-gnd`` resolved to
    "GND" and injected 0.3mm; ``ac_l``/``ac_n`` resolved to "HighVoltage"
    and injected 2.0mm instead of ACMains' 6.0mm.

    The expected figures are NOT written here as new constants -- each is
    read back below from ``TEMPER_NET_CLASSES`` via the same
    ``get_rules_for_net`` the production path now uses, so this test cannot
    pin a number the SSOT does not hold.
    """
    from temper_placer.core.design_rules import create_temper_design_rules

    dr = create_temper_design_rules()
    authoritative = dr.get_rules_for_net(net).clearance
    assert authoritative == min_expected_mm, (
        f"SSOT drift: {net} ({why}) now resolves to {authoritative}mm, "
        f"not the {min_expected_mm}mm this test was written against"
    )

    got = _clearance_distance_for(net, "WDT_KICK")
    assert got >= authoritative, (
        f"{net} ({why}) remediated at {got}mm, below its own net class's {authoritative}mm"
    )


def test_clearance_feedback_still_uses_the_lv_figure_for_two_lv_nets():
    """Anti-vacuity: the fix must not simply raise every separation.

    Two unclassified SELV signal nets must still be remediated at the LV
    default, not at an HV figure.
    """
    from temper_placer.core.design_rules import create_temper_design_rules

    dr = create_temper_design_rules()
    lv = dr.get_rules_for_net("WDT_KICK").clearance
    assert lv < 2.0, "premise stale: the LV default is no longer below the HV figure"
    assert _clearance_distance_for("WDT_KICK", "BTN_UP") == lv
