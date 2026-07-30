"""Absolute prover-coverage ratchet.

Coverage is the count of nets whose emitted copper passed the external DRC
soundness gate. It is intentionally not a ratio: narrowing the attempted set
must never make progress appear better.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class CoverageSnapshot:
    """Immutable coverage measurement with a stable domain breakdown."""

    proven_nets: int
    total_nets: int
    by_domain: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        if self.proven_nets < 0 or self.total_nets < 0:
            raise ValueError("coverage counts must be non-negative")
        if self.proven_nets > self.total_nets:
            raise ValueError("proven_nets cannot exceed total_nets")
        names = [name for name, _ in self.by_domain]
        if names != sorted(set(names)):
            raise ValueError("coverage domains must be unique and sorted")
        if any(count < 0 for _, count in self.by_domain):
            raise ValueError("domain coverage counts must be non-negative")

    @classmethod
    def from_mapping(
        cls,
        proven_nets: int,
        total_nets: int,
        by_domain: Mapping[str, int] | None = None,
    ) -> CoverageSnapshot:
        return cls(
            proven_nets=proven_nets,
            total_nets=total_nets,
            by_domain=tuple(sorted((str(name), int(count)) for name, count in (by_domain or {}).items())),
        )

    def domain_counts(self) -> dict[str, int]:
        return dict(self.by_domain)


@dataclass(frozen=True)
class CoverageRatchetResult:
    """Structured result for CI and human-readable summaries."""

    passed: bool
    reason: str
    proven_delta: int
    domain_deltas: tuple[tuple[str, int], ...]


def evaluate_coverage(
    baseline: CoverageSnapshot,
    current: CoverageSnapshot,
) -> CoverageRatchetResult:
    """Reject stale universes, absolute regressions, and domain regressions."""
    if current.total_nets != baseline.total_nets:
        return CoverageRatchetResult(
            passed=False,
            reason=(
                f"total net universe changed {baseline.total_nets} -> "
                f"{current.total_nets}; re-measure the baseline"
            ),
            proven_delta=current.proven_nets - baseline.proven_nets,
            domain_deltas=(),
        )

    baseline_domains = baseline.domain_counts()
    current_domains = current.domain_counts()
    domain_deltas = tuple(
        sorted(
            (name, current_domains.get(name, 0) - count)
            for name, count in baseline_domains.items()
        )
    )
    if current.proven_nets < baseline.proven_nets:
        return CoverageRatchetResult(
            passed=False,
            reason=(
                f"absolute proven-net count regressed "
                f"{baseline.proven_nets} -> {current.proven_nets}"
            ),
            proven_delta=current.proven_nets - baseline.proven_nets,
            domain_deltas=domain_deltas,
        )

    regressed_domains = [(name, delta) for name, delta in domain_deltas if delta < 0]
    if regressed_domains:
        return CoverageRatchetResult(
            passed=False,
            reason=f"coverage domain(s) regressed: {regressed_domains}",
            proven_delta=current.proven_nets - baseline.proven_nets,
            domain_deltas=domain_deltas,
        )

    return CoverageRatchetResult(
        passed=True,
        reason=(
            f"{current.proven_nets} nets proven safe / {current.total_nets} total nets"
        ),
        proven_delta=current.proven_nets - baseline.proven_nets,
        domain_deltas=domain_deltas,
    )
