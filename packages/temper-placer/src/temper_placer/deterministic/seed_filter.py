"""
filter_seed: pure accept/reject function over a seed candidate.

Iterates a seed's component positions against a :class:`BottleneckMap`
and applies the stricter HV threshold to HV-class components. The
function is intentionally side-effect free so callers can wire it into
anywhere a seed candidate is being evaluated.

@req(2026-06-23-004, R1)
@req(2026-06-23-004, K1)
@req(2026-06-23-004, K2)

Wave 4, **Phase 5** (deterministic hubs slice): the accept/reject fold is
implemented in Rust in the ``temper-design-bundle`` crate
(``temper_design_bundle_python.deterministic_hubs.filter_seed_kernel``). This
module keeps the pre-migration public API unchanged and delegates.

Bit-exactness: the kernel iterates the seed in insertion order (first-failure
short circuit — the accept/reject outcome is order-invariant, pinned by the
shuffled-seed differential), applies the stricter HV threshold to refs in
``hv_refs``, uses ``score >= limit`` equality-reject semantics, and clamps
out-of-bounds scores to ``0.0`` via the same CPython floor-division as the
BottleneckMap kernel. Verified by
``tests/deterministic/test_seed_filter_rust_differential.py`` (oracle:
``tests/deterministic/_seed_filter_py_oracle.py``) and the PBT suite
``tests/deterministic/test_seed_filter_pbt.py``; the structural proof is in
``packages/temper-design-bundle/VERIFICATION.md``.
"""

from __future__ import annotations

from collections.abc import Mapping

import temper_design_bundle_python as _tdb

from temper_placer.deterministic.bottleneck_map import BottleneckMap

_DH = _tdb.deterministic_hubs


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
    return _DH.filter_seed_kernel(
        dict(seed),
        bottleneck_map.cell_size_mm,
        bottleneck_map.width,
        bottleneck_map.height,
        bottleneck_map.origin_xy[0],
        bottleneck_map.origin_xy[1],
        list(bottleneck_map.scores),
        threshold,
        hv_threshold,
        set(hv_refs),
    )
