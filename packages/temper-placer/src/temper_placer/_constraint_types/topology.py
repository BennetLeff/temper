from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CriticalLoop(BaseModel):
    """Definition of a critical current loop to minimize."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Loop name")
    nets: list[str] = Field(default_factory=list, description="List of net names in the loop")
    pins: list[tuple[str, str]] | None = Field(default=None, description="Optional list of (component, pin) tuples")
    max_area_mm2: float | None = Field(default=None, ge=0, description="Maximum allowed loop area in mm^2")
    weight: float = Field(default=1.0, ge=0, description="Importance weight for this loop")
    description: str = Field(default="", description="Human-readable description")


class CriticalPath(BaseModel):
    """Definition of a critical signal path between two components."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Unique path name")
    from_comp: str = Field(description="Starting component reference")
    to_comp: str = Field(description="Ending component reference")
    pins: tuple[str, str] | None = Field(default=None, description="Optional (from_pin, to_pin) tuple")
    max_length_mm: float = Field(default=50.0, gt=0, description="Maximum allowed path length in mm")
    priority: str = Field(default="normal", description="Priority level: critical, high, or normal")
    matched_length_group: str | None = Field(default=None, description="Optional matched length group name")


class MatchedLengthGroup(BaseModel):
    """Group of signal paths that must have matched lengths."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Unique group name")
    tolerance_mm: float = Field(default=5.0, gt=0, description="Maximum length difference in mm")


class StarGroundConfig(BaseModel):
    """Definition of a star ground constraint."""

    model_config = ConfigDict(frozen=True)

    net: str = Field(description="Net name for star ground")
    weight: float = Field(default=1.0, ge=0, description="Importance weight")
    anchor: tuple[float, float] | None = Field(default=None, description="Optional (x, y) anchor position in mm")
    description: str = Field(default="", description="Human-readable description")
