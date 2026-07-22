"""KiCad zone/pour emission for power/ground/HV nets (U1).

Generates ``(zone ...)`` s-expressions for nets that the netclass SSOT
marks as zone-eligible.  Zones are gated behind ``RouterV6Pipeline.
enable_zone_pours`` (default ``False``).
"""

from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import MultiPoint


@dataclass(frozen=True)
class ZoneDefinition:
    net_name: str
    net_number: int
    layer: str
    points: tuple[tuple[float, float], ...]
    clearance: float = 0.3
    min_thickness: float = 0.25
    priority: int = 0


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


def _cluster_positions(
    positions: list[tuple[float, float]],
    distance: float,
) -> list[list[tuple[float, float]]]:
    """Group positions into clusters based on a distance threshold.

    Greedy clustering: each unassigned point starts a new cluster;
    any remaining point within *distance* of any cluster member is
    added to that cluster.  Suitable for the low-cardinality pad
    sets in zone emission (per-net pad counts are small).
    """
    if not positions:
        return []
    remaining = set(range(len(positions)))
    clusters: list[list[tuple[float, float]]] = []

    while remaining:
        seed = remaining.pop()
        cluster = [positions[seed]]
        # Grow the cluster by repeatedly scanning for points within
        # distance of any already-accepted cluster member.
        grew = True
        while grew:
            grew = False
            for i in list(remaining):
                px, py = positions[i]
                # Check against every point already in the cluster
                for cx, cy in cluster:
                    if ((px - cx) ** 2 + (py - cy) ** 2) <= distance ** 2:
                        cluster.append(positions[i])
                        remaining.discard(i)
                        grew = True
                        break
        clusters.append(cluster)

    return clusters


def _convex_hull_from_positions(
    positions: list[tuple[float, float]],
    margin: float = 0.0,
) -> tuple[tuple[float, float], ...]:
    """Compute a convex hull over positions, expanded by margin.

    Returns polygon corner points suitable for a KiCad zone outline.
    Handles degenerate cases (single point, two collinear points).
    """
    if not positions:
        return ()

    if len(positions) == 1:
        x, y = positions[0]
        # Tiny square around the single point
        h = margin if margin > 0 else 0.1
        return ((x - h, y - h), (x + h, y - h), (x + h, y + h), (x - h, y + h))

    points = MultiPoint(positions).convex_hull

    if margin > 0:
        points = points.buffer(margin, join_style=2)

    pts: list[tuple[float, float]] = []
    if hasattr(points, "exterior"):
        for x, y in points.exterior.coords:
            pts.append((float(x), float(y)))
        # Remove the closing duplicate point (shapely exterior repeats start)
        if len(pts) > 1 and pts[0] == pts[-1]:
            pts.pop()
    else:
        # Degenerate case (e.g., single-point hull)
        x, y = points.coords[0]
        h = margin if margin > 0 else 0.1
        pts = [(x - h, y - h), (x + h, y - h), (x + h, y + h), (x - h, y + h)]

    return tuple(pts)


def compute_zones_for_net(
    net_name: str,
    net_number: int,
    pads: list[tuple[float, float]],
    layer: str = "F.Cu",
    *,
    margin: float = 1.0,
    cluster_distance: float | None = None,
) -> list[ZoneDefinition]:
    """Return ZoneDefinitions for a net, one per spatial cluster if clustering
    is enabled, or a single hull over all pads if not.

    Raises ValueError if pads is empty.
    """
    if not pads:
        raise ValueError(f"Net {net_name} has no pad positions for zone emission")

    if cluster_distance is not None:
        clusters = _cluster_positions(pads, cluster_distance)
    else:
        clusters = [list(pads)]

    zones: list[ZoneDefinition] = []
    for cluster in clusters:
        hull = _convex_hull_from_positions(cluster, margin=margin)
        if not hull:
            continue
        zones.append(ZoneDefinition(
            net_name=net_name,
            net_number=net_number,
            layer=layer,
            points=hull,
        ))
    return zones


# Backward-compatible alias used by existing callers that expect a single
# ZoneDefinition (not a list).  Emits one hull over all positions.
def compute_zone_for_net(
    net_name: str,
    net_number: int,
    pads: list[tuple[float, float]],
    layer: str = "F.Cu",
    *,
    margin: float = 1.0,
) -> ZoneDefinition:
    """Return a ZoneDefinition for a net (single hull over all pads).

    Prefer ``compute_zones_for_net`` for clustered emission.
    """
    zones = compute_zones_for_net(
        net_name, net_number, pads, layer=layer, margin=margin,
        cluster_distance=None,
    )
    return zones[0]


def emit_zone_s_expr(zone: ZoneDefinition) -> str:
    """Render a ZoneDefinition as a KiCad ``(zone ...)`` s-expression."""
    poly = " ".join(
        f"(xy {x:.4f} {y:.4f})" for x, y in zone.points
    )
    return (
        f'  (zone (net {zone.net_number}) (net_name "{zone.net_name}")'
        f' (layer "{zone.layer}")'
        f' (hatch full 0.5)'
        f' (priority {zone.priority})'
        f' (connect_pads yes (clearance {zone.clearance:.4f}))'
        f' (min_thickness {zone.min_thickness:.4f})'
        # A zone with an outline polygon but no fill directive is just a
        # boundary -- KiCad's connectivity check sees zero copper there.
        # This must live in the file format itself (not a CLI flag like
        # --refill-zones) to fill correctly across KiCad CLI versions.
        f' (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))'
        f' (polygon (pts {poly})))'
    )
