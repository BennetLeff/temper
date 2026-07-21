"""KiCad zone/pour emission for power/ground/HV nets (U1).

Generates ``(zone ...)`` s-expressions for nets that the netclass SSOT
marks as zone-eligible.  Zones are gated behind ``RouterV6Pipeline.
enable_zone_pours`` (default ``False``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ZoneDefinition:
    net_name: str
    net_number: int
    layer: str
    points: tuple[tuple[float, float], ...]
    clearance: float = 0.3
    min_thickness: float = 0.25


def _bounding_box(
    positions: list[tuple[float, float]],
    margin: float = 1.0,
) -> tuple[tuple[float, float], ...]:
    """Axis-aligned bounding box expanded by margin, suitable for a KiCad zone."""
    if not positions:
        return ()
    xs = [p[0] for p in positions]
    ys = [p[1] for p in positions]
    x0, x1 = min(xs) - margin, max(xs) + margin
    y0, y1 = min(ys) - margin, max(ys) + margin
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def compute_zone_for_net(
    net_name: str,
    net_number: int,
    pads: list[tuple[float, float]],
    layer: str = "F.Cu",
    *,
    margin: float = 1.0,
) -> ZoneDefinition:
    """Return a ZoneDefinition for a net, or raise ValueError if insufficient pads."""
    bb = _bounding_box(pads, margin=margin)
    if not bb:
        raise ValueError(f"Net {net_name} has no pad positions for zone emission")
    return ZoneDefinition(
        net_name=net_name,
        net_number=net_number,
        layer=layer,
        points=bb,
    )


def emit_zone_s_expr(zone: ZoneDefinition) -> str:
    """Render a ZoneDefinition as a KiCad ``(zone ...)`` s-expression."""
    poly = " ".join(
        f"(xy {x:.4f} {y:.4f})" for x, y in zone.points
    )
    return (
        f'  (zone (net {zone.net_number}) (net_name "{zone.net_name}")'
        f' (layer "{zone.layer}")'
        f' (hatch full) (connect_pads yes (clearance {zone.clearance:.4f}))'
        f' (min_thickness {zone.min_thickness:.4f})'
        f' (fill yes (arc_segments 16) (thermal_gap 0.5080)'
        f' (thermal_bridge_width 0.5080))'
        f' (polygon (pts {poly})))'
    )
