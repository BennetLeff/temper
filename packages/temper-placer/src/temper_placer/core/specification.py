"""
Physical design specifications for PCB validation.

This module defines the data structures for physical performance targets
(EMI, Thermal, Signal Integrity) that the validation framework checks against.
"""

from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ThermalSpec:
    """Thermal performance targets."""
    max_junction_temp_c: float = 125.0
    ambient_temp_c: float = 40.0
    power_dissipation: dict[str, float] = field(default_factory=dict)


@dataclass
class EMISpec:
    """EMI performance targets (loop areas)."""
    max_loop_area_mm2: dict[str, float] = field(default_factory=dict)
    frequency_hz: float = 100000.0


@dataclass
class SignalIntegritySpec:
    """Signal integrity targets."""
    max_length_mm: dict[str, float] = field(default_factory=dict)
    length_match_mm: dict[str, float] = field(default_factory=dict)


@dataclass
class PcbSpecification:
    """Complete physical specification for a design."""
    name: str = "Unnamed Design"
    thermal: ThermalSpec = field(default_factory=ThermalSpec)
    emi: EMISpec = field(default_factory=EMISpec)
    signal_integrity: SignalIntegritySpec = field(default_factory=SignalIntegritySpec)

    @classmethod
    def load(cls, path: Path) -> PcbSpecification:
        """Load specification from YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
            
        thermal = ThermalSpec(**data.get("thermal", {}))
        emi = EMISpec(**data.get("emi", {}))
        si = SignalIntegritySpec(**data.get("signal_integrity", {}))
        
        return cls(
            name=data.get("name", path.stem),
            thermal=thermal,
            emi=emi,
            signal_integrity=si
        )
