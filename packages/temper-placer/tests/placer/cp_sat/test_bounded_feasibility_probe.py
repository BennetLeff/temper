"""Tests for the process-isolated stripped feasibility probe boundary."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from temper_placer.placer.cp_sat.bounded_feasibility_probe import (
    ProbeLimits,
    ProbeMode,
    run_bounded_probe,
)


@dataclass
class _Candidate:
    status: str
    positions: dict[str, tuple[float, float]]
    rotations: dict[str, int]


@dataclass
class _Verification:
    violations: tuple[object, ...]


def test_runs_both_modes_and_accepts_only_exhaustively_clean_candidate() -> None:
    def solve(mode: ProbeMode, _timeout_s: float) -> _Candidate:
        return _Candidate("feasible", {"R1": (1.0, 2.0)}, {"R1": 0})

    def verify(mode: ProbeMode, candidate: _Candidate) -> _Verification:
        assert candidate.positions == {"R1": (1.0, 2.0)}
        return _Verification(())

    result = run_bounded_probe(
        solve,
        verify,
        limits=ProbeLimits(timeout_s=3.0, memory_limit_mb=None),
    )

    assert result.accepted
    assert result.accepted_run() is not None
    assert set(result.runs) == {ProbeMode.FIXED, ProbeMode.ROTATABLE}
    assert all(run.accepted for run in result.runs.values())


def test_remaining_violation_rejects_candidate_and_discards_placement() -> None:
    def solve(_mode: ProbeMode, _timeout_s: float) -> _Candidate:
        return _Candidate("optimal", {"R1": (1.0, 2.0)}, {"R1": 0})

    result = run_bounded_probe(
        solve,
        lambda _mode, _candidate: _Verification(("R1/R2",)),
        limits=ProbeLimits(timeout_s=3.0, memory_limit_mb=None),
        modes=(ProbeMode.FIXED,),
    )

    run = result.runs[ProbeMode.FIXED]
    assert run.outcome == "verification-rejected"
    assert not run.accepted
    assert run.positions == {}
    assert run.rotations == {}
    assert "1 violation" in run.diagnostics[0]


def test_unknown_solver_status_is_fail_closed_without_verifier_call() -> None:
    verified = False

    def solve(_mode: ProbeMode, _timeout_s: float) -> _Candidate:
        return _Candidate("unknown", {"R1": (1.0, 2.0)}, {"R1": 0})

    def verify(_mode: ProbeMode, _candidate: _Candidate) -> _Verification:
        nonlocal verified
        verified = True
        return _Verification(())

    result = run_bounded_probe(
        solve,
        verify,
        limits=ProbeLimits(timeout_s=3.0, memory_limit_mb=None),
        modes=(ProbeMode.ROTATABLE,),
    )

    run = result.runs[ProbeMode.ROTATABLE]
    assert run.outcome == "solver-rejected"
    assert run.solver_status == "unknown"
    assert not verified
    assert not run.positions


def test_timeout_is_external_and_fail_closed() -> None:
    def solve(_mode: ProbeMode, _timeout_s: float) -> _Candidate:
        import time

        time.sleep(1.0)
        return _Candidate("feasible", {}, {})

    result = run_bounded_probe(
        solve,
        lambda _mode, _candidate: _Verification(()),
        limits=ProbeLimits(timeout_s=0.05, memory_limit_mb=None),
        modes=(ProbeMode.FIXED,),
    )

    run = result.runs[ProbeMode.FIXED]
    assert run.outcome == "timeout"
    assert not run.accepted
    assert run.positions == {}


def test_probe_limits_and_modes_are_validated() -> None:
    with pytest.raises(ValueError, match="timeout_s"):
        ProbeLimits(timeout_s=0.0)
    with pytest.raises(ValueError, match="memory_limit_mb"):
        ProbeLimits(memory_limit_mb=0)

    def solve(_mode: ProbeMode, _timeout_s: float) -> _Candidate:
        return _Candidate("unknown", {}, {})

    with pytest.raises(ValueError, match="unique"):
        run_bounded_probe(
            solve,
            lambda _mode, _candidate: _Verification(()),
            modes=(ProbeMode.FIXED, ProbeMode.FIXED),
        )
