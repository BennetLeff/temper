"""Contracts for unconditional group-deletion diagnosis.

These tests intentionally use tiny fake solver instances.  They specify the
important semantics of the experiment without making a real-board solve part
of the unit suite:

* prove the all-bounds baseline before trying a release;
* build every deletion probe from the original bounds (never carry a prior
  release into the next probe);
* treat unknown and malformed results conservatively; and
* only try deterministic balanced batches after every singleton failed.

The campaign is diagnostic.  A feasible production candidate still goes
through the exact verifier and retains its violation count; production
feasibility is not silently upgraded to creepage correctness.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from temper_placer.placer.cp_sat.constraint_restoration_campaign import (
    RestorationLimits,
    RestorationStageStatus,
)
from temper_placer.placer.cp_sat.displacement_deletion_campaign import (
    DisplacementDeletionCampaignStatus,
    run_displacement_deletion_campaign,
)


@dataclass
class _Component:
    ref: str


@dataclass
class _Netlist:
    components: list[_Component]


@dataclass
class _WarmStart:
    hints: dict[str, tuple[float, float, int]]
    usable: bool = True


@dataclass
class _Solve:
    status: str
    positions: dict[str, tuple[float, float]] | None = None
    rotations: dict[str, int] | None = None


@dataclass
class _Verification:
    violations: tuple[str, ...]


def _netlist(*refs: str) -> _Netlist:
    return _Netlist([_Component(ref) for ref in refs])


def _warm_start(*refs: str) -> _WarmStart:
    return _WarmStart({ref: (float(i), 10.0, 0) for i, ref in enumerate(refs)})


def _limits(*, stage: float = 1.0, total: float = 5.0) -> RestorationLimits:
    return RestorationLimits(total_timeout_s=total, stage_timeout_s=stage, memory_limit_mb=None)


def _candidate(*refs: str) -> _Solve:
    return _Solve(
        "feasible",
        positions={ref: (float(i), 1.0) for i, ref in enumerate(refs)},
        rotations=dict.fromkeys(refs, 0),
    )


def _released_refs(kwargs: dict[str, object], base: float = 2.0, released: float = 40.0) -> set[str]:
    radii = kwargs["hard_displacement_radii_mm"]
    assert isinstance(radii, dict)
    return {ref for ref, radius in radii.items() if radius == released and radius != base}


def test_baseline_is_proven_before_any_group_release() -> None:
    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        del kwargs
        return _Solve("infeasible")

    result = run_displacement_deletion_campaign(
        _netlist("A", "B", "C", "D"),
        object(),
        _warm_start("A", "B", "C", "D"),
        {"g0": ("A", "B"), "g1": ("C", "D")},
        solver=solver,
        limits=_limits(),
    )

    assert result.status is DisplacementDeletionCampaignStatus.COMPLETE
    assert result.baseline is not None and result.baseline.status is RestorationStageStatus.INFEASIBLE
    assert result.baseline.test_index == 0
    assert result.singleton_tests
    assert all(test.test_index > result.baseline.test_index for test in result.singleton_tests)


def test_each_singleton_release_is_fresh_and_balanced_batches_wait() -> None:
    expected_singletons = (("A", "B"), ("C", "D"), ("E", "F"), ("G", "H"))

    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        # Every probe is deliberately answered independently.  The fresh
        # model guarantee is checked from each report's complete radii map
        # below (a cumulative implementation would leave multiple groups at
        # the release radius).
        del kwargs
        return _Solve("infeasible")

    result = run_displacement_deletion_campaign(
        _netlist("A", "B", "C", "D", "E", "F", "G", "H"),
        object(),
        _warm_start("A", "B", "C", "D", "E", "F", "G", "H"),
        {"g0": ("A", "B"), "g1": ("C", "D"), "g2": ("E", "F"), "g3": ("G", "H")},
        solver=solver,
        limits=_limits(),
    )

    assert result.status is DisplacementDeletionCampaignStatus.COMPLETE
    assert result.baseline is not None
    assert not _released_refs({"hard_displacement_radii_mm": result.baseline.component_radii_mm})
    assert tuple(report.released_refs for report in result.singleton_tests) == expected_singletons
    assert all(
        len(_released_refs({"hard_displacement_radii_mm": report.component_radii_mm})) == len(report.released_refs)
        for report in result.singleton_tests
    )
    # Balanced halves are deterministic and occur only after all four
    # singleton releases have been tested.
    assert tuple(report.released_refs for report in result.balanced_half_tests) == (
        ("A", "B", "E", "F"),
        ("C", "D", "G", "H"),
    )


def test_unknown_baseline_never_attempts_release() -> None:
    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        assert not _released_refs(kwargs)
        return _Solve("unknown")

    result = run_displacement_deletion_campaign(
        _netlist("A", "B"), object(), _warm_start("A", "B"), {"g0": ("A",), "g1": ("B",)}, solver=solver, limits=_limits()
    )

    assert result.status is DisplacementDeletionCampaignStatus.STOPPED
    assert result.baseline is not None and not result.baseline.positions


def test_feasible_release_invokes_verifier_and_retains_violation_count() -> None:
    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        if not _released_refs(kwargs):
            return _Solve("infeasible")
        return _candidate("A", "B")

    def verify(candidate: object) -> _Verification:
        assert isinstance(candidate, _Solve)
        assert candidate.positions == {"A": (0.0, 1.0), "B": (1.0, 1.0)}
        return _Verification(("A:B", "A:C"))

    result = run_displacement_deletion_campaign(
        _netlist("A", "B"), object(), _warm_start("A", "B"), {"g0": ("A",), "g1": ("B",)}, solver=solver, verify=verify, limits=_limits()
    )

    assert result.status is DisplacementDeletionCampaignStatus.COMPLETE
    report = result.singleton_tests[0]
    assert report.status is RestorationStageStatus.ACCEPTED
    assert report.verification_passed is False
    assert report.violation_count == 2
    assert report.positions == {"A": (0.0, 1.0), "B": (1.0, 1.0)}


def test_incomplete_candidate_is_fail_closed_without_verifier() -> None:
    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        if not _released_refs(kwargs):
            return _Solve("infeasible")
        return _Solve("feasible", positions={"A": (1.0, 1.0)}, rotations={"A": 0})

    def verify(_candidate: object) -> _Verification:
        raise AssertionError("incomplete candidate must not reach exact verification")

    result = run_displacement_deletion_campaign(
        _netlist("A", "B"), object(), _warm_start("A", "B"), {"g0": ("A",), "g1": ("B",)}, solver=solver, verify=verify, limits=_limits()
    )

    assert result.status is DisplacementDeletionCampaignStatus.INVALID
    assert not result.singleton_tests[0].positions
    assert "incomplete placement" in result.diagnostics[0]


def test_malformed_solver_result_is_fail_closed() -> None:
    def solver(_netlist: object, _board: object, **kwargs: object) -> object:
        del kwargs
        return object()

    result = run_displacement_deletion_campaign(
        _netlist("A"), object(), _warm_start("A"), {"all": ("A",)}, solver=solver, limits=_limits()
    )

    # A result without a solver status is malformed, not an ordinary solver
    # unknown.  Bubble that diagnostic as INVALID so no release evidence can
    # be consumed accidentally.
    assert result.status is DisplacementDeletionCampaignStatus.INVALID
    assert result.baseline is not None
    assert not result.baseline.positions


def test_external_timeout_stops_campaign_before_release() -> None:
    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        del kwargs
        time.sleep(0.5)
        return _Solve("infeasible")

    result = run_displacement_deletion_campaign(
        _netlist("A"), object(), _warm_start("A"), {"all": ("A",)}, solver=solver,
        limits=RestorationLimits(total_timeout_s=2.0, stage_timeout_s=0.05, memory_limit_mb=None),
    )

    assert result.status is DisplacementDeletionCampaignStatus.TIMEOUT
    assert result.baseline is not None
    assert result.baseline.status is RestorationStageStatus.TIMEOUT
    assert not result.baseline.positions


def test_invalid_partition_fails_closed_before_solver() -> None:
    called = False

    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        nonlocal called
        called = True
        del kwargs
        return _Solve("infeasible")

    result = run_displacement_deletion_campaign(
        _netlist("A", "B"), object(), _warm_start("A", "B"), {"only": ("A",)}, solver=solver, limits=_limits()
    )

    assert result.status is DisplacementDeletionCampaignStatus.INVALID
    assert not called
