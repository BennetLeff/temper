"""KiCad zone/pour emission for power/ground/HV nets (U1).

Generates ``(zone ...)`` s-expressions for nets that the netclass SSOT
marks as zone-eligible.  Zones are gated behind ``RouterV6Pipeline.
enable_zone_pours`` (default ``False``).
"""

from __future__ import annotations

from dataclasses import dataclass

import temper_geometry as _tg
from shapely.geometry import MultiPoint, Polygon


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
    """Axis-aligned bounding box expanded by margin (fallback shape)."""
    if not positions:
        return ()
    xs = [p[0] for p in positions]
    ys = [p[1] for p in positions]
    x0, x1 = min(xs) - margin, max(xs) + margin
    y0, y1 = min(ys) - margin, max(ys) + margin
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def _cluster_positions(
    positions: list[tuple[float, float]],
) -> list[list[tuple[float, float]]]:
    """Group positions into spatial clusters using data-informed hierarchical
    clustering (scipy).  The cut threshold is derived from the largest gap in
    sorted nearest-neighbour distances — separating within-component adjacency
    (~0.6-2.5 mm) from inter-component separation (70-111 mm median on the
    production board).

    Falls back to a single cluster for nets with ≤2 pads or when no natural
    gap is detectable.
    """
    if len(positions) <= 2:
        return [list(positions)]

    # Nearest-neighbour distance for every pad
    nn_dists: list[float] = []
    for i, (xi, yi) in enumerate(positions):
        best = float("inf")
        for j, (xj, yj) in enumerate(positions):
            if j == i:
                continue
            d2 = (xj - xi) ** 2 + (yj - yi) ** 2
            if d2 < best:
                best = d2
        nn_dists.append(best**0.5 if best < float("inf") else 0.0)

    nn_dists.sort()

    # Largest relative gap in sorted NN distances -> natural cut threshold.
    # Only gaps significantly wider than the local neighbourhood are
    # considered natural separation points — this prevents splitting a
    # single component's pads (where NN distances are all similar in
    # magnitude) into multiple clusters.
    max_gap_ratio = 0.0
    threshold = nn_dists[-1] if nn_dists else 0.0
    for i in range(len(nn_dists) - 1):
        if nn_dists[i] > 0:
            gap = nn_dists[i + 1] - nn_dists[i]
            ratio = gap / nn_dists[i]
            if ratio > max_gap_ratio:
                max_gap_ratio = ratio
                threshold = (nn_dists[i] + nn_dists[i + 1]) / 2.0

    # If no natural gap (all NN distances are in the same order of
    # magnitude — the component-adjacent case), use the 95th percentile
    # NN distance, resulting in one large cluster.
    if max_gap_ratio < 1.0 or threshold < 0.5:
        idx = min(len(nn_dists) - 1, int(len(nn_dists) * 0.95))
        threshold = max(10.0, nn_dists[idx]) if nn_dists else 10.0

    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import pdist

    Z = linkage(pdist(positions), method="ward")
    labels = fcluster(Z, t=threshold, criterion="distance")  # type: ignore[attr-defined]

    clusters: dict[int, list[tuple[float, float]]] = {}
    for i, label in enumerate(labels):
        clusters.setdefault(int(label), []).append(positions[i])  # type: ignore[arg-type]

    return list(clusters.values())


def _convex_hull_from_positions(
    positions: list[tuple[float, float]],
    margin: float = 0.0,
) -> tuple[tuple[float, float], ...]:
    """Compute a convex hull over positions, expanded by margin.

    Handles degenerate cases (single point, collinear pair).
    """
    if not positions:
        return ()

    if len(positions) == 1:
        x, y = positions[0]
        h = margin if margin > 0 else 0.1
        return ((x - h, y - h), (x + h, y - h), (x + h, y + h), (x - h, y + h))

    points = MultiPoint(positions).convex_hull

    if margin > 0:
        points = points.buffer(margin, join_style=2)

    pts: list[tuple[float, float]] = []
    if hasattr(points, "exterior"):
        for x, y in points.exterior.coords:
            pts.append((float(x), float(y)))
        if len(pts) > 1 and pts[0] == pts[-1]:
            pts.pop()
    else:
        x, y = points.coords[0]
        h = margin if margin > 0 else 0.1
        pts = [(x - h, y - h), (x + h, y - h), (x + h, y + h), (x - h, y + h)]

    return tuple(pts)


