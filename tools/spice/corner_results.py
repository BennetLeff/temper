"""Corner simulation result schema and serialization."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CornerResult:
    """Result of a single corner simulation run.

    All metric values are None if convergence failed (convergence_error=True).
    """

    corner_name: str
    Vbus: float
    Iload: float
    Tj: float
    Zload_angle: float

    Vge_peak: float | None = None
    Vge_overshoot_pct: float | None = None
    Vce_peak: float | None = None
    tank_current_rms: float | None = None
    switching_loss_mJ: float | None = None
    Tj_primary: float | None = None

    convergence_error: bool = False
    error_message: str = ""

    extra_metrics: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "corner_name": self.corner_name,
            "parameters": {
                "Vbus": self.Vbus,
                "Iload": self.Iload,
                "Tj": self.Tj,
                "Zload_angle": self.Zload_angle,
            },
            "metrics": {
                "Vge_peak": self.Vge_peak,
                "Vge_overshoot_pct": self.Vge_overshoot_pct,
                "Vce_peak": self.Vce_peak,
                "tank_current_rms": self.tank_current_rms,
                "switching_loss_mJ": self.switching_loss_mJ,
                "Tj_primary": self.Tj_primary,
                **self.extra_metrics,
            },
            "convergence_error": self.convergence_error,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CornerResult:
        params = data["parameters"]
        metrics = data.get("metrics", {})
        extra = {k: v for k, v in metrics.items() if k not in {
            "Vge_peak", "Vge_overshoot_pct", "Vce_peak", "tank_current_rms",
            "switching_loss_mJ", "Tj_primary",
        }}
        return cls(
            corner_name=data["corner_name"],
            Vbus=params["Vbus"],
            Iload=params["Iload"],
            Tj=params["Tj"],
            Zload_angle=params["Zload_angle"],
            Vge_peak=metrics.get("Vge_peak"),
            Vge_overshoot_pct=metrics.get("Vge_overshoot_pct"),
            Vce_peak=metrics.get("Vce_peak"),
            tank_current_rms=metrics.get("tank_current_rms"),
            switching_loss_mJ=metrics.get("switching_loss_mJ"),
            Tj_primary=metrics.get("Tj_primary"),
            convergence_error=data.get("convergence_error", False),
            error_message=data.get("error_message", ""),
            extra_metrics=extra,
        )


def save_results(results: list[CornerResult], output_path: str) -> None:
    """Save corner results to a JSON file."""
    data = [r.to_dict() for r in results]
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)


def load_results(input_path: str) -> list[CornerResult]:
    """Load corner results from a JSON file."""
    with open(input_path) as f:
        data = json.load(f)
    return [CornerResult.from_dict(item) for item in data]
