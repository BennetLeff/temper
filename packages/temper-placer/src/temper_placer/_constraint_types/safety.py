from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class IsolationBarrier(BaseModel):
    """An isolation barrier line across the board."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Barrier name")
    x_mm: float = Field(description="X-position of the barrier in mm")
    y_span: tuple[float, float] = Field(description="(y_start, y_end) span of the barrier in mm")
    layers: str | list[str] = Field(default="all", description="Layer name(s) for the barrier")


class SnubberRequirement(BaseModel):
    """Snubber circuit requirement near an IGBT pair."""

    model_config = ConfigDict(frozen=True)

    igbt_pair: tuple[str, str] = Field(description="IGBT component reference pair")
    type: str = Field(default="RC", description="Snubber type: RC, RCD, etc.")
    across: str = Field(default="collector_emitter", description="Across which terminals: collector_emitter")


class BleedResistor(BaseModel):
    """Bleed resistor specification for bus discharge."""

    model_config = ConfigDict(frozen=True)

    bus_voltage_v: float = Field(gt=0, description="Bus voltage in Volts")
    target_voltage_v: float = Field(ge=0, description="Target voltage after discharge in Volts")
    timeout_s: float = Field(default=5.0, gt=0, description="Discharge timeout in seconds")


class SkinEffectDerating(BaseModel):
    """Skin-effect derating for high-frequency traces."""

    model_config = ConfigDict(frozen=True)

    frequency_hz: float = Field(gt=0, description="Operating frequency in Hz")
    derating_factor: float = Field(default=3.0, gt=0, description="Derating factor multiplier")
