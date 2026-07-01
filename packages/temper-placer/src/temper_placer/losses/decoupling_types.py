"""
Frozen dataclasses for decoupling capacitor classification and constraint generation.

Provides DecouplingClass enum, DecouplingDetection, and DecouplingDetectionSet
to classify decoupling capacitors (bypass vs bulk) from netlist analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DecouplingClass(Enum):
    """Classification of decoupling capacitor type and its placement requirements.

    BYPASS: Small-value caps placed within ~3mm of the IC for high-frequency
            noise suppression. Tier: HARD.
    BULK: Large-value reservoir caps placed within ~20mm of the load to handle
          transient current demands. Tier: STRONG.
    NOT_DECOUPLING: The capacitor is not classified for decoupling (tier access
                    raises ValueError).
    """

    BYPASS = ("bypass", 3.0, "HARD")
    BULK = ("bulk", 20.0, "STRONG")
    NOT_DECOUPLING = ("not_decoupling", float("inf"), "DISABLED")

    def __init__(self, label: str, max_distance_mm: float, tier_label: str):
        self._label = label
        self._max_distance_mm = max_distance_mm
        self._tier_label = tier_label

    @property
    def max_distance_mm(self) -> float:
        """Maximum recommended placement distance in mm."""
        if self == DecouplingClass.NOT_DECOUPLING:
            raise ValueError("NOT_DECOUPLING has no max distance")
        return self._max_distance_mm

    @property
    def tier_label(self) -> str:
        """Constraint tier label (HARD, STRONG)."""
        if self == DecouplingClass.NOT_DECOUPLING:
            raise ValueError("NOT_DECOUPLING has no tier")
        return self._tier_label


@dataclass(frozen=True)
class DecouplingDetection:
    """A detected decoupling capacitor association.

    Attributes:
        cap_ref: Reference designator of the capacitor (e.g., "C1").
        ic_ref: Reference designator of the IC (e.g., "U1").
        classification: How this capacitor is classified for decoupling.
        power_pin: Name of the power pin on the IC this cap serves.
        cap_value_pf: Capacitance value in picofarads, or 0 if unknown.
        cap_package: Capacitor package/footprint (e.g., "0603", "ELEC_D12_5").
        net_name: The shared power net connecting cap and IC.
    """

    cap_ref: str
    ic_ref: str
    classification: DecouplingClass
    power_pin: str
    cap_value_pf: float
    cap_package: str
    net_name: str

    def to_adjacent_constraint(self):
        """Convert this detection to an AdjacentConstraint.

        Returns:
            An AdjacentConstraint with appropriate max_distance and tier.
        """
        from temper_placer.pcl.constraints import AdjacentConstraint, ConstraintTier

        tier = (
            ConstraintTier.HARD
            if self.classification == DecouplingClass.BYPASS
            else ConstraintTier.STRONG
        )
        return AdjacentConstraint(
            a=self.cap_ref,
            b=self.ic_ref,
            max_distance_mm=self.classification.max_distance_mm,
            tier=tier,
            because=f"Decoupling capacitor {self.cap_ref} for {self.ic_ref} "
            f"({self.classification.name}) on net {self.net_name}",
            pin_b=self.power_pin if self.power_pin else None,
        )


@dataclass(frozen=True)
class DecouplingDetectionSet:
    """Immutable set of decoupling detections from a single netlist analysis.

    Attributes:
        detections: Tuple of DecouplingDetection instances.
        netlist_hash: A hash of the netlist for cache invalidation.
    """

    detections: tuple[DecouplingDetection, ...]
    netlist_hash: str

    def to_constraints(self) -> list:
        """Convert all detections to PCL AdjacentConstraints.

        Returns:
            List of AdjacentConstraint instances.
        """
        return [d.to_adjacent_constraint() for d in self.detections]

    def by_classification(self, cls: DecouplingClass) -> list[DecouplingDetection]:
        """Filter detections by classification."""
        return [d for d in self.detections if d.classification == cls]

    def __len__(self) -> int:
        return len(self.detections)

    def __iter__(self):
        return iter(self.detections)

    def __contains__(self, item):
        return item in self.detections
