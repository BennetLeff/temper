"""Bounded orchestration for replaying caller-supplied creepage cuts."""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from numbers import Real
from typing import Protocol, TypeAlias

from temper_placer.placer.cp_sat.creepage_cut_replay import (
    ReplayCut,
    decode_creepage_cut_replay,
    encode_creepage_cut_replay,
)

ReplayViolation: TypeAlias = tuple[str, str, float, float]
_SUCCESS = frozenset({"feasible", "optimal", "success"})
_CPSAT_SUCCESS = frozenset({"feasible", "optimal"})
_MAX_ATTEMPTS = 1024


class ReplayAttempt(Protocol):
    def __call__(self, prior_cuts: tuple[ReplayCut, ...], timeout_s: float) -> object: ...


class ReplayResultAdapter(Protocol):
    def __call__(self, result: object) -> ReplayAttemptOutcome: ...


class CpSatPlacementResultLike(Protocol):
    status: str
    positions: Mapping[str, object]
    decomposed_creepage_cuts: Iterable[object]
    decomposed_creepage_remaining_violations: Iterable[ReplayViolation]


class ReplayCampaignStatus(str, Enum):
    SUCCESS = "success"
    UNKNOWN = "unknown"
    STALLED = "stalled"
    TIMEOUT = "timeout"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class ReplayAttemptOutcome:
    status: str
    cuts: Iterable[object] = ()
    violations: Iterable[object] = ()
    placement: object | None = None


@dataclass(frozen=True, slots=True)
class ReplayCampaignResult:
    status: ReplayCampaignStatus
    reason: str
    attempts: int
    cuts: tuple[ReplayCut, ...]
    placement: object | None = None

    @property
    def successful(self) -> bool:
        return self.status is ReplayCampaignStatus.SUCCESS and self.placement is not None

    @property
    def diagnostics(self) -> dict[str, object]:
        return {"attempts": self.attempts, "cut_count": len(self.cuts), "reason": self.reason, "status": self.status.value}


def _canonical(cuts: Iterable[object]) -> tuple[ReplayCut, ...]:
    try:
        return decode_creepage_cut_replay(encode_creepage_cut_replay(cuts))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid replay cuts: {exc}") from exc


def _finite_nonnegative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{label} must be finite and non-negative")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{label} must be finite and non-negative")
    return result


def _violation_cuts(rows: Iterable[object]) -> tuple[ReplayCut, ...]:
    try:
        iterator = iter(rows)
    except TypeError as exc:
        raise ValueError("remaining violations must be iterable") from exc
    cuts: list[ReplayCut] = []
    for index, row in enumerate(iterator):
        if not isinstance(row, (tuple, list)) or len(row) != 4:
            raise ValueError(f"remaining violation {index} must contain four values")
        _finite_nonnegative(row[3], f"remaining violation {index} actual_gap_mm")
        cuts.append((row[0], row[1], row[2]))  # type: ignore[list-item]
    return _canonical(cuts)


def adapt_cpsat_placement_result(result: CpSatPlacementResultLike) -> ReplayAttemptOutcome:
    """Adapt the typed duck-typed result without importing the solver."""
    try:
        status = result.status
        cuts = result.decomposed_creepage_cuts
        rows = result.decomposed_creepage_remaining_violations
        positions = result.positions
    except AttributeError as exc:
        raise ValueError("placement result is missing replay attributes") from exc
    if not isinstance(status, str) or not status.strip():
        raise ValueError("placement result status must be a non-empty string")
    if not isinstance(positions, Mapping):
        raise ValueError("placement result positions must be a mapping")
    try:
        cuts_tuple = tuple(cuts)
        violation_cuts = _violation_cuts(rows)
    except TypeError as exc:
        raise ValueError("placement result cut fields must be iterable") from exc
    normalized = status.strip().lower()
    placement = dict(positions) if normalized in _CPSAT_SUCCESS and not violation_cuts else None
    return ReplayAttemptOutcome(normalized, cuts_tuple, violation_cuts, placement)


def _default_adapter(result: object) -> ReplayAttemptOutcome:
    if isinstance(result, ReplayAttemptOutcome):
        return result
    if isinstance(result, Mapping):
        if "status" not in result:
            raise ValueError("attempt result is missing status")
        return ReplayAttemptOutcome(
            result["status"], result.get("cuts", ()), result.get("violations", ()), result.get("placement")
        )  # type: ignore[arg-type]
    return adapt_cpsat_placement_result(result)  # type: ignore[arg-type]


