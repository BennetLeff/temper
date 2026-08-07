"""Validation methods for phased component assignment.

Contains the :class:`_PhaseValidationMixin` with bottleneck-map seed
filtering, critical-bottleneck violation detection, and the invariant
check.

Wave 4, **Phase 5, final leaves**: the critical-bottleneck violation kernel
(``find_critical_bottleneck_violations``) is implemented in Rust in the
``temper-design-bundle`` crate (``temper_design_bundle_python.deterministic_phase``).
This module keeps the pre-migration public API unchanged and delegates; the
``self.channel_map`` guard, the seed-filter orchestration and the DRC-fence
raise/opt-out logic stay Python.

Bit-exactness: the Rust kernel replicates the oracle's floor-to-cell grid
indexing (``int(math.floor((float(x_mm) * 1000.0) / cell_um))``), the
per-cell first-wins-on-score-ties critical map, and the VERBATIM quirk that
the violation ``severity`` reads the LAST bottleneck's severity (the first
loop's trailing ``bn``), not the matched cell's. Verified by
``tests/deterministic/stages/test_phase_validation_rust_differential.py``
(oracle: ``tests/deterministic/stages/_phase_validation_py_oracle.py``); the
structural proof lives in ``packages/temper-design-bundle/VERIFICATION.md``.
"""

from __future__ import annotations

import logging

import temper_design_bundle_python as _tdb

from ..flags import is_drc_fence_fail_enabled
from ._phase_core import PhasedComponentAssignmentError

_LOGGER = logging.getLogger(__name__)


class _PhaseValidationMixin:
    """Validation and bottleneck-filtering methods.

    Provides _apply_bottleneck_filter, find_critical_bottleneck_violations,
    and _check_critical_bottlenecks.
    """

    def _apply_bottleneck_filter(
        self,
        component_ref: str,
        candidate_slots: list[tuple[float, float]],
        comp_by_ref: dict | None = None,
    ) -> list[tuple[float, float]]:
        """Filter ``candidate_slots`` through the bottleneck map.

        Returns the unfiltered list when:

        * the seed filter is disabled at the config level
        * no ``BottleneckMap`` is reachable on the current state
        * the filter would drop every candidate (empty pool fallback
           per R2; a warning is logged and the original pool passes
           through unchanged)

        Otherwise returns the slot list with cells at or above the
        applicable (LV or HV) threshold removed, and emits one
        structured INFO log line per call with the keys required by R6.

        # @req(2026-06-23-004, R2)
        # @req(2026-06-23-004, R6)
        # @req(2026-06-23-004, K4)
        """
        logger = logging.getLogger(__name__)

        config = self.seed_filter
        if config is None or not config.enabled:
            return candidate_slots
        bmap = self._bottleneck_map
        if bmap is None:
            return candidate_slots

        is_hv = False
        if comp_by_ref is not None:
            is_hv = self._is_hv_ref(component_ref, comp_by_ref)
        limit = config.hv_threshold if is_hv else config.threshold

        accepted: list[tuple[float, float]] = []
        scores_accepted: list[float] = []
        all_scores: list[float] = []
        for slot in candidate_slots:
            score = bmap.score_at(slot[0], slot[1])
            all_scores.append(score)
            if score < limit:
                accepted.append(slot)
                scores_accepted.append(score)

        candidates_total = len(candidate_slots)
        candidates_accepted = len(accepted)
        candidates_rejected = candidates_total - candidates_accepted
        fallback_used = False

        if candidates_accepted == 0 and candidates_total > 0:
            logger.warning(
                "seed_filter: would reject all %d candidates for %s; "
                "falling back to unfiltered pool",
                candidates_total,
                component_ref,
            )
            fallback_used = True
            accepted = list(candidate_slots)
            scores_accepted = list(all_scores)
            candidates_accepted = candidates_total
            candidates_rejected = 0

        avg_score = sum(scores_accepted) / len(scores_accepted) if scores_accepted else 0.0
        logger.info(
            "seed_filter event=seed_filter "
            "component=%s "
            "candidates_total=%d "
            "candidates_accepted=%d "
            "candidates_rejected=%d "
            "avg_bottleneck_score_accepted=%.4f "
            "threshold=%.4f "
            "hv_threshold=%.4f "
            "is_hv=%s "
            "fallback_used=%s",
            component_ref,
            candidates_total,
            candidates_accepted,
            candidates_rejected,
            avg_score,
            config.threshold,
            config.hv_threshold,
            is_hv,
            fallback_used,
        )
        return accepted

    def find_critical_bottleneck_violations(
        self, placements: dict[str, tuple[float, float]]
    ) -> list[dict]:
        """Return a list of CRITICAL-severity bottleneck violations.

        Each violation is a dict with keys ``ref``, ``x``, ``y``, ``layer``,
        ``severity``. The center of each placed component is converted to
        grid coordinates (floor semantics, same as
        :func:`routability_penalty`); any cell covered by a CRITICAL
        bottleneck record produces a violation. MEDIUM/HIGH severities are
        not flagged - the invariant name
        (``no_component_center_in_critical_bottleneck``) is part of the
        contract.

        Out-of-grid placements (gx, gy outside the channel map bounds) are
        not flagged, matching the routability penalty 'no penalty at the
        board edge' semantics.
        """
        if self.channel_map is None or not self.channel_map.has_grid():
            return []

        cmap = self.channel_map
        cell_um = cmap.cell_size_um
        width = cmap.width
        height = cmap.height
        bottlenecks = [
            (bn.x, bn.y, bn.layer, bn.severity, bn.score) for bn in cmap.bottlenecks
        ]
        return _tdb.deterministic_phase.find_critical_bottleneck_violations_py(
            placements,
            bottlenecks,
            cell_um,
            width,
            height,
        )

    def _check_critical_bottlenecks(self, placements: dict[str, tuple[float, float]]) -> list[dict]:
        """Run the invariant check; blocking by default.

        When :func:`is_drc_fence_fail_enabled` returns True (the default),
        the first violation raises :class:`PhasedComponentAssignmentError`
        with the offending ref and severity in the message. Opt out by
        setting :envvar:`TEMPER_DRC_FENCE_FAIL` to ``"0"``, ``"false"``,
        ``"no"``, or ``"off"``.
        """
        violations = self.find_critical_bottleneck_violations(placements)
        for v in violations:
            if is_drc_fence_fail_enabled():
                raise PhasedComponentAssignmentError(
                    f"DRC fence violation (hard-fail): {v['ref']} placed in "
                    f"CRITICAL bottleneck cell ({v['x']}, {v['y']}) on "
                    f"layer {v['layer']}; severity={v['severity']}"
                )
            _LOGGER.warning(
                "DRC fence violation: %s placed in CRITICAL bottleneck cell "
                "(%d, %d) on layer %s; severity=%s",
                v["ref"],
                v["x"],
                v["y"],
                v["layer"],
                v["severity"],
            )
        return violations
