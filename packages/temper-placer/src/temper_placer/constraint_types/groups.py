from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field


class ProximityRule(BaseModel):
    """Proximity constraint between two components."""

    model_config = ConfigDict(frozen=True)

    component_a: str = Field(description="First component reference")
    component_b: str = Field(description="Second component reference")
    max_distance_mm: float = Field(
        default=10.0, gt=0, description="Maximum allowed distance between components in mm"
    )
    description: str = Field(default="", description="Human-readable description")
    tier: str = Field(default="soft", description="Constraint tier: hard or soft")


class GroupSeparation(BaseModel):
    """Minimum separation between two groups."""

    model_config = ConfigDict(frozen=True)

    group_a: str = Field(description="First group name")
    group_b: str = Field(description="Second group name")
    min_distance_mm: float = Field(
        default=20.0, ge=0, description="Minimum separation distance in mm"
    )
    description: str = Field(default="", description="Human-readable description")


class ComponentSpacingRule(BaseModel):
    """Minimum edge-to-edge spacing between specific component pairs."""

    model_config = ConfigDict(frozen=True)

    component_a: str = Field(description="First component reference")
    component_b: str = Field(description="Second component reference")
    min_separation_mm: float = Field(ge=0, description="Minimum edge-to-edge separation in mm")
    description: str = Field(default="", description="Human-readable description")
    weight: float = Field(default=1.0, ge=0, description="Importance weight")
    tier: str = Field(default="soft", description="Constraint tier: hard or soft")


class ManufacturingConstraint(BaseModel):
    """Manufacturing constraint for orientations and assembly side."""

    model_config = ConfigDict(frozen=True)

    components: list[str] = Field(description="List of component references")
    allowed_orientations: list[float] | None = Field(
        default=None, description="Allowed rotation angles in degrees"
    )
    side: str | None = Field(default=None, description="Allowed board side: top, bottom, both")
    tier: str = Field(default="hard", description="Constraint tier: hard or soft")
    because: str = Field(default="", description="Justification for the constraint")
    weight: float = Field(default=1.0, ge=0, description="Importance weight")


class EscapeClearance(BaseModel):
    """Keep area clear around fine-pitch ICs for escape routing."""

    model_config = ConfigDict(frozen=True)

    component: str = Field(description="Component reference (e.g., 'U_MCU')")
    clearance_mm: float | None = Field(
        default=None, description="Override clearance in mm; computed from pin density if None"
    )
    priority_sides: list[str] = Field(
        default_factory=list, description="Priority routing sides (e.g., ['bottom', 'right'])"
    )
    tier: str = Field(default="soft", description="Constraint tier: hard or soft")
    description: str = Field(default="", description="Human-readable description")

    def compute_clearance(self, pin_count: int, pitch_mm: float) -> float:
        """Compute clearance from pin density."""
        return math.sqrt(pin_count) * pitch_mm * 1.5


class ComponentGroup(BaseModel):
    """Group of components that should be placed together."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Group name")
    components: list[str] = Field(description="List of component references in this group")
    max_spread_mm: float = Field(
        default=30.0, gt=0, description="Maximum diameter of group bounding box in mm"
    )
    zone: str | None = Field(default=None, description="Required zone for the group")
    proximity_rules: list[ProximityRule] = Field(
        default_factory=list, description="Proximity rules within group"
    )
    weight: float = Field(
        default=1.0, ge=0, description="Importance weight (higher = stronger clustering)"
    )
    description: str = Field(default="", description="Human-readable description")
    template_group: str | None = Field(
        default=None, description="Optional ID for identical internal layouts"
    )
    primary_pin: str | None = Field(
        default=None, description="Pin number/name defining the front of the group"
    )
    stacked_layout: bool = Field(
        default=False, description="Organize group in a 2D matrix with dynamic gutters"
    )
