"""VERBATIM pin of ``temper_placer/io/_write_types.py`` at origin/main
``5e528b8aa`` (the Wave-4 Phase-3 formats/IO migration base for
``_write_types.py``).

This file is the pre-migration oracle for the ``_write_types.py`` migration:
the four write-result dataclasses and the ``_get_footprint_reference`` helper
are copied byte-for-byte from the shipped module and MUST NOT be "improved",
reformatted, or kept in sync with the post-migration source: their whole value
is that they are frozen. ``test_write_types_rust_differential.py`` asserts the
migrated Rust implementation (``temper_io_types.write_types``) reproduces
this file's output.

Only these four dataclasses and the one helper are pinned here -- not the
whole module. See ``packages/temper-io-types/src/write_types.rs``'s module
docstring for the full triage of what was and was not ported, and why.
"""

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