def _status(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("attempt status must be a non-empty string")
    return value.strip().lower()


def run_creepage_replay_campaign(
    attempt: ReplayAttempt,
    *,
    prior_cuts: Iterable[object] = (),
    max_attempts: int = 4,
    timeout_s: float = 30.0,
    result_adapter: ReplayResultAdapter | None = None,
    success_statuses: Iterable[str] = _SUCCESS,
    clock: Callable[[], float] = time.monotonic,
) -> ReplayCampaignResult:
    """Run bounded attempts with one global monotonic deadline."""
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= _MAX_ATTEMPTS:
        raise ValueError(f"max_attempts must be an integer from 1 to {_MAX_ATTEMPTS}")
    if isinstance(timeout_s, bool) or not isinstance(timeout_s, Real) or not math.isfinite(float(timeout_s)) or float(timeout_s) <= 0:
        raise ValueError("timeout_s must be finite and positive")
    try:
        current = _canonical(prior_cuts)
    except Exception:
        return ReplayCampaignResult(ReplayCampaignStatus.INVALID, "invalid_prior_cuts", 0, ())
    if isinstance(success_statuses, (str, bytes, bytearray)):
        raise ValueError("success_statuses must contain non-empty strings")
    try:
        success = frozenset(_status(value) for value in success_statuses)
    except (TypeError, ValueError) as exc:
        raise ValueError("success_statuses must contain non-empty strings") from exc
    if not success:
        raise ValueError("success_statuses must not be empty")
    try:
        started = float(clock())
    except (TypeError, ValueError) as exc:
        raise ValueError("clock must return a finite number") from exc
    deadline = started + float(timeout_s)
    if not math.isfinite(started) or not math.isfinite(deadline):
        raise ValueError("clock and timeout must produce a finite deadline")
    last = started
    adapter = result_adapter or _default_adapter
    seen = {current}
    for index in range(max_attempts):
        try:
            now = float(clock())
        except (TypeError, ValueError):
            return ReplayCampaignResult(ReplayCampaignStatus.INVALID, "invalid_clock", index, current)
        if not math.isfinite(now) or now < last:
            return ReplayCampaignResult(ReplayCampaignStatus.INVALID, "invalid_clock", index, current)
        last = now
        if deadline <= now:
            return ReplayCampaignResult(ReplayCampaignStatus.TIMEOUT, "deadline_exceeded", index, current)
        try:
            outcome = adapter(attempt(current, deadline - now))
            status = _status(outcome.status)
            returned = _canonical(outcome.cuts)
            violations = _canonical(outcome.violations)
            updated = _canonical((*current, *returned))
        except (TypeError, ValueError, AttributeError):
            return ReplayCampaignResult(ReplayCampaignStatus.INVALID, "invalid_attempt_result", index + 1, current)
        except Exception:
            return ReplayCampaignResult(ReplayCampaignStatus.INVALID, "attempt_error", index + 1, current)
        try:
            completed = float(clock())
        except (TypeError, ValueError):
            return ReplayCampaignResult(ReplayCampaignStatus.INVALID, "invalid_clock", index + 1, updated)
        if not math.isfinite(completed) or completed < last:
            return ReplayCampaignResult(ReplayCampaignStatus.INVALID, "invalid_clock", index + 1, updated)
        last = completed
        if completed >= deadline:
            return ReplayCampaignResult(ReplayCampaignStatus.TIMEOUT, "deadline_exceeded", index + 1, updated)
        if status in success and not violations:
            return ReplayCampaignResult(ReplayCampaignStatus.SUCCESS, "verified_zero_violations", index + 1, updated, outcome.placement)
        if updated == current:
            return ReplayCampaignResult(ReplayCampaignStatus.STALLED, "repeated_identical_cut_set" if updated else "no_cut_progress", index + 1, updated)
        if updated in seen:
            return ReplayCampaignResult(ReplayCampaignStatus.STALLED, "repeated_identical_cut_set", index + 1, updated)
        seen.add(updated)
        current = updated
    return ReplayCampaignResult(ReplayCampaignStatus.UNKNOWN, "max_attempts_exhausted", max_attempts, current)


__all__ = [
    "CpSatPlacementResultLike", "ReplayAttempt", "ReplayAttemptOutcome", "ReplayCampaignResult",
    "ReplayCampaignStatus", "ReplayCut", "ReplayResultAdapter", "ReplayViolation",
    "adapt_cpsat_placement_result", "run_creepage_replay_campaign",
]
