from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CriticalLoop:
    """Definition of a critical current loop to minimize."""

    name: str
    nets: list[str] = field(default_factory=list)
    pins: list[tuple[str, str]] | None = None
    max_area_mm2: float | None = None
    weight: float = 1.0
    description: str = ""


@dataclass
class CriticalPath:
    """
    Definition of a critical signal path between two components.

    Attributes:
        name: Unique name for the path.
        from_comp: Starting component reference.
        to_comp: Ending component reference.
        pins: Optional tuple of (from_pin, to_pin) names.
        max_length_mm: Maximum allowed length in mm.
        priority: Priority level ('critical', 'high', 'normal').
        matched_length_group: Optional name of matched length group.
    """

    name: str
    from_comp: str
    to_comp: str
    pins: tuple[str, str] | None = None
    max_length_mm: float = 50.0
    priority: str = "normal"
    matched_length_group: str | None = None


@dataclass
class MatchedLengthGroup:
    """
    Group of signal paths that must have matched lengths.

    Attributes:
        name: Unique name for the group.
        tolerance_mm: Maximum difference in length between any two paths in group.
    """

    name: str
    tolerance_mm: float = 5.0


@dataclass
class StarGroundConfig:
    """Definition of a star ground constraint."""

    net: str
    weight: float = 1.0
    anchor: tuple[float, float] | None = None
    description: str = ""
