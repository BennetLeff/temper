from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FabPreset:
    """Manufacturing capabilities and tolerances for a specific fab process."""
    name: str
    trace_width_pct: float = 0.15        # ±15%
    min_trace_mm: float = 0.127          # 5 mil
    min_clearance_mm: float = 0.127      # 5 mil
    etch_undercut_mm: float = 0.05       # Always positive
    layer_registration_mm: float = 0.1   # ±0.1mm
    drill_tolerance_mm: float = 0.05     # ±0.05mm

    @classmethod
    def jlcpcb_standard(cls) -> FabPreset:
        return cls(
            name="jlcpcb_standard",
            trace_width_pct=0.15,
            min_trace_mm=0.127,
            min_clearance_mm=0.127,
            etch_undercut_mm=0.05,
            layer_registration_mm=0.1
        )

    @classmethod
    def jlcpcb_hdi(cls) -> FabPreset:
        return cls(
            name="jlcpcb_hdi",
            trace_width_pct=0.10,
            min_trace_mm=0.075,
            min_clearance_mm=0.075,
            etch_undercut_mm=0.03,
            layer_registration_mm=0.05
        )

    @classmethod
    def oshpark(cls) -> FabPreset:
        return cls(
            name="oshpark",
            trace_width_pct=0.12,
            min_trace_mm=0.152,
            min_clearance_mm=0.152,
            etch_undercut_mm=0.04
        )

def get_fab_presets() -> dict[str, FabPreset]:
    """Get all pre-configured fab house presets."""
    return {
        "jlcpcb_standard": FabPreset.jlcpcb_standard(),
        "jlcpcb_hdi": FabPreset.jlcpcb_hdi(),
        "oshpark": FabPreset.oshpark()
    }

def inflated_clearance(nominal: float, tolerance: float = 0.1) -> float:
    """Calculate worst-case (smaller) clearance."""
    return max(0.0, nominal - tolerance)

def inflated_width(nominal: float, tolerance: float = 0.1) -> float:
    """Calculate worst-case (larger) trace width."""
    return nominal + tolerance
