from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import temper_design_bundle_python as _tdb

from .violation_mapper import MappedViolation

_DH = _tdb.deterministic_hubs


@dataclass
class ZoneAdjustment:
    """Calculated adjustment for a zone."""

    zone_name: str
    delta_width: float = 0.0
    delta_height: float = 0.0
    new_bounds: tuple[tuple[float, float], tuple[float, float]] | None = None


@dataclass
class AdjustmentResult:
    """Collection of zone adjustments."""

    adjustments: dict[str, ZoneAdjustment] = field(default_factory=dict)


class ZoneAdjuster:
    """Computes zone geometry adjustments based on DRC violations.

    Wave 4, **Phase 5** (deterministic hubs slice): the adjustment compute of
    ``compute_adjustments`` is implemented in Rust in the ``temper-design-bundle``
    crate (``temper_design_bundle_python.deterministic_hubs.zone_adjustments_kernel``).
    This class keeps the pre-migration public API unchanged and delegates.
    ``ZoneAdjustment``/``AdjustmentResult`` stay Python dataclasses; the live
    ``zone_config`` (re-assigned by the feedback orchestrator) crosses the
    boundary per call.
    """

    def __init__(
        self,
        zone_config: dict[str, Any],
        violation_threshold: int = 5,
        expansion_per_violation: float = 0.5,
    ):
        """
        Initialize adjuster.

        Args:
            zone_config: Dictionary mapping zone names to their configuration.
            violation_threshold: Minimum violations before a zone is adjusted.
            expansion_per_violation: mm to expand per violation above threshold.
        """
        self.zone_config = zone_config
        self.violation_threshold = violation_threshold
        self.expansion_per_violation = expansion_per_violation

    def compute_adjustments(self, violations: list[MappedViolation]) -> AdjustmentResult:
        """
        Compute adjustments based on violations.

        Args:
            violations: List of MappedViolation objects.

        Returns:
            AdjustmentResult object.
        """
        # Oracle's `if v.zone:` is a truthiness check — None AND empty-string
        # zones are skipped. Normalise falsy zones to None so the kernel
        # counts only the zones the oracle would count.
        zones = [z if z else None for z in (v.zone for v in violations)]
        adjustments = _DH.zone_adjustments_kernel(
            zones,
            self.zone_config,
            self.violation_threshold,
            self.expansion_per_violation,
        )
        return AdjustmentResult(
            adjustments={
                zone_name: ZoneAdjustment(
                    zone_name=zone_name, delta_width=delta_w, delta_height=delta_h
                )
                for zone_name, delta_w, delta_h in adjustments
            }
        )
