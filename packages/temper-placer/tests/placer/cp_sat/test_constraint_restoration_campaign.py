"""Tests for the bounded production constraint-restoration campaign."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from temper_placer.placer.cp_sat.constraint_restoration_campaign import (
    BoundedDisplacementSweepStatus,
    RestorationCampaignStatus,
    RestorationLimits,
    RestorationStage,
    RestorationStageStatus,
    _merge_kwargs,
    bounded_displacement_restoration_stages,
    default_restoration_stages,
    distance_tier_restoration_stages,
    neighborhood_batched_creepage_constraints,
    run_bounded_displacement_radius_sweep,
    run_bounded_displacement_restoration_campaign,
    run_constraint_restoration_campaign,
)


@dataclass
class _Component:
    ref: str


@dataclass
class _Netlist:
    components: list[_Component]


@dataclass
class _Board:
    pass


@dataclass
class _Solve:
    status: str
    positions: dict[str, tuple[float, float]]
    rotations: dict[str, int]


@dataclass
class _VerifiedWarmStart:
    hints: dict[str, tuple[float, float, int]]
    usable: bool = True


def test_distance_tiers_restore_exact_pairs_in_sorted_cumulative_order() -> None:
    stages = distance_tier_restoration_stages(
        SimpleNamespace(
            requirements=(
                ("B", "C", 12.6),
                ("A", "C", 0.5),
                ("A", "B", 12.6),
            )
        )
    )

    assert [stage.name for stage in stages] == [
        "baseline",
        "creepage_0.5mm",
        "creepage_12.6mm",
    ]
    assert stages[0].kwargs == {"experimental_omit_generated_creepage": True}
    half_mm = stages[1].kwargs["extra_constraints"]
    strongest = stages[2].kwargs["extra_constraints"]
    assert [(constraint.a, constraint.b) for constraint in half_mm] == [("A", "C")]
    assert [(constraint.a, constraint.b) for constraint in strongest] == [
        ("A", "B"),
        ("B", "C"),
    ]


def test_distance_tiers_reject_duplicate_pair_rows() -> None:
    instance = SimpleNamespace(
        requirements=(("A", "B", 0.5), ("B", "A", 12.6))
    )

    try:
        distance_tier_restoration_stages(instance)
    except ValueError as exc:
        assert "duplicate" in str(exc)
    else:  # pragma: no cover - assertion helper without pytest dependency
        raise AssertionError("duplicate pair was accepted")


def test_bounded_stages_keep_verified_centres_and_widen_monotonically() -> None:
    warm_start = _VerifiedWarmStart(
        {"B": (20.0, 30.0, 1), "A": (10.0, 15.0, 0)}
    )

    stages = bounded_displacement_restoration_stages(warm_start, (2, 5.5, 12))

    assert [stage.name for stage in stages] == [
        "bounded_displacement_2mm",
        "bounded_displacement_5.5mm",
        "bounded_displacement_12mm",
    ]
    assert [stage.kwargs["max_displacement_mm"] for stage in stages] == [2.0, 5.5, 12.0]
    expected_centres = {"A": (10.0, 15.0), "B": (20.0, 30.0)}
    assert all(stage.kwargs["minimize_displacement_to"] == expected_centres for stage in stages)


def test_bounded_stages_require_a_verified_complete_warm_start() -> None:
    for warm_start in (
        _VerifiedWarmStart({}, True),
        _VerifiedWarmStart({"A": (1.0, 2.0, 0)}, False),
    ):
        try:
            bounded_displacement_restoration_stages(warm_start)
        except ValueError as exc:
            assert "warm-start" in str(exc)
        else:  # pragma: no cover - assertion helper without pytest dependency
            raise AssertionError("invalid warm-start was accepted")


def test_bounded_stages_reject_non_increasing_or_invalid_radii() -> None:
    warm_start = _VerifiedWarmStart({"A": (1.0, 2.0, 0)})
    for radii in ((2.0, 2.0), (5.0, 2.0), (0.0, 1.0), (float("inf"),)):
        try:
            bounded_displacement_restoration_stages(warm_start, radii)
        except ValueError as exc:
            assert "radi" in str(exc)
        else:  # pragma: no cover - assertion helper without pytest dependency
            raise AssertionError("invalid radii were accepted")


def test_bounded_campaign_carries_original_centres_while_widening_bound() -> None:
    netlist = _Netlist([_Component("A")])

    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        # A forked campaign worker cannot mutate the parent's test state, so
        # encode the stage's radius in the returned candidate instead.
        if kwargs["max_displacement_mm"] == 1.0:
            return _Solve("optimal", {"A": (3.0, 4.0)}, {"A": 0})
        assert kwargs["max_displacement_mm"] == 4.0
        assert kwargs["minimize_displacement_to"] == {"A": (3.0, 4.0)}
        assert kwargs["hint_positions"] == {"A": (3.0, 4.0, 0)}
        return _Solve("optimal", {"A": (3.5, 4.0)}, {"A": 0})

    result = run_bounded_displacement_restoration_campaign(
        netlist,
        _Board(),
        _VerifiedWarmStart({"A": (3.0, 4.0, 0)}),
        radii_mm=(1.0, 4.0),
        solver=solver,
        limits=RestorationLimits(total_timeout_s=5.0, stage_timeout_s=2.0, memory_limit_mb=None),
    )

    assert result.status is RestorationCampaignStatus.ACCEPTED
    assert result.placement == {"A": (3.5, 4.0)}


def test_bounded_campaign_fails_closed_for_invalid_warm_start() -> None:
    result = run_bounded_displacement_restoration_campaign(
        _Netlist([_Component("A")]),
        _Board(),
        _VerifiedWarmStart({}, True),
        limits=RestorationLimits(total_timeout_s=5.0, stage_timeout_s=2.0, memory_limit_mb=None),
    )
    assert result.status is RestorationCampaignStatus.INVALID
    assert result.diagnostics


def test_bounded_campaign_rejects_warm_start_for_another_netlist() -> None:
    result = run_bounded_displacement_restoration_campaign(
        _Netlist([_Component("A"), _Component("B")]),
        _Board(),
        _VerifiedWarmStart({"A": (1.0, 2.0, 0)}),
        limits=RestorationLimits(total_timeout_s=5.0, stage_timeout_s=2.0, memory_limit_mb=None),
    )
    assert result.status is RestorationCampaignStatus.INVALID
    assert "missing" in result.diagnostics[0]


def test_bounded_radius_sweep_continues_after_failures_and_separates_verification() -> None:
    netlist = _Netlist([_Component("A")])

    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        radius = kwargs["max_displacement_mm"]
        assert kwargs["hint_positions"] == {"A": (3.0, 4.0, 0)}
        assert "minimize_displacement_to" not in kwargs
        assert kwargs["hard_displacement_to"] == {"A": (3.0, 4.0)}
        assert kwargs["timeout_ms"] == 2000
        if radius == 1.0:
            return _Solve("unknown", {}, {})
        if radius == 2.0:
            return _Solve("infeasible", {}, {})
        if radius == 4.0:
            return _Solve("optimal", {"A": (3.5, 4.0)}, {"A": 0})
        return _Solve("optimal", {"A": (4.0, 4.0)}, {"A": 0})

    class Verification:
        def __init__(self, violations: list[str]) -> None:
            self.violations = violations

    def verify(result: _Solve) -> Verification:
        return Verification([] if result.positions["A"] == (4.0, 4.0) else ["creepage"])

    result = run_bounded_displacement_radius_sweep(
        netlist,
        _Board(),
        _VerifiedWarmStart({"A": (3.0, 4.0, 0)}),
        radii_mm=(1.0, 2.0, 4.0, 8.0),
        solver=solver,
        verify=verify,
        limits=RestorationLimits(total_timeout_s=10.0, stage_timeout_s=2.0, memory_limit_mb=None),
    )

    assert result.status is BoundedDisplacementSweepStatus.COMPLETE
    assert [report.status for report in result.radii] == [
        RestorationStageStatus.UNKNOWN,
        RestorationStageStatus.INFEASIBLE,
        RestorationStageStatus.ACCEPTED,
        RestorationStageStatus.ACCEPTED,
    ]
    assert [report.production_feasible for report in result.radii] == [False, False, True, True]
    assert [report.verification_passed for report in result.radii] == [None, None, False, True]
    assert [report.violation_count for report in result.radii] == [None, None, 1, 0]
    assert [report.radius_mm for report in result.production_feasible_radii] == [4.0, 8.0]
    assert result.first_exact_clean is not None
    assert result.first_exact_clean.radius_mm == 8.0


def test_bounded_stages_are_independent_views_of_the_same_safe_centres() -> None:
    """Later radii must not retarget the envelope around a moved candidate."""
    warm_start = _VerifiedWarmStart({"A": (11.0, 13.0, 0)})
    stages = bounded_displacement_restoration_stages(warm_start, (1.0, 2.0))

    assert stages[0].kwargs["minimize_displacement_to"] == {"A": (11.0, 13.0)}
    assert stages[1].kwargs["minimize_displacement_to"] == {"A": (11.0, 13.0)}
    assert stages[0].kwargs["max_displacement_mm"] == 1.0
    assert stages[1].kwargs["max_displacement_mm"] == 2.0


def test_bounded_campaign_rejects_non_monotone_radius_before_solving() -> None:
    """The cumulative campaign may widen, never narrow, its hard envelope."""
    result = run_bounded_displacement_restoration_campaign(
        _Netlist([_Component("A")]),
        _Board(),
        _VerifiedWarmStart({"A": (3.0, 4.0, 0)}),
        radii_mm=(5.0, 2.0),
        limits=RestorationLimits(total_timeout_s=5.0, stage_timeout_s=2.0, memory_limit_mb=None),
    )

    assert result.status is RestorationCampaignStatus.INVALID
    assert not result.stages
    assert "increasing" in result.diagnostics[0]


def test_radius_merge_is_cumulative_only_for_a_widening_bound() -> None:
    current = {"max_displacement_mm": 2.0}

    widened = _merge_kwargs(
        current,
        RestorationStage("radius_5", {"max_displacement_mm": 5.0}),
    )
    assert widened["max_displacement_mm"] == 5.0
    # The helper must not mutate the caller's accumulated kwargs while
    # assembling a hypothetical later stage.
    assert current["max_displacement_mm"] == 2.0

    try:
        _merge_kwargs(
            widened,
            RestorationStage("radius_1", {"max_displacement_mm": 1.0}),
        )
    except ValueError as exc:
        assert "narrows" in str(exc)
    else:  # pragma: no cover - assertion helper without pytest dependency
        raise AssertionError("a narrower cumulative envelope was accepted")


def test_bounded_stages_reject_malformed_centres_and_rotations() -> None:
    malformed = (
        _VerifiedWarmStart({"": (1.0, 2.0, 0)}),
        _VerifiedWarmStart({"A": (1.0, 2.0)}),
        _VerifiedWarmStart({"A": (float("nan"), 2.0, 0)}),
        _VerifiedWarmStart({"A": (1.0, float("inf"), 0)}),
        _VerifiedWarmStart({"A": (1.0, 2.0, True)}),
        _VerifiedWarmStart({"A": (1.0, 2.0, 4)}),
    )

    for warm_start in malformed:
        try:
            bounded_displacement_restoration_stages(warm_start, (1.0,))
        except ValueError as exc:
            assert "warm-start" in str(exc)
        else:  # pragma: no cover - assertion helper without pytest dependency
            raise AssertionError("malformed warm-start was accepted")


def test_bounded_stages_reject_non_sequence_and_non_numeric_radii() -> None:
    warm_start = _VerifiedWarmStart({"A": (1.0, 2.0, 0)})
    for radii in ("1,2", None, ("bad",), (float("nan"),), (float("-inf"),)):
        try:
            bounded_displacement_restoration_stages(warm_start, radii)
        except ValueError as exc:
            assert "radi" in str(exc)
        else:  # pragma: no cover - assertion helper without pytest dependency
            raise AssertionError("malformed radii were accepted")


def test_bounded_campaign_discards_candidate_when_exact_verifier_rejects_it() -> None:
    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        # If the campaign wrongly continued after a rejected candidate, this
        # second-stage result would make the test falsely appear accepted.
        if kwargs["max_displacement_mm"] == 1.0:
            return _Solve("feasible", {"A": (8.0, 9.0)}, {"A": 0})
        return _Solve("feasible", {"A": (3.0, 4.0)}, {"A": 0})

    class Verification:
        violations = ("A/B",)

    result = run_bounded_displacement_restoration_campaign(
        _Netlist([_Component("A")]),
        _Board(),
        _VerifiedWarmStart({"A": (3.0, 4.0, 0)}),
        radii_mm=(1.0, 4.0),
        solver=solver,
        verify=lambda _candidate: Verification(),
        limits=RestorationLimits(total_timeout_s=5.0, stage_timeout_s=2.0, memory_limit_mb=None),
    )

    assert result.status is RestorationCampaignStatus.STOPPED
    assert result.stages[0].status is RestorationStageStatus.INVALID
    assert result.placement == {}


def test_neighborhood_batch_selects_local_alternatives_deterministically() -> None:
    requirements = (
        ("A", "B", 12.6),
        ("A", "D", 10.0),
        ("B", "C", 6.0),
        ("C", "D", 2.0),
        ("A", "E", 0.5),
    )
    positions = {
        "A": (0.0, 0.0),
        "C": (1.0, 1.0),
        "B": (10.0, 0.0),
        "D": (11.0, 1.0),
        "E": (100.0, 100.0),
    }

    constraints = neighborhood_batched_creepage_constraints(
        requirements,
        (("B", "A", 12.6, 5.0),),
        positions,
        radius_mm=2.0,
    )

    assert [(constraint.a, constraint.b) for constraint in constraints] == [
        ("C", "D"),
        ("B", "C"),
        ("A", "D"),
        ("A", "B"),
    ]


def test_neighborhood_batch_skips_active_pairs_and_rejects_missing_positions() -> None:
    requirements = (("A", "B", 12.6), ("A", "C", 6.0), ("B", "C", 2.0))
    positions = {"A": (0.0, 0.0), "B": (5.0, 0.0), "C": (5.0, 1.0)}
    constraints = neighborhood_batched_creepage_constraints(
        requirements,
        (("A", "B", 12.6, 0.0),),
        positions,
        radius_mm=6.1,
        existing_pairs=(("B", "A"),),
    )
    assert [(constraint.a, constraint.b) for constraint in constraints] == [
        ("B", "C"),
        ("A", "C"),
    ]

    try:
        neighborhood_batched_creepage_constraints(
            (("A", "MISSING", 1.0),),
            (("A", "MISSING", 1.0, 0.0),),
            {"A": (0.0, 0.0)},
        )
    except ValueError as exc:
        assert "without a position" in str(exc)
    else:  # pragma: no cover - assertion helper without pytest dependency
        raise AssertionError("missing position was accepted")


def test_default_stage_order_is_deterministic() -> None:
    stages = default_restoration_stages(
        body_collision_audit={},
        exact_creepage={"lazy_creepage": True},
        isolation_barrier={"manifest_path": "barrier.yaml"},
        fixed_copper={"parse_result": object()},
    )
    assert [stage.name for stage in stages] == [
        "baseline",
        "exact_creepage",
        "isolation_barrier",
        "fixed_copper",
        "body_collision_audit",
    ]
    assert stages[0].kwargs["experimental_omit_generated_creepage"] is True
    assert stages[1].kwargs["experimental_omit_generated_creepage"] is False


def test_campaign_carries_previous_solution_as_a_hint_and_appends_constraints() -> None:
    netlist = _Netlist([_Component("A"), _Component("B")])

    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        # Encode the second-stage behavior in the result so this test remains
        # valid with the campaign's deliberately process-isolated worker.
        if kwargs.get("extra_constraints") == ["existing-hard-rule", "new-hard-rule"]:
            return _Solve("optimal", {"A": (1.0, 2.0), "B": (3.0, 4.0)}, {"A": 0, "B": 1})
        return _Solve("optimal", {"A": (5.0, 6.0), "B": (7.0, 8.0)}, {"A": 2, "B": 3})

    result = run_constraint_restoration_campaign(
        netlist,
        _Board(),
        stages=(
            RestorationStage("baseline"),
            RestorationStage("family", {"extra_constraints": ["new-hard-rule"]}),
        ),
        production_kwargs={"extra_constraints": ["existing-hard-rule"]},
        initial_hint_positions={"A": (10.0, 10.0, 0), "B": (12.0, 10.0, 0)},
        solver=solver,
        limits=RestorationLimits(total_timeout_s=5.0, stage_timeout_s=2.0, memory_limit_mb=None),
    )
    assert result.status is RestorationCampaignStatus.ACCEPTED
    assert result.placement == {"A": (1.0, 2.0), "B": (3.0, 4.0)}
    assert result.stages[0].positions == {"A": (5.0, 6.0), "B": (7.0, 8.0)}
    assert result.stages[1].rotations == {"A": 0, "B": 1}


def test_non_feasible_stage_stops_and_exposes_no_partial_placement() -> None:
    netlist = _Netlist([_Component("A")])
    def solver(_netlist: object, _board: object, **_kwargs: object) -> _Solve:
        return _Solve("unknown", {}, {})

    result = run_constraint_restoration_campaign(
        netlist,
        _Board(),
        stages=(RestorationStage("baseline"), RestorationStage("never-reached")),
        solver=solver,
        limits=RestorationLimits(total_timeout_s=5.0, stage_timeout_s=2.0, memory_limit_mb=None),
    )
    assert result.status is RestorationCampaignStatus.STOPPED
    assert result.placement == {}
    assert result.stages[0].status is RestorationStageStatus.UNKNOWN


def test_verifier_is_required_to_accept_when_supplied() -> None:
    netlist = _Netlist([_Component("A")])

    def solver(_netlist: object, _board: object, **_kwargs: object) -> _Solve:
        return _Solve("feasible", {"A": (1.0, 2.0)}, {"A": 0})

    class Verification:
        violations = ["not-clean"]

    result = run_constraint_restoration_campaign(
        netlist,
        _Board(),
        solver=solver,
        verify=lambda _result: Verification(),
        limits=RestorationLimits(total_timeout_s=5.0, stage_timeout_s=2.0, memory_limit_mb=None),
    )
    assert result.status is RestorationCampaignStatus.STOPPED
    assert result.stages[0].status is RestorationStageStatus.INVALID
    assert not result.placement


def test_duplicate_stage_option_replacement_fails_closed() -> None:
    netlist = _Netlist([_Component("A")])

    def solver(_netlist: object, _board: object, **_kwargs: object) -> _Solve:
        return _Solve("optimal", {"A": (1.0, 2.0)}, {"A": 0})

    result = run_constraint_restoration_campaign(
        netlist,
        _Board(),
        stages=(
            RestorationStage("baseline", {"seed": 1}),
            RestorationStage("bad", {"seed": 2}),
        ),
        solver=solver,
        limits=RestorationLimits(total_timeout_s=5.0, stage_timeout_s=2.0, memory_limit_mb=None),
    )
    assert result.status is RestorationCampaignStatus.INVALID
    assert result.stages[-1].status is RestorationStageStatus.INVALID
