"""Typed attribution of external DRC findings to emitted copper.

The KiCad report is authoritative for whether a violation exists, but its
free-text descriptions do not reliably identify zones or bare copper. This
module keeps attribution conservative and deterministic: a finding is charged
to emitted copper only when its location lies within an emitted item's
geometry envelope and its reported nets are compatible with that item's net.
Unmatched findings remain explicitly inherited/unattributed evidence; they
are never silently counted as proof that emitted copper is safe.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal

from temper_placer.validation._drc_api import DrcError

CopperKind = Literal["track", "via", "zone", "pour"]
BoundingBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class EmittedCopper:
    """Stable identity and conservative geometry envelope for emitted copper."""

    identity: str
    kind: CopperKind
    net: str
    bbox: BoundingBox

    def __post_init__(self) -> None:
        x0, y0, x1, y1 = self.bbox
        if not self.identity:
            raise ValueError("emitted copper identity must be non-empty")
        if not self.net:
            raise ValueError("emitted copper net must be non-empty")
        if not all(isfinite(value) for value in self.bbox):
            raise ValueError("emitted copper bbox must contain finite coordinates")
        if x0 > x1 or y0 > y1:
            raise ValueError(f"emitted copper bbox is inverted: {self.bbox!r}")

    def contains(self, location: tuple[float, float], tolerance_mm: float) -> bool:
        """Return whether *location* is inside this item's expanded envelope."""
        x, y = location
        x0, y0, x1, y1 = self.bbox
        return (
            x0 - tolerance_mm <= x <= x1 + tolerance_mm
            and y0 - tolerance_mm <= y <= y1 + tolerance_mm
        )


@dataclass(frozen=True)
class DrcAttribution:
    """Partition of DRC errors by emitted-copper attribution."""

    emitted: tuple[tuple[DrcError, tuple[str, ...]], ...] = ()
    inherited: tuple[DrcError, ...] = ()

    @property
    def emitted_error_count(self) -> int:
        return len(self.emitted)

    @property
    def inherited_error_count(self) -> int:
        return len(self.inherited)

    @property
    def passed(self) -> bool:
        """P3 invariant: emitted copper has no externally observed errors."""
        return self.emitted_error_count == 0


def attribute_drc_errors(
    errors: tuple[DrcError, ...] | list[DrcError],
    emitted_copper: tuple[EmittedCopper, ...] | list[EmittedCopper],
    *,
    tolerance_mm: float = 0.05,
) -> DrcAttribution:
    """Attribute DRC errors to emitted items using conservative evidence.

    A DRC error with no parsed net list can still be attributed when its
    location matches one emitted item. When nets are present, at least one
    reported net must match. Multiple matching items are retained in sorted
    identity order so ambiguity is visible to callers and output order is
    stable.
    """
    if tolerance_mm < 0.0 or not isfinite(tolerance_mm):
        raise ValueError("tolerance_mm must be finite and non-negative")

    ordered_items = tuple(sorted(emitted_copper, key=lambda item: item.identity))
    emitted: list[tuple[DrcError, tuple[str, ...]]] = []
    inherited: list[DrcError] = []

    for error in errors:
        error_nets = frozenset(error.nets)
        candidates = tuple(
            item
            for item in ordered_items
            if item.contains(error.location, tolerance_mm)
            and (not error_nets or item.net in error_nets)
        )
        if candidates:
            emitted.append((error, tuple(item.identity for item in candidates)))
        else:
            inherited.append(error)

    return DrcAttribution(emitted=tuple(emitted), inherited=tuple(inherited))
