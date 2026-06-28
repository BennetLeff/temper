"""
DRC Constraints module for PCB routing.

Provides a queryable, real-time design rule constraint engine that routers
can query before placing geometry.

Epic: temper-lueu
"""

from temper_placer.routing.constraints.design_rules import (
    ClearanceMatrix,
    DesignRulesParser,
)
from temper_placer.routing.constraints.drc_oracle import (
    DRCOracle,
    Violation,
)
from temper_placer.routing.constraints.geometry import (
    LineSegment,
    Point,
    point_to_segment_distance,
    segment_to_segment_distance,
)
from temper_placer.routing.constraints.spatial_index import (
    Pad,
    PCBGeometry,
    Track,
    Via,
)

__all__ = [
    "ClearanceMatrix",
    "DesignRulesParser",
    "DRCOracle",
    "LineSegment",
    "Pad",
    "PCBGeometry",
    "Point",
    "Track",
    "Via",
    "Violation",
    "point_to_segment_distance",
    "segment_to_segment_distance",
]
