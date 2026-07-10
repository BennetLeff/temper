from __future__ import annotations

from dataclasses import dataclass


@dataclass
class IsolationBarrier:
    """An isolation barrier line across the board."""

    name: str
    x_mm: float
    y_span: tuple[float, float]
    layers: str | list[str] = "all"


@dataclass
class SnubberRequirement:
    """Snubber circuit requirement near an IGBT pair."""

    igbt_pair: tuple[str, str]
    type: str = "RC"
    across: str = "collector_emitter"


@dataclass
class BleedResistor:
    """Bleed resistor specification for bus discharge."""

    bus_voltage_v: float
    target_voltage_v: float
    timeout_s: float = 5.0


@dataclass
class SkinEffectDerating:
    """Skin-effect derating for high-frequency traces."""

    frequency_hz: float
    derating_factor: float = 3.0
