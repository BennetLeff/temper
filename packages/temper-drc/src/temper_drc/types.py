"""
Geometric DRC types: via and trace placement data.

These @dataclass types live in temper-drc (NOT in temper_placer/core/board.py)
to avoid circular imports between the placer and DRC packages.

Used by DRC checks that operate on via and trace geometry, extending the
existing component-only Placement model.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ViaPlacement:
    """Collection of placed vias for DRC checking.

    Carries via geometry independent of the placer's router_v6
    Via/ViaPlacement types. Converted from placer types by the
    RouterV6Pipeline fence adapter.
    """

    vias: list[Via] = field(default_factory=list)

    @property
    def via_count(self) -> int:
        return len(self.vias)

    def get_vias_for_net(self, net_name: str) -> list[Via]:
        return [v for v in self.vias if v.net_name == net_name]


@dataclass
class Via:
    """A single via for DRC clearance and annular ring checks."""

    position: tuple[float, float]
    from_layer: str
    to_layer: str
    diameter: float
    drill: float
    net_name: str

    @property
    def radius(self) -> float:
        return self.diameter / 2.0


@dataclass
class TracePlacement:
    """Collection of routed trace segments for DRC checking."""

    segments: list[TraceSegment] = field(default_factory=list)

    @property
    def segment_count(self) -> int:
        return len(self.segments)

    def get_segments_for_net(self, net_name: str) -> list[TraceSegment]:
        return [s for s in self.segments if s.net_name == net_name]


@dataclass
class TraceSegment:
    """A single trace segment for DRC clearance checks."""

    net_name: str
    layer: str
    width: float
    start: tuple[float, float]
    end: tuple[float, float]

    @property
    def length(self) -> float:
        from math import sqrt
        return sqrt(
            (self.end[0] - self.start[0]) ** 2
            + (self.end[1] - self.start[1]) ** 2
        )

    @property
    def bounding_box(self) -> tuple[float, float, float, float]:
        hw = self.width / 2.0
        return (
            min(self.start[0], self.end[0]) - hw,
            min(self.start[1], self.end[1]) - hw,
            max(self.start[0], self.end[0]) + hw,
            max(self.start[1], self.end[1]) + hw,
        )
