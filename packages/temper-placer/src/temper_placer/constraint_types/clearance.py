from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ClearanceRule(BaseModel):
    """Clearance rule between net classes or components."""

    model_config = ConfigDict(frozen=True)

    from_class: str = Field(description="Source net class (e.g., 'HV')")
    to_class: str = Field(description="Target net class (e.g., 'LV')")
    clearance_mm: float = Field(ge=0, description="Required clearance in mm")
    description: str = Field(default="", description="Human-readable description")


class NetClassRule(BaseModel):
    """Design rules for a specific net class."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Net class name (e.g., 'HighVoltage')")
    trace_width_mm: float = Field(default=0.2, gt=0, description="Trace width in mm")
    clearance_mm: float = Field(default=0.2, ge=0, description="Clearance to other traces in mm")
    via_size_mm: float = Field(default=0.6, gt=0, description="Via pad diameter in mm")
    via_drill_mm: float = Field(default=0.3, gt=0, description="Via drill diameter in mm")
    via_template: str | None = Field(default=None, description="Via array template name")
    creepage_mm: float = Field(default=0.0, ge=0, description="Creepage distance in mm")
    allow_neckdown: bool = Field(default=True, description="Allow trace neckdown")
    description: str = Field(default="", description="Human-readable description")
    voltage_v: float = Field(
        default=0.0, ge=0, description="Working voltage for creepage calculation"
    )
    max_current_rating: float | None = Field(default=None, description="Maximum current in Amps")
    routing_strategy: str | None = Field(
        default=None,
        description="Routing strategy: plane_required, plane_preferred, wide_trace, standard",
    )
    via_cost_multiplier: float = Field(
        default=1.0, ge=0, description="Multiplier for via cost (higher = fewer vias)"
    )
    target_impedance: float | None = Field(default=None, description="Target impedance in Ohms")


class DifferentialPairRule(BaseModel):
    """Configuration for a differential pair from YAML."""

    model_config = ConfigDict(frozen=True)

    net_pos: str = Field(description="Positive net name")
    net_neg: str = Field(description="Negative net name")
    spacing_mm: float = Field(
        default=0.2, gt=0, description="Nominal gap between differential traces in mm"
    )
    coupling_tolerance_mm: float = Field(
        default=0.5, ge=0, description="Maximum deviation from nominal spacing in mm"
    )
    impedance_ohm: float | None = Field(
        default=None, description="Target differential impedance in Ohms"
    )
    max_skew_mm: float = Field(default=0.5, ge=0, description="Maximum length mismatch in mm")
    description: str = Field(default="", description="Human-readable description")


class SignalToHVClearance(BaseModel):
    """Constraint ensuring signal paths maintain clearance from HV component pins."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Unique constraint identifier")
    signal_component: str = Field(description="Signal source component reference")
    signal_pin: str = Field(description="Signal source pin number")
    target_component: str = Field(description="Target component reference")
    target_pin: str = Field(description="Target pin number")
    hv_component: str = Field(description="Component with HV pins to avoid")
    hv_pins: list[str] = Field(description="List of HV pin numbers to avoid")
    required_clearance_mm: float = Field(
        default=6.0, ge=0, description="Minimum clearance from signal path to HV pins"
    )  # allow-safety-constant: IEC standard clearance
    max_path_length_mm: float = Field(
        default=20.0, gt=0, description="Maximum allowed signal path length in mm"
    )
    tier: str = Field(default="hard", description="Constraint tier: hard (fail) or soft (warn)")
    description: str = Field(default="", description="Human-readable description")
