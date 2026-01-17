"""
Shared types for KiCad PCB export.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class TraceSegment:
    """A single trace segment for export."""

    net: str
    start: tuple[float, float]
    end: tuple[float, float]
    width: float
    layer: str  # "F.Cu" or "B.Cu"


@dataclass
class TraceVia:
    """A via connecting layers."""

    net: str
    position: tuple[float, float]
    size: float  # Outer diameter
    drill: float  # Drill diameter
    layers: list[str]  # e.g., ["F.Cu", "B.Cu"]


@dataclass
class ExportResult:
    """Result of exporting routes to PCB file."""

    output_path: Path
    segments_added: int
    vias_added: int
    nets_exported: int
    nets_failed: int
    warnings: list[str]

    def __str__(self) -> str:
        return (
            f"Export complete: {self.nets_exported} nets, "
            f"{self.segments_added} segments, {self.vias_added} vias → {self.output_path}"
        )
