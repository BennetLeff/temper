"""Internal: shared data classes and helpers for kicad_writer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kiutils.footprint import Footprint


@dataclass
class WriteResult:
    """Result of writing placement to KiCad file."""

    output_path: Path
    components_updated: int
    components_skipped: int
    warnings: list[str]

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


@dataclass
class StrippingResult:
    """Result of stripping routing from a KiCad file."""

    output_path: Path
    traces_removed: int
    vias_removed: int
    zones_removed: int
    components_preserved: int
    warnings: list[str]

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


@dataclass
class PlacementUpdate:
    """
    Placement update for a single component.

    Attributes:
        ref: Component reference designator (e.g., "U1").
        x: New X position in mm.
        y: New Y position in mm.
        rotation: Rotation angle in degrees (0, 90, 180, or 270).
    """

    ref: str
    x: float
    y: float
    rotation: float  # degrees: 0, 90, 180, 270


@dataclass
class IsolationSlotResult:
    """Result of adding isolation slots to a KiCad file."""

    output_path: Path
    slots_added: int
    slots_skipped: int
    warnings: list[str]

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


def _get_footprint_reference(fp: Footprint) -> str | None:
    """Extract reference designator from footprint."""
    props = getattr(fp, "properties", {})
    if isinstance(props, dict):
        ref = props.get("Reference")
        if ref:
            return ref

    if isinstance(props, list):
        for prop in props:
            if hasattr(prop, "key") and prop.key == "Reference":
                return prop.value

    for item in getattr(fp, "graphicItems", []):
        if hasattr(item, "type") and item.type == "reference":
            return getattr(item, "text", None)

    return None
