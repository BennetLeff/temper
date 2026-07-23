from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RoutingCorridor(BaseModel):
    """Preserve routing channel between components."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Corridor name")
    from_component: str = Field(description="Source component reference")
    to_component: str = Field(description="Target component reference")
    width_mm: float = Field(gt=0, description="Corridor width in mm")
    keep_clear: bool = Field(
        default=True, description="If True, don't place components in corridor"
    )
    nets: list[str] = Field(default_factory=list, description="Associated net names")
    tier: str = Field(default="soft", description="Constraint tier: hard or soft")
    description: str = Field(default="", description="Human-readable description")


class PlacementProximityConstraint(BaseModel):
    """Constraint ensuring a component output pin is close to a target input pin."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Unique constraint identifier")
    from_component: str = Field(description="Source component reference")
    from_pin: str = Field(description="Source pin number")
    to_component: str = Field(description="Target component reference")
    to_pin: str = Field(description="Target pin number")
    max_distance_mm: float = Field(
        default=15.0, gt=0, description="Maximum pin-to-pin distance in mm"
    )
    tier: str = Field(default="hard", description="Constraint tier: hard or soft")
    description: str = Field(default="", description="Human-readable description")


class HVExclusionZone(BaseModel):
    """Defines a rectangular zone around HV components that signals must avoid."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Unique zone identifier")
    center: tuple[float, float] = Field(description="(x, y) center position in mm")
    size: tuple[float, float] = Field(description="(width, height) in mm")
    clearance_mm: float = Field(
        default=6.0, ge=0, description="Required creepage clearance in mm"
    )  # allow-safety-constant: HV exclusion zone default
    excluded_nets: list[str] = Field(
        default_factory=list, description="Net names that must avoid this zone"
    )
    component_refdes: str | None = Field(
        default=None, description="Optional parent component reference"
    )
    description: str = Field(default="", description="Human-readable description")


class IsolationSlot(BaseModel):
    """Defines a PCB slot for creepage isolation between HV and LV pins."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Unique slot identifier")
    component_ref: str = Field(description="Component reference for positioning")
    start_offset: tuple[float, float] = Field(
        description="(dx, dy) offset from component origin to slot start"
    )
    end_offset: tuple[float, float] = Field(
        description="(dx, dy) offset from component origin to slot end"
    )
    width_mm: float = Field(default=1.5, gt=0, description="Slot width in mm")
    lv_pin: str = Field(default="", description="Low-voltage pin number being isolated")
    hv_pin: str = Field(default="", description="High-voltage pin number")
    description: str = Field(default="", description="Human-readable description")