def _clip_to_board(
    hull: tuple[tuple[float, float], ...],
    board_polygon: Polygon,
) -> list[tuple[tuple[float, float], ...]]:
    """Intersect *hull* with *board_polygon*, returning zero or more
    clipped outlines (a hull that straddles a concave board boundary can
    split into multiple pieces; an empty result means the hull fell
    entirely outside the board and is dropped).

    R6 (docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md):
    ``_convex_hull_from_positions``'s margin/clearance buffer uses a
    mitre join (``join_style=2``), which extends a convex hull's corners
    past the flat margin distance at acute vertices -- measured up to
    ~12mm past a 6mm margin on this board's HighVoltage nets (see
    docs/evidence/2026-08-07-zone-emission-clustering-defect.md). Nothing
    upstream of this function ever bounded a hull to the physical board,
    so that overshoot reached the emitted zone unclipped. Clipping here
    is unconditionally correct: copper cannot exist off the board
    regardless of clustering policy.
    """
    clipped = Polygon(hull).intersection(board_polygon)
    if clipped.is_empty:
        return []
    polys = list(clipped.geoms) if hasattr(clipped, "geoms") else [clipped]
    out: list[tuple[tuple[float, float], ...]] = []
    for poly in polys:
        if not hasattr(poly, "exterior") or poly.is_empty:
            continue
        pts = [(float(x), float(y)) for x, y in poly.exterior.coords]
        if len(pts) > 1 and pts[0] == pts[-1]:
            pts.pop()
        if len(pts) >= 3:
            out.append(tuple(pts))
    return out


def compute_zones_for_net(
    net_name: str,
    net_number: int,
    pads: list[tuple[float, float]],
    layer: str = "F.Cu",
    *,
    margin: float = 1.0,
    cluster: bool = True,
    board_polygon: Polygon | None = None,
) -> list[ZoneDefinition]:
    """Return ZoneDefinitions for a net — one hull per spatial cluster
    when *cluster* is True, or a single hull over all pads otherwise.

    ``board_polygon``, when given, clips every emitted hull to the
    physical board outline (R6 -- see ``_clip_to_board``'s docstring).
    Copper cannot exist outside ``Edge.Cuts`` regardless of how the hull
    was constructed, so this clip is unconditional and independent of
    the ``cluster`` choice above.

    Raises ValueError if pads is empty.
    """
    if not pads:
        raise ValueError(f"Net {net_name} has no pad positions for zone emission")

    groups = _cluster_positions(pads) if cluster else [list(pads)]

    zones: list[ZoneDefinition] = []
    for group in groups:
        hull = _convex_hull_from_positions(group, margin=margin)
        if not hull:
            continue
        outlines = (
            _clip_to_board(hull, board_polygon) if board_polygon is not None else [hull]
        )
        for outline in outlines:
            zones.append(
                ZoneDefinition(
                    net_name=net_name,
                    net_number=net_number,
                    layer=layer,
                    points=outline,
                )
            )
    return zones


def compute_zone_for_net(
    net_name: str,
    net_number: int,
    pads: list[tuple[float, float]],
    layer: str = "F.Cu",
    *,
    margin: float = 1.0,
) -> ZoneDefinition:
    """Legacy single-zone wrapper.  Prefer ``compute_zones_for_net``."""
    zones = compute_zones_for_net(
        net_name,
        net_number,
        pads,
        layer=layer,
        margin=margin,
        cluster=False,
    )
    return zones[0]


def emit_zone_s_expr(zone: ZoneDefinition) -> str:
    """Render a ZoneDefinition as a KiCad ``(zone ...)`` s-expression.

    Wave 4: delegates to ``temper_geometry.emit_zone_s_expr_py`` (pure
    string formatting; see ``packages/temper-geometry/src/zone_pour.rs``).
    """
    return _tg.emit_zone_s_expr_py(
        zone.net_number,
        zone.net_name,
        zone.layer,
        list(zone.points),
        zone.clearance,
        zone.priority,
        zone.min_thickness,
    )
