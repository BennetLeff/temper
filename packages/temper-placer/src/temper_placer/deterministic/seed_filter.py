"""
filter_seed: pure accept/reject function over a seed candidate.

Iterates a seed's component positions against a :class:`BottleneckMap`
and applies the stricter HV threshold to HV-class components. The
function is intentionally side-effect free so callers can wire it into
anywhere a seed candidate is being evaluated.

@req(2026-06-23-004, R1)
@req(2026-06-23-004, K1)
@req(2026-06-23-004, K2)
"""

from __future__ import annotations

from collections.abc import Mapping

from temper_placer.deterministic.bottleneck_map import BottleneckMap


def filter_seed(
    seed: Mapping[str, tuple[float, float]],
    bottleneck_map: BottleneckMap,
    threshold: float,
    hv_threshold: float,
    hv_refs: frozenset[str],
) -> bool:
    """Return ``True`` iff every ref in ``seed`` passes the bottleneck filter.

    Args:
        seed: Component ref -> ``(x, y)`` placement candidate. The seed is
            accepted only if **every** ref's cell score is below the
            applicable threshold.
        bottleneck_map: Per-cell congestion score grid. Out-of-bounds
            samples clamp to 0.0 (so a missing map edge cannot cause
            over-rejection).
        threshold: Maximum score for low-voltage refs.
        hv_threshold: Maximum score for refs in ``hv_refs`` (stricter).
        hv_refs: Set of component refs that should be evaluated against
            ``hv_threshold``. References not in this set are evaluated
            against ``threshold``.

    Returns:
        ``True`` if all refs in the seed pass their threshold, ``False``
        if any ref meets or exceeds its threshold.
    """
    for ref, position in seed.items():
        x, y = position
        score = bottleneck_map.score_at(x, y)
        limit = hv_threshold if ref in hv_refs else threshold
        if score >= limit:
            return False
    return True
