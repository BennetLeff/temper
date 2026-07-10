from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class ProximityRule:
    """Proximity constraint between two components."""

    component_a: str
    component_b: str
    max_distance_mm: float = 10.0
    description: str = ""
    tier: str = "soft"  # "hard" or "soft"


@dataclass
class GroupSeparation:
    """Minimum separation between two groups."""

    group_a: str
    group_b: str
    min_distance_mm: float = 20.0
    description: str = ""


@dataclass
class ComponentSpacingRule:
    """Minimum edge-to-edge spacing between specific component pairs."""

    component_a: str
    component_b: str
    min_separation_mm: float
    description: str = ""
    weight: float = 1.0
    tier: str = "soft"  # "hard" or "soft"


@dataclass
class ManufacturingConstraint:
    """Manufacturing constraint for orientations and assembly side."""

    components: list[str]
    allowed_orientations: list[float] | None = None
    side: str | None = None  # "top", "bottom", "both"
    tier: str = "hard"
    because: str = ""
    weight: float = 1.0


@dataclass
class EscapeClearance:
    """Keep area clear around fine-pitch ICs for escape routing.

    The clearance is computed from pin density to ensure routes can escape.
    """

    component: str  # Component ref (e.g., "U_MCU")
    clearance_mm: float | None = None  # If None, computed from pin density
    priority_sides: list[str] = field(default_factory=list)  # ["bottom", "right"]
    tier: str = "soft"  # "hard" or "soft"
    description: str = ""

    def compute_clearance(self, pin_count: int, pitch_mm: float) -> float:
        """Compute clearance from pin density.

        Heuristic: clearance = sqrt(pin_count) * pitch * 1.5
        For QFN-56 with 0.5mm pitch: sqrt(56) * 0.5 * 1.5 ≈ 5.6mm
        """
        return math.sqrt(pin_count) * pitch_mm * 1.5


@dataclass
class ComponentGroup:
    """Group of components that should be placed together."""

    name: str
    components: list[str]
    max_spread_mm: float = 30.0  # Maximum diameter of group bounding box
    zone: str | None = None  # Required zone
    proximity_rules: list[ProximityRule] = field(default_factory=list)  # Proximity within group
    weight: float = 1.0  # Importance weight (higher = stronger clustering)
    description: str = ""
    # Optional ID to force identical internal layouts with other groups sharing this ID
    template_group: str | None = None
    # Optional pin number/name that defines the 'front' of the group for rotation
    primary_pin: str | None = None
    # Whether to organize the group in a 2D matrix with dynamic gutters
    stacked_layout: bool = False
