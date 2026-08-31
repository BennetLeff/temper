"""Differential test: Rust feedback-classifier sequencing vs the pinned Python oracle.

Orchestration-port unit U-I (Rust Orchestration Engine plan 2026-08-09-001):
the ``FeedbackClassifier.classify()`` feedback-DECISION sequencing moved to
``temper-orchestration``'s ``feedback.rs``. The pre-migration ``classify``
is pinned VERBATIM as ``_feedback_py_oracle.py``; every assertion drives
IDENTICAL routing-result / placement mocks through both the delegated
``FeedbackClassifier`` (Rust sequencing) and the oracle classifier, and
asserts the canonicalized ``ClassificationResult`` is byte-identical.

Boundary (what is NOT compared -- the Python call-backs both sides share by
construction): the four ``_handle_*`` constraint-building handlers (they
construct the real PCL ``SeparatedConstraint`` / ``KeepoutConstraint`` /
``AnchoredConstraint`` objects identically -- the handlers are unchanged in
the shim). The critical-net and persistence leaves are Rust-owned and are
therefore exercised by these same end-to-end oracle scenarios.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

import tests.placer.cp_sat._feedback_py_oracle as _oracle
from temper_placer.placer.cp_sat.feedback import (
    FeedbackClassifier,
    UnclassifiedFailure,
)

# ---------------------------------------------------------------------------
# Mocks
# ---------------------------------------------------------------------------


@dataclass
class MockRoutingResult:
    completion_rate: float = 0.5
    unrouted_nets: list = field(default_factory=list)
    drc_violations: list = field(default_factory=list)
    congestion_regions: list = field(default_factory=list)


@dataclass
class MockDrcViolation:
    comp_a: str | None = None
    comp_b: str | None = None
    components: list = field(default_factory=list)
    location: tuple = (0.0, 0.0)
    message: str = "clearance violation"
    required_mm: float = 6.0


@dataclass
class MockCongestionRegion:
    comp_a: str | None = None
    comp_b: str | None = None
    current_distance_mm: float = 2.0
    bbox: tuple | None = None


@dataclass
class MockPlacement:
    positions: dict = field(default_factory=dict)
    placed_refs: list = field(default_factory=list)


def _placement():
    return MockPlacement(
        positions={"Q1": (10.0, 20.0), "Q2": (30.0, 40.0), "C_BUS1": (50.0, 60.0)},
        placed_refs=["Q1", "Q2", "C_BUS1"],
    )


# ---------------------------------------------------------------------------
# Canonicalization
# ---------------------------------------------------------------------------


def _constraint_key(c):
    kind = type(c).__name__
    if kind == "SeparatedConstraint":
        return (
            kind,
            c.a,
            c.b,
            float(c.min_distance_mm).hex(),
            (c.tier.name, c.tier.value),
            c.id,
        )
    if kind == "KeepoutConstraint":
        return (kind, c.zone_name, (c.tier.name, c.tier.value), c.id)
    if kind == "AnchoredConstraint":
        return (kind, c.component, tuple(c.region), (c.tier.name, c.tier.value), c.id)
    return (kind, getattr(c, "id", None))


def _canon(result):
    return (
        tuple(
            (d.priority, d.reason, _constraint_key(d.constraint))
            for d in result.deltas
        ),
        tuple(
            (u.description, tuple(u.nets), tuple(u.components), u.region)
            for u in result.unclassified
        ),
        result.round_number,
    )


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

_SCENARIOS = [
    (
        "clean",
        MockRoutingResult(completion_rate=1.0),
        None,
        0,
    ),
    (
        "congestion_pair",
        MockRoutingResult(
            completion_rate=0.8,
            congestion_regions=[MockCongestionRegion(comp_a="Q1", comp_b="Q2")],
        ),
        None,
        0,
    ),
    (
        "congestion_pair_scaled_distance",
        MockRoutingResult(
            completion_rate=0.8,
            congestion_regions=[
                MockCongestionRegion(comp_a="Q1", comp_b="Q2", current_distance_mm=3.0)
            ],
        ),
        None,
        0,
    ),
    (
        "congestion_bbox",
        MockRoutingResult(
            completion_rate=0.8,
            congestion_regions=[MockCongestionRegion(bbox=(20, 20, 40, 40))],
        ),
        None,
        0,
    ),
    (
        "clearance_pair",
        MockRoutingResult(
            completion_rate=0.9,
            drc_violations=[MockDrcViolation(comp_a="Q1", comp_b="Q2", required_mm=6.0)],
        ),
        None,
        0,
    ),
    (
        "clearance_components_list",
        MockRoutingResult(
            completion_rate=0.85,
            drc_violations=[MockDrcViolation(components=["C_BUS1", "Q1"], required_mm=5.0)],
        ),
        None,
        0,
    ),
    (
        "clearance_no_comps_unclassified",
        MockRoutingResult(
            completion_rate=0.85,
            drc_violations=[
                MockDrcViolation(message="odd violation", location=(3.0, 7.0)),
            ],
        ),
        None,
        0,
    ),
    (
        "unrouted_critical_pin",
        MockRoutingResult(completion_rate=0.7, unrouted_nets=["GATE_DRIVE"]),
        None,
        0,
    ),
    (
        "unrouted_non_critical_unclassified",
        MockRoutingResult(completion_rate=0.7, unrouted_nets=["SOME_UNKNOWN_NET"]),
        None,
        0,
    ),
    (
        "persistent_ic_rotation",
        MockRoutingResult(completion_rate=0.5, unrouted_nets=["SW_NODE"]),
        [
            UnclassifiedFailure(description="fail 1", components=["Q1"]),
            UnclassifiedFailure(description="fail 2", components=["Q1"]),
            UnclassifiedFailure(description="fail 3", components=["Q1"]),
        ],
        4,
    ),
    (
        "persistent_below_threshold",
        MockRoutingResult(completion_rate=0.6, unrouted_nets=["SW_NODE"]),
        [
            UnclassifiedFailure(description="fail 1", components=["Q1"]),
            UnclassifiedFailure(description="fail 2", components=["Q1"]),
        ],
        2,
    ),
    (
        "combined_all_signals",
        MockRoutingResult(
            completion_rate=0.5,
            congestion_regions=[
                MockCongestionRegion(comp_a="Q1", comp_b="C_BUS1", bbox=(20, 20, 40, 40)),
            ],
            drc_violations=[MockDrcViolation(comp_a="Q1", comp_b="Q2", required_mm=6.0)],
            unrouted_nets=["SW_NODE"],
        ),
        [
            UnclassifiedFailure(description="fail 1", components=["Q1"]),
            UnclassifiedFailure(description="fail 2", components=["Q1"]),
            UnclassifiedFailure(description="fail 3", components=["Q1"]),
        ],
        4,
    ),
]


@pytest.mark.parametrize(
    "name,rr,prev,round_number",
    list(_SCENARIOS),
    ids=[s[0] for s in _SCENARIOS],
)
def test_classify_identical(name, rr, prev, round_number):
    delegated = FeedbackClassifier().classify(
        rr, _placement(), round_number=round_number, previous_unclassified=prev
    )
    oracle = _oracle.FeedbackClassifier().classify(
        rr, _placement(), round_number=round_number, previous_unclassified=prev
    )
    assert _canon(delegated) == _canon(oracle), (
        f"[{name}] ClassificationResult diverged:\n"
        f"  delegated={_canon(delegated)}\n  oracle={_canon(oracle)}"
    )
