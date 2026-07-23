from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ThermalConstraint(BaseModel):
    """Thermal placement constraint for heat-generating components."""

    model_config = ConfigDict(frozen=True)

    components: list[str] = Field(description="List of component references")
    prefer_edge: bool = Field(default=True, description="Place near board edge")
    min_spacing_mm: float = Field(
        default=5.0, ge=0, description="Minimum spacing between thermal components in mm"
    )
    max_distance_from_edge_mm: float = Field(
        default=20.0, gt=0, description="Maximum distance from board edge in mm"
    )
    description: str = Field(default="", description="Human-readable description")


class ThermalProperties(BaseModel):
    """Extended thermal properties for comprehensive thermal management."""

    model_config = ConfigDict(frozen=True)

    high_power_components: list[str] = Field(
        default_factory=list, description="High-power heat source component references"
    )
    power_dissipation_w: dict[str, float] = Field(
        default_factory=dict, description="Component-to-power-dissipation map in Watts"
    )
    min_separation_mm: float = Field(
        default=15.0, ge=0, description="Minimum separation between high-power components in mm"
    )

    heat_sensitive_components: list[str] = Field(
        default_factory=list, description="Heat-sensitive component references"
    )
    max_temp_rise_c: float = Field(
        default=20.0, gt=0, description="Maximum allowed temperature rise in Celsius"
    )
    min_distance_from_heat_sources_mm: float = Field(
        default=20.0, ge=0, description="Minimum distance from heat sources in mm"
    )

    thermal_pad_components: list[str] = Field(
        default_factory=list, description="Thermal pad component references"
    )
    prefer_edge: bool = Field(
        default=True, description="Prefer edge placement for thermal pad components"
    )
    preferred_edge_margin_mm: float = Field(
        default=10.0, ge=0, description="Preferred margin from board edge in mm"
    )

    airflow_vector: tuple[float, float] | None = Field(
        default=None, description="Airflow direction vector (m/s, degrees)"
    )
    rated_tj_max: dict[str, float] = Field(
        default_factory=dict, description="Component-to-max-junction-temp map in Celsius"
    )


_RJC_PACKAGE_LOOKUP: dict[str, float] = {
    "TO-247": 0.6,
    "TO-220": 1.0,
    "DPAK": 2.0,
    "D2PAK": 1.5,
    "SOT-223": 15.0,
    "SOIC-8": 50.0,
    "TO-263": 1.5,
    "TO-252": 2.0,
    "QFN-48": 5.0,
}

_DEFAULT_RJC: float = 0.6
