from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .violation_mapper import MappedViolation


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
    """Computes zone geometry adjustments based on DRC violations."""

    def __init__(
        self,
        zone_config: dict[str, Any],
        violation_threshold: int = 5,
        expansion_per_violation: float = 0.5
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
        # 1. Count violations per zone
        zone_counts = {}
        for v in violations:
            if v.zone:
                zone_counts[v.zone] = zone_counts.get(v.zone, 0) + 1

        adjustments = {}

        # 2. Compute adjustments for zones exceeding threshold
        for zone_name, count in zone_counts.items():
            if count >= self.violation_threshold:
                config = self.zone_config.get(zone_name)
                if not config:
                    continue

                # Calculate required expansion
                excess = count - self.violation_threshold + 1
                expansion = excess * self.expansion_per_violation

                # Get current size and max size
                bounds = config.get('bounds')
                if not bounds or len(bounds) != 2:
                    continue

                (x1, y1), (x2, y2) = bounds
                width = abs(x2 - x1)
                height = abs(y2 - y1)

                max_size = config.get('max_size', (float('inf'), float('inf')))
                max_width, max_height = max_size

                can_expand = config.get('can_expand', ['right', 'left', 'up', 'down'])

                delta_w = 0.0
                delta_h = 0.0

                # Expand width if allowed
                if any(d in ['right', 'left'] for d in can_expand):
                    target_width = min(width + expansion, max_width)
                    delta_w = target_width - width

                # Expand height if allowed
                if any(d in ['up', 'down'] for d in can_expand):
                    target_height = min(height + expansion, max_height)
                    delta_h = target_height - height

                if delta_w > 0 or delta_h > 0:
                    adjustments[zone_name] = ZoneAdjustment(
                        zone_name=zone_name,
                        delta_width=delta_w,
                        delta_height=delta_h
                    )

        return AdjustmentResult(adjustments=adjustments)
