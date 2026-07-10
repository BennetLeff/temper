from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ThermalConstraint:
    """Thermal placement constraint for heat-generating components."""

    components: list[str]  # Component refs
    prefer_edge: bool = True  # Place near board edge
    min_spacing_mm: float = 5.0  # Minimum spacing between thermal components
    max_distance_from_edge_mm: float = 20.0
    description: str = ""


@dataclass
class ThermalProperties:
    """
    Extended thermal properties for comprehensive thermal management.

    This extends the basic ThermalConstraint with:
    - Power dissipation values for heat spreading calculations
    - Heat-sensitive component specifications
    - Thermal pad component identification
    """

    # High-power heat sources
    high_power_components: list[str] = field(default_factory=list)
    power_dissipation_w: dict[str, float] = field(default_factory=dict)
    min_separation_mm: float = 15.0  # Between high-power components

    # Heat-sensitive components (MCU, sensors)
    heat_sensitive_components: list[str] = field(default_factory=list)
    max_temp_rise_c: float = 20.0
    min_distance_from_heat_sources_mm: float = 20.0

    # Thermal pad components (for edge preference)
    thermal_pad_components: list[str] = field(default_factory=list)
    prefer_edge: bool = True
    preferred_edge_margin_mm: float = 10.0

    # Airflow direction (m/s magnitude at 0°, direction in degrees from +x)
    airflow_vector: tuple[float, float] | None = None

    # Per-component rated maximum junction temperature (°C)
    rated_tj_max: dict[str, float] = field(default_factory=dict)


# Package-type Rjc lookup table for thermal anchoring inference.
# Values in K/W (junction-to-case).
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


_DEFAULT_RJC: float = 0.6  # Conservative default (TO-247 class)
